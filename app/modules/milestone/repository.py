"""Repository for the Milestone Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.milestone.models import (
    Milestone,
    MilestoneStatus,
    MilestoneType,
)
from app.repositories.base import BaseRepository

_OPEN_STATUSES = (MilestoneStatus.PLANNED, MilestoneStatus.IN_PROGRESS)


class MilestoneRepository(BaseRepository[Milestone]):
    """Data access for :class:`Milestone`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Milestone)

    def next_number(self, project_id: uuid.UUID) -> int:
        """Return the next running milestone number within a project."""
        stmt = select(func.coalesce(func.max(Milestone.number), 0)).where(
            Milestone.project_id == project_id
        )
        return int(self.session.execute(stmt).scalar_one()) + 1

    def total_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the total number of live milestones for a project."""
        stmt = select(func.count()).where(
            Milestone.organization_id == organization_id,
            Milestone.project_id == project_id,
            Milestone.is_deleted.is_(False),
        )
        return int(self.session.execute(stmt).scalar_one())

    def key_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the number of key milestones for a project."""
        stmt = select(func.count()).where(
            Milestone.organization_id == organization_id,
            Milestone.project_id == project_id,
            Milestone.is_deleted.is_(False),
            Milestone.is_key.is_(True),
        )
        return int(self.session.execute(stmt).scalar_one())

    def overdue_count(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, as_of: date
    ) -> int:
        """Return the number of open milestones past their target date."""
        stmt = select(func.count()).where(
            Milestone.organization_id == organization_id,
            Milestone.project_id == project_id,
            Milestone.is_deleted.is_(False),
            Milestone.status.in_(_OPEN_STATUSES),
            Milestone.target_date < as_of,
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_by_status(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[tuple[MilestoneStatus, int]]:
        """Return live milestone counts grouped by lifecycle state."""
        stmt = (
            select(Milestone.status, func.count())
            .where(
                Milestone.organization_id == organization_id,
                Milestone.project_id == project_id,
                Milestone.is_deleted.is_(False),
            )
            .group_by(Milestone.status)
        )
        return [(row[0], int(row[1])) for row in self.session.execute(stmt).all()]

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: MilestoneStatus | None,
        milestone_type: MilestoneType | None,
        is_key: bool | None,
        owner_user_id: uuid.UUID | None,
    ) -> Select[tuple[Milestone]]:
        """Build the filtered (unpaginated) milestone query."""
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(func.lower(Milestone.name).like(f"%{query.lower()}%"))
        if project_id is not None:
            stmt = stmt.where(Milestone.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Milestone.status == status)
        if milestone_type is not None:
            stmt = stmt.where(Milestone.milestone_type == milestone_type)
        if is_key is not None:
            stmt = stmt.where(Milestone.is_key.is_(is_key))
        if owner_user_id is not None:
            stmt = stmt.where(Milestone.owner_user_id == owner_user_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: MilestoneStatus | None = None,
        milestone_type: MilestoneType | None = None,
        is_key: bool | None = None,
        owner_user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Milestone]:
        """Return a filtered, paginated page of milestones (by target date)."""
        stmt = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            milestone_type=milestone_type,
            is_key=is_key,
            owner_user_id=owner_user_id,
        )
        stmt = stmt.order_by(Milestone.target_date.asc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: MilestoneStatus | None = None,
        milestone_type: MilestoneType | None = None,
        is_key: bool | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> int:
        """Return the number of milestones matching the filters."""
        inner = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            milestone_type=milestone_type,
            is_key=is_key,
            owner_user_id=owner_user_id,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live milestone of a project."""
        stmt = self._base_query(organization_id).where(Milestone.project_id == project_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for milestone in rows:
            milestone.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
