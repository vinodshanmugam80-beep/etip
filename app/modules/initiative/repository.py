"""Data access for Strategic Initiatives, Business Goals and KPIs."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.initiative.models import (
    BusinessGoal,
    GoalKPI,
    InitiativeStatus,
    StrategicInitiative,
)
from app.repositories.base import BaseRepository


class InitiativeRepository(BaseRepository[StrategicInitiative]):
    """Repository for :class:`StrategicInitiative`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, StrategicInitiative)

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        status: InitiativeStatus | None,
        portfolio_id: uuid.UUID | None,
    ) -> Select[tuple[StrategicInitiative]]:
        stmt = self._base_query(organization_id)
        if status is not None:
            stmt = stmt.where(StrategicInitiative.status == status)
        if portfolio_id is not None:
            stmt = stmt.where(StrategicInitiative.portfolio_id == portfolio_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        status: InitiativeStatus | None = None,
        portfolio_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[StrategicInitiative]:
        """Return a filtered, paginated page of initiatives (newest first)."""
        stmt = self._search_stmt(organization_id, status=status, portfolio_id=portfolio_id)
        stmt = stmt.order_by(StrategicInitiative.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        status: InitiativeStatus | None = None,
        portfolio_id: uuid.UUID | None = None,
    ) -> int:
        """Return the number of initiatives matching the filters."""
        inner = self._search_stmt(
            organization_id, status=status, portfolio_id=portfolio_id
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())


class GoalRepository(BaseRepository[BusinessGoal]):
    """Repository for :class:`BusinessGoal`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, BusinessGoal)

    def list_for_initiative(
        self, organization_id: uuid.UUID, initiative_id: uuid.UUID
    ) -> Sequence[BusinessGoal]:
        """Return all goals under an initiative."""
        stmt = self._base_query(organization_id).where(BusinessGoal.initiative_id == initiative_id)
        return self.session.execute(stmt).scalars().all()


class GoalKPIRepository(BaseRepository[GoalKPI]):
    """Repository for :class:`GoalKPI`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, GoalKPI)

    def list_for_goal(self, organization_id: uuid.UUID, goal_id: uuid.UUID) -> Sequence[GoalKPI]:
        """Return all KPIs under a goal."""
        stmt = self._base_query(organization_id).where(GoalKPI.goal_id == goal_id)
        return self.session.execute(stmt).scalars().all()

    def list_for_goals(
        self, organization_id: uuid.UUID, goal_ids: Sequence[uuid.UUID]
    ) -> Sequence[GoalKPI]:
        """Return all KPIs under any of the given goals."""
        if not goal_ids:
            return []
        stmt = self._base_query(organization_id).where(GoalKPI.goal_id.in_(goal_ids))
        return self.session.execute(stmt).scalars().all()

    def list_all(self, organization_id: uuid.UUID) -> Sequence[GoalKPI]:
        """Return every KPI for the tenant."""
        return self.session.execute(self._base_query(organization_id)).scalars().all()
