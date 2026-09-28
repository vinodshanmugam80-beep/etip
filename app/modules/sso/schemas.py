"""Pydantic v2 schemas for SSO configuration and login."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


def _url(v: str) -> str:
    if v and not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("URLs must start with http:// or https://")
    return v


class SsoConfigUpsert(BaseModel):
    """Create or update the tenant's OIDC configuration."""

    client_id: str = Field(min_length=1, max_length=500)
    client_secret: str = Field(default="", max_length=1000)
    issuer: str = Field(min_length=1, max_length=1000)
    # Endpoints may be left blank and filled from the issuer via /sso/discover.
    authorize_url: str = Field(default="", max_length=1000)
    token_url: str = Field(default="", max_length=1000)
    jwks_url: str = Field(default="", max_length=1000)
    default_role_name: str = Field(default="Member", max_length=200)
    allowed_domains: list[str] = Field(default_factory=list)
    role_mappings: dict[str, str] = Field(default_factory=dict)
    is_enabled: bool = False

    @field_validator("issuer", "authorize_url", "token_url", "jwks_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return _url(v)


class SsoDiscoverRequest(BaseModel):
    """Request to auto-discover OIDC endpoints from an issuer."""

    issuer: str | None = Field(default=None, max_length=1000)

    @field_validator("issuer")
    @classmethod
    def _validate_url(cls, v: str | None) -> str | None:
        return _url(v) if v else v


class SsoConfigResponse(BaseModel):
    """The tenant's OIDC configuration (the client secret is never returned)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    provider: str
    client_id: str
    issuer: str
    authorize_url: str
    token_url: str
    jwks_url: str
    default_role_name: str
    allowed_domains: list[str]
    role_mappings: dict[str, str] | None = None
    is_enabled: bool
    client_secret: str = Field(exclude=True, default="")
    created_date: datetime
    version: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def secret_set(self) -> bool:
        """Whether a client secret is configured (its value stays hidden)."""
        return bool(self.client_secret)


class SsoLoginResponse(BaseModel):
    """The IdP authorize URL to redirect the user to."""

    authorize_url: str
