"""Repositories for the RAID Log aggregates (actions and decisions)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.raid.models import (
    Action,
    ActionStatus,
    Decision,
    DecisionStatus,
)
from app.repositories.base import BaseRepository


class ActionRepository(BaseRepository[Action]):
    """Data access for :class:`Action`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Action)

    def next_number(self, project_id: uuid.UUID) -> int:
        """Return the next running action number within a project."""
        stmt = select(func.coalesce(func.max(Action.number), 0)).where(
            Action.project_id == project_id
        )
        return int(self.session.execute(stmt).scalar_one()) + 1

    def open_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the number of open/in-progress actions for a project."""
        stmt = select(func.count()).where(
            Action.organization_id == organization_id,
            Action.project_id == project_id,
            Action.is_deleted.is_(False),
            Action.status.in_((ActionStatus.OPEN, ActionStatus.IN_PROGRESS)),
        )
        return int(self.session.execute(stmt).scalar_one())

    def total_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the total number of live actions for a project."""
        stmt = select(func.count()).where(
            Action.organization_id == organization_id,
            Action.project_id == project_id,
            Action.is_deleted.is_(False),
        )
        return int(self.session.execute(stmt).scalar_one())

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: ActionStatus | None = None,
        owner_user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Action]:
        """Return a filtered, paginated page of actions."""
        stmt = self._filtered(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            owner_user_id=owner_user_id,
        )
        stmt = stmt.order_by(Action.number.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: ActionStatus | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> int:
        """Return the number of actions matching the filters."""
        inner = self._filtered(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            owner_user_id=owner_user_id,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def _filtered(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: ActionStatus | None,
        owner_user_id: uuid.UUID | None,
    ) -> Select[tuple[Action]]:
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(func.lower(Action.title).like(f"%{query.lower()}%"))
        if project_id is not None:
            stmt = stmt.where(Action.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Action.status == status)
        if owner_user_id is not None:
            stmt = stmt.where(Action.owner_user_id == owner_user_id)
        return stmt

    def list_by_meeting(
        self, organization_id: uuid.UUID, meeting_id: uuid.UUID
    ) -> Sequence[Action]:
        """Return live actions raised in a given meeting (newest number first)."""
        stmt = (
            self._base_query(organization_id)
            .where(Action.source_meeting_id == meeting_id)
            .order_by(Action.number.desc())
        )
        return self.session.execute(stmt).scalars().all()

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live action of a project."""
        stmt = self._base_query(organization_id).where(Action.project_id == project_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for action in rows:
            action.soft_delete(actor_id)
        self.session.flush()
        return len(rows)


class DecisionRepository(BaseRepository[Decision]):
    """Data access for :class:`Decision`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Decision)

    def next_number(self, project_id: uuid.UUID) -> int:
        """Return the next running decision number within a project."""
        stmt = select(func.coalesce(func.max(Decision.number), 0)).where(
            Decision.project_id == project_id
        )
        return int(self.session.execute(stmt).scalar_one()) + 1

    def open_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the number of still-proposed decisions for a project."""
        stmt = select(func.count()).where(
            Decision.organization_id == organization_id,
            Decision.project_id == project_id,
            Decision.is_deleted.is_(False),
            Decision.status == DecisionStatus.PROPOSED,
        )
        return int(self.session.execute(stmt).scalar_one())

    def total_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the total number of live decisions for a project."""
        stmt = select(func.count()).where(
            Decision.organization_id == organization_id,
            Decision.project_id == project_id,
            Decision.is_deleted.is_(False),
        )
        return int(self.session.execute(stmt).scalar_one())

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: DecisionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Decision]:
        """Return a filtered, paginated page of decisions."""
        stmt = self._filtered(organization_id, query=query, project_id=project_id, status=status)
        stmt = stmt.order_by(Decision.number.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: DecisionStatus | None = None,
    ) -> int:
        """Return the number of decisions matching the filters."""
        inner = self._filtered(
            organization_id, query=query, project_id=project_id, status=status
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def _filtered(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: DecisionStatus | None,
    ) -> Select[tuple[Decision]]:
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(func.lower(Decision.title).like(f"%{query.lower()}%"))
        if project_id is not None:
            stmt = stmt.where(Decision.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Decision.status == status)
        return stmt

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live decision of a project."""
        stmt = self._base_query(organization_id).where(Decision.project_id == project_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for decision in rows:
            decision.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
