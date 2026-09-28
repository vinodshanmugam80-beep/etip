"""HTTP routes for the per-project KPI register.

Reads require ``projectkpi:read``; mutations require ``projectkpi:manage``. KPIs
are created and listed under a project; a KPI is then updated or deleted by its
own id. Each response carries derived ``attainment_percent`` and ``on_target``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import ProjectKPIServiceDep, UowDep, require_permission
from app.modules.projectkpi.schemas import (
    MessageResponse,
    PaginatedProjectKPIs,
    ProjectKPICreateRequest,
    ProjectKPIResponse,
    ProjectKPISummary,
    ProjectKPIUpdateRequest,
)

router = APIRouter(tags=["Project KPIs"])
_READ = Depends(require_permission("projectkpi:read"))
_MANAGE = Depends(require_permission("projectkpi:manage"))


@router.post(
    "/projects/{project_id}/kpis",
    response_model=ProjectKPIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Add a KPI to a project",
)
def create_kpi(
    project_id: uuid.UUID,
    payload: ProjectKPICreateRequest,
    service: ProjectKPIServiceDep,
    uow: UowDep,
) -> ProjectKPIResponse:
    """Create a KPI on a project."""
    kpi = service.create(project_id, payload)
    uow.commit()
    return service.to_response(kpi)


@router.get(
    "/projects/{project_id}/kpis",
    response_model=PaginatedProjectKPIs,
    dependencies=[_READ],
    summary="List a project's KPIs",
)
def list_kpis(
    project_id: uuid.UUID,
    service: ProjectKPIServiceDep,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedProjectKPIs:
    """Return a project's KPIs with derived attainment."""
    items, total = service.list_for_project(project_id, limit=limit, offset=offset)
    return PaginatedProjectKPIs(
        items=[service.to_response(k) for k in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/kpi-summary",
    response_model=ProjectKPISummary,
    dependencies=[_READ],
    summary="Get a project's KPI summary",
)
def kpi_summary(project_id: uuid.UUID, service: ProjectKPIServiceDep) -> ProjectKPISummary:
    """Return on-target / off-target counts and average attainment for a project."""
    return service.summary(project_id)


@router.patch(
    "/project-kpis/{kpi_id}",
    response_model=ProjectKPIResponse,
    dependencies=[_MANAGE],
    summary="Update a project KPI (e.g. record the current value)",
)
def update_kpi(
    kpi_id: uuid.UUID,
    payload: ProjectKPIUpdateRequest,
    service: ProjectKPIServiceDep,
    uow: UowDep,
) -> ProjectKPIResponse:
    """Apply a partial update to a KPI."""
    kpi = service.update(kpi_id, payload)
    uow.commit()
    return service.to_response(kpi)


@router.delete(
    "/project-kpis/{kpi_id}",
    response_model=MessageResponse,
    dependencies=[_MANAGE],
    summary="Delete a project KPI",
)
def delete_kpi(kpi_id: uuid.UUID, service: ProjectKPIServiceDep, uow: UowDep) -> MessageResponse:
    """Soft-delete a KPI."""
    service.delete(kpi_id)
    uow.commit()
    return MessageResponse(detail="KPI deleted.")
