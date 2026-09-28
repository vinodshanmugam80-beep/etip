"""Pydantic v2 schemas for Benefits Realization."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.modules.benefit.models import BenefitCategory, BenefitStatus


class BenefitCreateRequest(BaseModel):
    """Payload to create a benefit."""

    project_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    category: BenefitCategory = BenefitCategory.OPERATIONAL
    status: BenefitStatus = BenefitStatus.PLANNED
    target_value: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    realized_value: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    investment_cost: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    target_date: date | None = None
    realized_date: date | None = None
    owner_user_id: uuid.UUID | None = None


class BenefitUpdateRequest(BaseModel):
    """Payload to update a benefit (all fields optional)."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    category: BenefitCategory | None = None
    status: BenefitStatus | None = None
    target_value: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    investment_cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    target_date: date | None = None
    owner_user_id: uuid.UUID | None = None


class BenefitRealizationRequest(BaseModel):
    """Payload to record realised value for a benefit."""

    realized_value: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    realized_date: date | None = None
    status: BenefitStatus | None = None


class BenefitResponse(BaseModel):
    """A benefit with derived realisation %, ROI % and variance."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    owner_user_id: uuid.UUID | None
    title: str
    description: str
    category: BenefitCategory
    status: BenefitStatus
    target_value: Decimal
    realized_value: Decimal
    investment_cost: Decimal
    target_date: date | None
    realized_date: date | None
    created_date: datetime
    version: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def realization_percent(self) -> float | None:
        """Realised value as a percentage of target (None if no target)."""
        if self.target_value <= 0:
            return None
        return round(float(self.realized_value / self.target_value) * 100, 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def roi_percent(self) -> float | None:
        """Return on investment: (realised - investment) / investment."""
        if self.investment_cost <= 0:
            return None
        return round(
            float((self.realized_value - self.investment_cost) / self.investment_cost) * 100,
            2,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def variance(self) -> Decimal:
        """Benefit variance: realised minus target (negative = shortfall)."""
        return self.realized_value - self.target_value


class PaginatedBenefits(BaseModel):
    """A page of benefits with total-count metadata."""

    items: list[BenefitResponse]
    total: int
    limit: int
    offset: int


class BenefitSummaryResponse(BaseModel):
    """Aggregated benefits realisation for a scope."""

    scope: str  # project | program | portfolio
    scope_id: uuid.UUID | None
    benefit_count: int
    total_target: Decimal
    total_realized: Decimal
    total_investment: Decimal
    realization_percent: float | None
    roi_percent: float | None
    variance: Decimal
    count_by_status: dict[str, int]
