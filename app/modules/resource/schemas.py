"""Pydantic v2 schemas for the Resource Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.resource.models import ResourceType


# --- Resource --------------------------------------------------------------
class ResourceCreateRequest(BaseModel):
    """Payload to create a resource."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Ada Engineer",
                "user_id": None,
                "department_id": None,
                "resource_type": "employee",
                "capacity_hours_per_week": "40.00",
                "cost_rate": "120.00",
                "currency": "USD",
                "skills": ["python", "postgres"],
            }
        }
    )

    name: str = Field(min_length=2, max_length=200)
    user_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    resource_type: ResourceType = ResourceType.EMPLOYEE
    capacity_hours_per_week: Decimal = Field(
        default=Decimal("40.00"), ge=0, le=168, max_digits=6, decimal_places=2
    )
    cost_rate: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    skills: list[str] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("skills")
    @classmethod
    def _clean_skills(cls, value: list[str]) -> list[str]:
        cleaned = [s.strip().lower() for s in value if s.strip()]
        return list(dict.fromkeys(cleaned))


class ResourceUpdateRequest(BaseModel):
    """Partial update for a resource; unset fields are left unchanged."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    department_id: uuid.UUID | None = None
    resource_type: ResourceType | None = None
    capacity_hours_per_week: Decimal | None = Field(
        default=None, ge=0, le=168, max_digits=6, decimal_places=2
    )
    cost_rate: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    skills: list[str] | None = None
    is_active: bool | None = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class ResourceResponse(BaseModel):
    """Resource representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    department_id: uuid.UUID | None
    name: str
    resource_type: ResourceType
    capacity_hours_per_week: Decimal
    cost_rate: Decimal
    currency: str
    skills: list[str]
    is_active: bool
    created_date: datetime
    version: int


class PaginatedResources(BaseModel):
    """A page of resources with total-count metadata."""

    items: list[ResourceResponse]
    total: int
    limit: int
    offset: int


# --- Allocation ------------------------------------------------------------
class AllocationCreateRequest(BaseModel):
    """Payload to allocate a resource to a project over a date range."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "start_date": "2026-03-01",
                "end_date": "2026-05-31",
                "allocation_percent": 50,
                "role_label": "Backend Lead",
                "notes": "",
            }
        }
    )

    project_id: uuid.UUID
    start_date: date
    end_date: date
    allocation_percent: int = Field(ge=1, le=100)
    role_label: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=500)
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_dates(self) -> AllocationCreateRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date.")
        return self


class AllocationUpdateRequest(BaseModel):
    """Partial update for an allocation; unset fields are left unchanged."""

    start_date: date | None = None
    end_date: date | None = None
    allocation_percent: int | None = Field(default=None, ge=1, le=100)
    role_label: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class AllocationResponse(BaseModel):
    """Resource allocation representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    resource_id: uuid.UUID
    project_id: uuid.UUID
    start_date: date
    end_date: date
    allocation_percent: int
    role_label: str
    notes: str
    created_date: datetime
    version: int


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
