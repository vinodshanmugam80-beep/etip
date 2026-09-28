"""ORM model for the Financial Management module.

A :class:`FinancialEntry` is a single line in a project's cost ledger. Each entry
is one of three kinds — a planned **budget** line, a **forecast**, or an
**actual** incurred cost — categorised (labour, materials, ...) and dated. The
service aggregates entries into a project financial summary and keeps the
project's ``forecast`` and ``actual_cost`` rollups in sync.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class FinancialEntryType(enum.StrEnum):
    """Kind of a financial ledger entry."""

    BUDGET = "budget"
    FORECAST = "forecast"
    ACTUAL = "actual"


class CostCategory(enum.StrEnum):
    """Category of a financial ledger entry."""

    LABOR = "labor"
    MATERIALS = "materials"
    TRAVEL = "travel"
    SOFTWARE = "software"
    HARDWARE = "hardware"
    SERVICES = "services"
    OVERHEAD = "overhead"
    OTHER = "other"


class FinancialEntry(BaseEntity, TenantMixin):
    """A single line in a project's cost ledger.

    ``amount`` may be negative to record credits or adjustments. The entry's
    currency must match its project's currency (enforced in the service) so that
    aggregates are always single-currency.
    """

    __tablename__ = "financial_entries"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_type: Mapped[FinancialEntryType] = mapped_column(
        enum_column(FinancialEntryType), nullable=False, index=True
    )
    category: Mapped[CostCategory] = mapped_column(
        enum_column(CostCategory), default=CostCategory.OTHER, index=True
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)

    description: Mapped[str] = mapped_column(String(500), default="")
    vendor: Mapped[str] = mapped_column(String(200), default="")
