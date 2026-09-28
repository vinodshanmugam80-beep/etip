"""SSO service — manage OIDC config, start the login redirect, and complete the
callback by verifying the ID token, just-in-time provisioning the user, and
issuing ETIP session tokens.

Config management is tenant-scoped; login/callback run pre-authentication (the
tenant is carried in the signed state), so ``organization_id`` / ``actor_id`` are
optional and only required by the config methods.
"""

from __future__ import annotations

import secrets
import uuid

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, NotFoundError, ValidationError
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.repository import (
    OrganizationRepository,
    RefreshTokenRepository,
    RoleRepository,
    UserRepository,
)
from app.modules.sso import oidc
from app.modules.sso.models import SsoConfiguration
from app.modules.sso.repository import SsoConfigRepository
from app.modules.sso.schemas import SsoConfigUpsert

_CONFIG_FIELDS = (
    "client_id",
    "issuer",
    "authorize_url",
    "token_url",
    "jwks_url",
    "default_role_name",
    "allowed_domains",
    "role_mappings",
    "is_enabled",
)


def _claim_groups(claims: dict[str, object]) -> list[str]:
    """Extract group/role values from common OIDC claim shapes."""
    values: list[str] = []
    for key in ("groups", "roles"):
        raw = claims.get(key)
        if isinstance(raw, list):
            values.extend(str(v) for v in raw)
        elif isinstance(raw, str) and raw.strip():
            values.extend(part for part in raw.replace(",", " ").split())
    return values


