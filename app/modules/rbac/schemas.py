"""Pydantic v2 schemas for the Roles & Permissions module.

Permissions are referenced by their stable ``resource:action`` code rather than
by id, which keeps the API readable and decoupled from database identifiers.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PermissionResponse(BaseModel):
    """A single catalogue permission."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    description: str


class RoleCreateRequest(BaseModel):
    """Payload to create a custom (non-system) role."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Portfolio Analyst",
                "description": "Read-only access across portfolios",
                "permissions": ["project:read", "organization:read"],
            }
        }
    )

    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=300)
    permissions: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Role name must not be empty.")
        return cleaned


class RoleUpdateRequest(BaseModel):
    """Partial update for a role's descriptive fields."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=300)


class SetPermissionsRequest(BaseModel):
    """Replace the full permission set of a role."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"permissions": ["project:read", "project:update"]}}
    )

    permissions: list[str] = Field(default_factory=list)


class RoleResponse(BaseModel):
    """A role together with its granted permissions."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str
    is_system: bool
    permissions: list[PermissionResponse]
    created_date: datetime
    version: int


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
