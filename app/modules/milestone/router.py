"""HTTP routes for the Milestone Management module.

Thin adapters over :class:`MilestoneService`. Reads require ``milestone:read``;
mutations require the corresponding ``milestone:*`` permission. Responses carry a
derived ``is_overdue`` flag computed against today's date.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import MilestoneServiceDep, UowDep, require_permission
from app.db.base import utcnow
from app.modules.milestone.models import Milestone, MilestoneStatus, MilestoneType
from app.modules.milestone.schemas import (
    FinancialMilestoneOverview,
    MessageResponse,
    MilestoneCreateRequest,
    MilestoneResponse,
    MilestoneSummaryResponse,
    MilestoneUpdateRequest,
    PaginatedMilestones,
)
from app.modules.milestone.service import milestone_is_overdue

router = APIRouter(tags=["Milestone Management"])


def _to_response(milestone: Milestone) -> MilestoneResponse:
    """Build a response, computing the derived ``is_overdue`` flag."""
    response = MilestoneResponse.model_validate(milestone)
    response.is_overdue = milestone_is_overdue(milestone, utcnow().date())
    return response


@router.post(
    "/milestones",
    response_model=MilestoneResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("milestone:create"))],
    summary="Create a milestone",
)
def create_milestone(
    payload: MilestoneCreateRequest, service: MilestoneServiceDep, uow: UowDep
) -> MilestoneResponse:
    """Create a milestone on a project."""
    milestone = service.create_milestone(
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
        milestone_type=payload.milestone_type,
        target_date=payload.target_date,
        owner_user_id=payload.owner_user_id,
        task_id=payload.task_id,
        is_key=payload.is_key,
        deliverable=payload.deliverable,
        payment_amount=payload.payment_amount,
        currency=payload.currency,
    )
    uow.commit()
    return _to_response(milestone)


@router.get(
    "/milestones",
    response_model=PaginatedMilestones,
    dependencies=[Depends(require_permission("milestone:read"))],
    summary="List and search milestones",
)
def list_milestones(
    service: MilestoneServiceDep,
    q: str | None = Query(default=None, description="Search name"),
    project_id: uuid.UUID | None = Query(default=None),
    status_filter: MilestoneStatus | None = Query(default=None, alias="status"),
    milestone_type: MilestoneType | None = Query(default=None),
    is_key: bool | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedMilestones:
    """Return a filtered, paginated page of milestones (by target date)."""
    items, total = service.search_milestones(
        query=q,
        project_id=project_id,
        status=status_filter,
        milestone_type=milestone_type,
        is_key=is_key,
        owner_user_id=owner_user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedMilestones(
        items=[_to_response(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/milestones/financial",
    response_model=FinancialMilestoneOverview,
    dependencies=[Depends(require_permission("milestone:read"))],
    summary="Financial milestones & deliverable-acceptance overview",
)
def financial_overview(service: MilestoneServiceDep) -> FinancialMilestoneOverview:
    """Return billing milestones with their deliverable-acceptance + payment state."""
    return service.financial_overview()


@router.get(
    "/milestones/{milestone_id}",
    response_model=MilestoneResponse,
    dependencies=[Depends(require_permission("milestone:read"))],
    summary="Get a milestone",
)
def get_milestone(milestone_id: uuid.UUID, service: MilestoneServiceDep) -> MilestoneResponse:
    """Return a single milestone by id."""
    return _to_response(service.get_milestone(milestone_id))


@router.post(
    "/milestones/{milestone_id}/submit-for-acceptance",
    response_model=MilestoneResponse,
    dependencies=[Depends(require_permission("milestone:update"))],
    summary="Submit a deliverable for acceptance (opens the gate)",
)
def submit_for_acceptance(
    milestone_id: uuid.UUID, service: MilestoneServiceDep, uow: UowDep
) -> MilestoneResponse:
    """Open the deliverable-acceptance gate for a financial milestone."""
    milestone = service.submit_for_acceptance(milestone_id)
    uow.commit()
    return _to_response(milestone)


@router.post(
    "/milestones/{milestone_id}/release-payment",
    response_model=MilestoneResponse,
    dependencies=[Depends(require_permission("milestone:accept"))],
    summary="Release the milestone payment once the deliverable is accepted",
)
def release_payment(
    milestone_id: uuid.UUID, service: MilestoneServiceDep, uow: UowDep
) -> MilestoneResponse:
    """Post the payment to the project ledger after the acceptance gate completes."""
    milestone = service.release_payment(milestone_id)
    uow.commit()
    return _to_response(milestone)


@router.patch(
    "/milestones/{milestone_id}",
    response_model=MilestoneResponse,
    dependencies=[Depends(require_permission("milestone:update"))],
    summary="Update a milestone",
)
def update_milestone(
    milestone_id: uuid.UUID,
    payload: MilestoneUpdateRequest,
    service: MilestoneServiceDep,
    uow: UowDep,
) -> MilestoneResponse:
    """Apply a partial update, including a validated status transition."""
    milestone = service.update_milestone(
        milestone_id,
        name=payload.name,
        description=payload.description,
        milestone_type=payload.milestone_type,
        status=payload.status,
        target_date=payload.target_date,
        actual_date=payload.actual_date,
        owner_user_id=payload.owner_user_id,
        task_id=payload.task_id,
        is_key=payload.is_key,
        deliverable=payload.deliverable,
        payment_amount=payload.payment_amount,
        currency=payload.currency,
    )
    uow.commit()
    return _to_response(milestone)


@router.delete(
    "/milestones/{milestone_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("milestone:delete"))],
    summary="Delete a milestone",
)
def delete_milestone(
    milestone_id: uuid.UUID, service: MilestoneServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a milestone."""
    service.delete_milestone(milestone_id)
    uow.commit()
    return MessageResponse(detail="Milestone deleted.")


@router.get(
    "/projects/{project_id}/milestone-summary",
    response_model=MilestoneSummaryResponse,
    dependencies=[Depends(require_permission("milestone:read"))],
    summary="Get a project's milestone summary",
)
def get_summary(project_id: uuid.UUID, service: MilestoneServiceDep) -> MilestoneSummaryResponse:
    """Return the aggregated milestone position of a project."""
    return service.get_summary(project_id)
