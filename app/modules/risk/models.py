"""ORM model for the Risk Management module.

A :class:`Risk` belongs to a project and represents a potential threat. Its
exposure is scored as ``probability × impact`` (each on a 1–5 scale, so the
score ranges 1–25) and bucketed into a :class:`RiskSeverity` band. Both the
score and the band are stored (computed on write) so they can be filtered and
aggregated efficiently. The service keeps the owning project's ``risk_score``
rollup in sync with the highest open risk.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class RiskCategory(enum.StrEnum):
    """Source category of a risk."""

    TECHNICAL = "technical"
    SCHEDULE = "schedule"
    COST = "cost"
    RESOURCE = "resource"
    SCOPE = "scope"
    EXTERNAL = "external"
    ORGANIZATIONAL = "organizational"
    OTHER = "other"


class RiskStatus(enum.StrEnum):
    """Lifecycle state of a risk."""

    IDENTIFIED = "identified"
    ANALYZING = "analyzing"
    MITIGATING = "mitigating"
    MONITORING = "monitoring"
    CLOSED = "closed"


class RiskResponse(enum.StrEnum):
    """Planned response strategy for a risk (PMBOK threat responses)."""

    AVOID = "avoid"
    MITIGATE = "mitigate"
    TRANSFER = "transfer"
    ACCEPT = "accept"
    ESCALATE = "escalate"


class RiskSeverity(enum.StrEnum):
    """Severity band derived from the risk score (probability × impact)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def severity_for_score(score: int) -> RiskSeverity:
    """Map a 1–25 risk score to a severity band."""
    if score >= 15:
        return RiskSeverity.CRITICAL
    if score >= 10:
        return RiskSeverity.HIGH
    if score >= 5:
        return RiskSeverity.MEDIUM
    return RiskSeverity.LOW


class Risk(BaseEntity, TenantMixin):
    """A potential threat tracked against a project.

    ``number`` is unique per project. ``risk_score`` and ``severity`` are
    derived from ``probability`` and ``impact`` on every write.
    """

    __tablename__ = "risks"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_risk_number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="")

    category: Mapped[RiskCategory] = mapped_column(
        enum_column(RiskCategory), default=RiskCategory.OTHER, index=True
    )
    status: Mapped[RiskStatus] = mapped_column(
        enum_column(RiskStatus), default=RiskStatus.IDENTIFIED, index=True
    )
    response_strategy: Mapped[RiskResponse | None] = mapped_column(
        enum_column(RiskResponse), nullable=True
    )

    probability: Mapped[int] = mapped_column(Integer, nullable=False)
    impact: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    severity: Mapped[RiskSeverity] = mapped_column(
        enum_column(RiskSeverity), default=RiskSeverity.LOW, index=True
    )

    mitigation_plan: Mapped[str] = mapped_column(String(4000), default="")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
