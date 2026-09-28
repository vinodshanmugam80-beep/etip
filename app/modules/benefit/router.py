"""HTTP routes for Benefits Realization."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import BenefitServiceDep, UowDep, require_permission
from app.modules.benefit.models import BenefitCategory, BenefitStatus
from app.modules.benefit.schemas import (
    BenefitCreateRequest,
    BenefitRealizationRequest,
    BenefitResponse,
    BenefitSummaryResponse,
    BenefitUpdateRequest,
    PaginatedBenefits,
)

router = APIRouter(prefix="/benefits", tags=["Benefits"])


@router.post(
    "",
    response_model=BenefitResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("benefit:create"))],
    summary="Create a benefit",
)
def create_benefit(
    payload: BenefitCreateRequest, service: BenefitServiceDep, uow: UowDep
) -> BenefitResponse:
    """Create a benefit under a project."""
    benefit = service.create(payload)
    uow.commit()
    return BenefitResponse.model_validate(benefit)


@router.get(
    "",
    response_model=PaginatedBenefits,
    dependencies=[Depends(require_permission("benefit:read"))],
    summary="Search benefits",
)
def list_benefits(
    service: BenefitServiceDep,
    project_id: uuid.UUID | None = Query(default=None),
    category: BenefitCategory | None = Query(default=None),
    benefit_status: BenefitStatus | None = Query(default=None, alias="status"),
    owner_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedBenefits:
    """Return a filtered, paginated page of benefits."""
    items, total = service.search(
        project_id=project_id,
        category=category,
        status=benefit_status,
        owner_user_id=owner_user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedBenefits(
        items=[BenefitResponse.model_validate(b) for b in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/summary/projects/{project_id}",
    response_model=BenefitSummaryResponse,
    dependencies=[Depends(require_permission("benefit:read"))],
    summary="Project benefits realisation summary",
)
def project_summary(project_id: uuid.UUID, service: BenefitServiceDep) -> BenefitSummaryResponse:
    """Return a realisation rollup for a project."""
    return service.project_summary(project_id)


@router.get(
    "/summary/programs/{program_id}",
    response_model=BenefitSummaryResponse,
    dependencies=[Depends(require_permission("benefit:read"))],
    summary="Program benefits realisation summary",
)
def program_summary(program_id: uuid.UUID, service: BenefitServiceDep) -> BenefitSummaryResponse:
    """Return a realisation rollup across a program's projects."""
    return service.program_summary(program_id)


@router.get(
    "/summary/portfolios/{portfolio_id}",
    response_model=BenefitSummaryResponse,
    dependencies=[Depends(require_permission("benefit:read"))],
    summary="Portfolio benefits realisation summary",
)
def portfolio_summary(
    portfolio_id: uuid.UUID, service: BenefitServiceDep
) -> BenefitSummaryResponse:
    """Return a realisation rollup across a portfolio's projects."""
    return service.portfolio_summary(portfolio_id)


@router.get(
    "/{benefit_id}",
    response_model=BenefitResponse,
    dependencies=[Depends(require_permission("benefit:read"))],
    summary="Get a benefit",
)
def get_benefit(benefit_id: uuid.UUID, service: BenefitServiceDep) -> BenefitResponse:
    """Return a single benefit."""
    return BenefitResponse.model_validate(service.get(benefit_id))


@router.patch(
    "/{benefit_id}",
    response_model=BenefitResponse,
    dependencies=[Depends(require_permission("benefit:update"))],
    summary="Update a benefit",
)
def update_benefit(
    benefit_id: uuid.UUID,
    payload: BenefitUpdateRequest,
    service: BenefitServiceDep,
    uow: UowDep,
) -> BenefitResponse:
    """Update a benefit's fields, target or status."""
    benefit = service.update(benefit_id, payload)
    uow.commit()
    return BenefitResponse.model_validate(benefit)


@router.post(
    "/{benefit_id}/realization",
    response_model=BenefitResponse,
    dependencies=[Depends(require_permission("benefit:update"))],
    summary="Record realised value",
)
def record_realization(
    benefit_id: uuid.UUID,
    payload: BenefitRealizationRequest,
    service: BenefitServiceDep,
    uow: UowDep,
) -> BenefitResponse:
    """Record realised value for a benefit (auto-advances status)."""
    benefit = service.record_realization(benefit_id, payload)
    uow.commit()
    return BenefitResponse.model_validate(benefit)


@router.delete(
    "/{benefit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("benefit:delete"))],
    summary="Delete a benefit",
)
def delete_benefit(benefit_id: uuid.UUID, service: BenefitServiceDep, uow: UowDep) -> None:
    """Soft-delete a benefit."""
    service.delete(benefit_id)
    uow.commit()
