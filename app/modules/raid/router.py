"""HTTP routes for the RAID Log module.

Thin adapters over :class:`RaidService`. Reads require ``raid:read``; create and
update require ``raid:create`` / ``raid:update`` (members hold these so they can
raise and progress actions); delete requires ``raid:delete``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import RaidServiceDep, UowDep, require_permission
from app.modules.raid.models import ActionStatus, DecisionStatus
from app.modules.raid.schemas import (
    ActionCreateRequest,
    ActionResponse,
    ActionUpdateRequest,
    DecisionCreateRequest,
    DecisionResponse,
    DecisionUpdateRequest,
    MessageResponse,
    PaginatedActions,
    PaginatedDecisions,
    RaidSummaryResponse,
)

router = APIRouter(tags=["RAID Log"])


# --- Actions ---------------------------------------------------------------
@router.post(
    "/actions",
    response_model=ActionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("raid:create"))],
    summary="Raise an action item",
)
def create_action(
    payload: ActionCreateRequest, service: RaidServiceDep, uow: UowDep
) -> ActionResponse:
    """Raise an action item against a project."""
    action = service.create_action(
        project_id=payload.project_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        owner_user_id=payload.owner_user_id,
        due_date=payload.due_date,
    )
    uow.commit()
    return ActionResponse.model_validate(action)


@router.get(
    "/actions",
    response_model=PaginatedActions,
    dependencies=[Depends(require_permission("raid:read"))],
    summary="List and search action items",
)
def list_actions(
    service: RaidServiceDep,
    q: str | None = Query(default=None, description="Search title"),
    project_id: uuid.UUID | None = Query(default=None),
    status_filter: ActionStatus | None = Query(default=None, alias="status"),
    owner_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedActions:
    """Return a filtered, paginated page of action items."""
    items, total = service.search_actions(
        query=q,
        project_id=project_id,
        status=status_filter,
        owner_user_id=owner_user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedActions(
        items=[ActionResponse.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/actions/{action_id}",
    response_model=ActionResponse,
    dependencies=[Depends(require_permission("raid:read"))],
    summary="Get an action item",
)
def get_action(action_id: uuid.UUID, service: RaidServiceDep) -> ActionResponse:
    """Return a single action item by id."""
    return ActionResponse.model_validate(service.get_action(action_id))


@router.patch(
    "/actions/{action_id}",
    response_model=ActionResponse,
    dependencies=[Depends(require_permission("raid:update"))],
    summary="Update an action item",
)
def update_action(
    action_id: uuid.UUID,
    payload: ActionUpdateRequest,
    service: RaidServiceDep,
    uow: UowDep,
) -> ActionResponse:
    """Apply a partial update, including a validated status transition."""
    action = service.update_action(
        action_id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        priority=payload.priority,
        owner_user_id=payload.owner_user_id,
        due_date=payload.due_date,
    )
    uow.commit()
    return ActionResponse.model_validate(action)


@router.delete(
    "/actions/{action_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("raid:delete"))],
    summary="Delete an action item",
)
def delete_action(action_id: uuid.UUID, service: RaidServiceDep, uow: UowDep) -> MessageResponse:
    """Soft-delete an action item."""
    service.delete_action(action_id)
    uow.commit()
    return MessageResponse(detail="Action deleted.")


# --- Decisions -------------------------------------------------------------
@router.post(
    "/decisions",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("raid:create"))],
    summary="Log a decision",
)
def create_decision(
    payload: DecisionCreateRequest, service: RaidServiceDep, uow: UowDep
) -> DecisionResponse:
    """Log a decision against a project."""
    decision = service.create_decision(
        project_id=payload.project_id,
        title=payload.title,
        description=payload.description,
        rationale=payload.rationale,
        decided_by_user_id=payload.decided_by_user_id,
    )
    uow.commit()
    return DecisionResponse.model_validate(decision)


@router.get(
    "/decisions",
    response_model=PaginatedDecisions,
    dependencies=[Depends(require_permission("raid:read"))],
    summary="List and search decisions",
)
def list_decisions(
    service: RaidServiceDep,
    q: str | None = Query(default=None, description="Search title"),
    project_id: uuid.UUID | None = Query(default=None),
    status_filter: DecisionStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedDecisions:
    """Return a filtered, paginated page of decisions."""
    items, total = service.search_decisions(
        query=q,
        project_id=project_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return PaginatedDecisions(
        items=[DecisionResponse.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/decisions/{decision_id}",
    response_model=DecisionResponse,
    dependencies=[Depends(require_permission("raid:read"))],
    summary="Get a decision",
)
def get_decision(decision_id: uuid.UUID, service: RaidServiceDep) -> DecisionResponse:
    """Return a single decision by id."""
    return DecisionResponse.model_validate(service.get_decision(decision_id))


@router.patch(
    "/decisions/{decision_id}",
    response_model=DecisionResponse,
    dependencies=[Depends(require_permission("raid:update"))],
    summary="Update a decision",
)
def update_decision(
    decision_id: uuid.UUID,
    payload: DecisionUpdateRequest,
    service: RaidServiceDep,
    uow: UowDep,
) -> DecisionResponse:
    """Apply a partial update, including a validated status transition."""
    decision = service.update_decision(
        decision_id,
        title=payload.title,
        description=payload.description,
        rationale=payload.rationale,
        status=payload.status,
        decided_by_user_id=payload.decided_by_user_id,
    )
    uow.commit()
    return DecisionResponse.model_validate(decision)


@router.delete(
    "/decisions/{decision_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("raid:delete"))],
    summary="Delete a decision",
)
def delete_decision(
    decision_id: uuid.UUID, service: RaidServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a decision."""
    service.delete_decision(decision_id)
    uow.commit()
    return MessageResponse(detail="Decision deleted.")


# --- Consolidated summary --------------------------------------------------
@router.get(
    "/projects/{project_id}/raid",
    response_model=RaidSummaryResponse,
    dependencies=[Depends(require_permission("raid:read"))],
    summary="Get a project's consolidated RAID summary",
)
def get_raid_summary(project_id: uuid.UUID, service: RaidServiceDep) -> RaidSummaryResponse:
    """Return open/total counts across risks, actions, issues and decisions."""
    return service.get_summary(project_id)
