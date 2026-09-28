"""Metrics service — capture intelligence values over time and serve sparklines."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.db.base import utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.intelligence.service import IntelligenceService
from app.modules.metrics.repository import MetricSnapshotRepository
from app.modules.metrics.schemas import Sparklines

_SPARK_HEADLINE = ("success_score", "spi", "cpi", "realization")


class MetricsService:
    """Capture point-in-time intelligence metrics and expose their history."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        self.snapshots = MetricSnapshotRepository(uow.session)

    def _intel(self) -> IntelligenceService:
        return IntelligenceService(self._uow, organization_id=self._org_id, actor_id=self._actor_id)

    # ------------------------------------------------------------------ capture
    def _headline_values(self, as_of: date) -> dict[str, float]:
        intel = self._intel()
        t = intel.transformation_intelligence(as_of=as_of)
        ben = intel.benefits_variance_transformation()
        values: dict[str, float] = {"success_score": float(t.success_score)}
        if t.spi is not None:
            values["spi"] = float(t.spi)
        if t.cpi is not None:
            values["cpi"] = float(t.cpi)
        if ben.realization_percent is not None:
            values["realization"] = float(ben.realization_percent)
        return values

    def _project_spis(self, as_of: date) -> dict[uuid.UUID, float]:
        intel = self._intel()
        perf = intel.transformation_performance(as_of=as_of)
        return {item.project_id: float(item.spi) for item in perf.breakdown if item.spi is not None}

    def capture(self, *, as_of: date | None = None) -> int:
        """Snapshot the current headline + per-project metrics for one day."""
        day = as_of or utcnow().date()
        count = 0
        for metric, value in self._headline_values(day).items():
            self.snapshots.upsert_day(
                self._org_id, "transformation", None, metric, value, day, self._actor_id
            )
            count += 1
        for project_id, spi in self._project_spis(day).items():
            self.snapshots.upsert_day(
                self._org_id, "project", project_id, "spi", spi, day, self._actor_id
            )
            count += 1
        self._uow.record_audit(
            "MetricSnapshot",
            uuid.uuid4(),
            "capture",
            f"Captured {count} metric snapshots",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return count

    def backfill_demo(self, *, days: int = 10) -> int:
        """Seed a short daily history so sparklines have a trend (demo only).

        Writes points for the past ``days`` days by nudging each metric toward its
        current value with a small deterministic wave, then captures today exactly.
        """
        import math

        today = utcnow().date()
        headline = self._headline_values(today)
        project_spis = self._project_spis(today)
        count = 0
        for d in range(days, 0, -1):
            day = today - timedelta(days=d)
            factor = 1 - (d / (days + 4)) * 0.18  # ramps up toward today
            wave = 1 + 0.03 * math.sin(d)
            for metric, value in headline.items():
                v = value * factor * wave
                if metric == "success_score":
                    v = max(0, min(100, v))
                self.snapshots.upsert_day(
                    self._org_id,
                    "transformation",
                    None,
                    metric,
                    round(v, 4),
                    day,
                    self._actor_id,
                )
                count += 1
            for project_id, spi in project_spis.items():
                v = max(0, spi * factor * wave)
                self.snapshots.upsert_day(
                    self._org_id,
                    "project",
                    project_id,
                    "spi",
                    round(v, 4),
                    day,
                    self._actor_id,
                )
                count += 1
        count += self.capture(as_of=today)
        return count

    # ------------------------------------------------------------------- series
    def sparklines(self, *, limit: int = 12) -> Sparklines:
        """Return the compact trend bundle used by the dashboard."""
        headline: dict[str, list[float]] = {}
        for metric in _SPARK_HEADLINE:
            pts = self.snapshots.series(self._org_id, "transformation", None, metric, limit)
            if pts:
                headline[metric] = [float(p.value) for p in pts]
        projects = self.snapshots.all_project_series(self._org_id, "spi", limit)
        return Sparklines(headline=headline, projects=projects)
