"""Data access for AI Delivery."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.aidelivery.models import (
    BuildRequest,
    BuildStatus,
    BuildTargetType,
    Deployment,
    PipelineRun,
)
from app.repositories.base import BaseRepository


class BuildRequestRepository(BaseRepository[BuildRequest]):
    """Repository for :class:`BuildRequest`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, BuildRequest)

    def _filtered(
        self,
        organization_id: uuid.UUID,
        *,
        status: BuildStatus | None,
        target_type: BuildTargetType | None,
        project_id: uuid.UUID | None,
    ) -> Select[tuple[BuildRequest]]:
        stmt = self._base_query(organization_id)
        if status is not None:
            stmt = stmt.where(BuildRequest.status == status)
        if target_type is not None:
            stmt = stmt.where(BuildRequest.target_type == target_type)
        if project_id is not None:
            stmt = stmt.where(BuildRequest.project_id == project_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        status: BuildStatus | None = None,
        target_type: BuildTargetType | None = None,
        project_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[BuildRequest]:
        """Return a filtered, paginated page of build requests (newest first)."""
        stmt = self._filtered(
            organization_id,
            status=status,
            target_type=target_type,
            project_id=project_id,
        )
        stmt = stmt.order_by(BuildRequest.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        status: BuildStatus | None = None,
        target_type: BuildTargetType | None = None,
        project_id: uuid.UUID | None = None,
    ) -> int:
        """Return the number of build requests matching the filters."""
        inner = self._filtered(
            organization_id,
            status=status,
            target_type=target_type,
            project_id=project_id,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())


class PipelineRunRepository(BaseRepository[PipelineRun]):
    """Repository for :class:`PipelineRun`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, PipelineRun)

    def list_for_build(
        self, organization_id: uuid.UUID, build_request_id: uuid.UUID
    ) -> Sequence[PipelineRun]:
        """Return a build's runs, oldest first."""
        stmt = (
            self._base_query(organization_id)
            .where(PipelineRun.build_request_id == build_request_id)
            .order_by(PipelineRun.created_date)
        )
        return self.session.execute(stmt).scalars().all()


class DeploymentRepository(BaseRepository[Deployment]):
    """Repository for :class:`Deployment`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Deployment)

    def list_for_build(
        self, organization_id: uuid.UUID, build_request_id: uuid.UUID
    ) -> Sequence[Deployment]:
        """Return a build's deployments, newest first."""
        stmt = (
            self._base_query(organization_id)
            .where(Deployment.build_request_id == build_request_id)
            .order_by(Deployment.created_date.desc())
        )
        return self.session.execute(stmt).scalars().all()
