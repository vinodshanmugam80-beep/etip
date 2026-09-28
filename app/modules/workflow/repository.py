"""Data access for the Stage-Gate / Workflow / Approval engine."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.workflow.models import (
    GateApproval,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStage,
    WorkflowStatus,
)
from app.repositories.base import BaseRepository


class WorkflowDefinitionRepository(BaseRepository[WorkflowDefinition]):
    """Repository for :class:`WorkflowDefinition`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WorkflowDefinition)

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[WorkflowDefinition]:
        """Return a filtered, paginated page of definitions."""
        stmt = self._filtered(organization_id, entity_type, is_active)
        stmt = stmt.order_by(WorkflowDefinition.name).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        """Return the number of definitions matching the filters."""
        inner = self._filtered(organization_id, entity_type, is_active).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def _filtered(
        self,
        organization_id: uuid.UUID,
        entity_type: str | None,
        is_active: bool | None,
    ) -> Select[tuple[WorkflowDefinition]]:
        stmt = self._base_query(organization_id)
        if entity_type is not None:
            stmt = stmt.where(WorkflowDefinition.entity_type == entity_type)
        if is_active is not None:
            stmt = stmt.where(WorkflowDefinition.is_active.is_(is_active))
        return stmt


class WorkflowStageRepository(BaseRepository[WorkflowStage]):
    """Repository for :class:`WorkflowStage`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WorkflowStage)

    def list_for_definition(
        self, organization_id: uuid.UUID, definition_id: uuid.UUID
    ) -> Sequence[WorkflowStage]:
        """Return a definition's stages ordered by sequence."""
        stmt = (
            self._base_query(organization_id)
            .where(WorkflowStage.definition_id == definition_id)
            .order_by(WorkflowStage.sequence)
        )
        return self.session.execute(stmt).scalars().all()


class WorkflowInstanceRepository(BaseRepository[WorkflowInstance]):
    """Repository for :class:`WorkflowInstance`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WorkflowInstance)

    def _filtered(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        status: WorkflowStatus | None,
        definition_id: uuid.UUID | None,
    ) -> Select[tuple[WorkflowInstance]]:
        stmt = self._base_query(organization_id)
        if entity_type is not None:
            stmt = stmt.where(WorkflowInstance.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(WorkflowInstance.entity_id == entity_id)
        if status is not None:
            stmt = stmt.where(WorkflowInstance.status == status)
        if definition_id is not None:
            stmt = stmt.where(WorkflowInstance.definition_id == definition_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        status: WorkflowStatus | None = None,
        definition_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[WorkflowInstance]:
        """Return a filtered, paginated page of instances (newest first)."""
        stmt = self._filtered(
            organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            definition_id=definition_id,
        )
        stmt = stmt.order_by(WorkflowInstance.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        status: WorkflowStatus | None = None,
        definition_id: uuid.UUID | None = None,
    ) -> int:
        """Return the number of instances matching the filters."""
        inner = self._filtered(
            organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            definition_id=definition_id,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())


class GateApprovalRepository(BaseRepository[GateApproval]):
    """Repository for :class:`GateApproval`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, GateApproval)

    def list_for_instance(
        self, organization_id: uuid.UUID, instance_id: uuid.UUID
    ) -> Sequence[GateApproval]:
        """Return an instance's decisions, oldest first."""
        stmt = (
            self._base_query(organization_id)
            .where(GateApproval.instance_id == instance_id)
            .order_by(GateApproval.created_date)
        )
        return self.session.execute(stmt).scalars().all()
