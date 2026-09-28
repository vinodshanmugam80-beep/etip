"""HTTP routes for the Stage-Gate / Workflow / Approval engine.

Reads require ``workflow:read``; managing definitions and running instances
requires ``workflow:manage``; recording gate decisions requires
``workflow:approve``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import UowDep, WorkflowServiceDep, require_permission
from app.modules.workflow.models import WorkflowStatus
from app.modules.workflow.schemas import (
    GateApprovalResponse,
    GovernanceOverview,
    PaginatedWorkflowDefinitions,
    PaginatedWorkflowInstances,
    WorkflowDecisionRequest,
    WorkflowDefinitionCreateRequest,
    WorkflowDefinitionResponse,
    WorkflowDefinitionUpdateRequest,
    WorkflowInstanceResponse,
    WorkflowInstanceStartRequest,
    WorkflowStageCreateRequest,
    WorkflowStageResponse,
    WorkflowStageUpdateRequest,
)

router = APIRouter(prefix="/workflows", tags=["Workflows"])
_READ = Depends(require_permission("workflow:read"))
_MANAGE = Depends(require_permission("workflow:manage"))
_APPROVE = Depends(require_permission("workflow:approve"))


# --- Definitions -----------------------------------------------------------
@router.post(
    "",
    response_model=WorkflowDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Create a workflow definition",
)
def create_definition(
    payload: WorkflowDefinitionCreateRequest, service: WorkflowServiceDep, uow: UowDep
) -> WorkflowDefinitionResponse:
    """Create a workflow definition."""
    definition = service.create_definition(payload)
    uow.commit()
    return WorkflowDefinitionResponse.model_validate(definition)


@router.get(
    "",
    response_model=PaginatedWorkflowDefinitions,
    dependencies=[_READ],
    summary="Search workflow definitions",
)
def list_definitions(
    service: WorkflowServiceDep,
    entity_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedWorkflowDefinitions:
    """Return a filtered, paginated page of definitions."""
    items, total = service.search_definitions(
        entity_type=entity_type, is_active=is_active, limit=limit, offset=offset
    )
    return PaginatedWorkflowDefinitions(
        items=[WorkflowDefinitionResponse.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# --- Governance overview (literal routes before /{definition_id}) ----------
@router.get(
    "/governance",
    response_model=GovernanceOverview,
    dependencies=[_READ],
    summary="SDLC stage-gate governance overview",
)
def governance_overview(
    service: WorkflowServiceDep, limit: int = Query(100, ge=1, le=500)
) -> GovernanceOverview:
    """Return per-subject SDLC gate approvals plus a portfolio roll-up."""
    return service.governance_overview(limit=limit)


@router.post(
    "/setup-sdlc",
    response_model=WorkflowDefinitionResponse,
    dependencies=[_MANAGE],
    summary="Create (or return) the canonical SDLC stage-gate definition",
)
def setup_sdlc(service: WorkflowServiceDep, uow: UowDep) -> WorkflowDefinitionResponse:
    """Idempotently ensure the standard SDLC stage-gate workflow exists."""
    definition = service.ensure_sdlc_definition()
    uow.commit()
    return WorkflowDefinitionResponse.model_validate(definition)


# --- Instances (literal routes before /{definition_id}) --------------------
@router.post(
    "/instances",
    response_model=WorkflowInstanceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Start a workflow instance",
)
def start_instance(
    payload: WorkflowInstanceStartRequest, service: WorkflowServiceDep, uow: UowDep
) -> WorkflowInstanceResponse:
    """Start a workflow instance against a subject."""
    instance = service.start_instance(payload)
    uow.commit()
    return WorkflowInstanceResponse.model_validate(instance)


@router.get(
    "/instances",
    response_model=PaginatedWorkflowInstances,
    dependencies=[_READ],
    summary="Search workflow instances",
)
def list_instances(
    service: WorkflowServiceDep,
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    instance_status: WorkflowStatus | None = Query(default=None, alias="status"),
    definition_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedWorkflowInstances:
    """Return a filtered, paginated page of instances."""
    items, total = service.search_instances(
        entity_type=entity_type,
        entity_id=entity_id,
        status=instance_status,
        definition_id=definition_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedWorkflowInstances(
        items=[WorkflowInstanceResponse.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/instances/{instance_id}",
    response_model=WorkflowInstanceResponse,
    dependencies=[_READ],
    summary="Get a workflow instance",
)
def get_instance(instance_id: uuid.UUID, service: WorkflowServiceDep) -> WorkflowInstanceResponse:
    """Return a single workflow instance."""
    return WorkflowInstanceResponse.model_validate(service.get_instance(instance_id))


@router.post(
    "/instances/{instance_id}/advance",
    response_model=WorkflowInstanceResponse,
    dependencies=[_MANAGE],
    summary="Advance past a non-approval stage",
)
def advance_instance(
    instance_id: uuid.UUID, service: WorkflowServiceDep, uow: UowDep
) -> WorkflowInstanceResponse:
    """Advance an instance past a stage that does not require approval."""
    instance = service.advance_instance(instance_id)
    uow.commit()
    return WorkflowInstanceResponse.model_validate(instance)


@router.post(
    "/instances/{instance_id}/decision",
    response_model=WorkflowInstanceResponse,
    dependencies=[_APPROVE],
    summary="Record a gate decision",
)
def record_decision(
    instance_id: uuid.UUID,
    payload: WorkflowDecisionRequest,
    service: WorkflowServiceDep,
    uow: UowDep,
) -> WorkflowInstanceResponse:
    """Record an approve/reject decision at an approval gate."""
    instance = service.record_decision(instance_id, payload)
    uow.commit()
    return WorkflowInstanceResponse.model_validate(instance)


@router.post(
    "/instances/{instance_id}/cancel",
    response_model=WorkflowInstanceResponse,
    dependencies=[_MANAGE],
    summary="Cancel a workflow instance",
)
def cancel_instance(
    instance_id: uuid.UUID, service: WorkflowServiceDep, uow: UowDep
) -> WorkflowInstanceResponse:
    """Cancel an in-progress instance."""
    instance = service.cancel_instance(instance_id)
    uow.commit()
    return WorkflowInstanceResponse.model_validate(instance)


@router.get(
    "/instances/{instance_id}/approvals",
    response_model=list[GateApprovalResponse],
    dependencies=[_READ],
    summary="Gate decision history",
)
def list_approvals(
    instance_id: uuid.UUID, service: WorkflowServiceDep
) -> list[GateApprovalResponse]:
    """Return an instance's decision history."""
    return [GateApprovalResponse.model_validate(a) for a in service.list_approvals(instance_id)]


