"""Reports service.

Manages saved report definitions (owned, optionally shared) and runs them.
Assembly of results is delegated to :class:`ReportEngine`, a service-independent
helper that reads across other modules — so this service never imports another
service.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.report.engine import ReportEngine
from app.modules.report.models import ReportDefinition, ReportType
from app.modules.report.repository import ReportDefinitionRepository
from app.modules.report.schemas import ReportResult

logger = get_logger(__name__)


class ReportService:
    """Coordinates report definitions and report execution within a tenant."""

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
        self.reports = ReportDefinitionRepository(uow.session)
        self._engine = ReportEngine(uow.session, organization_id)

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------
    def _get_visible_or_404(self, report_id: uuid.UUID) -> ReportDefinition:
        report = self.reports.get_visible(report_id, self._org_id, self._actor_id)
        if report is None:
            raise NotFoundError("Report not found.")
        return report

    def _require_owner(self, report: ReportDefinition) -> None:
        if report.created_by != self._actor_id:
            raise PermissionDeniedError("Only the owner can modify this report definition.")

    def create_report(
        self,
        *,
        name: str,
        description: str,
        report_type: ReportType,
        parameters: dict[str, Any],
        is_shared: bool,
    ) -> ReportDefinition:
        """Save a new report definition owned by the caller."""
        report = ReportDefinition(
            organization_id=self._org_id,
            name=name,
            description=description,
            report_type=report_type,
            parameters=parameters,
            is_shared=is_shared,
            created_by=self._actor_id,
        )
        self.reports.add(report)
        self._uow.record_audit(
            "ReportDefinition",
            report.id,
            "create",
            f"Created report '{name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return report

    def get_report(self, report_id: uuid.UUID) -> ReportDefinition:
        """Return a report definition visible to the caller."""
        return self._get_visible_or_404(report_id)

    def search_reports(
        self,
        *,
        report_type: ReportType | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ReportDefinition], int]:
        """Return a page of definitions visible to the caller and the total."""
        items = list(
            self.reports.search(
                self._org_id,
                self._actor_id,
                report_type=report_type,
                limit=limit,
                offset=offset,
            )
        )
        total = self.reports.count(self._org_id, self._actor_id, report_type=report_type)
        return items, total

    def update_report(
        self,
        report_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
        parameters: dict[str, Any] | None,
        is_shared: bool | None,
    ) -> ReportDefinition:
        """Update a report definition (owner only)."""
        report = self._get_visible_or_404(report_id)
        self._require_owner(report)
        if name is not None:
            report.name = name
        if description is not None:
            report.description = description
        if parameters is not None:
            report.parameters = parameters
        if is_shared is not None:
            report.is_shared = is_shared
        report.modified_by = self._actor_id
        self.reports.update(report)
        return report

    def delete_report(self, report_id: uuid.UUID) -> None:
        """Delete a report definition (owner only)."""
        report = self._get_visible_or_404(report_id)
        self._require_owner(report)
        self.reports.soft_delete(report, actor_id=self._actor_id)

    # ------------------------------------------------------------------
    # Running (assembly delegated to the engine)
    # ------------------------------------------------------------------
    def run_saved(self, report_id: uuid.UUID) -> ReportResult:
        """Run a saved report definition and stamp its last-run time."""
        report = self._get_visible_or_404(report_id)
        result = self._engine.assemble(report.report_type, report.parameters)
        report.last_run_date = utcnow()
        self.reports.update(report)
        return result

    def run_adhoc(self, report_type: ReportType, parameters: dict[str, Any]) -> ReportResult:
        """Run a report from an ad-hoc type and parameters, without saving."""
        return self._engine.assemble(report_type, parameters)
