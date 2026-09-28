"""Repository for the Sprint Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.sprint.models import Sprint, SprintStatus
from app.repositories.base import BaseRepository


class SprintRepository(BaseRepository[Sprint]):
    """Data access for :class:`Sprint`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Sprint)

    def next_number(self, project_id: uuid.UUID) -> int:
        """Return the next running sprint number within a project."""
        stmt = select(func.coalesce(func.max(Sprint.number), 0)).where(
            Sprint.project_id == project_id
        )
        return int(self.session.execute(stmt).scalar_one()) + 1

    def get_active_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Sprint | None:
        """Return the project's active sprint, if any."""
        stmt = self._base_query(organization_id).where(
            Sprint.project_id == project_id,
            Sprint.status == SprintStatus.ACTIVE,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None,
        status: SprintStatus | None,
    ) -> Select[tuple[Sprint]]:
        """Build the filtered (unpaginated) sprint query."""
        stmt = self._base_query(organization_id)
        if project_id is not None:
            stmt = stmt.where(Sprint.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Sprint.status == status)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        status: SprintStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Sprint]:
        """Return a filtered, paginated page of sprints (newest number first)."""
        stmt = self._search_stmt(organization_id, project_id=project_id, status=status)
        stmt = stmt.order_by(Sprint.number.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        status: SprintStatus | None = None,
    ) -> int:
        """Return the total number of sprints matching the filters."""
        inner = self._search_stmt(organization_id, project_id=project_id, status=status).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())
