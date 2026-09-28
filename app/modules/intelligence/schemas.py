"""Pydantic v2 schemas for the Intelligence Layer.

Performance schemas model Earned Value Management (EVM) metrics and derived
health for a project and for program / portfolio / transformation rollups. Money
values are fixed-2-decimal strings; performance indices are floats (or ``null``
when a divisor is unavailable).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class EVMMetrics(BaseModel):
    """Earned Value Management metrics for a scope."""

    bac: str  # Budget at Completion
    pv: str | None  # Planned Value
    ev: str  # Earned Value
    ac: str  # Actual Cost
    sv: str | None  # Schedule Variance (EV - PV)
    cv: str  # Cost Variance (EV - AC)
    spi: float | None  # Schedule Performance Index (EV / PV)
    cpi: float | None  # Cost Performance Index (EV / AC)
    eac: str  # Estimate at Completion
    etc: str  # Estimate to Complete
    vac: str  # Variance at Completion (BAC - EAC)
    tcpi: float | None  # To-Complete Performance Index
    planned_percent: float | None
    actual_percent: float


class EffortMetrics(BaseModel):
    """Effort (hours) metrics derived from tasks."""

    estimate_hours: str
    logged_hours: str
    effort_burn_ratio: float | None


class HealthResult(BaseModel):
    """A RAG health rating with the drivers behind it."""

    rag: str  # green | amber | red | not_started | unknown
    drivers: list[str]


class ProjectPerformance(BaseModel):
    """Full performance snapshot for a single project."""

    scope: str = "project"
    project_id: uuid.UUID
    code: str
    name: str
    as_of: date
    evm: EVMMetrics
    effort: EffortMetrics
    health: HealthResult
    risk_score: int
    issue_count: int


class PerformanceBreakdownItem(BaseModel):
    """A child project's headline numbers within a rollup."""

    project_id: uuid.UUID
    code: str
    rag: str
    spi: float | None
    cpi: float | None
    bac: str  # Budget at Completion
    ac: str  # Actual Cost (cost to date)
    eac: str  # Estimate at Completion
    etc: str  # Estimate to Complete


class RollupPerformance(BaseModel):
    """Aggregated performance for a program, portfolio or the transformation."""

    scope: str  # program | portfolio | transformation
    scope_id: uuid.UUID | None
    scope_label: str
    as_of: date
    project_count: int
    evm: EVMMetrics
    health: HealthResult
    breakdown: list[PerformanceBreakdownItem]


# --- Variance engine -------------------------------------------------------
class VarianceItem(BaseModel):
    """One variance measure: amount, percent, and whether it's favourable."""

    label: str
    amount: str | None
    percent: float | None
    favourable: bool


class ProjectVariance(BaseModel):
    """Schedule / cost / budget / forecast variance for a single project."""

    scope: str = "project"
    project_id: uuid.UUID
    code: str
    name: str
    as_of: date
    schedule: VarianceItem
    cost: VarianceItem
    budget: VarianceItem
    forecast: VarianceItem


class VarianceBreakdownItem(BaseModel):
    """A child project's headline variance amounts within a rollup."""

    project_id: uuid.UUID
    code: str
    schedule_amount: str | None
    cost_amount: str
    budget_amount: str


class RollupVariance(BaseModel):
    """Aggregated variance for a program, portfolio, department or transformation."""

    scope: str  # program | portfolio | department | transformation
    scope_id: uuid.UUID | None
    scope_label: str
    as_of: date
    project_count: int
    schedule: VarianceItem
    cost: VarianceItem
    budget: VarianceItem
    forecast: VarianceItem
    breakdown: list[VarianceBreakdownItem]


class ResourceVarianceItem(BaseModel):
    """Capacity-vs-allocation variance for a single resource."""

    resource_id: uuid.UUID
    name: str
    capacity_percent: int
    allocated_percent: int
    variance_percent: int
    status: str  # over_allocated | under_utilized | balanced


