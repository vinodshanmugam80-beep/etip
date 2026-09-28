"""The Transformation Intelligence Engine.

A service-independent engine that assembles a single consolidated executive
briefing for the whole transformation, composing the Performance, Forecast, Heat
Map and Recommendation engines with the project risk/issue rollups. It produces
the headline health, financials, success outlook, heat-map summary, resource
shortage, a plain-language narrative and the top prioritised recommendations.
Pure read; no schema change.

The narrative is a deterministic template over the computed numbers — not an LLM
generation — so the briefing is reproducible and auditable.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.modules.intelligence.engines.forecast import ForecastEngine
from app.modules.intelligence.engines.heatmap import HeatMapEngine
from app.modules.intelligence.engines.performance import PerformanceEngine
from app.modules.intelligence.engines.recommendation import RecommendationEngine
from app.modules.intelligence.schemas import TransformationIntelligence
from app.modules.project.repository import ProjectRepository

_ATTENTION_LIMIT = 5
_HIGH_RISK_SCORE = 15


class TransformationIntelligenceEngine:
    """Assembles the consolidated transformation intelligence briefing."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self.projects = ProjectRepository(session)
        self.performance = PerformanceEngine(session, organization_id)
        self.forecast = ForecastEngine(session, organization_id)
        self.heatmap = HeatMapEngine(session, organization_id)
        self.recommendations = RecommendationEngine(session, organization_id)

    def transformation_intelligence(
        self, *, as_of: date | None = None
    ) -> TransformationIntelligence:
        """Return the consolidated executive intelligence briefing."""
        as_of = as_of or utcnow().date()
        perf = self.performance.transformation_performance(as_of=as_of)
        fcst = self.forecast.transformation_forecast(as_of=as_of)
        heat = self.heatmap.transformation_heatmap(as_of=as_of)
        recs = self.recommendations.transformation_recommendations(as_of=as_of)

        projects = self.projects.search(self._org_id, limit=1000)
        projects_high_risk = sum(1 for p in projects if p.risk_score >= _HIGH_RISK_SCORE)
        open_issues = sum(p.issue_count for p in projects)
        projects_red = sum(1 for b in perf.breakdown if b.rag == "red")

        # Budget figures come from the same EVM basis as the dashboard's cost
        # tiles (EAC / VAC), so the narrative and the tiles always reconcile.
        # (The Forecast tab keeps the schedule-based forecast, a distinct method.)
        forecast_cost = perf.evm.eac
        budget_overrun = f"{Decimal(perf.evm.eac) - Decimal(perf.evm.bac):.2f}"

        narrative = self._narrative(
            success_label=fcst.success_label,
            success_score=fcst.success_score,
            projects_red=projects_red,
            projects_total=perf.project_count,
            budget_overrun=budget_overrun,
            projects_slipping=fcst.projects_slipping,
            projects_high_risk=projects_high_risk,
            over_allocated=fcst.resource_shortage.over_allocated,
        )
        return TransformationIntelligence(
            as_of=as_of,
            health=perf.health,
            spi=perf.evm.spi,
            cpi=perf.evm.cpi,
            success_score=fcst.success_score,
            success_label=fcst.success_label,
            bac=perf.evm.bac,
            forecast_cost=forecast_cost,
            budget_overrun=budget_overrun,
            projects_total=perf.project_count,
            projects_red=projects_red,
            projects_high_risk=projects_high_risk,
            open_issues=open_issues,
            resource_shortage=fcst.resource_shortage,
            heat_summary=heat.summary,
            narrative=narrative,
            attention=recs.recommendations[:_ATTENTION_LIMIT],
        )

    @staticmethod
    def _narrative(
        *,
        success_label: str,
        success_score: int,
        projects_red: int,
        projects_total: int,
        budget_overrun: str,
        projects_slipping: int,
        projects_high_risk: int,
        over_allocated: int,
    ) -> str:
        parts = [
            f"Transformation success is {success_label} ({success_score}/100).",
            f"{projects_red} of {projects_total} projects are red.",
        ]
        if budget_overrun != "0.00" and not budget_overrun.startswith("-"):
            parts.append(f"Forecast is over budget by {budget_overrun}.")
        if projects_slipping:
            parts.append(f"{projects_slipping} project(s) are slipping.")
        if projects_high_risk:
            parts.append(f"{projects_high_risk} project(s) carry high risk exposure.")
        if over_allocated:
            parts.append(f"{over_allocated} resource(s) are over-allocated.")
        return " ".join(parts)
