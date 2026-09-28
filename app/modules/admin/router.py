"""HTTP routes for the Administration module.

Reads (audit log, overview, diagnostics) require ``admin:read``; the permission
reconciliation requires ``admin:manage``. Both are held only by the Organization
Admin role.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import AdminServiceDep, UowDep, require_permission
from app.modules.admin.schemas import (
    AdminOverviewResponse,
    AuditLogResponse,
    DiagnosticsResponse,
    PaginatedAuditLogs,
    ReconcileResult,
)

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get(
    "/audit-logs",
    response_model=PaginatedAuditLogs,
    dependencies=[Depends(require_permission("admin:read"))],
    summary="Search the audit log",
)
def list_audit_logs(
    service: AdminServiceDep,
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedAuditLogs:
    """Return a filtered, paginated page of the tenant's audit entries."""
    items, total = service.search_audit_logs(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return PaginatedAuditLogs(
        items=[AuditLogResponse.model_validate(entry) for entry in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/audit-logs/{entry_id}",
    response_model=AuditLogResponse,
    dependencies=[Depends(require_permission("admin:read"))],
    summary="Get an audit-log entry",
)
def get_audit_entry(entry_id: uuid.UUID, service: AdminServiceDep) -> AuditLogResponse:
    """Return a single audit entry belonging to the tenant."""
    return AuditLogResponse.model_validate(service.get_audit_entry(entry_id))


@router.get(
    "/overview",
    response_model=AdminOverviewResponse,
    dependencies=[Depends(require_permission("admin:read"))],
    summary="Tenant governance overview",
)
def overview(service: AdminServiceDep) -> AdminOverviewResponse:
    """Return governance counts for the tenant."""
    return service.overview()


@router.get(
    "/diagnostics",
    response_model=DiagnosticsResponse,
    dependencies=[Depends(require_permission("admin:read"))],
    summary="System diagnostics",
)
def diagnostics(service: AdminServiceDep) -> DiagnosticsResponse:
    """Return system diagnostics, including a database connectivity check."""
    return service.diagnostics()


@router.post(
    "/reconcile-permissions",
    response_model=ReconcileResult,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("admin:manage"))],
    summary="Reconcile the permission catalogue",
)
def reconcile_permissions(service: AdminServiceDep, uow: UowDep) -> ReconcileResult:
    """Backfill catalogue permissions and system-role grants for the tenant."""
    result = service.reconcile_permissions()
    uow.commit()
    return result