# --- Single definition + stages --------------------------------------------
@router.get(
    "/{definition_id}",
    response_model=WorkflowDefinitionResponse,
    dependencies=[_READ],
    summary="Get a workflow definition",
)
def get_definition(
    definition_id: uuid.UUID, service: WorkflowServiceDep
) -> WorkflowDefinitionResponse:
    """Return a single workflow definition."""
    return WorkflowDefinitionResponse.model_validate(service.get_definition(definition_id))


@router.patch(
    "/{definition_id}",
    response_model=WorkflowDefinitionResponse,
    dependencies=[_MANAGE],
    summary="Update a workflow definition",
)
def update_definition(
    definition_id: uuid.UUID,
    payload: WorkflowDefinitionUpdateRequest,
    service: WorkflowServiceDep,
    uow: UowDep,
) -> WorkflowDefinitionResponse:
    """Update a workflow definition."""
    definition = service.update_definition(definition_id, payload)
    uow.commit()
    return WorkflowDefinitionResponse.model_validate(definition)


@router.delete(
    "/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_MANAGE],
    summary="Delete a workflow definition",
)
def delete_definition(definition_id: uuid.UUID, service: WorkflowServiceDep, uow: UowDep) -> None:
    """Soft-delete a definition and its stages and instances."""
    service.delete_definition(definition_id)
    uow.commit()


@router.post(
    "/{definition_id}/stages",
    response_model=WorkflowStageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Add a stage",
)
def add_stage(
    definition_id: uuid.UUID,
    payload: WorkflowStageCreateRequest,
    service: WorkflowServiceDep,
    uow: UowDep,
) -> WorkflowStageResponse:
    """Add an ordered stage to a definition."""
    stage = service.add_stage(definition_id, payload)
    uow.commit()
    return WorkflowStageResponse.model_validate(stage)


@router.get(
    "/{definition_id}/stages",
    response_model=list[WorkflowStageResponse],
    dependencies=[_READ],
    summary="List stages",
)
def list_stages(
    definition_id: uuid.UUID, service: WorkflowServiceDep
) -> list[WorkflowStageResponse]:
    """Return a definition's stages, ordered by sequence."""
    return [WorkflowStageResponse.model_validate(s) for s in service.list_stages(definition_id)]


@router.patch(
    "/stages/{stage_id}",
    response_model=WorkflowStageResponse,
    dependencies=[_MANAGE],
    summary="Update a stage",
)
def update_stage(
    stage_id: uuid.UUID,
    payload: WorkflowStageUpdateRequest,
    service: WorkflowServiceDep,
    uow: UowDep,
) -> WorkflowStageResponse:
    """Update a stage."""
    stage = service.update_stage(stage_id, payload)
    uow.commit()
    return WorkflowStageResponse.model_validate(stage)


@router.delete(
    "/stages/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_MANAGE],
    summary="Delete a stage",
)
def delete_stage(stage_id: uuid.UUID, service: WorkflowServiceDep, uow: UowDep) -> None:
    """Soft-delete a stage."""
    service.delete_stage(stage_id)
    uow.commit()
