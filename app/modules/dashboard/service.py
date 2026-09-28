"""Dashboards service.

Manages dashboards (owned, optionally shared) and their widgets, and renders a
dashboard by running each REPORT widget through the shared :class:`ReportEngine`.
A failing widget is captured per-tile (its ``error`` is set) so one bad widget
never breaks the whole dashboard.

Framework-agnostic apart from returning render result schemas (as the Reports
service does); raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.exceptions import AppError, NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.dashboard.models import Dashboard, DashboardWidget, WidgetType
from app.modules.dashboard.repository import (
    DashboardRepository,
    DashboardWidgetRepository,
)
from app.modules.dashboard.schemas import RenderedWidget
from app.modules.report.engine import ReportEngine
from app.modules.report.models import ReportType

logger = get_logger(__name__)


class DashboardService:
    """Coordinates dashboard and widget use cases within a tenant."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.dashboards = DashboardRepository(session)
        self.widgets = DashboardWidgetRepository(session)
        self._engine = ReportEngine(session, organization_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_visible_or_404(self, dashboard_id: uuid.UUID) -> Dashboard:
        dashboard = self.dashboards.get_visible(dashboard_id, self._org_id, self._actor_id)
        if dashboard is None:
            raise NotFoundError("Dashboard not found.")
        return dashboard

    def _require_owner(self, dashboard: Dashboard) -> None:
        if dashboard.created_by != self._actor_id:
            raise PermissionDeniedError("Only the owner can modify this dashboard.")

    def _owned_or_403(self, dashboard_id: uuid.UUID) -> Dashboard:
        dashboard = self._get_visible_or_404(dashboard_id)
        self._require_owner(dashboard)
        return dashboard

    def _get_widget_or_404(self, dashboard_id: uuid.UUID, widget_id: uuid.UUID) -> DashboardWidget:
        widget = self.widgets.get(widget_id, organization_id=self._org_id)
        if widget is None or widget.dashboard_id != dashboard_id:
            raise NotFoundError("Widget not found.")
        return widget

    # ------------------------------------------------------------------
    # Dashboards
    # ------------------------------------------------------------------
    def create_dashboard(
        self,
        *,
        name: str,
        description: str,
        is_shared: bool,
        layout: dict[str, Any],
    ) -> Dashboard:
        """Create a dashboard owned by the caller."""
        dashboard = Dashboard(
            organization_id=self._org_id,
            name=name,
            description=description,
            is_shared=is_shared,
            layout=layout,
            created_by=self._actor_id,
        )
        self.dashboards.add(dashboard)
        self._uow.record_audit(
            "Dashboard",
            dashboard.id,
            "create",
            f"Created dashboard '{name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return dashboard

    def get_dashboard(self, dashboard_id: uuid.UUID) -> Dashboard:
        """Return a dashboard visible to the caller."""
        return self._get_visible_or_404(dashboard_id)

    def search_dashboards(self, *, limit: int, offset: int) -> tuple[list[Dashboard], int]:
        """Return a page of dashboards visible to the caller and the total."""
        items = list(
            self.dashboards.search(self._org_id, self._actor_id, limit=limit, offset=offset)
        )
        total = self.dashboards.count(self._org_id, self._actor_id)
        return items, total

    def update_dashboard(
        self,
        dashboard_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
        is_shared: bool | None,
        layout: dict[str, Any] | None,
    ) -> Dashboard:
        """Update a dashboard (owner only)."""
        dashboard = self._owned_or_403(dashboard_id)
        if name is not None:
            dashboard.name = name
        if description is not None:
            dashboard.description = description
        if is_shared is not None:
            dashboard.is_shared = is_shared
        if layout is not None:
            dashboard.layout = layout
        dashboard.modified_by = self._actor_id
        self.dashboards.update(dashboard)
        return dashboard

    def delete_dashboard(self, dashboard_id: uuid.UUID) -> None:
        """Soft-delete a dashboard and its widgets (owner only)."""
        dashboard = self._owned_or_403(dashboard_id)
        self.widgets.soft_delete_for_dashboard(self._org_id, dashboard_id, actor_id=self._actor_id)
        self.dashboards.soft_delete(dashboard, actor_id=self._actor_id)

    def set_default(self, dashboard_id: uuid.UUID) -> Dashboard:
        """Make this the caller's single default dashboard (owner only)."""
        dashboard = self._owned_or_403(dashboard_id)
        self.dashboards.clear_default_for_user(
            self._org_id, self._actor_id, actor_id=self._actor_id
        )
        dashboard.is_default = True
        dashboard.modified_by = self._actor_id
        self.dashboards.update(dashboard)
        return dashboard

    # ------------------------------------------------------------------
    # Widgets
    # ------------------------------------------------------------------
    def list_widgets(self, dashboard_id: uuid.UUID) -> list[DashboardWidget]:
        """Return a dashboard's widgets (visible dashboard)."""
        self._get_visible_or_404(dashboard_id)
        return list(self.widgets.list_for_dashboard(self._org_id, dashboard_id))

    def add_widget(
        self,
        dashboard_id: uuid.UUID,
        *,
        title: str,
        widget_type: WidgetType,
        report_type: ReportType | None,
        parameters: dict[str, Any],
        content: str,
        position: int,
        width: int,
    ) -> DashboardWidget:
        """Add a widget to a dashboard (owner only)."""
        self._owned_or_403(dashboard_id)
        widget = DashboardWidget(
            organization_id=self._org_id,
            dashboard_id=dashboard_id,
            title=title,
            widget_type=widget_type,
            report_type=report_type if widget_type == WidgetType.REPORT else None,
            parameters=parameters if widget_type == WidgetType.REPORT else {},
            content=content if widget_type == WidgetType.TEXT else "",
            position=position,
            width=width,
            created_by=self._actor_id,
        )
        self.widgets.add(widget)
        return widget

    def update_widget(
        self,
        dashboard_id: uuid.UUID,
        widget_id: uuid.UUID,
        *,
        title: str | None,
        report_type: ReportType | None,
        parameters: dict[str, Any] | None,
        content: str | None,
        position: int | None,
        width: int | None,
    ) -> DashboardWidget:
        """Update a widget (owner only)."""
        self._owned_or_403(dashboard_id)
        widget = self._get_widget_or_404(dashboard_id, widget_id)
        if title is not None:
            widget.title = title
        if report_type is not None and widget.widget_type == WidgetType.REPORT:
            widget.report_type = report_type
        if parameters is not None and widget.widget_type == WidgetType.REPORT:
            widget.parameters = parameters
        if content is not None and widget.widget_type == WidgetType.TEXT:
            widget.content = content
        if position is not None:
            widget.position = position
        if width is not None:
            widget.width = width
        widget.modified_by = self._actor_id
        self.widgets.update(widget)
        return widget

    def remove_widget(self, dashboard_id: uuid.UUID, widget_id: uuid.UUID) -> None:
        """Remove a widget from a dashboard (owner only)."""
        self._owned_or_403(dashboard_id)
        widget = self._get_widget_or_404(dashboard_id, widget_id)
        self.widgets.soft_delete(widget, actor_id=self._actor_id)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render(self, dashboard_id: uuid.UUID) -> tuple[Dashboard, list[RenderedWidget]]:
        """Render a dashboard: run each REPORT widget through the engine.

        A widget that fails to render captures its error rather than aborting the
        whole dashboard.
        """
        dashboard = self._get_visible_or_404(dashboard_id)
        widgets = self.widgets.list_for_dashboard(self._org_id, dashboard_id)
        rendered: list[RenderedWidget] = []
        for widget in widgets:
            if widget.widget_type == WidgetType.TEXT:
                rendered.append(
                    RenderedWidget(
                        id=widget.id,
                        title=widget.title,
                        widget_type=widget.widget_type,
                        position=widget.position,
                        width=widget.width,
                        content=widget.content,
                    )
                )
                continue
            data: dict[str, Any] | None = None
            error: str | None = None
            if widget.report_type is None:
                error = "Report widget has no report_type configured."
            else:
                try:
                    data = self._engine.assemble(widget.report_type, widget.parameters).data
                except AppError as exc:
                    error = exc.message
            rendered.append(
                RenderedWidget(
                    id=widget.id,
                    title=widget.title,
                    widget_type=widget.widget_type,
                    position=widget.position,
                    width=widget.width,
                    report_type=widget.report_type,
                    data=data,
                    error=error,
                )
            )
        return dashboard, rendered
