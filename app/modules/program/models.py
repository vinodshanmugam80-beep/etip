"""ORM model for the Program Management module.

A :class:`Program` sits between a portfolio and its projects: it **belongs to a
portfolio** (required) and groups related projects toward a shared outcome.
Projects (a later module) reference the program. It carries its own manager,
status lifecycle, priority, health and budget envelope.

Enum columns reuse the shared, string-backed enum column factory so the schema
is portable across PostgreSQL and SQLite.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class ProgramStatus(enum.StrEnum):
    """Lifecycle state of a program."""

    PROPOSED = "proposed"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ProgramPriority(enum.StrEnum):
    """Relative priority of a program."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProgramHealth(enum.StrEnum):
    """Health indicator for a program."""

    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OFF_TRACK = "off_track"


class Program(BaseEntity, TenantMixin):
    """A program grouping related projects within a portfolio.

    ``code`` is unique per organization. ``portfolio_id`` is required — a
    program always lives inside exactly one portfolio.
    """

    __tablename__ = "programs"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_program_code"),)

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="")

    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[ProgramStatus] = mapped_column(
        enum_column(ProgramStatus), default=ProgramStatus.PROPOSED
    )
    priority: Mapped[ProgramPriority] = mapped_column(
        enum_column(ProgramPriority), default=ProgramPriority.MEDIUM
    )
    health: Mapped[ProgramHealth | None] = mapped_column(enum_column(ProgramHealth), nullable=True)

    planned_budget: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
