"""HTTP routes for the Intelligence Layer.

Phase 1a exposes the Performance (EVM) engine: per-project metrics and program /
portfolio / transformation rollups. All routes require ``intelligence:read`` and
accept an optional ``as_of`` date (defaults to today) used for Planned Value.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.dependencies import IntelligenceServiceDep, require_permission
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

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


@router.get(
    "/performance/projects/{project_id}",
    response_model=ProjectPerformance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Project performance (EVM)",
)
def project_performance(
    project_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> ProjectPerformance:
    """Return an Earned-Value performance and health snapshot for a project."""
    return service.project_performance(project_id, as_of=as_of)


@router.get(
    "/performance/programs/{program_id}",
    response_model=RollupPerformance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Program performance (aggregated EVM)",
)
def program_performance(
    program_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RollupPerformance:
    """Return an aggregated Earned-Value snapshot for a program."""
    return service.program_performance(program_id, as_of=as_of)


@router.get(
    "/performance/portfolios/{portfolio_id}",
    response_model=RollupPerformance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Portfolio performance (aggregated EVM)",
)
def portfolio_performance(
    portfolio_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RollupPerformance:
    """Return an aggregated Earned-Value snapshot for a portfolio."""
    return service.portfolio_performance(portfolio_id, as_of=as_of)


@router.get(
    "/performance/transformation",
    response_model=RollupPerformance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Transformation performance (organization-wide EVM)",
)
def transformation_performance(
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RollupPerformance:
    """Return an organization-wide aggregated Earned-Value snapshot."""
    return service.transformation_performance(as_of=as_of)


# --- Variance --------------------------------------------------------------
@router.get(
    "/variance/projects/{project_id}",
    response_model=ProjectVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Project variance (schedule/cost/budget/forecast)",
)
def project_variance(
    project_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> ProjectVariance:
    """Return schedule / cost / budget / forecast variance for a project."""
    return service.project_variance(project_id, as_of=as_of)


@router.get(
    "/variance/programs/{program_id}",
    response_model=RollupVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Program variance (aggregated)",
)
def program_variance(
    program_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RollupVariance:
    """Return aggregated variance for a program."""
    return service.program_variance(program_id, as_of=as_of)


@router.get(
    "/variance/portfolios/{portfolio_id}",
    response_model=RollupVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Portfolio variance (aggregated)",
)
def portfolio_variance(
    portfolio_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RollupVariance:
    """Return aggregated variance for a portfolio."""
    return service.portfolio_variance(portfolio_id, as_of=as_of)


@router.get(
    "/variance/departments/{department_id}",
    response_model=RollupVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Department variance (aggregated)",
)
def department_variance(
    department_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RollupVariance:
    """Return aggregated variance for a department."""
    return service.department_variance(department_id, as_of=as_of)


@router.get(
    "/variance/transformation",
    response_model=RollupVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Transformation variance (organization-wide)",
)
def transformation_variance(
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RollupVariance:
    """Return organization-wide aggregated variance."""
    return service.transformation_variance(as_of=as_of)


@router.get(
    "/variance/resources",
    response_model=ResourceVarianceSummary,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Resource capacity variance",
)
def resource_variance(
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> ResourceVarianceSummary:
    """Return capacity-vs-allocation variance across active resources."""
    return service.resource_variance(as_of=as_of)


# --- Benefits variance (Phase 2a data) -------------------------------------
@router.get(
    "/variance/benefits/projects/{project_id}",
    response_model=BenefitsVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Benefits variance (project)",
)
def benefits_variance_project(
    project_id: uuid.UUID, service: IntelligenceServiceDep
) -> BenefitsVariance:
    """Return realised-vs-target benefits variance for a project."""
    return service.benefits_variance_project(project_id)


@router.get(
    "/variance/benefits/portfolios/{portfolio_id}",
    response_model=BenefitsVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Benefits variance (portfolio)",
)
def benefits_variance_portfolio(
    portfolio_id: uuid.UUID, service: IntelligenceServiceDep
) -> BenefitsVariance:
    """Return benefits variance across a portfolio's projects."""
    return service.benefits_variance_portfolio(portfolio_id)


