"""ORM model for the Task Management module.

A :class:`Task` belongs to a project and represents a unit of work. Tasks may be
nested via ``parent_task_id`` to form subtasks, carry an assignee, a task-
specific status lifecycle, priority, effort estimates vs. logged hours, a
schedule, and an ordering ``position`` within their project/parent.

``number`` is a per-project running number (unique within the project), giving
each task a stable, human-friendly reference.
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class TaskStatus(enum.StrEnum):
    """Lifecycle state of a task."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(enum.StrEnum):
    """Relative priority of a task."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Task(BaseEntity, TenantMixin):
    """A unit of work within a project.

    ``number`` is unique per project. ``parent_task_id`` (optional) forms a
    subtask hierarchy; cycle prevention is enforced in the service layer.
    """

    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_task_number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sprint_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True, index=True
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="")

    status: Mapped[TaskStatus] = mapped_column(
        enum_column(TaskStatus), default=TaskStatus.TODO, index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(
        enum_column(TaskPriority), default=TaskPriority.MEDIUM
    )

    estimate_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    logged_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    position: Mapped[int] = mapped_column(Integer, default=0)

    parent: Mapped[Task | None] = relationship(back_populates="subtasks", remote_side="Task.id")
    subtasks: Mapped[list[Task]] = relationship(back_populates="parent")
