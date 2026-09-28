"""Pydantic v2 schemas for the Financial Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.finance.models import CostCategory, FinancialEntryType


class FinancialEntryCreateRequest(BaseModel):
    """Payload to add a line to a project's cost ledger."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "entry_type": "actual",
                "category": "labor",
                "amount": "12500.00",
                "currency": "USD",
                "entry_date": "2026-03-31",
                "description": "March engineering time",
                "vendor": "",
            }
        }
    )

    project_id: uuid.UUID
    entry_type: FinancialEntryType
    category: CostCategory = CostCategory.OTHER
    amount: Decimal = Field(max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    entry_date: date
    description: str = Field(default="", max_length=500)
    vendor: str = Field(default="", max_length=200)

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()


class FinancialEntryUpdateRequest(BaseModel):
    """Partial update for a financial entry; unset fields are unchanged."""

    entry_type: FinancialEntryType | None = None
    category: CostCategory | None = None
    amount: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    entry_date: date | None = None
    description: str | None = Field(default=None, max_length=500)
    vendor: str | None = Field(default=None, max_length=200)


class FinancialEntryResponse(BaseModel):
    """Financial entry representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    entry_type: FinancialEntryType
    category: CostCategory
    amount: Decimal
    currency: str
    entry_date: date
    description: str
    vendor: str
    created_date: datetime
    version: int


class PaginatedFinancialEntries(BaseModel):
    """A page of financial entries with total-count metadata."""

    items: list[FinancialEntryResponse]
    total: int
    limit: int
    offset: int


class CategoryTotal(BaseModel):
    """Actual spend aggregated for a single category."""

    category: CostCategory
    amount: Decimal


class FinancialSummaryResponse(BaseModel):
    """Aggregated financial position for a project.

    ``approved_budget`` is the top-down figure set on the project;
    ``planned_total`` is the bottom-up sum of BUDGET ledger lines. Variances are
    expressed as *remaining* against the approved budget (positive = under).
    """

    project_id: uuid.UUID
    currency: str
    approved_budget: Decimal
    planned_total: Decimal
    forecast_total: Decimal
    actual_total: Decimal
    budget_variance: Decimal
    forecast_variance: Decimal
    actual_by_category: list[CategoryTotal]


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