@router.get(
    "/variance/benefits/transformation",
    response_model=BenefitsVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Benefits variance (organisation-wide)",
)
def benefits_variance_transformation(
    service: IntelligenceServiceDep,
) -> BenefitsVariance:
    """Return organisation-wide benefits variance."""
    return service.benefits_variance_transformation()


# --- KPI variance (Phase 2c data) ------------------------------------------
@router.get(
    "/variance/kpis/transformation",
    response_model=KPIVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="KPI variance (organisation-wide)",
)
def kpi_variance_transformation(service: IntelligenceServiceDep) -> KPIVariance:
    """Return organisation-wide KPI target attainment."""
    return service.kpi_variance_transformation()


@router.get(
    "/variance/kpis/initiatives/{initiative_id}",
    response_model=KPIVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="KPI variance (initiative)",
)
def kpi_variance_initiative(
    initiative_id: uuid.UUID, service: IntelligenceServiceDep
) -> KPIVariance:
    """Return KPI target attainment for an initiative."""
    return service.kpi_variance_initiative(initiative_id)


@router.get(
    "/variance/kpis/portfolios/{portfolio_id}",
    response_model=KPIVariance,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="KPI variance (portfolio)",
)
def kpi_variance_portfolio(portfolio_id: uuid.UUID, service: IntelligenceServiceDep) -> KPIVariance:
    """Return KPI target attainment across a portfolio's initiatives."""
    return service.kpi_variance_portfolio(portfolio_id)


@router.get(
    "/resource-forecast",
    response_model=ResourceDemandForecast,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Time-phased resource demand vs capacity",
)
def resource_forecast(
    service: IntelligenceServiceDep,
    weeks: int = Query(8, ge=1, le=26),
    as_of: date | None = Query(default=None),
) -> ResourceDemandForecast:
    """Return the resource demand forecast for the next N weekly periods."""
    return service.resource_demand_forecast(as_of=as_of, weeks=weeks)


# --- Board-pack exports ----------------------------------------------------
@router.get(
    "/exports/board-pack.xlsx",
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Download the board pack as an Excel workbook",
)
def export_board_pack_xlsx(service: IntelligenceServiceDep) -> Response:
    """Return the transformation board pack as an XLSX download."""
    return Response(
        content=service.board_pack_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=etip-board-pack.xlsx"},
    )


