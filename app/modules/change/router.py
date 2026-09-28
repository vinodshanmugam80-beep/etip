"""HTTP routes for the Change Request Management module.

Thin adapters over :class:`ChangeRequestService`. Reads require ``change:read``;
create/edit require ``change:create`` / ``change:update``; **approving and
rejecting require the separate ``change:approve`` permission**; delete requires
``change:delete``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import ChangeServiceDep, UowDep, require_permission
from app.modules.change.models import ChangePriority, ChangeStatus, ChangeType
from app.modules.change.schemas import (
    ChangeDecisionRequest,
    ChangeRequestCreateRequest,
    ChangeRequestResponse,
    ChangeRequestUpdateRequest,
    ChangeSummaryResponse,
    MessageResponse,
    PaginatedChangeRequests,
)

router = APIRouter(tags=["Change Request Management"])


@router.post(
    "/change-requests",
    response_model=ChangeRequestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("change:create"))],
    summary="Raise a change request",
)
def create_change_request(
    payload: ChangeRequestCreateRequest, service: ChangeServiceDep, uow: UowDep
) -> ChangeRequestResponse:
    """Raise a change request against a project."""
    change = service.create_change_request(
        project_id=payload.project_id,
        title=payload.title,
        description=payload.description,
        reason=payload.reason,
        change_type=payload.change_type,
        priority=payload.priority,
        schedule_impact_days=payload.schedule_impact_days,
        cost_impact=payload.cost_impact,
        impact_summary=payload.impact_summary,
        approver_user_id=payload.approver_user_id,
        target_date=payload.target_date,
    )
    uow.commit()
    return ChangeRequestResponse.model_validate(change)


@router.get(
    "/change-requests",
    response_model=PaginatedChangeRequests,
    dependencies=[Depends(require_permission("change:read"))],
    summary="List and search change requests",
)
def list_change_requests(
    service: ChangeServiceDep,
    q: str | None = Query(default=None, description="Search title"),
    project_id: uuid.UUID | None = Query(default=None),
    status_filter: ChangeStatus | None = Query(default=None, alias="status"),
    change_type: ChangeType | None = Query(default=None),
    priority: ChangePriority | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedChangeRequests:
    """Return a filtered, paginated page of change requests."""
    items, total = service.search_change_requests(
        query=q,
        project_id=project_id,
        status=status_filter,
        change_type=change_type,
        priority=priority,
        limit=limit,
        offset=offset,
    )
    return PaginatedChangeRequests(
        items=[ChangeRequestResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/change-requests/{change_id}",
    response_model=ChangeRequestResponse,
    dependencies=[Depends(require_permission("change:read"))],
    summary="Get a change request",
)
def get_change_request(change_id: uuid.UUID, service: ChangeServiceDep) -> ChangeRequestResponse:
    """Return a single change request by id."""
    return ChangeRequestResponse.model_validate(service.get_change_request(change_id))


@router.patch(
    "/change-requests/{change_id}",
    response_model=ChangeRequestResponse,
    dependencies=[Depends(require_permission("change:update"))],
    summary="Update a change request",
)
def update_change_request(
    change_id: uuid.UUID,
    payload: ChangeRequestUpdateRequest,
    service: ChangeServiceDep,
    uow: UowDep,
) -> ChangeRequestResponse:
    """Apply a partial update and non-decision status transitions."""
    change = service.update_change_request(
        change_id,
        title=payload.title,
        description=payload.description,
        reason=payload.reason,
        change_type=payload.change_type,
        priority=payload.priority,
        status=payload.status,
        schedule_impact_days=payload.schedule_impact_days,
        cost_impact=payload.cost_impact,
        impact_summary=payload.impact_summary,
        approver_user_id=payload.approver_user_id,
        target_date=payload.target_date,
    )
    uow.commit()
    return ChangeRequestResponse.model_validate(change)


@router.post(
    "/change-requests/{change_id}/approve",
    response_model=ChangeRequestResponse,
    dependencies=[Depends(require_permission("change:approve"))],
    summary="Approve a change request",
)
def approve_change_request(
    change_id: uuid.UUID,
    payload: ChangeDecisionRequest,
    service: ChangeServiceDep,
    uow: UowDep,
) -> ChangeRequestResponse:
    """Approve a change request (requires change:approve)."""
    change = service.approve(change_id, decision_notes=payload.decision_notes)
    uow.commit()
    return ChangeRequestResponse.model_validate(change)


@router.post(
    "/change-requests/{change_id}/reject",
    response_model=ChangeRequestResponse,
    dependencies=[Depends(require_permission("change:approve"))],
    summary="Reject a change request",
)
def reject_change_request(
    change_id: uuid.UUID,
    payload: ChangeDecisionRequest,
    service: ChangeServiceDep,
    uow: UowDep,
) -> ChangeRequestResponse:
    """Reject a change request (requires change:approve)."""
    change = service.reject(change_id, decision_notes=payload.decision_notes)
    uow.commit()
    return ChangeRequestResponse.model_validate(change)


@router.delete(
    "/change-requests/{change_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("change:delete"))],
    summary="Delete a change request",
)
def delete_change_request(
    change_id: uuid.UUID, service: ChangeServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a change request."""
    service.delete_change_request(change_id)
    uow.commit()
    return MessageResponse(detail="Change request deleted.")


@router.get(
    "/projects/{project_id}/change-summary",
    response_model=ChangeSummaryResponse,
    dependencies=[Depends(require_permission("change:read"))],
    summary="Get a project's change-control summary",
)
def get_summary(project_id: uuid.UUID, service: ChangeServiceDep) -> ChangeSummaryResponse:
    """Return the aggregated change-control position of a project."""
    return service.get_summary(project_id)
