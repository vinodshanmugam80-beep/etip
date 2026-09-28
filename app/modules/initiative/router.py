"""HTTP routes for Strategic Initiatives, Business Goals and KPIs.

Reads require ``initiative:read``; mutations require ``initiative:manage``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import InitiativeServiceDep, UowDep, require_permission
from app.modules.initiative.models import InitiativeStatus
from app.modules.initiative.schemas import (
    GoalCreateRequest,
    GoalKPISummary,
    GoalResponse,
    GoalUpdateRequest,
    InitiativeCreateRequest,
    InitiativeResponse,
    InitiativeSummary,
    InitiativeUpdateRequest,
    KPICreateRequest,
    KPIMeasurementRequest,
    KPIResponse,
    KPIUpdateRequest,
    PaginatedInitiatives,
)

router = APIRouter(tags=["Strategic Initiatives"])
_READ = Depends(require_permission("initiative:read"))
_MANAGE = Depends(require_permission("initiative:manage"))


# --- Initiatives -----------------------------------------------------------
@router.post(
    "/initiatives",
    response_model=InitiativeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Create an initiative",
)
def create_initiative(
    payload: InitiativeCreateRequest, service: InitiativeServiceDep, uow: UowDep
) -> InitiativeResponse:
    """Create a strategic initiative."""
    initiative = service.create_initiative(payload)
    uow.commit()
    return InitiativeResponse.model_validate(initiative)


@router.get(
    "/initiatives",
    response_model=PaginatedInitiatives,
    dependencies=[_READ],
    summary="Search initiatives",
)
def list_initiatives(
    service: InitiativeServiceDep,
    initiative_status: InitiativeStatus | None = Query(default=None, alias="status"),
    portfolio_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedInitiatives:
    """Return a filtered, paginated page of initiatives."""
    items, total = service.search_initiatives(
        status=initiative_status, portfolio_id=portfolio_id, limit=limit, offset=offset
    )
    return PaginatedInitiatives(
        items=[InitiativeResponse.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/initiatives/{initiative_id}",
    response_model=InitiativeResponse,
    dependencies=[_READ],
    summary="Get an initiative",
)
def get_initiative(initiative_id: uuid.UUID, service: InitiativeServiceDep) -> InitiativeResponse:
    """Return a single initiative."""
    return InitiativeResponse.model_validate(service.get_initiative(initiative_id))


@router.patch(
    "/initiatives/{initiative_id}",
    response_model=InitiativeResponse,
    dependencies=[_MANAGE],
    summary="Update an initiative",
)
def update_initiative(
    initiative_id: uuid.UUID,
    payload: InitiativeUpdateRequest,
    service: InitiativeServiceDep,
    uow: UowDep,
) -> InitiativeResponse:
    """Update a strategic initiative."""
    initiative = service.update_initiative(initiative_id, payload)
    uow.commit()
    return InitiativeResponse.model_validate(initiative)


@router.delete(
    "/initiatives/{initiative_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_MANAGE],
    summary="Delete an initiative",
)
def delete_initiative(initiative_id: uuid.UUID, service: InitiativeServiceDep, uow: UowDep) -> None:
    """Soft-delete an initiative and its goals and KPIs."""
    service.delete_initiative(initiative_id)
    uow.commit()


@router.get(
    "/initiatives/{initiative_id}/goals",
    response_model=list[GoalResponse],
    dependencies=[_READ],
    summary="An initiative's goals",
)
def list_goals(initiative_id: uuid.UUID, service: InitiativeServiceDep) -> list[GoalResponse]:
    """Return the goals under an initiative."""
    return [GoalResponse.model_validate(g) for g in service.list_goals(initiative_id)]


@router.get(
    "/initiatives/{initiative_id}/summary",
    response_model=InitiativeSummary,
    dependencies=[_READ],
    summary="Initiative attainment summary",
)
def initiative_summary(
    initiative_id: uuid.UUID, service: InitiativeServiceDep
) -> InitiativeSummary:
    """Return an attainment rollup across the initiative's goals and KPIs."""
    return service.initiative_summary(initiative_id)


