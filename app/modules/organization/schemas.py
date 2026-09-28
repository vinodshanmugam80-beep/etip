"""Pydantic v2 schemas for the Organization Management module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CODE_MAX = 50


class _CodeMixin(BaseModel):
    """Shared validation for human-facing ``code`` fields."""

    @field_validator("code", check_fields=False)
    @classmethod
    def _normalise_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Code must not be empty.")
        if len(cleaned) > _CODE_MAX:
            raise ValueError(f"Code must be at most {_CODE_MAX} characters.")
        return cleaned


# --- Business Unit ---------------------------------------------------------
class BusinessUnitCreateRequest(_CodeMixin):
    """Payload to create a business unit."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Technology",
                "code": "TECH",
                "description": "Engineering and platform teams",
                "lead_user_id": None,
            }
        }
    )

    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    description: str = Field(default="", max_length=500)
    lead_user_id: uuid.UUID | None = None


class BusinessUnitUpdateRequest(BaseModel):
    """Partial update for a business unit; unset fields are left unchanged."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    lead_user_id: uuid.UUID | None = None
    is_active: bool | None = None


class BusinessUnitResponse(BaseModel):
    """Business unit representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    description: str
    lead_user_id: uuid.UUID | None
    is_active: bool
    created_date: datetime
    version: int


# --- Department ------------------------------------------------------------
class DepartmentCreateRequest(_CodeMixin):
    """Payload to create a department."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Platform Engineering",
                "code": "PLAT",
                "description": "Core platform services",
                "business_unit_id": None,
                "parent_department_id": None,
                "head_user_id": None,
            }
        }
    )

    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    description: str = Field(default="", max_length=500)
    business_unit_id: uuid.UUID | None = None
    parent_department_id: uuid.UUID | None = None
    head_user_id: uuid.UUID | None = None


class DepartmentUpdateRequest(BaseModel):
    """Partial update for a department; unset fields are left unchanged."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    business_unit_id: uuid.UUID | None = None
    parent_department_id: uuid.UUID | None = None
    head_user_id: uuid.UUID | None = None
    is_active: bool | None = None


class DepartmentResponse(BaseModel):
    """Department representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    description: str
    business_unit_id: uuid.UUID | None
    parent_department_id: uuid.UUID | None
    head_user_id: uuid.UUID | None
    is_active: bool
    created_date: datetime
    version: int


# --- Settings --------------------------------------------------------------
class OrganizationSettingsUpdateRequest(BaseModel):
    """Update payload for organization settings."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "currency": "EUR",
                "timezone": "Europe/Berlin",
                "date_format": "DD/MM/YYYY",
                "fiscal_year_start_month": 4,
                "week_start_day": 1,
            }
        }
    )

    currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, max_length=64)
    date_format: str | None = Field(default=None, max_length=32)
    fiscal_year_start_month: int | None = Field(default=None, ge=1, le=12)
    week_start_day: int | None = Field(default=None, ge=0, le=6)

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class OrganizationSettingsResponse(BaseModel):
    """Organization settings representation."""

    model_config = ConfigDict(from_attributes=True)

    organization_id: uuid.UUID
    currency: str
    timezone: str
    date_format: str
    fiscal_year_start_month: int
    week_start_day: int


# --- Membership ------------------------------------------------------------
class DepartmentMemberAddRequest(BaseModel):
    """Payload to add a user to a department."""

    user_id: uuid.UUID
    is_primary: bool = False


class DepartmentMemberResponse(BaseModel):
    """Department membership representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    department_id: uuid.UUID
    user_id: uuid.UUID
    is_primary: bool


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
