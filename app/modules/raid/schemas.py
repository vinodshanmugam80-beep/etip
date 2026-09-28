"""Pydantic v2 schemas for the RAID Log module."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.raid.models import (
    ActionPriority,
    ActionStatus,
    DecisionStatus,
)


class _TitleMixin(BaseModel):
    """Strips and length-checks a ``title`` field."""

    @field_validator("title", check_fields=False)
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Title must be at least 2 characters.")
        return cleaned


# --- Actions ---------------------------------------------------------------
class ActionCreateRequest(_TitleMixin):
    """Payload to raise an action item."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "title": "Confirm data-migration window with ops",
                "description": "Need a 4h maintenance slot",
                "priority": "high",
                "owner_user_id": None,
                "due_date": "2026-04-05",
            }
        }
    )

    project_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    priority: ActionPriority = ActionPriority.MEDIUM
    owner_user_id: uuid.UUID | None = None
    due_date: date | None = None


class ActionUpdateRequest(BaseModel):
    """Partial update for an action item."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    status: ActionStatus | None = None
    priority: ActionPriority | None = None
    owner_user_id: uuid.UUID | None = None
    due_date: date | None = None


class ActionResponse(BaseModel):
    """Action item representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    owner_user_id: uuid.UUID | None
    number: int
    title: str
    description: str
    status: ActionStatus
    priority: ActionPriority
    due_date: date | None
    completed_date: date | None
    source_meeting_id: uuid.UUID | None = None
    created_date: datetime
    version: int


class PaginatedActions(BaseModel):
    """A page of action items with total-count metadata."""

    items: list[ActionResponse]
    total: int
    limit: int
    offset: int


# --- Decisions -------------------------------------------------------------
class DecisionCreateRequest(_TitleMixin):
    """Payload to log a decision."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "title": "Adopt event-sourced billing",
                "description": "Use an append-only ledger for billing state",
                "rationale": "Auditability and replay outweigh added complexity",
                "decided_by_user_id": None,
            }
        }
    )

    project_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    rationale: str = Field(default="", max_length=4000)
    decided_by_user_id: uuid.UUID | None = None


class DecisionUpdateRequest(BaseModel):
    """Partial update for a decision."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    rationale: str | None = Field(default=None, max_length=4000)
    status: DecisionStatus | None = None
    decided_by_user_id: uuid.UUID | None = None


class DecisionResponse(BaseModel):
    """Decision representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    decided_by_user_id: uuid.UUID | None
    number: int
    title: str
    description: str
    rationale: str
    status: DecisionStatus
    decision_date: date | None
    created_date: datetime
    version: int


class PaginatedDecisions(BaseModel):
    """A page of decisions with total-count metadata."""

    items: list[DecisionResponse]
    total: int
    limit: int
    offset: int


# --- Consolidated summary --------------------------------------------------
class QuadrantSummary(BaseModel):
    """Open vs total counts for one RAID quadrant."""

    open_count: int
    total_count: int


class RaidSummaryResponse(BaseModel):
    """Consolidated RAID position for a project across all four quadrants."""

    project_id: uuid.UUID
    risks: QuadrantSummary
    actions: QuadrantSummary
    issues: QuadrantSummary
    decisions: QuadrantSummary


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
