"""Pydantic v2 schemas for Strategic Initiatives, Business Goals and KPIs."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.modules.initiative.logic import attainment_percent, target_met
from app.modules.initiative.models import (
    GoalCategory,
    GoalStatus,
    InitiativePriority,
    InitiativeStatus,
    KPIDirection,
)


# --- Initiative ------------------------------------------------------------
class InitiativeCreateRequest(BaseModel):
    """Payload to create a strategic initiative."""

    name: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    portfolio_id: uuid.UUID | None = None
    sponsor_user_id: uuid.UUID | None = None
    status: InitiativeStatus = InitiativeStatus.PROPOSED
    priority: InitiativePriority = InitiativePriority.MEDIUM
    start_date: date | None = None
    target_date: date | None = None


class InitiativeUpdateRequest(BaseModel):
    """Payload to update a strategic initiative (all optional)."""

    name: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    portfolio_id: uuid.UUID | None = None
    sponsor_user_id: uuid.UUID | None = None
    status: InitiativeStatus | None = None
    priority: InitiativePriority | None = None
    start_date: date | None = None
    target_date: date | None = None


class InitiativeResponse(BaseModel):
    """A strategic initiative."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    portfolio_id: uuid.UUID | None
    sponsor_user_id: uuid.UUID | None
    name: str
    description: str
    status: InitiativeStatus
    priority: InitiativePriority
    start_date: date | None
    target_date: date | None
    created_date: datetime
    version: int


class PaginatedInitiatives(BaseModel):
    """A page of initiatives with total-count metadata."""

    items: list[InitiativeResponse]
    total: int
    limit: int
    offset: int


# --- Goal ------------------------------------------------------------------
class GoalCreateRequest(BaseModel):
    """Payload to create a business goal under an initiative."""

    initiative_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    category: GoalCategory = GoalCategory.OTHER
    status: GoalStatus = GoalStatus.NOT_STARTED
    target_date: date | None = None


class GoalUpdateRequest(BaseModel):
    """Payload to update a business goal (all optional)."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    category: GoalCategory | None = None
    status: GoalStatus | None = None
    target_date: date | None = None


class GoalResponse(BaseModel):
    """A business goal."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    initiative_id: uuid.UUID
    title: str
    description: str
    category: GoalCategory
    status: GoalStatus
    target_date: date | None
    created_date: datetime
    version: int


# --- KPI -------------------------------------------------------------------
class KPICreateRequest(BaseModel):
    """Payload to create a KPI on a goal."""

    goal_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    unit: str = Field(default="", max_length=50)
    direction: KPIDirection = KPIDirection.INCREASE
    baseline_value: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    current_value: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    target_value: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)


class KPIUpdateRequest(BaseModel):
    """Payload to update a KPI's definition (all optional)."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    unit: str | None = Field(default=None, max_length=50)
    direction: KPIDirection | None = None
    baseline_value: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    target_value: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)


class KPIMeasurementRequest(BaseModel):
    """Payload to record a KPI's current value."""

    current_value: Decimal = Field(max_digits=18, decimal_places=4)


class KPIResponse(BaseModel):
    """A KPI with computed attainment, variance and target-met flag."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    goal_id: uuid.UUID
    name: str
    unit: str
    direction: KPIDirection
    baseline_value: Decimal
    current_value: Decimal
    target_value: Decimal
    created_date: datetime
    version: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def attainment_percent(self) -> float | None:
        """Progress from baseline toward target, as a percentage."""
        return attainment_percent(
            self.baseline_value, self.current_value, self.target_value, self.direction
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def variance(self) -> Decimal:
        """KPI variance: current minus target."""
        return self.current_value - self.target_value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def target_met(self) -> bool:
        """Whether the KPI has reached or beaten its target."""
        return target_met(self.current_value, self.target_value, self.direction)


# --- Summaries -------------------------------------------------------------
class GoalKPISummary(BaseModel):
    """KPI attainment rollup for a goal."""

    goal_id: uuid.UUID
    title: str
    status: GoalStatus
    kpi_count: int
    kpis_met: int
    average_attainment: float | None


class InitiativeSummary(BaseModel):
    """Attainment rollup across an initiative's goals and KPIs."""

    initiative_id: uuid.UUID
    name: str
    status: InitiativeStatus
    goal_count: int
    kpi_count: int
    kpis_met: int
    average_attainment: float | None
    goals: list[GoalKPISummary]
