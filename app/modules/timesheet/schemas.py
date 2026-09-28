"""Pydantic v2 schemas for the Timesheet Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.timesheet.models import ActivityType, TimeEntryStatus


class TimeEntryCreateRequest(BaseModel):
    """Payload to log a time entry (logged for the calling user)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "task_id": None,
                "work_date": "2026-03-02",
                "hours": "6.50",
                "billable": True,
                "activity_type": "development",
                "description": "Implemented the export pipeline",
            }
        }
    )

    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    work_date: date
    hours: Decimal = Field(gt=0, le=24, max_digits=6, decimal_places=2)
    billable: bool = True
    activity_type: ActivityType = ActivityType.DEVELOPMENT
    description: str = Field(default="", max_length=2000)


class TimeEntryUpdateRequest(BaseModel):
    """Partial update for a time entry (allowed only while draft/rejected).

    ``status`` may move between ``draft`` and ``submitted``; deciding is done via
    the approve/reject endpoints.
    """

    task_id: uuid.UUID | None = None
    work_date: date | None = None
    hours: Decimal | None = Field(default=None, gt=0, le=24, max_digits=6, decimal_places=2)
    billable: bool | None = None
    activity_type: ActivityType | None = None
    description: str | None = Field(default=None, max_length=2000)
    status: TimeEntryStatus | None = None


class TimeEntryDecisionRequest(BaseModel):
    """Payload for an approve/reject decision."""

    decision_notes: str = Field(default="", max_length=2000)


class TimeEntryResponse(BaseModel):
    """Time entry representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    user_id: uuid.UUID
    approver_user_id: uuid.UUID | None
    work_date: date
    hours: Decimal
    billable: bool
    activity_type: ActivityType
    description: str
    status: TimeEntryStatus
    decision_notes: str
    decided_date: date | None
    created_date: datetime
    version: int


class PaginatedTimeEntries(BaseModel):
    """A page of time entries with total-count metadata."""

    items: list[TimeEntryResponse]
    total: int
    limit: int
    offset: int


class StatusHours(BaseModel):
    """Hours and entry count for a workflow state."""

    status: TimeEntryStatus
    hours: Decimal
    count: int


class TimesheetSummaryResponse(BaseModel):
    """Aggregated hours for a filtered set of time entries."""

    total_hours: Decimal
    billable_hours: Decimal
    approved_hours: Decimal
    entry_count: int
    by_status: list[StatusHours]


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
