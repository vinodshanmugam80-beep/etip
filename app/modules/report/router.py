"""HTTP routes for the Reports module.

Thin adapters over :class:`ReportService`. Viewing and running require
``report:read``; creating requires ``report:create``; editing and deleting a
definition require ``report:update`` / ``report:delete`` and are restricted to
the definition's owner in the service.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import ReportServiceDep, UowDep, require_permission
from app.modules.report.models import ReportType
from app.modules.report.schemas import (
    AdHocRunRequest,
    MessageResponse,
    PaginatedReportDefinitions,
    ReportDefinitionCreateRequest,
    ReportDefinitionResponse,
    ReportDefinitionUpdateRequest,
    ReportResult,
)

router = APIRouter(tags=["Reports"])


@router.post(
    "/reports",
    response_model=ReportDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("report:create"))],
    summary="Save a report definition",
)
def create_report(
    payload: ReportDefinitionCreateRequest, service: ReportServiceDep, uow: UowDep
) -> ReportDefinitionResponse:
    """Save a report definition owned by the caller."""
    report = service.create_report(
        name=payload.name,
        description=payload.description,
        report_type=payload.report_type,
        parameters=payload.parameters,
        is_shared=payload.is_shared,
    )
    uow.commit()
    return ReportDefinitionResponse.model_validate(report)


@router.get(
    "/reports",
    response_model=PaginatedReportDefinitions,
    dependencies=[Depends(require_permission("report:read"))],
    summary="List report definitions",
)
def list_reports(
    service: ReportServiceDep,
    report_type: ReportType | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedReportDefinitions:
    """Return the definitions visible to the caller (owned + shared)."""
    items, total = service.search_reports(report_type=report_type, limit=limit, offset=offset)
    return PaginatedReportDefinitions(
        items=[ReportDefinitionResponse.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/reports/run",
    response_model=ReportResult,
    dependencies=[Depends(require_permission("report:read"))],
    summary="Run an ad-hoc report",
)
def run_adhoc(payload: AdHocRunRequest, service: ReportServiceDep) -> ReportResult:
    """Run a report from a type and parameters, without saving a definition."""
    return service.run_adhoc(payload.report_type, payload.parameters)


@router.get(
    "/reports/{report_id}",
    response_model=ReportDefinitionResponse,
    dependencies=[Depends(require_permission("report:read"))],
    summary="Get a report definition",
)
def get_report(report_id: uuid.UUID, service: ReportServiceDep) -> ReportDefinitionResponse:
    """Return a report definition visible to the caller."""
    return ReportDefinitionResponse.model_validate(service.get_report(report_id))


@router.patch(
    "/reports/{report_id}",
    response_model=ReportDefinitionResponse,
    dependencies=[Depends(require_permission("report:update"))],
    summary="Update a report definition",
)
def update_report(
    report_id: uuid.UUID,
    payload: ReportDefinitionUpdateRequest,
    service: ReportServiceDep,
    uow: UowDep,
) -> ReportDefinitionResponse:
    """Update a report definition (owner only)."""
    report = service.update_report(
        report_id,
        name=payload.name,
        description=payload.description,
        parameters=payload.parameters,
        is_shared=payload.is_shared,
    )
    uow.commit()
    return ReportDefinitionResponse.model_validate(report)


@router.delete(
    "/reports/{report_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("report:delete"))],
    summary="Delete a report definition",
)
def delete_report(report_id: uuid.UUID, service: ReportServiceDep, uow: UowDep) -> MessageResponse:
    """Delete a report definition (owner only)."""
    service.delete_report(report_id)
    uow.commit()
    return MessageResponse(detail="Report deleted.")


@router.post(
    "/reports/{report_id}/run",
    response_model=ReportResult,
    dependencies=[Depends(require_permission("report:read"))],
    summary="Run a saved report",
)
def run_saved(report_id: uuid.UUID, service: ReportServiceDep, uow: UowDep) -> ReportResult:
    """Run a saved report definition and record its last-run time."""
    result = service.run_saved(report_id)
    uow.commit()
    return result
