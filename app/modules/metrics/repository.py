"""Data access for metric snapshots."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.modules.metrics.models import MetricSnapshot
from app.repositories.base import BaseRepository


class MetricSnapshotRepository(BaseRepository[MetricSnapshot]):
    """Repository for :class:`MetricSnapshot`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, MetricSnapshot)

    def series(
        self,
        organization_id: uuid.UUID,
        scope: str,
        scope_id: uuid.UUID | None,
        metric: str,
        limit: int = 12,
    ) -> list[MetricSnapshot]:
        """Return the most recent ``limit`` points for a metric, oldest first."""
        stmt = (
            self._base_query(organization_id)
            .where(
                MetricSnapshot.scope == scope,
                MetricSnapshot.scope_id == scope_id,
                MetricSnapshot.metric == metric,
            )
            .order_by(MetricSnapshot.captured_date.desc())
            .limit(limit)
        )
        rows = list(self.session.execute(stmt).scalars())
        return list(reversed(rows))

    def upsert_day(
        self,
        organization_id: uuid.UUID,
        scope: str,
        scope_id: uuid.UUID | None,
        metric: str,
        value: float,
        day: date,
        actor_id: uuid.UUID | None,
    ) -> None:
        """Insert or update the value for a metric/scope on a given day."""
        stmt = self._base_query(organization_id).where(
            MetricSnapshot.scope == scope,
            MetricSnapshot.scope_id == scope_id,
            MetricSnapshot.metric == metric,
            MetricSnapshot.captured_date == day,
        )
        existing = self.session.execute(stmt).scalars().first()
        if existing is not None:
            existing.value = value
            existing.modified_by = actor_id
            self.update(existing)
            return
        self.add(
            MetricSnapshot(
                organization_id=organization_id,
                scope=scope,
                scope_id=scope_id,
                metric=metric,
                value=value,
                captured_date=day,
                created_by=actor_id,
            )
        )

    def all_project_series(
        self, organization_id: uuid.UUID, metric: str, limit: int
    ) -> dict[str, list[float]]:
        """Return ``{project_id: [values...]}`` for a project-scoped metric."""
        stmt = (
            self._base_query(organization_id)
            .where(MetricSnapshot.scope == "project", MetricSnapshot.metric == metric)
            .order_by(MetricSnapshot.captured_date.asc())
        )
        out: dict[str, list[float]] = {}
        for row in self.session.execute(stmt).scalars():
            key = str(row.scope_id)
            out.setdefault(key, []).append(float(row.value))
        return {k: v[-limit:] for k, v in out.items()}
