"""Repository for the Risk Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.risk.models import (
    Risk,
    RiskCategory,
    RiskSeverity,
    RiskStatus,
)
from app.repositories.base import BaseRepository


class RiskRepository(BaseRepository[Risk]):
    """Data access for :class:`Risk`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Risk)

    def next_number(self, project_id: uuid.UUID) -> int:
        """Return the next running risk number within a project."""
        stmt = select(func.coalesce(func.max(Risk.number), 0)).where(Risk.project_id == project_id)
        return int(self.session.execute(stmt).scalar_one()) + 1

    def max_open_score(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the highest score among non-closed risks (0 if none)."""
        stmt = select(func.coalesce(func.max(Risk.risk_score), 0)).where(
            Risk.organization_id == organization_id,
            Risk.project_id == project_id,
            Risk.is_deleted.is_(False),
            Risk.status != RiskStatus.CLOSED,
        )
        return int(self.session.execute(stmt).scalar_one())

    def open_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the number of non-closed risks for a project."""
        stmt = select(func.count()).where(
            Risk.organization_id == organization_id,
            Risk.project_id == project_id,
            Risk.is_deleted.is_(False),
            Risk.status != RiskStatus.CLOSED,
        )
        return int(self.session.execute(stmt).scalar_one())

    def open_by_severity(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[tuple[RiskSeverity, int]]:
        """Return counts of non-closed risks grouped by severity."""
        stmt = (
            select(Risk.severity, func.count())
            .where(
                Risk.organization_id == organization_id,
                Risk.project_id == project_id,
                Risk.is_deleted.is_(False),
                Risk.status != RiskStatus.CLOSED,
            )
            .group_by(Risk.severity)
        )
        return [(row[0], int(row[1])) for row in self.session.execute(stmt).all()]

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: RiskStatus | None,
        category: RiskCategory | None,
        severity: RiskSeverity | None,
        owner_user_id: uuid.UUID | None,
    ) -> Select[tuple[Risk]]:
        """Build the filtered (unpaginated) risk query."""
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(func.lower(Risk.title).like(f"%{query.lower()}%"))
        if project_id is not None:
            stmt = stmt.where(Risk.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Risk.status == status)
        if category is not None:
            stmt = stmt.where(Risk.category == category)
        if severity is not None:
            stmt = stmt.where(Risk.severity == severity)
        if owner_user_id is not None:
            stmt = stmt.where(Risk.owner_user_id == owner_user_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: RiskStatus | None = None,
        category: RiskCategory | None = None,
        severity: RiskSeverity | None = None,
        owner_user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Risk]:
        """Return a filtered, paginated page of risks (highest score first)."""
        stmt = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            category=category,
            severity=severity,
            owner_user_id=owner_user_id,
        )
        stmt = stmt.order_by(Risk.risk_score.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: RiskStatus | None = None,
        category: RiskCategory | None = None,
        severity: RiskSeverity | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> int:
        """Return the total number of risks matching the filters."""
        inner = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            category=category,
            severity=severity,
            owner_user_id=owner_user_id,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live risk of a project."""
        stmt = self._base_query(organization_id).where(Risk.project_id == project_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for risk in rows:
            risk.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
