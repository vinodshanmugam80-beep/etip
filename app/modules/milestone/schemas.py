"""Pydantic v2 schemas for the Milestone Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.milestone.models import (
    MilestonePaymentStatus,
    MilestoneStatus,
    MilestoneType,
)


class MilestoneCreateRequest(BaseModel):
    """Payload to create a milestone."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "name": "Beta launch",
                "description": "Feature-complete beta to pilot customers",
                "milestone_type": "go_live",
                "target_date": "2026-06-15",
                "owner_user_id": None,
                "task_id": None,
                "is_key": True,
            }
        }
    )

    project_id: uuid.UUID
    name: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    milestone_type: MilestoneType = MilestoneType.CHECKPOINT
    target_date: date
    owner_user_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    is_key: bool = False
    # Financial (billing) milestone: name the deliverable and the payment it
    # releases on acceptance. ``payment_amount`` is optional; a schedule-only
    # milestone omits it.
    deliverable: str = Field(default="", max_length=500)
    payment_amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Name must be at least 2 characters.")
        return cleaned


class MilestoneUpdateRequest(BaseModel):
    """Partial update for a milestone; unset fields are left unchanged."""

    name: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    milestone_type: MilestoneType | None = None
    status: MilestoneStatus | None = None
    target_date: date | None = None
    actual_date: date | None = None
    owner_user_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    is_key: bool | None = None
    deliverable: str | None = Field(default=None, max_length=500)
    payment_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class MilestoneResponse(BaseModel):
    """Milestone representation, including a derived ``is_overdue`` flag."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    owner_user_id: uuid.UUID | None
    number: int
    name: str
    description: str
    milestone_type: MilestoneType
    status: MilestoneStatus
    target_date: date
    actual_date: date | None
    is_key: bool
    deliverable: str
    payment_amount: Decimal | None
    currency: str
    payment_status: MilestonePaymentStatus
    acceptance_instance_id: uuid.UUID | None
    paid_date: date | None
    is_overdue: bool = False
    created_date: datetime
    version: int


class PaginatedMilestones(BaseModel):
    """A page of milestones with total-count metadata."""

    items: list[MilestoneResponse]
    total: int
    limit: int
    offset: int


class StatusCount(BaseModel):
    """Count of milestones in a lifecycle state."""

    status: MilestoneStatus
    count: int


class MilestoneSummaryResponse(BaseModel):
    """Aggregated milestone position for a project."""

    project_id: uuid.UUID
    total_count: int
    key_count: int
    overdue_count: int
    by_status: list[StatusCount]


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str


# --- Financial milestone / deliverable-acceptance overview -----------------
class FinancialMilestoneItem(BaseModel):
    """A billing milestone with its deliverable-acceptance and payment state.

    ``acceptance_status`` is one of: ``not_submitted`` (no gate started),
    ``pending`` (deliverable awaiting acceptance at the gate), ``accepted``
    (gate approved, payment may be released) or ``rejected`` (deliverable sent
    back). ``can_release`` is true once accepted and not yet paid.
    """

    milestone_id: uuid.UUID
    project_id: uuid.UUID
    project_label: str
    name: str
    deliverable: str
    payment_amount: Decimal
    currency: str
    status: MilestoneStatus
    payment_status: MilestonePaymentStatus
    target_date: date
    acceptance_status: str
    acceptance_instance_id: uuid.UUID | None
    current_gate: str | None
    awaiting_my_acceptance: bool
    can_release: bool
    paid_date: date | None


class FinancialMilestoneSummary(BaseModel):
    """Portfolio roll-up of billing milestones by value and state."""

    total_value: Decimal
    released_value: Decimal
    pending_value: Decimal
    count: int
    awaiting_acceptance: int
    awaiting_my_acceptance: int
    ready_to_release: int


class FinancialMilestoneOverview(BaseModel):
    """Dashboard read model for financial milestones and deliverable acceptance."""

    summary: FinancialMilestoneSummary
    items: list[FinancialMilestoneItem]
