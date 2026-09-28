"""ORM model for the Timesheet Management module.

A :class:`TimeEntry` records hours a user worked on a project (optionally against
a specific task) on a given day. Entries move through a submit → approve/reject
workflow; while a draft or rejected entry is editable, submitted and approved
entries are locked. Approved hours against a task roll up into the task's
``logged_hours``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class ActivityType(enum.StrEnum):
    """Category of work logged."""

    DEVELOPMENT = "development"
    DESIGN = "design"
    TESTING = "testing"
    MEETING = "meeting"
    MANAGEMENT = "management"
    SUPPORT = "support"
    OTHER = "other"


class TimeEntryStatus(enum.StrEnum):
    """Approval-workflow state of a time entry."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class TimeEntry(BaseEntity, TenantMixin):
    """A user's logged hours against a project (and optionally a task)."""

    __tablename__ = "time_entries"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    activity_type: Mapped[ActivityType] = mapped_column(
        enum_column(ActivityType), default=ActivityType.DEVELOPMENT, index=True
    )
    description: Mapped[str] = mapped_column(String(2000), default="")

    status: Mapped[TimeEntryStatus] = mapped_column(
        enum_column(TimeEntryStatus), default=TimeEntryStatus.DRAFT, index=True
    )
    decision_notes: Mapped[str] = mapped_column(String(2000), default="")
    decided_date: Mapped[date | None] = mapped_column(Date, nullable=True)
