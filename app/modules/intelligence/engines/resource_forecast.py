"""Time-phased resource demand forecast.

A service-independent engine that projects, per future period, each resource's
committed demand (sum of overlapping allocation percentages) against its 100%
capacity — flagging over-allocation ahead of time. Pure read; no schema change.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.modules.intelligence.schemas import (
    DemandPeriodSummary,
    ForecastPeriod,
    ResourceDemandForecast,
    ResourceDemandRow,
)
from app.modules.resource.models import ResourceAllocation
from app.modules.resource.repository import AllocationRepository, ResourceRepository


class ResourceForecastEngine:
    """Projects resource demand vs capacity across a rolling horizon."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self.resources = ResourceRepository(session)
        self.allocations = AllocationRepository(session)

    def forecast(
        self, *, as_of: date | None = None, weeks: int = 8, period_days: int = 7
    ) -> ResourceDemandForecast:
        """Return demand vs capacity for the next ``weeks`` periods."""
        as_of = as_of or utcnow().date()
        periods = [
            ForecastPeriod(
                index=i,
                start_date=as_of + timedelta(days=i * period_days),
                end_date=as_of + timedelta(days=(i + 1) * period_days - 1),
            )
            for i in range(weeks)
        ]

        resources = [r for r in self.resources.search(self._org_id, limit=1000) if r.is_active]
        by_resource: dict[uuid.UUID, list[ResourceAllocation]] = {}
        for alloc in self.allocations.list_all(self._org_id):
            by_resource.setdefault(alloc.resource_id, []).append(alloc)

        rows: list[ResourceDemandRow] = []
        period_totals = [0] * weeks
        period_over = [0] * weeks
        for resource in resources:
            allocs = by_resource.get(resource.id, [])
            demand: list[int] = []
            for period in periods:
                d = sum(
                    a.allocation_percent
                    for a in allocs
                    if a.start_date <= period.end_date and a.end_date >= period.start_date
                )
                demand.append(d)
            over = sum(1 for d in demand if d > 100)
            for i, d in enumerate(demand):
                period_totals[i] += d
                if d > 100:
                    period_over[i] += 1
            rows.append(
                ResourceDemandRow(
                    resource_id=resource.id,
                    resource_name=resource.name,
                    demand=demand,
                    over_periods=over,
                    peak_demand=max(demand) if demand else 0,
                )
            )

        n = len(resources)
        summary = [
            DemandPeriodSummary(
                index=period.index,
                start_date=period.start_date,
                end_date=period.end_date,
                resource_count=n,
                total_demand_percent=period_totals[i],
                over_allocated_count=period_over[i],
                average_demand_percent=round(period_totals[i] / n, 1) if n else 0.0,
            )
            for i, period in enumerate(periods)
        ]
        return ResourceDemandForecast(
            as_of=as_of,
            period_days=period_days,
            periods=periods,
            summary=summary,
            resources=rows,
        )