class SsoService:
    """OIDC single sign-on for the tenant."""

    def __init__(
        self,
        uow: UnitOfWork,
        settings: Settings,
        *,
        organization_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        self._uow = uow
        self._settings = settings
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.configs = SsoConfigRepository(session)
        self.orgs = OrganizationRepository(session)
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    # ------------------------------------------------------------------
    # Configuration (tenant-scoped; requires org + actor)
    # ------------------------------------------------------------------
    def upsert_config(self, payload: SsoConfigUpsert) -> SsoConfiguration:
        """Create or update the tenant's OIDC configuration."""
        assert self._org_id is not None
        config = self.configs.get_for_org(self._org_id)
        creating = config is None
        if config is None:
            config = SsoConfiguration(organization_id=self._org_id, created_by=self._actor_id)
        for field in _CONFIG_FIELDS:
            setattr(config, field, getattr(payload, field))
        # Only overwrite the secret when a new one is supplied (so a GET→PUT
        # round-trip that omits it doesn't wipe the stored secret).
        if payload.client_secret:
            config.client_secret = payload.client_secret
        config.modified_by = self._actor_id
        config = self.configs.add(config) if creating else self.configs.update(config)
        self._uow.record_audit(
            "SsoConfiguration",
            config.id,
            "upsert",
            "Updated SSO configuration",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return config

    def get_config(self) -> SsoConfiguration | None:
        """Return the tenant's OIDC configuration, if any."""
        assert self._org_id is not None
        return self.configs.get_for_org(self._org_id)

    def discover(self, issuer: str | None = None) -> SsoConfiguration:
        """Auto-fill the authorize / token / JWKS endpoints from the IdP.

        Reads the issuer's OpenID Connect discovery document and stores the
        resulting endpoints on the tenant's configuration, so an admin only needs
        to supply the issuer and client credentials.
        """
        assert self._org_id is not None
        config = self.configs.get_for_org(self._org_id)
        if config is None:
            raise NotFoundError("Save the SSO client id and issuer before running discovery.")
        target = (issuer or config.issuer or "").strip()
        if not target:
            raise ValidationError("An issuer URL is required for discovery.")
        found = oidc.fetch_discovery(target)
        config.issuer = found["issuer"]
        config.authorize_url = found["authorize_url"]
        config.token_url = found["token_url"]
        config.jwks_url = found["jwks_url"]
        config.modified_by = self._actor_id
        config = self.configs.update(config)
        self._uow.record_audit(
            "SsoConfiguration", config.id, "discover",
            f"Discovered OIDC endpoints from {target}",
            actor_id=self._actor_id, organization_id=self._org_id,
        )
        return config

    # ------------------------------------------------------------------
    # Login flow (pre-authentication)
    # ------------------------------------------------------------------
    def _redirect_uri(self) -> str:
        return self._settings.public_base_url.rstrip("/") + "/api/v1/auth/sso/callback"

    def begin_login(self, organization_slug: str) -> str:
        """Return the IdP authorize URL to redirect the user to."""
        org = self.orgs.get_by_slug(organization_slug)
        if org is None:
            raise NotFoundError("Organization not found.")
        config = self.configs.find_enabled_unscoped(org.id)
        if config is None:
            raise ValidationError("SSO is not enabled for this organization.")
        nonce = secrets.token_urlsafe(16)
        state = oidc.sign_state(self._settings, org.id, nonce)
        return oidc.build_authorize_url(config, state, nonce, self._redirect_uri())

    def complete_login(self, state: str, code: str) -> tuple[str, str, int]:
        """Verify the callback, provision the user, and issue ETIP tokens."""
        org_id, nonce = oidc.verify_state(self._settings, state)
        config = self.configs.find_enabled_unscoped(org_id)
        if config is None:
            raise AuthenticationError("SSO is not enabled for this organization.")
        claims = oidc.fetch_oidc_claims(config, code, self._redirect_uri(), nonce)
        email = str(claims.get("email") or "").lower().strip()
        if not email:
            raise AuthenticationError("The identity provider did not return an email.")
        if config.allowed_domains:
            allowed = {d.lower().lstrip("@") for d in config.allowed_domains}
            if email.split("@")[-1] not in allowed:
                raise AuthenticationError("This email domain is not permitted for SSO.")

        user = self.users.get_by_email(org_id, email)
        if user is None:
            role_names = self._roles_from_claims(config, claims)
            user = User(
                organization_id=org_id,
                email=email,
                full_name=str(claims.get("name") or claims.get("preferred_username") or email),
                hashed_password=hash_password(secrets.token_urlsafe(32)),
                is_active=True,
            )
            for name in role_names:
                role = self.roles.get_by_name(org_id, name)
                if role is not None and role not in user.roles:
                    user.roles.append(role)
            if not user.roles:
                fallback = self.roles.get_by_name(org_id, "Member")
                if fallback is not None:
                    user.roles.append(fallback)
            user = self.users.add(user)
            self._uow.record_audit(
                "User",
                user.id,
                "sso_provision",
                f"Provisioned via SSO ({email})",
                actor_id=user.id,
                organization_id=org_id,
            )
        if not user.is_active:
            raise AuthenticationError("This user account is inactive.")
        return self._issue_tokens(user)

    def _roles_from_claims(
        self, config: SsoConfiguration, claims: dict[str, object]
    ) -> list[str]:
        """Resolve ETIP role names for a new SSO user from mapped IdP groups.

        Falls back to the configured default role when no group maps.
        """
        mappings = config.role_mappings or {}
        names: list[str] = []
        for group in _claim_groups(claims):
            mapped = mappings.get(group)
            if mapped and mapped not in names:
                names.append(mapped)
        if not names and config.default_role_name:
            names.append(config.default_role_name)
        return names

    def _issue_tokens(self, user: User) -> tuple[str, str, int]:
        access = create_access_token(
            self._settings, subject=user.id, organization_id=user.organization_id
        )
        refresh, jti, expires_at = create_refresh_token(
            self._settings, subject=user.id, organization_id=user.organization_id
        )
        self.refresh_tokens.add(
            RefreshToken(
                organization_id=user.organization_id,
                user_id=user.id,
                jti=jti,
                expires_at=expires_at,
            )
        )
        return access, refresh, self._settings.access_token_expire_minutes * 60
