"""Pydantic v2 schemas for the Task Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.task.models import TaskPriority, TaskStatus


class _DateRangeMixin(BaseModel):
    """Validates that ``due_date`` is not before ``start_date`` when both set."""

    @model_validator(mode="after")
    def _check_dates(self) -> _DateRangeMixin:
        start = getattr(self, "start_date", None)
        due = getattr(self, "due_date", None)
        if start and due and due < start:
            raise ValueError("due_date must not be before start_date.")
        return self


class TaskCreateRequest(_DateRangeMixin):
    """Payload to create a task within a project."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "title": "Design the billing schema",
                "description": "ERD and migration plan",
                "assignee_user_id": None,
                "parent_task_id": None,
                "priority": "high",
                "estimate_hours": "16.00",
                "start_date": "2026-03-02",
                "due_date": "2026-03-09",
            }
        }
    )

    project_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    assignee_user_id: uuid.UUID | None = None
    parent_task_id: uuid.UUID | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    estimate_hours: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2)
    start_date: date | None = None
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Title must be at least 2 characters.")
        return cleaned


class TaskUpdateRequest(_DateRangeMixin):
    """Partial update for a task; unset fields are left unchanged."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    assignee_user_id: uuid.UUID | None = None
    parent_task_id: uuid.UUID | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    estimate_hours: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    logged_hours: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    start_date: date | None = None
    due_date: date | None = None
    position: int | None = Field(default=None, ge=0)


class TaskResponse(BaseModel):
    """Task representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    parent_task_id: uuid.UUID | None
    assignee_user_id: uuid.UUID | None
    sprint_id: uuid.UUID | None
    number: int
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    estimate_hours: Decimal
    logged_hours: Decimal
    start_date: date | None
    due_date: date | None
    position: int
    created_date: datetime
    version: int


class PaginatedTasks(BaseModel):
    """A page of tasks with total-count metadata."""

    items: list[TaskResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