class ResourceVarianceSummary(BaseModel):
    """Organization-wide resource capacity variance."""

    scope: str = "resource"
    as_of: date
    resource_count: int
    over_allocated: int
    under_utilized: int
    balanced: int
    items: list[ResourceVarianceItem]


# --- Benefits variance (Phase 2a data) -------------------------------------
class BenefitsVariance(BaseModel):
    """Realised-vs-target benefits variance for a scope."""

    scope: str  # project | portfolio | transformation
    scope_id: uuid.UUID | None
    scope_label: str
    benefit_count: int
    total_target: Decimal
    total_realized: Decimal
    variance: Decimal  # realised - target (negative = shortfall)
    realization_percent: float | None
    favourable: bool


# --- KPI variance (Phase 2c data) ------------------------------------------
class KPIVarianceItem(BaseModel):
    """Current-vs-target variance for a single KPI."""

    kpi_id: uuid.UUID
    name: str
    unit: str
    current_value: Decimal
    target_value: Decimal
    variance: Decimal
    attainment_percent: float | None
    on_target: bool


class KPIVariance(BaseModel):
    """KPI target attainment across a scope."""

    scope: str  # transformation | initiative
    scope_id: uuid.UUID | None
    scope_label: str
    kpi_count: int
    kpis_on_target: int
    kpis_off_target: int
    average_attainment: float | None
    items: list[KPIVarianceItem]


# --- Resource demand forecast ---------------------------------------------
class ForecastPeriod(BaseModel):
    """One time bucket in the resource demand forecast."""

    index: int
    start_date: date
    end_date: date


class ResourceDemandRow(BaseModel):
    """A resource's demand across the horizon (percent of capacity)."""

    resource_id: uuid.UUID
    resource_name: str
    demand: list[int]
    over_periods: int
    peak_demand: int


class DemandPeriodSummary(BaseModel):
    """Aggregate demand for one period across all resources."""

    index: int
    start_date: date
    end_date: date
    resource_count: int
    total_demand_percent: int
    over_allocated_count: int
    average_demand_percent: float


class ResourceDemandForecast(BaseModel):
    """Time-phased resource demand vs capacity."""

    as_of: date
    period_days: int
    periods: list[ForecastPeriod]
    summary: list[DemandPeriodSummary]
    resources: list[ResourceDemandRow]


# --- Forecast engine -------------------------------------------------------
class ScheduleForecast(BaseModel):
    """Projected completion and slippage from schedule performance."""

    baseline_end: date | None
    forecast_completion: date | None
    slippage_days: int | None
    will_slip: bool
    basis: str


class BudgetForecast(BaseModel):
    """Projected cost at completion and overrun from cost performance."""

    bac: str
    forecast_cost: str  # EAC
    overrun_amount: str
    overrun_percent: float | None
    will_overrun: bool


class ProjectForecast(BaseModel):
    """Forecast snapshot for a single project."""

    scope: str = "project"
    project_id: uuid.UUID
    code: str
    name: str
    as_of: date
    schedule: ScheduleForecast
    budget: BudgetForecast


class ForecastBreakdownItem(BaseModel):
    """A child project's headline forecast within a rollup."""

    project_id: uuid.UUID
    code: str
    forecast_completion: date | None
    slippage_days: int | None
    overrun_amount: str


class RollupForecast(BaseModel):
    """Aggregated forecast for a program, portfolio or department."""

    scope: str
    scope_id: uuid.UUID | None
    scope_label: str
    as_of: date
    project_count: int
    bac: str
    forecast_cost: str
    budget_overrun: str
    projects_overrunning: int
    projects_slipping: int
    worst_slippage_days: int | None
    breakdown: list[ForecastBreakdownItem]


class ResourceShortage(BaseModel):
    """Whether resource demand exceeds capacity (over-allocation signal)."""

    over_allocated: int
    total_excess_percent: int
    shortage: bool


