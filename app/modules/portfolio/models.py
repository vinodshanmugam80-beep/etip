"""ORM models for the Portfolio Management module.

A :class:`Portfolio` is the top-level container of the PPM domain; programs and
projects (later modules) reference it. It carries an owner, a budget envelope,
a status lifecycle, priority and health, and owns a collection of
:class:`PortfolioObjective` rows capturing its strategic objectives.

Enum columns are stored as portable strings (``native_enum=False``) so the same
schema works on PostgreSQL and on the SQLite database used in tests.
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class PortfolioStatus(enum.StrEnum):
    """Lifecycle state of a portfolio."""

    PROPOSED = "proposed"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class PortfolioPriority(enum.StrEnum):
    """Relative priority of a portfolio."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PortfolioHealth(enum.StrEnum):
    """Health indicator for a portfolio."""

    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OFF_TRACK = "off_track"


class Portfolio(BaseEntity, TenantMixin):
    """A top-level container grouping programs and projects under a strategy.

    ``code`` is unique per organization. ``planned_budget`` is the funding
    envelope; actuals roll up from child projects in later modules.
    """

    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_portfolio_code"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="")

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[PortfolioStatus] = mapped_column(
        enum_column(PortfolioStatus), default=PortfolioStatus.PROPOSED
    )
    priority: Mapped[PortfolioPriority] = mapped_column(
        enum_column(PortfolioPriority), default=PortfolioPriority.MEDIUM
    )
    health: Mapped[PortfolioHealth | None] = mapped_column(
        enum_column(PortfolioHealth), nullable=True
    )

    planned_budget: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    objectives: Mapped[list[PortfolioObjective]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PortfolioObjective(BaseEntity, TenantMixin):
    """A strategic objective belonging to a portfolio.

    ``weight`` expresses the objective's relative importance (0–100) and is
    used by reporting rollups in later modules.
    """

    __tablename__ = "portfolio_objectives"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    weight: Mapped[int] = mapped_column(default=0)

    portfolio: Mapped[Portfolio] = relationship(back_populates="objectives")
