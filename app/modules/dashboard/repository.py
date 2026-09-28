"""Repositories for the Dashboards module."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.modules.dashboard.models import Dashboard, DashboardWidget
from app.repositories.base import BaseRepository


class DashboardRepository(BaseRepository[Dashboard]):
    """Data access for :class:`Dashboard` (owner + shared visibility)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Dashboard)

    def _visible(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> Select[tuple[Dashboard]]:
        return self._base_query(organization_id).where(
            or_(Dashboard.created_by == user_id, Dashboard.is_shared.is_(True))
        )

    def get_visible(
        self, dashboard_id: uuid.UUID, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> Dashboard | None:
        """Return a dashboard if the user owns it or it is shared."""
        stmt = self._visible(organization_id, user_id).where(Dashboard.id == dashboard_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def search(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Dashboard]:
        """Return a page of dashboards visible to the user (newest first)."""
        stmt = (
            self._visible(organization_id, user_id)
            .order_by(Dashboard.created_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.session.execute(stmt).scalars().all()

    def count(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Return the number of dashboards visible to the user."""
        inner = self._visible(organization_id, user_id).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def clear_default_for_user(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        """Unset the default flag on any of the user's own dashboards."""
        stmt = self._base_query(organization_id).where(
            Dashboard.created_by == user_id,
            Dashboard.is_default.is_(True),
        )
        for dashboard in self.session.execute(stmt).scalars().all():
            dashboard.is_default = False
            dashboard.modified_by = actor_id
        self.session.flush()


class DashboardWidgetRepository(BaseRepository[DashboardWidget]):
    """Data access for :class:`DashboardWidget`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, DashboardWidget)

    def list_for_dashboard(
        self, organization_id: uuid.UUID, dashboard_id: uuid.UUID
    ) -> Sequence[DashboardWidget]:
        """Return a dashboard's widgets ordered by position."""
        stmt = (
            self._base_query(organization_id)
            .where(DashboardWidget.dashboard_id == dashboard_id)
            .order_by(DashboardWidget.position.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def soft_delete_for_dashboard(
        self,
        organization_id: uuid.UUID,
        dashboard_id: uuid.UUID,
        *,
        actor_id: uuid.UUID,
    ) -> int:
        """Soft-delete every widget of a dashboard."""
        stmt = self._base_query(organization_id).where(DashboardWidget.dashboard_id == dashboard_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for widget in rows:
            widget.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
