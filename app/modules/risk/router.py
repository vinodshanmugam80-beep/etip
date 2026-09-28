"""HTTP routes for the Risk Management module.

Thin adapters over :class:`RiskService`. Reads require ``risk:read``; mutations
require the corresponding ``risk:*`` permission. The per-project summary lives
under the projects path for discoverability.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import RiskServiceDep, UowDep, require_permission
from app.modules.risk.models import RiskCategory, RiskSeverity, RiskStatus
from app.modules.risk.schemas import (
    MessageResponse,
    PaginatedRisks,
    RiskCreateRequest,
    RiskResponseModel,
    RiskSummaryResponse,
    RiskUpdateRequest,
)

router = APIRouter(tags=["Risk Management"])


@router.post(
    "/risks",
    response_model=RiskResponseModel,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("risk:create"))],
    summary="Raise a risk",
)
def create_risk(
    payload: RiskCreateRequest, service: RiskServiceDep, uow: UowDep
) -> RiskResponseModel:
    """Raise a risk against a project (score derived from probability × impact)."""
    risk = service.create_risk(
        project_id=payload.project_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        probability=payload.probability,
        impact=payload.impact,
        response_strategy=payload.response_strategy,
        owner_user_id=payload.owner_user_id,
        mitigation_plan=payload.mitigation_plan,
        target_date=payload.target_date,
    )
    uow.commit()
    return RiskResponseModel.model_validate(risk)


@router.get(
    "/risks",
    response_model=PaginatedRisks,
    dependencies=[Depends(require_permission("risk:read"))],
    summary="List and search risks",
)
def list_risks(
    service: RiskServiceDep,
    q: str | None = Query(default=None, description="Search title"),
    project_id: uuid.UUID | None = Query(default=None),
    status_filter: RiskStatus | None = Query(default=None, alias="status"),
    category: RiskCategory | None = Query(default=None),
    severity: RiskSeverity | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedRisks:
    """Return a filtered, paginated page of risks (highest score first)."""
    items, total = service.search_risks(
        query=q,
        project_id=project_id,
        status=status_filter,
        category=category,
        severity=severity,
        owner_user_id=owner_user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedRisks(
        items=[RiskResponseModel.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/risks/{risk_id}",
    response_model=RiskResponseModel,
    dependencies=[Depends(require_permission("risk:read"))],
    summary="Get a risk",
)
def get_risk(risk_id: uuid.UUID, service: RiskServiceDep) -> RiskResponseModel:
    """Return a single risk by id."""
    return RiskResponseModel.model_validate(service.get_risk(risk_id))


@router.patch(
    "/risks/{risk_id}",
    response_model=RiskResponseModel,
    dependencies=[Depends(require_permission("risk:update"))],
    summary="Update a risk",
)
def update_risk(
    risk_id: uuid.UUID,
    payload: RiskUpdateRequest,
    service: RiskServiceDep,
    uow: UowDep,
) -> RiskResponseModel:
    """Apply a partial update, re-scoring and refreshing the project rollup."""
    risk = service.update_risk(
        risk_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        status=payload.status,
        probability=payload.probability,
        impact=payload.impact,
        response_strategy=payload.response_strategy,
        owner_user_id=payload.owner_user_id,
        mitigation_plan=payload.mitigation_plan,
        target_date=payload.target_date,
    )
    uow.commit()
    return RiskResponseModel.model_validate(risk)


@router.delete(
    "/risks/{risk_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("risk:delete"))],
    summary="Delete a risk",
)
def delete_risk(risk_id: uuid.UUID, service: RiskServiceDep, uow: UowDep) -> MessageResponse:
    """Soft-delete a risk and refresh the project rollup."""
    service.delete_risk(risk_id)
    uow.commit()
    return MessageResponse(detail="Risk deleted.")


@router.get(
    "/projects/{project_id}/risk-summary",
    response_model=RiskSummaryResponse,
    dependencies=[Depends(require_permission("risk:read"))],
    summary="Get a project's risk summary",
)
def get_summary(project_id: uuid.UUID, service: RiskServiceDep) -> RiskSummaryResponse:
    """Return the aggregated open-risk position of a project."""
    return service.get_summary(project_id)
