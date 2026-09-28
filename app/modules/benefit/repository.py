"""Data access for Benefits Realization."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.benefit.models import Benefit, BenefitCategory, BenefitStatus
from app.repositories.base import BaseRepository


class BenefitRepository(BaseRepository[Benefit]):
    """Repository for :class:`Benefit`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Benefit)

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None,
        category: BenefitCategory | None,
        status: BenefitStatus | None,
        owner_user_id: uuid.UUID | None,
    ) -> Select[tuple[Benefit]]:
        stmt = self._base_query(organization_id)
        if project_id is not None:
            stmt = stmt.where(Benefit.project_id == project_id)
        if category is not None:
            stmt = stmt.where(Benefit.category == category)
        if status is not None:
            stmt = stmt.where(Benefit.status == status)
        if owner_user_id is not None:
            stmt = stmt.where(Benefit.owner_user_id == owner_user_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        category: BenefitCategory | None = None,
        status: BenefitStatus | None = None,
        owner_user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Benefit]:
        """Return a filtered, paginated page of benefits (newest first)."""
        stmt = self._search_stmt(
            organization_id,
            project_id=project_id,
            category=category,
            status=status,
            owner_user_id=owner_user_id,
        )
        stmt = stmt.order_by(Benefit.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        category: BenefitCategory | None = None,
        status: BenefitStatus | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> int:
        """Return the number of benefits matching the filters."""
        inner = self._search_stmt(
            organization_id,
            project_id=project_id,
            category=category,
            status=status,
            owner_user_id=owner_user_id,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def list_for_projects(
        self, organization_id: uuid.UUID, project_ids: Sequence[uuid.UUID]
    ) -> Sequence[Benefit]:
        """Return all benefits belonging to any of the given projects."""
        if not project_ids:
            return []
        stmt = self._base_query(organization_id).where(Benefit.project_id.in_(project_ids))
        return self.session.execute(stmt).scalars().all()

    def totals_for_projects(
        self, organization_id: uuid.UUID, project_ids: Sequence[uuid.UUID]
    ) -> tuple[Decimal, Decimal, Decimal, int]:
        """Return ``(target, realized, investment, count)`` for the projects."""
        if not project_ids:
            return Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), 0
        stmt = select(
            func.coalesce(func.sum(Benefit.target_value), 0),
            func.coalesce(func.sum(Benefit.realized_value), 0),
            func.coalesce(func.sum(Benefit.investment_cost), 0),
            func.count(),
        ).where(
            Benefit.organization_id == organization_id,
            Benefit.is_deleted.is_(False),
            Benefit.project_id.in_(project_ids),
        )
        target, realized, investment, count = self.session.execute(stmt).one()
        return (
            Decimal(str(target)),
            Decimal(str(realized)),
            Decimal(str(investment)),
            int(count),
        )
