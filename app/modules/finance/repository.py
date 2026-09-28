"""Repository for the Financial Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.finance.models import (
    CostCategory,
    FinancialEntry,
    FinancialEntryType,
)
from app.repositories.base import BaseRepository


class FinancialEntryRepository(BaseRepository[FinancialEntry]):
    """Data access for :class:`FinancialEntry`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, FinancialEntry)

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None,
        entry_type: FinancialEntryType | None,
        category: CostCategory | None,
    ) -> Select[tuple[FinancialEntry]]:
        """Build the filtered (unpaginated) entry query."""
        stmt = self._base_query(organization_id)
        if project_id is not None:
            stmt = stmt.where(FinancialEntry.project_id == project_id)
        if entry_type is not None:
            stmt = stmt.where(FinancialEntry.entry_type == entry_type)
        if category is not None:
            stmt = stmt.where(FinancialEntry.category == category)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        entry_type: FinancialEntryType | None = None,
        category: CostCategory | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[FinancialEntry]:
        """Return a filtered, paginated page of entries (newest date first)."""
        stmt = self._search_stmt(
            organization_id,
            project_id=project_id,
            entry_type=entry_type,
            category=category,
        )
        stmt = stmt.order_by(FinancialEntry.entry_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        entry_type: FinancialEntryType | None = None,
        category: CostCategory | None = None,
    ) -> int:
        """Return the total number of entries matching the filters."""
        inner = self._search_stmt(
            organization_id,
            project_id=project_id,
            entry_type=entry_type,
            category=category,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def totals_by_type(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> dict[FinancialEntryType, Decimal]:
        """Return the summed amount per entry type for a project."""
        stmt = (
            select(
                FinancialEntry.entry_type,
                func.coalesce(func.sum(FinancialEntry.amount), 0),
            )
            .where(
                FinancialEntry.organization_id == organization_id,
                FinancialEntry.project_id == project_id,
                FinancialEntry.is_deleted.is_(False),
            )
            .group_by(FinancialEntry.entry_type)
        )
        result = self.session.execute(stmt).all()
        return {row[0]: Decimal(row[1]) for row in result}

    def actual_by_category(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[tuple[CostCategory, Decimal]]:
        """Return summed ACTUAL spend grouped by category (descending)."""
        stmt = (
            select(
                FinancialEntry.category,
                func.coalesce(func.sum(FinancialEntry.amount), 0).label("total"),
            )
            .where(
                FinancialEntry.organization_id == organization_id,
                FinancialEntry.project_id == project_id,
                FinancialEntry.is_deleted.is_(False),
                FinancialEntry.entry_type == FinancialEntryType.ACTUAL,
            )
            .group_by(FinancialEntry.category)
            .order_by(func.sum(FinancialEntry.amount).desc())
        )
        return [(row[0], Decimal(row[1])) for row in self.session.execute(stmt).all()]

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live financial entry of a project."""
        stmt = self._base_query(organization_id).where(FinancialEntry.project_id == project_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for entry in rows:
            entry.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
