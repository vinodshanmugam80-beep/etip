"""Strategic Initiatives, Business Goals and Goal KPIs.

A three-level strategic layer that sits above the portfolio hierarchy:
``StrategicInitiative`` -> ``BusinessGoal`` -> ``GoalKPI``. Each KPI carries a
baseline, current and target value, which yields attainment %, KPI variance and
an on-track signal — the data source for KPI-vs-target variance. Additive: the
Portfolio module's ``PortfolioObjective`` is left untouched.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Numeric

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class InitiativeStatus(enum.StrEnum):
    """Lifecycle of a strategic initiative."""

    PROPOSED = "proposed"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InitiativePriority(enum.StrEnum):
    """Priority of a strategic initiative."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GoalCategory(enum.StrEnum):
    """The nature of a business goal."""

    GROWTH = "growth"
    EFFICIENCY = "efficiency"
    CUSTOMER = "customer"
    QUALITY = "quality"
    FINANCIAL = "financial"
    SUSTAINABILITY = "sustainability"
    OTHER = "other"


class GoalStatus(enum.StrEnum):
    """Lifecycle of a business goal."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    AT_RISK = "at_risk"
    ACHIEVED = "achieved"
    MISSED = "missed"


class KPIDirection(enum.StrEnum):
    """Whether a higher or lower KPI value is better."""

    INCREASE = "increase"
    DECREASE = "decrease"


class StrategicInitiative(BaseEntity, TenantMixin):
    """A major transformation initiative, optionally mapped to a portfolio."""

    __tablename__ = "strategic_initiatives"

    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sponsor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="")
    status: Mapped[InitiativeStatus] = mapped_column(
        enum_column(InitiativeStatus), default=InitiativeStatus.PROPOSED, index=True
    )
    priority: Mapped[InitiativePriority] = mapped_column(
        enum_column(InitiativePriority), default=InitiativePriority.MEDIUM, index=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class BusinessGoal(BaseEntity, TenantMixin):
    """A measurable business goal under a strategic initiative."""

    __tablename__ = "business_goals"

    initiative_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("strategic_initiatives.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="")
    category: Mapped[GoalCategory] = mapped_column(
        enum_column(GoalCategory), default=GoalCategory.OTHER, index=True
    )
    status: Mapped[GoalStatus] = mapped_column(
        enum_column(GoalStatus), default=GoalStatus.NOT_STARTED, index=True
    )
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class GoalKPI(BaseEntity, TenantMixin):
    """A measurable KPI on a business goal (baseline / current / target)."""

    __tablename__ = "goal_kpis"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("business_goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), default="")
    direction: Mapped[KPIDirection] = mapped_column(
        enum_column(KPIDirection), default=KPIDirection.INCREASE
    )
    baseline_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )
    current_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )
    target_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0.0000"), nullable=False
    )
