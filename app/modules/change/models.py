"""ORM model for the Change Request Management module.

A :class:`ChangeRequest` is a formal, auditable request to change a project's
scope, schedule, budget, or resources. It carries an impact assessment and moves
through an approval workflow. Approving or rejecting is a privileged action
(separate ``change:approve`` permission) distinct from raising or editing a
request, giving a basic separation of duties.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class ChangeType(enum.StrEnum):
    """Aspect of the project a change affects."""

    SCOPE = "scope"
    SCHEDULE = "schedule"
    BUDGET = "budget"
    RESOURCE = "resource"
    QUALITY = "quality"
    OTHER = "other"


class ChangePriority(enum.StrEnum):
    """Priority of a change request."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeStatus(enum.StrEnum):
    """Approval-workflow state of a change request."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    CANCELLED = "cancelled"


class ChangeRequest(BaseEntity, TenantMixin):
    """A formal change request against a project.

    ``number`` is unique per project. Impact fields may be negative (a change
    can reduce cost or accelerate the schedule).
    """

    __tablename__ = "change_requests"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_change_number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="")
    reason: Mapped[str] = mapped_column(String(4000), default="")

    change_type: Mapped[ChangeType] = mapped_column(
        enum_column(ChangeType), default=ChangeType.SCOPE, index=True
    )
    priority: Mapped[ChangePriority] = mapped_column(
        enum_column(ChangePriority), default=ChangePriority.MEDIUM
    )
    status: Mapped[ChangeStatus] = mapped_column(
        enum_column(ChangeStatus), default=ChangeStatus.DRAFT, index=True
    )

    # Impact assessment (signed: negatives mean savings / acceleration).
    schedule_impact_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_impact: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    impact_summary: Mapped[str] = mapped_column(String(4000), default="")

    # Decision.
    decision_notes: Mapped[str] = mapped_column(String(4000), default="")
    decided_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
