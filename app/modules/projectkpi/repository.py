"""Data access for the per-project KPI register."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.projectkpi.models import ProjectKPI
from app.repositories.base import BaseRepository


class ProjectKPIRepository(BaseRepository[ProjectKPI]):
    """Repository for :class:`ProjectKPI`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ProjectKPI)

    def _for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Select[tuple[ProjectKPI]]:
        return self._base_query(organization_id).where(ProjectKPI.project_id == project_id)

    def list_for_project(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ProjectKPI]:
        """Return a project's KPIs ordered by name."""
        stmt = (
            self._for_project(organization_id, project_id)
            .order_by(ProjectKPI.name)
            .limit(limit)
            .offset(offset)
        )
        return self.session.execute(stmt).scalars().all()

    def count_for_project(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the number of KPIs on a project."""
        inner = self._for_project(organization_id, project_id).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())
