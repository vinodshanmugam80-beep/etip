"""Pydantic v2 schemas for the Sprint Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.sprint.models import SprintStatus
from app.modules.task.schemas import TaskResponse


class _DateRangeMixin(BaseModel):
    """Validates that ``end_date`` is not before ``start_date`` when both set."""

    @model_validator(mode="after")
    def _check_dates(self) -> _DateRangeMixin:
        start = getattr(self, "start_date", None)
        end = getattr(self, "end_date", None)
        if start and end and end < start:
            raise ValueError("end_date must not be before start_date.")
        return self


class SprintCreateRequest(_DateRangeMixin):
    """Payload to create a sprint within a project."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "name": "Sprint 1",
                "goal": "Ship the billing schema and API skeleton",
                "start_date": "2026-03-02",
                "end_date": "2026-03-15",
                "capacity_hours": "160.00",
            }
        }
    )

    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(default="", max_length=1000)
    start_date: date | None = None
    end_date: date | None = None
    capacity_hours: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name must not be empty.")
        return cleaned


class SprintUpdateRequest(_DateRangeMixin):
    """Partial update for a sprint; unset fields are left unchanged."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=1000)
    status: SprintStatus | None = None
    start_date: date | None = None
    end_date: date | None = None
    capacity_hours: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class SprintResponse(BaseModel):
    """Sprint representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    number: int
    name: str
    goal: str
    status: SprintStatus
    start_date: date | None
    end_date: date | None
    capacity_hours: Decimal
    created_date: datetime
    version: int


class PaginatedSprints(BaseModel):
    """A page of sprints with total-count metadata."""

    items: list[SprintResponse]
    total: int
    limit: int
    offset: int


class SprintTasksResponse(BaseModel):
    """A sprint's assigned tasks."""

    sprint_id: uuid.UUID
    tasks: list[TaskResponse]


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
