"""Pydantic v2 schemas for the authentication module.

These define the API contract: request bodies are validated on the way in and
response models shape the JSON returned to clients. Business rules that require
database access live in the service layer; only self-contained validation
(password strength, field formats) lives here.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import get_settings

_PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).+$")


class RegisterOrganizationRequest(BaseModel):
    """Payload to bootstrap a new tenant with its first administrator."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "organization_name": "Contoso Ltd",
                "admin_email": "admin@contoso.com",
                "admin_full_name": "Ada Admin",
                "password": "Str0ng-Passphrase!",
            }
        }
    )

    organization_name: str = Field(min_length=2, max_length=200)
    admin_email: EmailStr
    admin_full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        settings = get_settings()
        if len(value) < settings.password_min_length:
            raise ValueError(
                f"Password must be at least {settings.password_min_length} characters."
            )
        if not _PASSWORD_PATTERN.match(value):
            raise ValueError(
                "Password must include upper- and lower-case letters, a digit and a symbol."
            )
        return value


class LoginRequest(BaseModel):
    """Password login payload, scoped to an organization slug."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "organization_slug": "contoso-ltd",
                "email": "admin@contoso.com",
                "password": "Str0ng-Passphrase!",
                "mfa_code": "123456",
            }
        }
    )

    organization_slug: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6)


class RefreshRequest(BaseModel):
    """Payload carrying a refresh token to be rotated."""

    refresh_token: str


class TokenResponse(BaseModel):
    """Issued token pair returned on successful authentication."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1Ni...",
                "refresh_token": "eyJhbGciOiJIUzI1NiI...",
                "token_type": "bearer",
                "expires_in": 900,
            }
        }
    )

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RoleResponse(BaseModel):
    """Role summary embedded in user responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_system: bool


class UserResponse(BaseModel):
    """Public representation of a user account."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    roles: list[RoleResponse] = Field(default_factory=list)


class MfaEnrollResponse(BaseModel):
    """Secret and provisioning URI returned when enrolling in MFA."""

    secret: str
    otpauth_uri: str


class MfaVerifyRequest(BaseModel):
    """Six-digit TOTP code confirming MFA enrolment."""

    code: str = Field(min_length=6, max_length=6)


class MessageResponse(BaseModel):
    """Generic success envelope for operations without a resource body."""

    detail: str
