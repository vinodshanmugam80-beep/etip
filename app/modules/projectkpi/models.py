"""ORM model for the per-project KPI register.

A :class:`ProjectKPI` is a measurable indicator defined directly on a single
project — a baseline, the current value and a target, with a direction telling
whether higher or lower is better. Attainment and on-target status are derived
(not stored) so they always reflect the latest values.
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class KPIDirection(enum.StrEnum):
    """Which way of moving is an improvement for a KPI."""

    INCREASE = "increase"
    DECREASE = "decrease"


class ProjectKPI(BaseEntity, TenantMixin):
    """A measurable KPI owned by a single project."""

    __tablename__ = "project_kpis"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="")
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
