"""Intelligence Layer service.

A thin, read-only coordinator over the Intelligence engines. It currently
surfaces the Performance (EVM) engine; later phases add Variance, Forecast,
Heat Map, KPI, Recommendation and Transformation engines behind the same
service. No persistence — every call assembles a fresh snapshot from current
data.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.intelligence.engines.early_warning import EarlyWarningEngine
from app.modules.intelligence.engines.forecast import ForecastEngine
from app.modules.intelligence.engines.heatmap import HeatMapEngine
from app.modules.intelligence.engines.kpi import KPIEngine
from app.modules.intelligence.engines.performance import PerformanceEngine
from app.modules.intelligence.engines.recommendation import RecommendationEngine
from app.modules.intelligence.engines.resource_forecast import ResourceForecastEngine
from app.modules.intelligence.engines.transformation import (
    TransformationIntelligenceEngine,
)
from app.modules.intelligence.engines.variance import VarianceEngine
from app.modules.intelligence.schemas import (
    BenefitsVariance,
    EarlyWarningReport,
    ExecutiveKPIs,
    HeatMap,
    KPIVariance,
    ProjectEarlyWarning,
    ProjectForecast,
    ProjectPerformance,
    ProjectVariance,
    RecommendationReport,
    ResourceDemandForecast,
    ResourceVarianceSummary,
    RiskHeatMap,
    RollupForecast,
    RollupPerformance,
    RollupVariance,
    TransformationForecast,
    TransformationIntelligence,
)

logger = get_logger(__name__)


class IntelligenceService:
    """Read-only analytics over the platform, scoped to the caller's tenant."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        self._org_id = organization_id
        self._actor_id = actor_id
        self.performance = PerformanceEngine(uow.session, organization_id)
        self.variance = VarianceEngine(uow.session, organization_id)
        self.forecast = ForecastEngine(uow.session, organization_id)
        self.heatmap = HeatMapEngine(uow.session, organization_id)
        self.kpi = KPIEngine(uow.session, organization_id)
        self.recommendations = RecommendationEngine(uow.session, organization_id)
        self.resource_forecast = ResourceForecastEngine(uow.session, organization_id)
        self.early_warning = EarlyWarningEngine(uow.session, organization_id)
        self.transformation = TransformationIntelligenceEngine(uow.session, organization_id)

    def project_performance(
        self, project_id: uuid.UUID, *, as_of: date | None
    ) -> ProjectPerformance:
        """Return an EVM performance snapshot for a project."""
        return self.performance.project_performance(project_id, as_of=as_of)

    def program_performance(
        self, program_id: uuid.UUID, *, as_of: date | None
    ) -> RollupPerformance:
        """Return an aggregated EVM snapshot for a program."""
        return self.performance.program_performance(program_id, as_of=as_of)

    def portfolio_performance(
        self, portfolio_id: uuid.UUID, *, as_of: date | None
    ) -> RollupPerformance:
        """Return an aggregated EVM snapshot for a portfolio."""
        return self.performance.portfolio_performance(portfolio_id, as_of=as_of)

    def transformation_performance(self, *, as_of: date | None) -> RollupPerformance:
        """Return an organization-wide aggregated EVM snapshot."""
        return self.performance.transformation_performance(as_of=as_of)

    # -- Variance -------------------------------------------------------
    def project_variance(self, project_id: uuid.UUID, *, as_of: date | None) -> ProjectVariance:
        """Return schedule/cost/budget/forecast variance for a project."""
        return self.variance.project_variance(project_id, as_of=as_of)

    def program_variance(self, program_id: uuid.UUID, *, as_of: date | None) -> RollupVariance:
        """Return aggregated variance for a program."""
        return self.variance.program_variance(program_id, as_of=as_of)

    def portfolio_variance(self, portfolio_id: uuid.UUID, *, as_of: date | None) -> RollupVariance:
        """Return aggregated variance for a portfolio."""
        return self.variance.portfolio_variance(portfolio_id, as_of=as_of)

    def department_variance(
        self, department_id: uuid.UUID, *, as_of: date | None
    ) -> RollupVariance:
        """Return aggregated variance for a department."""
        return self.variance.department_variance(department_id, as_of=as_of)

    def transformation_variance(self, *, as_of: date | None) -> RollupVariance:
        """Return organization-wide aggregated variance."""
        return self.variance.transformation_variance(as_of=as_of)

    def resource_variance(self, *, as_of: date | None) -> ResourceVarianceSummary:
        """Return resource capacity variance across active resources."""
        return self.variance.resource_variance(as_of=as_of)

    def benefits_variance_project(self, project_id: uuid.UUID) -> BenefitsVariance:
        """Return realised-vs-target benefits variance for a project."""
        return self.variance.benefits_variance_project(project_id)

    def benefits_variance_portfolio(self, portfolio_id: uuid.UUID) -> BenefitsVariance:
        """Return benefits variance across a portfolio's projects."""
        return self.variance.benefits_variance_portfolio(portfolio_id)

    def benefits_variance_transformation(self) -> BenefitsVariance:
        """Return organisation-wide benefits variance."""
        return self.variance.benefits_variance_transformation()

    def kpi_variance_transformation(self) -> KPIVariance:
        """Return organisation-wide KPI target attainment."""
        return self.variance.kpi_variance_transformation()

    def kpi_variance_initiative(self, initiative_id: uuid.UUID) -> KPIVariance:
        """Return KPI target attainment for an initiative."""
        return self.variance.kpi_variance_initiative(initiative_id)

    def kpi_variance_portfolio(self, portfolio_id: uuid.UUID) -> KPIVariance:
        """Return KPI target attainment across a portfolio's initiatives."""
        return self.variance.kpi_variance_portfolio(portfolio_id)

    def resource_demand_forecast(self, *, as_of: date | None, weeks: int) -> ResourceDemandForecast:
        """Return the time-phased resource demand vs capacity forecast."""
        return self.resource_forecast.forecast(as_of=as_of, weeks=weeks)

    def early_warning_transformation(self, *, as_of: date | None) -> EarlyWarningReport:
        """Return leading-indicator warnings across all active projects."""
        return self.early_warning.transformation(as_of=as_of)

    def early_warning_project(
        self, project_id: uuid.UUID, *, as_of: date | None
    ) -> ProjectEarlyWarning:
        """Return leading-indicator warnings for one project."""
        return self.early_warning.project(project_id, as_of=as_of)

    # -- Board-pack exports ---------------------------------------------
    def board_pack_xlsx(self) -> bytes:
        """Render the transformation board pack as an XLSX workbook."""
        from app.modules.intelligence import exports

        return exports.board_pack_xlsx(self)

    def board_pack_pdf(self) -> bytes:
        """Render the transformation board pack as a PDF."""
        from app.modules.intelligence import exports

        return exports.board_pack_pdf(self)

    # -- Forecast -------------------------------------------------------
    def project_forecast(self, project_id: uuid.UUID, *, as_of: date | None) -> ProjectForecast:
        """Return schedule/budget forecast for a project."""
        return self.forecast.project_forecast(project_id, as_of=as_of)

    def program_forecast(self, program_id: uuid.UUID, *, as_of: date | None) -> RollupForecast:
        """Return aggregated forecast for a program."""
        return self.forecast.program_forecast(program_id, as_of=as_of)

    def portfolio_forecast(self, portfolio_id: uuid.UUID, *, as_of: date | None) -> RollupForecast:
        """Return aggregated forecast for a portfolio."""
        return self.forecast.portfolio_forecast(portfolio_id, as_of=as_of)

    def transformation_forecast(self, *, as_of: date | None) -> TransformationForecast:
        """Return organization-wide forecast, success outlook and resource shortage."""
        return self.forecast.transformation_forecast(as_of=as_of)

    # -- Heat maps ------------------------------------------------------
    def portfolio_heatmap(self, portfolio_id: uuid.UUID, *, as_of: date | None) -> HeatMap:
        """Return a project × dimension RAG grid for a portfolio."""
        return self.heatmap.portfolio_heatmap(portfolio_id, as_of=as_of)

    def program_heatmap(self, program_id: uuid.UUID, *, as_of: date | None) -> HeatMap:
        """Return a project × dimension RAG grid for a program."""
        return self.heatmap.program_heatmap(program_id, as_of=as_of)

    def transformation_heatmap(self, *, as_of: date | None) -> HeatMap:
        """Return a project × dimension RAG grid for the whole organization."""
        return self.heatmap.transformation_heatmap(as_of=as_of)

    def risk_heatmap(self, *, as_of: date | None) -> RiskHeatMap:
        """Return the probability × impact risk matrix."""
        return self.heatmap.risk_heatmap(as_of=as_of)

    def resource_heatmap(self, *, as_of: date | None) -> HeatMap:
        """Return a resource utilisation heat map."""
        return self.heatmap.resource_heatmap(as_of=as_of)

    # -- Executive KPIs -------------------------------------------------
    def executive_kpis(self, *, as_of: date | None) -> ExecutiveKPIs:
        """Return the organization-wide executive scorecard."""
        return self.kpi.executive_kpis(as_of=as_of)

    def portfolio_kpis(self, portfolio_id: uuid.UUID, *, as_of: date | None) -> ExecutiveKPIs:
        """Return a portfolio-scoped executive scorecard."""
        return self.kpi.portfolio_kpis(portfolio_id, as_of=as_of)

    # -- Recommendations ------------------------------------------------
    def project_recommendations(
        self, project_id: uuid.UUID, *, as_of: date | None
    ) -> RecommendationReport:
        """Return prioritised recommendations for a project."""
        return self.recommendations.project_recommendations(project_id, as_of=as_of)

    def portfolio_recommendations(
        self, portfolio_id: uuid.UUID, *, as_of: date | None
    ) -> RecommendationReport:
        """Return prioritised recommendations across a portfolio."""
        return self.recommendations.portfolio_recommendations(portfolio_id, as_of=as_of)

    def transformation_recommendations(self, *, as_of: date | None) -> RecommendationReport:
        """Return organisation-wide recommendations."""
        return self.recommendations.transformation_recommendations(as_of=as_of)

    # -- Transformation intelligence ------------------------------------
    def transformation_intelligence(self, *, as_of: date | None) -> TransformationIntelligence:
        """Return the consolidated executive intelligence briefing."""
        return self.transformation.transformation_intelligence(as_of=as_of)
