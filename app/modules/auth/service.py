"""Authentication service.

Holds all business logic for tenancy bootstrap, login, token rotation, logout
and MFA. It orchestrates repositories through a :class:`UnitOfWork`, enforces
security rules (lockout, MFA, token rotation) and writes audit entries. It has
no knowledge of HTTP.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_mfa_secret,
    hash_password,
    mfa_provisioning_uri,
    verify_mfa_code,
    verify_password,
)
from app.db.base import ensure_aware
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.models import (
    Organization,
    Permission,
    RefreshToken,
    Role,
    User,
)
from app.modules.auth.repository import (
    OrganizationRepository,
    PermissionRepository,
    RefreshTokenRepository,
    RoleRepository,
    UserRepository,
)
from app.modules.auth.seeds import (
    BOOTSTRAP_ADMIN_ROLE,
    PERMISSION_CATALOGUE,
    SYSTEM_ROLES,
)

logger = get_logger(__name__)

_MAX_FAILED_LOGINS = 5
_LOCKOUT_MINUTES = 15
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    """Convert a display name into a URL-safe slug."""
    return _SLUG_RE.sub("-", value.lower()).strip("-")


class AuthService:
    """Coordinates authentication and access-control use cases.

    :param settings: Application settings (token lifetimes, secrets).
    :param uow: An open Unit of Work bound to the current transaction.
    """

    def __init__(self, settings: Settings, uow: UnitOfWork) -> None:
        self._settings = settings
        self._uow = uow
        session = uow.session
        self.organizations = OrganizationRepository(session)
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.permissions = PermissionRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------
    def ensure_permission_catalogue(self) -> dict[str, Permission]:
        """Ensure every catalogue permission exists, returning them by code."""
        existing = {perm.code: perm for perm in self.permissions.list_all()}
        for code, description in PERMISSION_CATALOGUE.items():
            if code not in existing:
                perm = Permission(code=code, description=description)
                existing[code] = self.permissions.add(perm)
        return existing

    # ------------------------------------------------------------------
    # Registration / tenancy bootstrap
    # ------------------------------------------------------------------
    def register_organization(
        self, *, name: str, admin_email: str, admin_full_name: str, password: str
    ) -> tuple[Organization, User]:
        """Create a new tenant, seed roles, and create the first admin user.

        :raises ConflictError: If the derived organization slug is taken.
        """
        slug = _slugify(name)
        if not slug:
            raise ValidationError("Organization name yields an empty slug.")
        if self.organizations.get_by_slug(slug):
            raise ConflictError(
                f"An organization with slug '{slug}' already exists.",
                details={"slug": slug},
            )

        org = self.organizations.add(Organization(name=name, slug=slug))
        catalogue = self.ensure_permission_catalogue()
        seeded_roles = self._seed_system_roles(org.id, catalogue)

        admin = User(
            organization_id=org.id,
            email=admin_email.lower(),
            full_name=admin_full_name,
            hashed_password=hash_password(password),
            created_by=None,
        )
        admin.roles.append(seeded_roles[BOOTSTRAP_ADMIN_ROLE])
        self.users.add(admin)

        # Backfill created_by now that the admin id exists.
        org.created_by = admin.id
        admin.created_by = admin.id

        self._uow.record_audit(
            "Organization",
            org.id,
            "create",
            f"Registered '{name}'",
            actor_id=admin.id,
            organization_id=org.id,
        )
        logger.info("organization registered", extra={"ctx_org_id": str(org.id)})
        return org, admin

    def _seed_system_roles(
        self, organization_id: uuid.UUID, catalogue: dict[str, Permission]
    ) -> dict[str, Role]:
        """Create the system roles for a new organization."""
        result: dict[str, Role] = {}
        for role_name, permission_codes in SYSTEM_ROLES.items():
            role = Role(
                organization_id=organization_id,
                name=role_name,
                is_system=True,
                description=f"System role: {role_name}",
            )
            role.permissions = [catalogue[code] for code in permission_codes]
            result[role_name] = self.roles.add(role)
        return result

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    def authenticate(
        self,
        *,
        organization_slug: str,
        email: str,
        password: str,
        mfa_code: str | None,
    ) -> tuple[str, str, int]:
        """Verify credentials and issue an access/refresh token pair.

        :returns: ``(access_token, refresh_token, expires_in_seconds)``.
        :raises AuthenticationError: On any credential, lockout or MFA failure.
            The message is deliberately generic to avoid user enumeration.
        """
        generic = "Invalid credentials."
        org = self.organizations.get_by_slug(organization_slug)
        if org is None:
            raise AuthenticationError(generic)

        user = self.users.get_by_email(org.id, email)
        if user is None:
            # Perform a dummy hash comparison to equalise timing.
            verify_password(password, hash_password("timing-equaliser"))
            raise AuthenticationError(generic)

        self._assert_not_locked(user)

        if not user.is_active:
            raise AuthenticationError(generic)

        if not verify_password(password, user.hashed_password):
            self._register_failed_login(user)
            raise AuthenticationError(generic)

        if user.mfa_enabled:
            if not mfa_code:
                raise AuthenticationError("MFA code required.", code="mfa_required")
            if not user.mfa_secret or not verify_mfa_code(user.mfa_secret, mfa_code):
                self._register_failed_login(user)
                raise AuthenticationError("Invalid MFA code.", code="mfa_invalid")

        # Success: reset counters and issue tokens.
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = datetime.now(UTC)
        return self._issue_token_pair(user)

    def _assert_not_locked(self, user: User) -> None:
        """Raise if the account is currently locked out."""
        if user.locked_until and ensure_aware(user.locked_until) > datetime.now(UTC):
            raise AuthenticationError(
                "Account temporarily locked. Try again later.",
                code="account_locked",
            )

    def _register_failed_login(self, user: User) -> None:
        """Increment failed-login counter and lock after the threshold."""
        user.failed_login_count += 1
        if user.failed_login_count >= _MAX_FAILED_LOGINS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=_LOCKOUT_MINUTES)
            self._uow.record_audit(
                "User",
                user.id,
                "lockout",
                "Account locked after failed logins",
                actor_id=user.id,
                organization_id=user.organization_id,
            )
        self.users.update(user)
        # Security accounting must persist even though the request ends in a
        # 401, so this side effect is committed independently of the caller.
        self._uow.commit()

    # ------------------------------------------------------------------
    # Tokens
    # ------------------------------------------------------------------
    def _issue_token_pair(self, user: User) -> tuple[str, str, int]:
        """Create and persist a new access/refresh token pair for ``user``."""
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
        expires_in = self._settings.access_token_expire_minutes * 60
        return access, refresh, expires_in

    def refresh(self, refresh_token: str) -> tuple[str, str, int]:
        """Rotate a refresh token, returning a fresh token pair.

        Implements refresh-token rotation with reuse detection: a valid, active
        token is revoked and replaced; presentation of an already-revoked token
        revokes the entire family as a theft countermeasure.
        """
        try:
            claims = decode_token(self._settings, refresh_token, expected_type="refresh")
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid refresh token.") from exc

        record = self.refresh_tokens.get_by_jti(claims.jti)
        if record is None:
            raise AuthenticationError("Unknown refresh token.")

        if record.revoked:
            # Reuse of a rotated token: revoke the whole family.
            self.refresh_tokens.revoke_all_for_user(record.user_id)
            self._uow.record_audit(
                "RefreshToken",
                record.id,
                "reuse_detected",
                "Revoked token replayed; family revoked",
                actor_id=record.user_id,
                organization_id=record.organization_id,
            )
            # Persist the revocation despite the 401 that follows.
            self._uow.commit()
            raise AuthenticationError("Refresh token reuse detected.")

        if ensure_aware(record.expires_at) <= datetime.now(UTC):
            raise AuthenticationError("Refresh token expired.")

        user = self.users.get(record.user_id, organization_id=claims.organization_id)
        if user is None or not user.is_active:
            raise AuthenticationError("User is no longer active.")

        record.revoked = True
        self.refresh_tokens.update(record)
        return self._issue_token_pair(user)

    def logout(self, refresh_token: str) -> None:
        """Revoke the supplied refresh token (idempotent)."""
        try:
            claims = decode_token(self._settings, refresh_token, expected_type="refresh")
        except jwt.PyJWTError:
            return
        record = self.refresh_tokens.get_by_jti(claims.jti)
        if record and not record.revoked:
            record.revoked = True
            self.refresh_tokens.update(record)

    # ------------------------------------------------------------------
    # MFA
    # ------------------------------------------------------------------
    def begin_mfa_enrollment(self, user: User) -> tuple[str, str]:
        """Generate and store a provisional TOTP secret for ``user``."""
        secret = generate_mfa_secret()
        user.mfa_secret = secret
        user.mfa_enabled = False
        self.users.update(user)
        uri = mfa_provisioning_uri(
            secret, account_name=user.email, issuer=self._settings.mfa_issuer
        )
        return secret, uri

    def confirm_mfa_enrollment(self, user: User, code: str) -> None:
        """Activate MFA after verifying the first TOTP ``code``.

        :raises ValidationError: If no enrolment is in progress.
        :raises AuthenticationError: If the code is incorrect.
        """
        if not user.mfa_secret:
            raise ValidationError("No MFA enrolment in progress.")
        if not verify_mfa_code(user.mfa_secret, code):
            raise AuthenticationError("Invalid MFA code.", code="mfa_invalid")
        user.mfa_enabled = True
        self.users.update(user)
        self._uow.record_audit(
            "User",
            user.id,
            "mfa_enabled",
            "MFA activated",
            actor_id=user.id,
            organization_id=user.organization_id,
        )

    # ------------------------------------------------------------------
    # Lookups used by dependencies
    # ------------------------------------------------------------------
    def get_active_user(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> User:
        """Return an active user or raise :class:`NotFoundError`."""
        user = self.users.get(user_id, organization_id=organization_id)
        if user is None or not user.is_active:
            raise NotFoundError("User not found.")
        return user