@router.get(
    "/exports/board-pack.pdf",
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Download the board pack as a PDF",
)
def export_board_pack_pdf(service: IntelligenceServiceDep) -> Response:
    """Return the transformation board pack as a PDF download."""
    return Response(
        content=service.board_pack_pdf(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=etip-board-pack.pdf"},
    )


# --- Forecast --------------------------------------------------------------
@router.get(
    "/forecast/projects/{project_id}",
    response_model=ProjectForecast,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Project forecast (completion, slippage, overrun)",
)
def project_forecast(
    project_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> ProjectForecast:
    """Return schedule and budget forecast for a project."""
    return service.project_forecast(project_id, as_of=as_of)


@router.get(
    "/forecast/programs/{program_id}",
    response_model=RollupForecast,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Program forecast (aggregated)",
)
def program_forecast(
    program_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RollupForecast:
    """Return aggregated forecast for a program."""
    return service.program_forecast(program_id, as_of=as_of)


@router.get(
    "/forecast/portfolios/{portfolio_id}",
    response_model=RollupForecast,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Portfolio forecast (aggregated)",
)
def portfolio_forecast(
    portfolio_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RollupForecast:
    """Return aggregated forecast for a portfolio."""
    return service.portfolio_forecast(portfolio_id, as_of=as_of)


@router.get(
    "/forecast/transformation",
    response_model=TransformationForecast,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Transformation forecast (success outlook + resource shortage)",
)
def transformation_forecast(
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> TransformationForecast:
    """Return organization-wide forecast, success outlook and resource shortage."""
    return service.transformation_forecast(as_of=as_of)


# --- Heat maps -------------------------------------------------------------
@router.get(
    "/heatmap/portfolios/{portfolio_id}",
    response_model=HeatMap,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Portfolio heat map (project × dimension RAG)",
)
def portfolio_heatmap(
    portfolio_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> HeatMap:
    """Return a project × dimension RAG grid for a portfolio."""
    return service.portfolio_heatmap(portfolio_id, as_of=as_of)


@router.get(
    "/heatmap/programs/{program_id}",
    response_model=HeatMap,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Program heat map (project × dimension RAG)",
)
def program_heatmap(
    program_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> HeatMap:
    """Return a project × dimension RAG grid for a program."""
    return service.program_heatmap(program_id, as_of=as_of)


@router.get(
    "/heatmap/transformation",
    response_model=HeatMap,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Transformation heat map (organization-wide)",
)
def transformation_heatmap(
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> HeatMap:
    """Return a project × dimension RAG grid for the whole organization."""
    return service.transformation_heatmap(as_of=as_of)


@router.get(
    "/heatmap/risk",
    response_model=RiskHeatMap,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Risk heat map (probability × impact matrix)",
)
def risk_heatmap(
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RiskHeatMap:
    """Return the probability × impact matrix of open-risk counts."""
    return service.risk_heatmap(as_of=as_of)


@router.get(
    "/heatmap/resources",
    response_model=HeatMap,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Resource utilisation heat map",
)
def resource_heatmap(
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> HeatMap:
    """Return a resource utilisation heat map."""
    return service.resource_heatmap(as_of=as_of)


# --- Executive KPIs --------------------------------------------------------
@router.get(
    "/kpi/executive",
    response_model=ExecutiveKPIs,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Executive KPI scorecard (organization-wide)",
)
def executive_kpis(
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> ExecutiveKPIs:
    """Return the organization-wide executive scorecard."""
    return service.executive_kpis(as_of=as_of)


@router.get(
    "/kpi/portfolios/{portfolio_id}",
    response_model=ExecutiveKPIs,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Executive KPI scorecard (portfolio)",
)
def portfolio_kpis(
    portfolio_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> ExecutiveKPIs:
    """Return a portfolio-scoped executive scorecard."""
    return service.portfolio_kpis(portfolio_id, as_of=as_of)


# --- Recommendations -------------------------------------------------------
@router.get(
    "/recommendations/projects/{project_id}",
    response_model=RecommendationReport,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Project recommendations (prioritised)",
)
def project_recommendations(
    project_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RecommendationReport:
    """Return prioritised, actionable recommendations for a project."""
    return service.project_recommendations(project_id, as_of=as_of)


@router.get(
    "/recommendations/portfolios/{portfolio_id}",
    response_model=RecommendationReport,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Portfolio recommendations (prioritised)",
)
def portfolio_recommendations(
    portfolio_id: uuid.UUID,
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RecommendationReport:
    """Return prioritised recommendations across a portfolio's projects."""
    return service.portfolio_recommendations(portfolio_id, as_of=as_of)


@router.get(
    "/recommendations/transformation",
    response_model=RecommendationReport,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Transformation recommendations (organisation-wide)",
)
def transformation_recommendations(
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> RecommendationReport:
    """Return organisation-wide prioritised recommendations."""
    return service.transformation_recommendations(as_of=as_of)


# --- Transformation intelligence -------------------------------------------
@router.get(
    "/transformation",
    response_model=TransformationIntelligence,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Transformation intelligence briefing (consolidated)",
)
def transformation_intelligence(
    service: IntelligenceServiceDep,
    as_of: date | None = Query(default=None),
) -> TransformationIntelligence:
    """Return the consolidated executive intelligence briefing."""
    return service.transformation_intelligence(as_of=as_of)


@router.get(
    "/early-warning",
    response_model=EarlyWarningReport,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Early-warning signals across active projects",
)
def early_warning(
    service: IntelligenceServiceDep, as_of: date | None = Query(default=None)
) -> EarlyWarningReport:
    """Return leading-indicator warnings before projects turn red."""
    return service.early_warning_transformation(as_of=as_of)


@router.get(
    "/early-warning/projects/{project_id}",
    response_model=ProjectEarlyWarning,
    dependencies=[Depends(require_permission("intelligence:read"))],
    summary="Early-warning signals for one project",
)
def early_warning_project(
    project_id: uuid.UUID, service: IntelligenceServiceDep, as_of: date | None = Query(default=None)
) -> ProjectEarlyWarning:
    """Return leading-indicator warnings for a single project."""
    return service.early_warning_project(project_id, as_of=as_of)