class TransformationForecast(BaseModel):
    """Organization-wide forecast plus a success outlook and resource shortage."""

    scope: str = "transformation"
    as_of: date
    project_count: int
    bac: str
    forecast_cost: str
    budget_overrun: str
    projects_overrunning: int
    projects_slipping: int
    worst_slippage_days: int | None
    success_score: int  # 0-100 heuristic
    success_label: str  # likely | at_risk | unlikely
    resource_shortage: ResourceShortage
    breakdown: list[ForecastBreakdownItem]


# --- Heat map engine -------------------------------------------------------
class HeatCell(BaseModel):
    """One cell of a dimensional heat map: a subject × dimension RAG."""

    row_key: str
    row_label: str
    column: str
    rag: str
    detail: str | None = None


class HeatMap(BaseModel):
    """A subject × dimension RAG grid (portfolio / program / transformation / resource)."""

    scope: str
    scope_id: uuid.UUID | None
    scope_label: str
    as_of: date
    columns: list[str]
    cells: list[HeatCell]
    summary: dict[str, int]


class RiskHeatCell(BaseModel):
    """A cell of the probability × impact risk matrix."""

    probability: int
    impact: int
    count: int
    severity: str


class RiskHeatMap(BaseModel):
    """The classic probability × impact risk exposure matrix (open risks)."""

    scope: str = "risk"
    as_of: date
    max_probability: int
    max_impact: int
    total_open: int
    cells: list[RiskHeatCell]


# --- Executive KPI engine --------------------------------------------------
class KPIItem(BaseModel):
    """A single executive KPI value, optionally RAG-rated."""

    key: str
    label: str
    value: str
    unit: str | None = None
    rag: str | None = None


class KPIGroup(BaseModel):
    """A named group of related KPIs."""

    name: str
    items: list[KPIItem]


class ExecutiveKPIs(BaseModel):
    """An executive KPI scorecard for the org or a portfolio."""

    scope: str
    scope_id: uuid.UUID | None
    scope_label: str
    as_of: date
    groups: list[KPIGroup]


# --- Recommendation engine -------------------------------------------------
class Recommendation(BaseModel):
    """A prioritised, actionable recommendation derived from the analytics."""

    subject_type: str  # project | resource | transformation
    subject_id: uuid.UUID | None
    subject_label: str
    category: str  # schedule | cost | risk | issue | resource | delivery
    priority: str  # high | medium | low
    title: str
    rationale: str
    recommended_action: str


class RecommendationReport(BaseModel):
    """A prioritised set of recommendations for a scope."""

    scope: str
    scope_id: uuid.UUID | None
    scope_label: str
    as_of: date
    total: int
    recommendations: list[Recommendation]


# --- Transformation intelligence -------------------------------------------
class TransformationIntelligence(BaseModel):
    """A consolidated executive intelligence briefing for the transformation."""

    scope: str = "transformation"
    as_of: date
    health: HealthResult
    spi: float | None
    cpi: float | None
    success_score: int
    success_label: str
    bac: str
    forecast_cost: str
    budget_overrun: str
    projects_total: int
    projects_red: int
    projects_high_risk: int
    open_issues: int
    resource_shortage: ResourceShortage
    heat_summary: dict[str, int]
    narrative: str
    attention: list[Recommendation]


class EarlyWarningSignal(BaseModel):
    """A single leading-indicator signal."""

    type: str
    severity: str  # watch | warning
    message: str
    recommendation: str


class ProjectEarlyWarning(BaseModel):
    """Early-warning signals for one project."""

    project_id: uuid.UUID
    code: str
    name: str
    level: str  # clear | watch | warning
    signals: list[EarlyWarningSignal]


class EarlyWarningReport(BaseModel):
    """Early-warning signals across the portfolio."""

    as_of: date
    projects_total: int
    projects_warning: int
    projects_watch: int
    items: list[ProjectEarlyWarning]
