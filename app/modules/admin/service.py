"""Administration service.

Provides tenant-facing operational tooling: read access to the audit log, a
governance overview, system diagnostics, and — closing a long-standing gap —
reconciliation of the permission catalogue for an *existing* tenant. New modules
add permissions and system-role grants that only reach a tenant at registration;
reconciliation backfills those permissions and grants for tenants created
earlier.

Framework-agnostic apart from returning result schemas; raises domain exceptions
from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.base import AuditLog, utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.admin.reconcile import reconcile_organization
from app.modules.admin.repository import AdminStatsRepository, AuditLogRepository
from app.modules.admin.schemas import (
    AdminOverviewResponse,
    DiagnosticsResponse,
    ReconcileResult,
)
from app.modules.auth.seeds import PERMISSION_CATALOGUE

logger = get_logger(__name__)


class AdminService:
    """Administrative operations scoped to the caller's tenant."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        app_name: str,
        app_env: str,
    ) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        self._app_name = app_name
        self._app_env = app_env
        session = uow.session
        self.audit = AuditLogRepository(session)
        self.stats = AdminStatsRepository(session)

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------
    def search_audit_logs(
        self,
        *,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        action: str | None,
        actor_id: uuid.UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLog], int]:
        """Return a filtered page of the tenant's audit entries and the total."""
        items = list(
            self.audit.search(
                self._org_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_id=actor_id,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
            )
        )
        total = self.audit.count(
            self._org_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            date_from=date_from,
            date_to=date_to,
        )
        return items, total

    def get_audit_entry(self, entry_id: uuid.UUID) -> AuditLog:
        """Return a single audit entry belonging to the tenant."""
        entry = self.audit.get(entry_id, self._org_id)
        if entry is None:
            raise NotFoundError("Audit entry not found.")
        return entry

    # ------------------------------------------------------------------
    # Overview & diagnostics
    # ------------------------------------------------------------------
    def overview(self) -> AdminOverviewResponse:
        """Return governance counts for the tenant."""
        total_users, active_users = self.stats.user_counts(self._org_id)
        return AdminOverviewResponse(
            total_users=total_users,
            active_users=active_users,
            roles=self.stats.role_count(self._org_id),
            projects=self.stats.project_count(self._org_id),
            portfolios=self.stats.portfolio_count(self._org_id),
            audit_entries=self.stats.audit_count(self._org_id),
            permission_catalogue_size=len(PERMISSION_CATALOGUE),
        )

    def diagnostics(self) -> DiagnosticsResponse:
        """Return system diagnostics, including a database connectivity check."""
        try:
            self._uow.session.execute(select(1))
            database = "ok"
            status = "healthy"
        except Exception:  # pragma: no cover - defensive
            database = "error"
            status = "degraded"
        return DiagnosticsResponse(
            status=status,
            database=database,
            app_name=self._app_name,
            app_env=self._app_env,
            server_time=utcnow(),
        )

    # ------------------------------------------------------------------
    # Permission reconciliation
    # ------------------------------------------------------------------
    def reconcile_permissions(self) -> ReconcileResult:
        """Backfill catalogue permissions and system-role grants for the tenant.

        Delegates the data operation to :func:`reconcile_organization` and records
        an audit entry for the administrative action.
        """
        result = reconcile_organization(self._uow.session, self._org_id, self._actor_id)
        self._uow.record_audit(
            "Organization",
            self._org_id,
            "reconcile",
            (
                f"Reconciled permissions: +{result.permissions_created} permissions, "
                f"+{result.total_grants_added} grants"
            ),
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return result
