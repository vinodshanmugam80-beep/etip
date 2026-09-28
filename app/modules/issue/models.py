"""ORM model for the Issue Management module.

An :class:`Issue` is a defect, incident, or request raised against a project and
optionally linked to a specific task. It carries a type, severity and priority,
an assignee and reporter, a status workflow (with reopen), and resolution
tracking. The service keeps the owning project's ``issue_count`` rollup equal to
the number of open (non-closed) issues.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class IssueType(enum.StrEnum):
    """Nature of an issue."""

    BUG = "bug"
    INCIDENT = "incident"
    IMPROVEMENT = "improvement"
    QUESTION = "question"
    OTHER = "other"


class IssueSeverity(enum.StrEnum):
    """Impact severity of an issue."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssuePriority(enum.StrEnum):
    """Handling priority of an issue."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueStatus(enum.StrEnum):
    """Workflow state of an issue."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Issue(BaseEntity, TenantMixin):
    """A defect, incident, or request tracked against a project.

    ``number`` is unique per project. ``task_id`` optionally links the issue to
    a specific task; deleting that task unlinks the issue (the issue stays with
    the project).
    """

    __tablename__ = "issues"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_issue_number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reporter_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="")

    issue_type: Mapped[IssueType] = mapped_column(
        enum_column(IssueType), default=IssueType.BUG, index=True
    )
    severity: Mapped[IssueSeverity] = mapped_column(
        enum_column(IssueSeverity), default=IssueSeverity.MEDIUM, index=True
    )
    priority: Mapped[IssuePriority] = mapped_column(
        enum_column(IssuePriority), default=IssuePriority.MEDIUM, index=True
    )
    status: Mapped[IssueStatus] = mapped_column(
        enum_column(IssueStatus), default=IssueStatus.OPEN, index=True
    )

    resolution: Mapped[str] = mapped_column(String(4000), default="")
    resolved_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
