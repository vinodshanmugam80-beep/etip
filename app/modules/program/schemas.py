"""Pydantic v2 schemas for the Program Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.program.models import (
    ProgramHealth,
    ProgramPriority,
    ProgramStatus,
)

_CODE_MAX = 50


class _DateRangeMixin(BaseModel):
    """Validates that ``end_date`` is not before ``start_date`` when both set."""

    @model_validator(mode="after")
    def _check_dates(self) -> _DateRangeMixin:
        start = getattr(self, "start_date", None)
        end = getattr(self, "end_date", None)
        if start and end and end < start:
            raise ValueError("end_date must not be before start_date.")
        return self


class ProgramCreateRequest(_DateRangeMixin):
    """Payload to create a program within a portfolio."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "portfolio_id": "00000000-0000-0000-0000-000000000000",
                "name": "Cloud Migration",
                "code": "CLOUD",
                "description": "Migrate core systems to the cloud",
                "manager_user_id": None,
                "priority": "high",
                "planned_budget": "1200000.00",
                "currency": "USD",
                "start_date": "2026-02-01",
                "end_date": "2026-11-30",
            }
        }
    )

    portfolio_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    description: str = Field(default="", max_length=1000)
    manager_user_id: uuid.UUID | None = None
    priority: ProgramPriority = ProgramPriority.MEDIUM
    planned_budget: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("code")
    @classmethod
    def _normalise_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Code must not be empty.")
        return cleaned

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()


class ProgramUpdateRequest(_DateRangeMixin):
    """Partial update for a program; unset fields are left unchanged."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    manager_user_id: uuid.UUID | None = None
    status: ProgramStatus | None = None
    priority: ProgramPriority | None = None
    health: ProgramHealth | None = None
    planned_budget: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class ProgramResponse(BaseModel):
    """Program representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    portfolio_id: uuid.UUID
    name: str
    code: str
    description: str
    manager_user_id: uuid.UUID | None
    status: ProgramStatus
    priority: ProgramPriority
    health: ProgramHealth | None
    planned_budget: Decimal
    currency: str
    start_date: date | None
    end_date: date | None
    created_date: datetime
    version: int


class PaginatedPrograms(BaseModel):
    """A page of programs with total-count metadata."""

    items: list[ProgramResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
