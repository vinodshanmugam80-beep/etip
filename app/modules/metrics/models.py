"""Metric snapshot model — time-series history of computed intelligence metrics.

The intelligence engines compute point-in-time values (SPI, CPI, success score,
benefits realization, per-project SPI, …). To draw trend sparklines we need those
values *over time*, so a scheduled (or on-demand) capture writes one row per
metric per day here. One row per (organization, scope, scope_id, metric, day).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin


class MetricSnapshot(BaseEntity, TenantMixin):
    """A single captured value of one metric for one scope on one day."""

    __tablename__ = "metric_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "scope",
            "scope_id",
            "metric",
            "captured_date",
            name="uq_metric_snapshot",
        ),
    )

    scope: Mapped[str] = mapped_column(String(20), default="transformation", index=True)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    metric: Mapped[str] = mapped_column(String(40), index=True)
    value: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    captured_date: Mapped[date] = mapped_column(Date, index=True)
