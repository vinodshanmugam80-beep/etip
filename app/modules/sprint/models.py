"""ORM model for the Sprint Management module.

A :class:`Sprint` is a time-boxed iteration within a project. Tasks are assigned
to a sprint via ``Task.sprint_id`` (managed by the sprint service). Each sprint
has a per-project running ``number``, a goal, a status lifecycle, a schedule and
an optional capacity.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class SprintStatus(enum.StrEnum):
    """Lifecycle state of a sprint."""

    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Sprint(BaseEntity, TenantMixin):
    """A time-boxed iteration within a project.

    ``number`` is unique per project. At most one sprint per project may be in
    the ``active`` state at a time (enforced in the service layer).
    """

    __tablename__ = "sprints"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_sprint_number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[str] = mapped_column(String(1000), default="")

    status: Mapped[SprintStatus] = mapped_column(
        enum_column(SprintStatus), default=SprintStatus.PLANNED, index=True
    )

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    capacity_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
