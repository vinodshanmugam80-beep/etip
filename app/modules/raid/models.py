"""ORM models for the RAID Log module.

RAID = Risks, Actions, Issues, Decisions. Risks and Issues have their own
modules; this module owns the two remaining quadrants:

* :class:`Action` — an assignable action item with an owner, due date and a
  small completion workflow.
* :class:`Decision` — an entry in the project decision log, with a rationale and
  a proposed → decided lifecycle.

The module also exposes a consolidated per-project RAID summary that aggregates
across all four quadrants (see the service).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class ActionStatus(enum.StrEnum):
    """Workflow state of an action item."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class ActionPriority(enum.StrEnum):
    """Priority of an action item."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionStatus(enum.StrEnum):
    """Lifecycle state of a decision."""

    PROPOSED = "proposed"
    DECIDED = "decided"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class Action(BaseEntity, TenantMixin):
    """An assignable action item tracked against a project."""

    __tablename__ = "raid_actions"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_action_number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="")

    status: Mapped[ActionStatus] = mapped_column(
        enum_column(ActionStatus), default=ActionStatus.OPEN, index=True
    )
    priority: Mapped[ActionPriority] = mapped_column(
        enum_column(ActionPriority), default=ActionPriority.MEDIUM
    )

    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Optional provenance: the meeting this action item was raised in. Stored as
    # a plain UUID (no FK) to keep the raid schema independent of the meeting
    # module and to avoid a SQLite ALTER-add-constraint migration.
    source_meeting_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)


class Decision(BaseEntity, TenantMixin):
    """An entry in a project's decision log."""

    __tablename__ = "raid_decisions"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_decision_number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="")
    rationale: Mapped[str] = mapped_column(String(4000), default="")

    status: Mapped[DecisionStatus] = mapped_column(
        enum_column(DecisionStatus), default=DecisionStatus.PROPOSED, index=True
    )
    decision_date: Mapped[date | None] = mapped_column(Date, nullable=True)
