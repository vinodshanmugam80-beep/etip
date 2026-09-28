"""Pydantic v2 schemas for the User Management module.

Reuses :class:`app.modules.auth.schemas.UserResponse` and ``RoleResponse`` for
the user representation to avoid duplicating the identity contract; this module
adds the administrative request payloads and a paginated list envelope.
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import get_settings
from app.modules.auth.schemas import UserResponse

__all__ = [
    "UserResponse",
    "UserCreateRequest",
    "UserUpdateRequest",
    "SetRolesRequest",
    "ChangePasswordRequest",
    "ResetPasswordRequest",
    "PaginatedUsers",
    "MessageResponse",
]

_PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).+$")


def _validate_password_strength(value: str) -> str:
    """Validate a password against the configured policy."""
    settings = get_settings()
    if len(value) < settings.password_min_length:
        raise ValueError(f"Password must be at least {settings.password_min_length} characters.")
    if not _PASSWORD_PATTERN.match(value):
        raise ValueError(
            "Password must include upper- and lower-case letters, a digit and a symbol."
        )
    return value


class UserCreateRequest(BaseModel):
    """Payload for an administrator to create a user within the tenant."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "member@contoso.com",
                "full_name": "Mel Member",
                "password": "Initial-Passphrase!1",
                "role_ids": [],
                "must_change_password": True,
            }
        }
    )

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=128)
    role_ids: list[uuid.UUID] = Field(default_factory=list)
    must_change_password: bool = True

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class UserUpdateRequest(BaseModel):
    """Partial update for a user's profile; unset fields are unchanged."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    is_active: bool | None = None


class SetRolesRequest(BaseModel):
    """Replace the full set of roles assigned to a user."""

    role_ids: list[uuid.UUID] = Field(default_factory=list)


class ChangePasswordRequest(BaseModel):
    """Self-service password change payload."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class ResetPasswordRequest(BaseModel):
    """Administrator-initiated password reset payload."""

    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class PaginatedUsers(BaseModel):
    """A page of users with total-count metadata for pagination."""

    items: list[UserResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
