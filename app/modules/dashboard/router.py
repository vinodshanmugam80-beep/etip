"""HTTP routes for the Dashboards module.

Viewing and rendering require ``dashboard:read``; creating requires
``dashboard:create``; edits, widget management, and setting a default require
``dashboard:update`` and are restricted to the owner in the service; deletion
requires ``dashboard:delete``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import DashboardServiceDep, UowDep, require_permission
from app.db.base import utcnow
from app.modules.dashboard.schemas import (
    DashboardCreateRequest,
    DashboardRenderResponse,
    DashboardResponse,
    DashboardUpdateRequest,
    MessageResponse,
    PaginatedDashboards,
    WidgetCreateRequest,
    WidgetResponse,
    WidgetUpdateRequest,
)

router = APIRouter(tags=["Dashboards"])


@router.post(
    "/dashboards",
    response_model=DashboardResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("dashboard:create"))],
    summary="Create a dashboard",
)
def create_dashboard(
    payload: DashboardCreateRequest, service: DashboardServiceDep, uow: UowDep
) -> DashboardResponse:
    """Create a dashboard owned by the caller."""
    dashboard = service.create_dashboard(
        name=payload.name,
        description=payload.description,
        is_shared=payload.is_shared,
        layout=payload.layout,
    )
    uow.commit()
    return DashboardResponse.model_validate(dashboard)


@router.get(
    "/dashboards",
    response_model=PaginatedDashboards,
    dependencies=[Depends(require_permission("dashboard:read"))],
    summary="List dashboards",
)
def list_dashboards(
    service: DashboardServiceDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedDashboards:
    """Return the dashboards visible to the caller (owned + shared)."""
    items, total = service.search_dashboards(limit=limit, offset=offset)
    return PaginatedDashboards(
        items=[DashboardResponse.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/dashboards/{dashboard_id}",
    response_model=DashboardResponse,
    dependencies=[Depends(require_permission("dashboard:read"))],
    summary="Get a dashboard",
)
def get_dashboard(dashboard_id: uuid.UUID, service: DashboardServiceDep) -> DashboardResponse:
    """Return a dashboard visible to the caller."""
    return DashboardResponse.model_validate(service.get_dashboard(dashboard_id))


@router.patch(
    "/dashboards/{dashboard_id}",
    response_model=DashboardResponse,
    dependencies=[Depends(require_permission("dashboard:update"))],
    summary="Update a dashboard",
)
def update_dashboard(
    dashboard_id: uuid.UUID,
    payload: DashboardUpdateRequest,
    service: DashboardServiceDep,
    uow: UowDep,
) -> DashboardResponse:
    """Update a dashboard (owner only)."""
    dashboard = service.update_dashboard(
        dashboard_id,
        name=payload.name,
        description=payload.description,
        is_shared=payload.is_shared,
        layout=payload.layout,
    )
    uow.commit()
    return DashboardResponse.model_validate(dashboard)


@router.delete(
    "/dashboards/{dashboard_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("dashboard:delete"))],
    summary="Delete a dashboard",
)
def delete_dashboard(
    dashboard_id: uuid.UUID, service: DashboardServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a dashboard and its widgets (owner only)."""
    service.delete_dashboard(dashboard_id)
    uow.commit()
    return MessageResponse(detail="Dashboard deleted.")


@router.post(
    "/dashboards/{dashboard_id}/set-default",
    response_model=DashboardResponse,
    dependencies=[Depends(require_permission("dashboard:update"))],
    summary="Set as my default dashboard",
)
def set_default(
    dashboard_id: uuid.UUID, service: DashboardServiceDep, uow: UowDep
) -> DashboardResponse:
    """Make this the caller's single default dashboard (owner only)."""
    dashboard = service.set_default(dashboard_id)
    uow.commit()
    return DashboardResponse.model_validate(dashboard)


@router.get(
    "/dashboards/{dashboard_id}/render",
    response_model=DashboardRenderResponse,
    dependencies=[Depends(require_permission("dashboard:read"))],
    summary="Render a dashboard's widgets",
)
def render_dashboard(
    dashboard_id: uuid.UUID, service: DashboardServiceDep
) -> DashboardRenderResponse:
    """Render every widget, running REPORT widgets through the report engine."""
    dashboard, widgets = service.render(dashboard_id)
    return DashboardRenderResponse(
        dashboard=DashboardResponse.model_validate(dashboard),
        generated_at=utcnow(),
        widgets=widgets,
    )


@router.get(
    "/dashboards/{dashboard_id}/widgets",
    response_model=list[WidgetResponse],
    dependencies=[Depends(require_permission("dashboard:read"))],
    summary="List a dashboard's widgets",
)
def list_widgets(dashboard_id: uuid.UUID, service: DashboardServiceDep) -> list[WidgetResponse]:
    """Return a dashboard's widgets ordered by position."""
    return [WidgetResponse.model_validate(w) for w in service.list_widgets(dashboard_id)]


@router.post(
    "/dashboards/{dashboard_id}/widgets",
    response_model=WidgetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("dashboard:update"))],
    summary="Add a widget",
)
def add_widget(
    dashboard_id: uuid.UUID,
    payload: WidgetCreateRequest,
    service: DashboardServiceDep,
    uow: UowDep,
) -> WidgetResponse:
    """Add a widget to a dashboard (owner only)."""
    widget = service.add_widget(
        dashboard_id,
        title=payload.title,
        widget_type=payload.widget_type,
        report_type=payload.report_type,
        parameters=payload.parameters,
        content=payload.content,
        position=payload.position,
        width=payload.width,
    )
    uow.commit()
    return WidgetResponse.model_validate(widget)


@router.patch(
    "/dashboards/{dashboard_id}/widgets/{widget_id}",
    response_model=WidgetResponse,
    dependencies=[Depends(require_permission("dashboard:update"))],
    summary="Update a widget",
)
def update_widget(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    payload: WidgetUpdateRequest,
    service: DashboardServiceDep,
    uow: UowDep,
) -> WidgetResponse:
    """Update a widget (owner only)."""
    widget = service.update_widget(
        dashboard_id,
        widget_id,
        title=payload.title,
        report_type=payload.report_type,
        parameters=payload.parameters,
        content=payload.content,
        position=payload.position,
        width=payload.width,
    )
    uow.commit()
    return WidgetResponse.model_validate(widget)


@router.delete(
    "/dashboards/{dashboard_id}/widgets/{widget_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("dashboard:update"))],
    summary="Remove a widget",
)
def remove_widget(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    service: DashboardServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Remove a widget from a dashboard (owner only)."""
    service.remove_widget(dashboard_id, widget_id)
    uow.commit()
    return MessageResponse(detail="Widget removed.")
