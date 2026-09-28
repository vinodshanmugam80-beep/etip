"""Repository for the Change Request Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.change.models import (
    ChangePriority,
    ChangeRequest,
    ChangeStatus,
    ChangeType,
)
from app.repositories.base import BaseRepository

_PENDING = (
    ChangeStatus.DRAFT,
    ChangeStatus.SUBMITTED,
    ChangeStatus.UNDER_REVIEW,
)


class ChangeRequestRepository(BaseRepository[ChangeRequest]):
    """Data access for :class:`ChangeRequest`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ChangeRequest)

    def next_number(self, project_id: uuid.UUID) -> int:
        """Return the next running change-request number within a project."""
        stmt = select(func.coalesce(func.max(ChangeRequest.number), 0)).where(
            ChangeRequest.project_id == project_id
        )
        return int(self.session.execute(stmt).scalar_one()) + 1

    def pending_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the number of not-yet-decided change requests."""
        stmt = select(func.count()).where(
            ChangeRequest.organization_id == organization_id,
            ChangeRequest.project_id == project_id,
            ChangeRequest.is_deleted.is_(False),
            ChangeRequest.status.in_(_PENDING),
        )
        return int(self.session.execute(stmt).scalar_one())

    def total_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the total number of live change requests for a project."""
        stmt = select(func.count()).where(
            ChangeRequest.organization_id == organization_id,
            ChangeRequest.project_id == project_id,
            ChangeRequest.is_deleted.is_(False),
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_by_status(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[tuple[ChangeStatus, int]]:
        """Return live change-request counts grouped by workflow state."""
        stmt = (
            select(ChangeRequest.status, func.count())
            .where(
                ChangeRequest.organization_id == organization_id,
                ChangeRequest.project_id == project_id,
                ChangeRequest.is_deleted.is_(False),
            )
            .group_by(ChangeRequest.status)
        )
        return [(row[0], int(row[1])) for row in self.session.execute(stmt).all()]

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: ChangeStatus | None,
        change_type: ChangeType | None,
        priority: ChangePriority | None,
    ) -> Select[tuple[ChangeRequest]]:
        """Build the filtered (unpaginated) change-request query."""
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(func.lower(ChangeRequest.title).like(f"%{query.lower()}%"))
        if project_id is not None:
            stmt = stmt.where(ChangeRequest.project_id == project_id)
        if status is not None:
            stmt = stmt.where(ChangeRequest.status == status)
        if change_type is not None:
            stmt = stmt.where(ChangeRequest.change_type == change_type)
        if priority is not None:
            stmt = stmt.where(ChangeRequest.priority == priority)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: ChangeStatus | None = None,
        change_type: ChangeType | None = None,
        priority: ChangePriority | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ChangeRequest]:
        """Return a filtered, paginated page of change requests."""
        stmt = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            change_type=change_type,
            priority=priority,
        )
        stmt = stmt.order_by(ChangeRequest.number.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: ChangeStatus | None = None,
        change_type: ChangeType | None = None,
        priority: ChangePriority | None = None,
    ) -> int:
        """Return the number of change requests matching the filters."""
        inner = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            change_type=change_type,
            priority=priority,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live change request of a project."""
        stmt = self._base_query(organization_id).where(ChangeRequest.project_id == project_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for cr in rows:
            cr.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
