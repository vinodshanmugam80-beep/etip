"""SSO configuration model — per-tenant OpenID Connect (OIDC) settings.

Each organization configures its own identity provider (Okta, Azure AD, Google,
Keycloak, …). Users then sign in through that IdP; ETIP verifies the ID token and
issues its own session tokens, provisioning the user just-in-time on first login.
The client secret is stored but never returned by the API.
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin


class SsoConfiguration(BaseEntity, TenantMixin):
    """A tenant's OIDC identity-provider configuration (one per organization)."""

    __tablename__ = "sso_configurations"

    provider: Mapped[str] = mapped_column(String(50), default="oidc")
    client_id: Mapped[str] = mapped_column(String(500), default="")
    client_secret: Mapped[str] = mapped_column(String(1000), default="")
    issuer: Mapped[str] = mapped_column(String(1000), default="")
    authorize_url: Mapped[str] = mapped_column(String(1000), default="")
    token_url: Mapped[str] = mapped_column(String(1000), default="")
    jwks_url: Mapped[str] = mapped_column(String(1000), default="")
    default_role_name: Mapped[str] = mapped_column(String(200), default="Member")
    allowed_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Maps an IdP group/role claim value -> an ETIP role name, applied when a user
    # is provisioned via SSO. Example: {"etip-admins": "Organization Admin"}.
    role_mappings: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
