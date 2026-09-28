"""The Recommendation Engine.

A service-independent intelligence engine that turns the analytics into
prioritised, actionable recommendations. It applies transparent, deterministic
rules to each project's EVM/forecast figures and its maintained risk/issue
rollups, plus an organisation-level resource-rebalancing rule. Pure read; no
schema change.

Rules are explicit (no ML/black box): every recommendation carries its rationale
and a suggested action, so the advice is auditable.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.base import utcnow
from app.modules.intelligence import evm
from app.modules.intelligence.engines.variance import VarianceEngine
from app.modules.intelligence.schemas import Recommendation, RecommendationReport
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Thresholds (shared with the RAG bands where sensible).
_CPI_HIGH = 0.85
_CPI_MED = 0.95
_SPI_HIGH = 0.85
_SPI_MED = 0.95
_OVERRUN_HIGH = 10.0  # percent
_RISK_CRITICAL = 15  # risk_score band (probability x impact)
_RISK_HIGH = 10
_ISSUE_HIGH = 20
_ISSUE_MED = 10


class RecommendationEngine:
    """Generates prioritised recommendations from the analytics."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self.projects = ProjectRepository(session)
        self.portfolios = PortfolioRepository(session)
        self.variance = VarianceEngine(session, organization_id)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def project_recommendations(
        self, project_id: uuid.UUID, *, as_of: date | None = None
    ) -> RecommendationReport:
        """Return recommendations for a single project."""
        as_of = as_of or utcnow().date()
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        recs = self._project_recs(project, as_of)
        return self._report(recs, "project", project.id, project.name, as_of)

    def portfolio_recommendations(
        self, portfolio_id: uuid.UUID, *, as_of: date | None = None
    ) -> RecommendationReport:
        """Return recommendations across a portfolio's projects."""
        as_of = as_of or utcnow().date()
        portfolio = self.portfolios.get(portfolio_id, organization_id=self._org_id)
        if portfolio is None:
            raise NotFoundError("Portfolio not found.")
        projects = self.projects.search(self._org_id, portfolio_id=portfolio_id, limit=500)
        recs: list[Recommendation] = []
        for project in projects:
            recs.extend(self._project_recs(project, as_of))
        return self._report(recs, "portfolio", portfolio_id, portfolio.name, as_of)

    def transformation_recommendations(self, *, as_of: date | None = None) -> RecommendationReport:
        """Return organisation-wide recommendations (projects + resources)."""
        as_of = as_of or utcnow().date()
        projects = self.projects.search(self._org_id, limit=1000)
        recs: list[Recommendation] = []
        for project in projects:
            recs.extend(self._project_recs(project, as_of))
        recs.extend(self._resource_recs(as_of))
        return self._report(recs, "transformation", None, "Transformation", as_of)

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------
    def _project_recs(self, project: Project, as_of: date) -> list[Recommendation]:
        raw = evm.raw_for_project(project, as_of)
        spi, cpi = evm.indices(raw)
        recs: list[Recommendation] = []

        if cpi is not None and cpi < _CPI_MED:
            priority = "high" if cpi < _CPI_HIGH else "medium"
            recs.append(
                self._rec(
                    project,
                    "cost",
                    priority,
                    "Cost performance below plan",
                    f"CPI is {cpi:.2f} (< {_CPI_MED}).",
                    "Review the cost baseline and EAC; identify overspend drivers.",
                )
            )

        if spi is not None and spi < _SPI_MED:
            priority = "high" if spi < _SPI_HIGH else "medium"
            recs.append(
                self._rec(
                    project,
                    "schedule",
                    priority,
                    "Schedule performance below plan",
                    f"SPI is {spi:.2f} (< {_SPI_MED}).",
                    "Build a recovery plan; re-sequence or add capacity to the critical work.",
                )
            )

        if raw.bac > 0:
            overrun_percent = float((evm.eac(raw) - raw.bac) / raw.bac) * 100
            if overrun_percent > 0:
                priority = "high" if overrun_percent > _OVERRUN_HIGH else "medium"
                recs.append(
                    self._rec(
                        project,
                        "cost",
                        priority,
                        "Projected budget overrun",
                        f"Forecast (EAC) exceeds budget by {overrun_percent:.1f}%.",
                        "Re-baseline the budget or reduce scope to bring EAC within BAC.",
                    )
                )

        if project.risk_score >= _RISK_HIGH:
            priority = "high" if project.risk_score >= _RISK_CRITICAL else "medium"
            recs.append(
                self._rec(
                    project,
                    "risk",
                    priority,
                    "Elevated risk exposure",
                    f"Highest open risk score is {project.risk_score} (1-25 scale).",
                    "Review and action mitigation plans for the top risks.",
                )
            )

        if project.issue_count >= _ISSUE_MED:
            priority = "high" if project.issue_count >= _ISSUE_HIGH else "medium"
            recs.append(
                self._rec(
                    project,
                    "issue",
                    priority,
                    "High open-issue volume",
                    f"{project.issue_count} open issues are recorded.",
                    "Triage and clear ageing issues; check for a systemic cause.",
                )
            )

        start = project.baseline_start_date
        if (
            start is not None
            and start < as_of
            and project.progress_percent == 0
            and not evm.started(raw)
        ):
            recs.append(
                self._rec(
                    project,
                    "delivery",
                    "medium",
                    "Not started past baseline start",
                    "The baseline start date has passed but no progress is recorded.",
                    "Confirm kickoff status and update the schedule or baseline.",
                )
            )
        return recs

    def _resource_recs(self, as_of: date) -> list[Recommendation]:
        summary = self.variance.resource_variance(as_of=as_of)
        if summary.over_allocated == 0:
            return []
        priority = "high" if summary.over_allocated >= 3 else "medium"
        return [
            Recommendation(
                subject_type="resource",
                subject_id=None,
                subject_label="Resource pool",
                category="resource",
                priority=priority,
                title="Resources over-allocated",
                rationale=f"{summary.over_allocated} resource(s) are allocated beyond 100%.",
                recommended_action="Rebalance assignments or add capacity to relieve the overload.",
            )
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _rec(
        project: Project,
        category: str,
        priority: str,
        title: str,
        rationale: str,
        action: str,
    ) -> Recommendation:
        return Recommendation(
            subject_type="project",
            subject_id=project.id,
            subject_label=project.code,
            category=category,
            priority=priority,
            title=title,
            rationale=rationale,
            recommended_action=action,
        )

    @staticmethod
    def _report(
        recs: Sequence[Recommendation],
        scope: str,
        scope_id: uuid.UUID | None,
        label: str,
        as_of: date,
    ) -> RecommendationReport:
        ordered = sorted(recs, key=lambda r: _PRIORITY_ORDER.get(r.priority, 3))
        return RecommendationReport(
            scope=scope,
            scope_id=scope_id,
            scope_label=label,
            as_of=as_of,
            total=len(ordered),
            recommendations=list(ordered),
        )