# --- Goals -----------------------------------------------------------------
@router.post(
    "/goals",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Create a goal",
)
def create_goal(
    payload: GoalCreateRequest, service: InitiativeServiceDep, uow: UowDep
) -> GoalResponse:
    """Create a business goal under an initiative."""
    goal = service.create_goal(payload)
    uow.commit()
    return GoalResponse.model_validate(goal)


@router.get(
    "/goals/{goal_id}", response_model=GoalResponse, dependencies=[_READ], summary="Get a goal"
)
def get_goal(goal_id: uuid.UUID, service: InitiativeServiceDep) -> GoalResponse:
    """Return a single goal."""
    return GoalResponse.model_validate(service.get_goal(goal_id))


@router.patch(
    "/goals/{goal_id}", response_model=GoalResponse, dependencies=[_MANAGE], summary="Update a goal"
)
def update_goal(
    goal_id: uuid.UUID, payload: GoalUpdateRequest, service: InitiativeServiceDep, uow: UowDep
) -> GoalResponse:
    """Update a business goal."""
    goal = service.update_goal(goal_id, payload)
    uow.commit()
    return GoalResponse.model_validate(goal)


@router.delete(
    "/goals/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_MANAGE],
    summary="Delete a goal",
)
def delete_goal(goal_id: uuid.UUID, service: InitiativeServiceDep, uow: UowDep) -> None:
    """Soft-delete a goal and its KPIs."""
    service.delete_goal(goal_id)
    uow.commit()


@router.get(
    "/goals/{goal_id}/kpis",
    response_model=list[KPIResponse],
    dependencies=[_READ],
    summary="A goal's KPIs",
)
def list_kpis(goal_id: uuid.UUID, service: InitiativeServiceDep) -> list[KPIResponse]:
    """Return the KPIs under a goal."""
    return [KPIResponse.model_validate(k) for k in service.list_kpis(goal_id)]


@router.get(
    "/goals/{goal_id}/summary",
    response_model=GoalKPISummary,
    dependencies=[_READ],
    summary="Goal KPI attainment summary",
)
def goal_summary(goal_id: uuid.UUID, service: InitiativeServiceDep) -> GoalKPISummary:
    """Return a KPI attainment rollup for a goal."""
    return service.goal_summary(goal_id)


# --- KPIs ------------------------------------------------------------------
@router.post(
    "/kpis",
    response_model=KPIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Create a KPI",
)
def create_kpi(
    payload: KPICreateRequest, service: InitiativeServiceDep, uow: UowDep
) -> KPIResponse:
    """Create a KPI on a goal."""
    kpi = service.create_kpi(payload)
    uow.commit()
    return KPIResponse.model_validate(kpi)


@router.get("/kpis/{kpi_id}", response_model=KPIResponse, dependencies=[_READ], summary="Get a KPI")
def get_kpi(kpi_id: uuid.UUID, service: InitiativeServiceDep) -> KPIResponse:
    """Return a single KPI."""
    return KPIResponse.model_validate(service.get_kpi(kpi_id))


@router.patch(
    "/kpis/{kpi_id}", response_model=KPIResponse, dependencies=[_MANAGE], summary="Update a KPI"
)
def update_kpi(
    kpi_id: uuid.UUID, payload: KPIUpdateRequest, service: InitiativeServiceDep, uow: UowDep
) -> KPIResponse:
    """Update a KPI's definition."""
    kpi = service.update_kpi(kpi_id, payload)
    uow.commit()
    return KPIResponse.model_validate(kpi)


@router.post(
    "/kpis/{kpi_id}/measurement",
    response_model=KPIResponse,
    dependencies=[_MANAGE],
    summary="Record a KPI value",
)
def record_kpi(
    kpi_id: uuid.UUID, payload: KPIMeasurementRequest, service: InitiativeServiceDep, uow: UowDep
) -> KPIResponse:
    """Record a KPI's current value."""
    kpi = service.record_kpi(kpi_id, payload)
    uow.commit()
    return KPIResponse.model_validate(kpi)


@router.delete(
    "/kpis/{kpi_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_MANAGE],
    summary="Delete a KPI",
)
def delete_kpi(kpi_id: uuid.UUID, service: InitiativeServiceDep, uow: UowDep) -> None:
    """Soft-delete a KPI."""
    service.delete_kpi(kpi_id)
    uow.commit()
