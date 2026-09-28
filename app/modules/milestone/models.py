"""ORM model for the Milestone Management module.

A :class:`Milestone` is a named schedule checkpoint on a project — a target date
the project is steering toward (a phase gate, deliverable, go-live, etc.). It
tracks a target vs actual date, a small status lifecycle, an optional link to
the task expected to complete it, and a ``is_key`` flag for reporting.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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


class MilestoneType(enum.StrEnum):
    """Nature of a milestone."""

    CHECKPOINT = "checkpoint"
    DELIVERABLE = "deliverable"
    PHASE_GATE = "phase_gate"
    GO_LIVE = "go_live"
    EXTERNAL = "external"
    OTHER = "other"


class MilestoneStatus(enum.StrEnum):
    """Lifecycle state of a milestone."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    ACHIEVED = "achieved"
    MISSED = "missed"
    CANCELLED = "cancelled"


class MilestonePaymentStatus(enum.StrEnum):
    """Payment lifecycle of a financial (billing) milestone.

    A milestone with no ``payment_amount`` is ``NOT_APPLICABLE``. Once it carries
    a payment it is ``PENDING`` until its deliverable is accepted at the
    acceptance gate, then ``RELEASED`` when the payment is posted to the project
    ledger.
    """

    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    RELEASED = "released"


class Milestone(BaseEntity, TenantMixin):
    """A dated checkpoint on a project.

    ``number`` is unique per project. ``target_date`` is required; ``actual_date``
    is stamped when the milestone is achieved. ``task_id`` optionally links the
    task expected to complete the milestone (same project).
    """

    __tablename__ = "milestones"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_milestone_number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="")

    milestone_type: Mapped[MilestoneType] = mapped_column(
        enum_column(MilestoneType), default=MilestoneType.CHECKPOINT, index=True
    )
    status: Mapped[MilestoneStatus] = mapped_column(
        enum_column(MilestoneStatus), default=MilestoneStatus.PLANNED, index=True
    )

    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_key: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # --- Financial (billing) milestone: a payment linked to a deliverable, ---
    # --- released only once the deliverable is accepted at the gate.        ---
    deliverable: Mapped[str] = mapped_column(String(500), default="")
    payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    payment_status: Mapped[MilestonePaymentStatus] = mapped_column(
        enum_column(MilestonePaymentStatus),
        default=MilestonePaymentStatus.NOT_APPLICABLE,
        index=True,
    )
    # The workflow instance gating deliverable acceptance (entity_type="Milestone").
    acceptance_instance_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
