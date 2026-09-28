"""Financial Management service.

Business rules for the project cost ledger. Each entry belongs to a project and
must share its currency (so aggregates stay single-currency). Whenever entries
change, the project's ``forecast`` and ``actual_cost`` rollups are recomputed
from the ledger. A summary compares the top-down ``approved_budget`` (set on the
project) against bottom-up planned, forecast and actual totals.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.finance.models import (
    CostCategory,
    FinancialEntry,
    FinancialEntryType,
)
from app.modules.finance.repository import FinancialEntryRepository
from app.modules.finance.schemas import (
    CategoryTotal,
    FinancialSummaryResponse,
)
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository

logger = get_logger(__name__)

_ZERO = Decimal("0.00")


class FinanceService:
    """Coordinates financial ledger use cases within a tenant."""

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
        self.entries = FinancialEntryRepository(session)
        self.projects = ProjectRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_project_or_404(self, project_id: uuid.UUID) -> Project:
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    def _get_entry_or_404(self, entry_id: uuid.UUID) -> FinancialEntry:
        entry = self.entries.get(entry_id, organization_id=self._org_id)
        if entry is None:
            raise NotFoundError("Financial entry not found.")
        return entry

    def _sync_project_rollups(self, project: Project) -> None:
        """Recompute the project's forecast and actual_cost from the ledger."""
        totals = self.entries.totals_by_type(self._org_id, project.id)
        project.forecast = totals.get(FinancialEntryType.FORECAST, _ZERO)
        project.actual_cost = totals.get(FinancialEntryType.ACTUAL, _ZERO)
        project.modified_by = self._actor_id
        self.projects.update(project)

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_entry(
        self,
        *,
        project_id: uuid.UUID,
        entry_type: FinancialEntryType,
        category: CostCategory,
        amount: Decimal,
        currency: str,
        entry_date: date,
        description: str,
        vendor: str,
    ) -> FinancialEntry:
        """Add a ledger line and refresh the project rollups."""
        project = self._get_project_or_404(project_id)
        if currency != project.currency:
            raise ValidationError(
                "Entry currency must match the project currency.",
                code="currency_mismatch",
                details={"expected": project.currency, "got": currency},
            )
        entry = FinancialEntry(
            organization_id=self._org_id,
            project_id=project_id,
            entry_type=entry_type,
            category=category,
            amount=amount,
            currency=currency,
            entry_date=entry_date,
            description=description,
            vendor=vendor,
            created_by=self._actor_id,
        )
        self.entries.add(entry)
        self._sync_project_rollups(project)
        self._uow.record_audit(
            "FinancialEntry",
            entry.id,
            "create",
            f"Added {entry_type.value} entry of {amount} {currency}",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return entry

    def get_entry(self, entry_id: uuid.UUID) -> FinancialEntry:
        """Return a single financial entry by id."""
        return self._get_entry_or_404(entry_id)

    def search_entries(
        self,
        *,
        project_id: uuid.UUID | None,
        entry_type: FinancialEntryType | None,
        category: CostCategory | None,
        limit: int,
        offset: int,
    ) -> tuple[list[FinancialEntry], int]:
        """Return a filtered page of entries and the total matching count."""
        items = list(
            self.entries.search(
                self._org_id,
                project_id=project_id,
                entry_type=entry_type,
                category=category,
                limit=limit,
                offset=offset,
            )
        )
        total = self.entries.count(
            self._org_id,
            project_id=project_id,
            entry_type=entry_type,
            category=category,
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_entry(
        self,
        entry_id: uuid.UUID,
        *,
        entry_type: FinancialEntryType | None,
        category: CostCategory | None,
        amount: Decimal | None,
        entry_date: date | None,
        description: str | None,
        vendor: str | None,
    ) -> FinancialEntry:
        """Apply a partial update and refresh the project rollups."""
        entry = self._get_entry_or_404(entry_id)
        for attr, value in (
            ("entry_type", entry_type),
            ("category", category),
            ("amount", amount),
            ("entry_date", entry_date),
            ("description", description),
            ("vendor", vendor),
        ):
            if value is not None:
                setattr(entry, attr, value)
        entry.modified_by = self._actor_id
        self.entries.update(entry)

        project = self._get_project_or_404(entry.project_id)
        self._sync_project_rollups(project)
        self._uow.record_audit(
            "FinancialEntry",
            entry.id,
            "update",
            "Updated financial entry",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return entry

    def delete_entry(self, entry_id: uuid.UUID) -> None:
        """Soft-delete an entry and refresh the project rollups."""
        entry = self._get_entry_or_404(entry_id)
        project_id = entry.project_id
        self.entries.soft_delete(entry, actor_id=self._actor_id)
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is not None:
            self._sync_project_rollups(project)
        self._uow.record_audit(
            "FinancialEntry",
            entry.id,
            "delete",
            "Deleted financial entry",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def get_summary(self, project_id: uuid.UUID) -> FinancialSummaryResponse:
        """Return the aggregated financial position of a project."""
        project = self._get_project_or_404(project_id)
        totals = self.entries.totals_by_type(self._org_id, project_id)
        planned = totals.get(FinancialEntryType.BUDGET, _ZERO)
        forecast = totals.get(FinancialEntryType.FORECAST, _ZERO)
        actual = totals.get(FinancialEntryType.ACTUAL, _ZERO)
        by_category = [
            CategoryTotal(category=cat, amount=amount)
            for cat, amount in self.entries.actual_by_category(self._org_id, project_id)
        ]
        return FinancialSummaryResponse(
            project_id=project_id,
            currency=project.currency,
            approved_budget=project.budget,
            planned_total=planned,
            forecast_total=forecast,
            actual_total=actual,
            budget_variance=project.budget - actual,
            forecast_variance=project.budget - forecast,
            actual_by_category=by_category,
        )
