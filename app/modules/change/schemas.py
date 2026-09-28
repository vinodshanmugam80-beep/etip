"""Pydantic v2 schemas for the Change Request Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.change.models import (
    ChangePriority,
    ChangeStatus,
    ChangeType,
)


class ChangeRequestCreateRequest(BaseModel):
    """Payload to raise a change request."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "title": "Add SSO to phase 1 scope",
                "description": "Enterprise customers require SAML at launch",
                "reason": "Unblocks three enterprise deals",
                "change_type": "scope",
                "priority": "high",
                "schedule_impact_days": 15,
                "cost_impact": "40000.00",
                "impact_summary": "Two extra sprints; one contractor",
                "approver_user_id": None,
                "target_date": "2026-06-01",
            }
        }
    )

    project_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    reason: str = Field(default="", max_length=4000)
    change_type: ChangeType = ChangeType.SCOPE
    priority: ChangePriority = ChangePriority.MEDIUM
    schedule_impact_days: int | None = None
    cost_impact: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    impact_summary: str = Field(default="", max_length=4000)
    approver_user_id: uuid.UUID | None = None
    target_date: date | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Title must be at least 2 characters.")
        return cleaned


class ChangeRequestUpdateRequest(BaseModel):
    """Partial update for a change request (non-decision fields and status).

    Status may move through the workflow **except** to ``approved`` /
    ``rejected`` — those are made via the approve/reject endpoints.
    """

    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    reason: str | None = Field(default=None, max_length=4000)
    change_type: ChangeType | None = None
    priority: ChangePriority | None = None
    status: ChangeStatus | None = None
    schedule_impact_days: int | None = None
    cost_impact: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    impact_summary: str | None = Field(default=None, max_length=4000)
    approver_user_id: uuid.UUID | None = None
    target_date: date | None = None


class ChangeDecisionRequest(BaseModel):
    """Payload for an approve/reject decision."""

    decision_notes: str = Field(default="", max_length=4000)


class ChangeRequestResponse(BaseModel):
    """Change request representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    requested_by_user_id: uuid.UUID | None
    approver_user_id: uuid.UUID | None
    number: int
    title: str
    description: str
    reason: str
    change_type: ChangeType
    priority: ChangePriority
    status: ChangeStatus
    schedule_impact_days: int | None
    cost_impact: Decimal | None
    impact_summary: str
    decision_notes: str
    decided_date: date | None
    target_date: date | None
    created_date: datetime
    version: int


class PaginatedChangeRequests(BaseModel):
    """A page of change requests with total-count metadata."""

    items: list[ChangeRequestResponse]
    total: int
    limit: int
    offset: int


class StatusCount(BaseModel):
    """Count of change requests in a workflow state."""

    status: ChangeStatus
    count: int


class ChangeSummaryResponse(BaseModel):
    """Aggregated change-control position for a project."""

    project_id: uuid.UUID
    pending_count: int
    total_count: int
    by_status: list[StatusCount]


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
