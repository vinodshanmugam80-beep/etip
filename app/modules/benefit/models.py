"""Benefits Realization models.

A :class:`Benefit` is an expected outcome delivered through a project, tracked
from plan to realisation. Target, realised and investment amounts are stored so
that realisation %, ROI and benefits variance can be computed, and rolled up to
programs and portfolios by the owning project's associations.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class BenefitCategory(enum.StrEnum):
    """The nature of a benefit."""

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    STRATEGIC = "strategic"
    CUSTOMER = "customer"
    COMPLIANCE = "compliance"
    RISK_REDUCTION = "risk_reduction"


class BenefitStatus(enum.StrEnum):
    """Lifecycle state of a benefit's realisation."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    PARTIALLY_REALIZED = "partially_realized"
    REALIZED = "realized"
    AT_RISK = "at_risk"
    MISSED = "missed"


class Benefit(BaseEntity, TenantMixin):
    """An expected outcome delivered through a project."""

    __tablename__ = "benefits"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="")
    category: Mapped[BenefitCategory] = mapped_column(
        enum_column(BenefitCategory), default=BenefitCategory.OPERATIONAL, index=True
    )
    status: Mapped[BenefitStatus] = mapped_column(
        enum_column(BenefitStatus), default=BenefitStatus.PLANNED, index=True
    )

    target_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )
    realized_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )
    investment_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )

    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    realized_date: Mapped[date | None] = mapped_column(Date, nullable=True)
