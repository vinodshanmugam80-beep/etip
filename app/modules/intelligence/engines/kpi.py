"""The Executive KPI Engine.

A service-independent intelligence engine that assembles an executive scorecard
by composing the Performance, Forecast and Variance engines with open-risk,
open-issue and overdue-milestone counts. Pure read; no schema change.

KPI **variance against explicit targets** is deliberately not produced: no KPI
target model exists yet (that arrives with Business Goals, roadmap Phase 2c). The
KPIs here are RAG-rated against sensible performance thresholds, not fabricated
targets.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.modules.intelligence import evm
from app.modules.intelligence.engines.forecast import ForecastEngine
from app.modules.intelligence.engines.performance import PerformanceEngine
from app.modules.intelligence.engines.variance import VarianceEngine
from app.modules.intelligence.schemas import (
    ExecutiveKPIs,
    KPIGroup,
    KPIItem,
    ResourceVarianceSummary,
    RollupForecast,
    RollupPerformance,
    TransformationForecast,
)
from app.modules.issue.models import IssueStatus
from app.modules.issue.repository import IssueRepository
from app.modules.milestone.repository import MilestoneRepository
from app.modules.risk.models import RiskSeverity, RiskStatus
from app.modules.risk.repository import RiskRepository


class KPIEngine:
    """Assembles executive KPI scorecards for the org or a portfolio."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self.performance = PerformanceEngine(session, organization_id)
        self.forecast = ForecastEngine(session, organization_id)
        self.variance = VarianceEngine(session, organization_id)
        self.risks = RiskRepository(session)
        self.issues = IssueRepository(session)
        self.milestones = MilestoneRepository(session)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def executive_kpis(self, *, as_of: date | None = None) -> ExecutiveKPIs:
        """Return the organization-wide executive scorecard."""
        as_of = as_of or utcnow().date()
        perf = self.performance.transformation_performance(as_of=as_of)
        fcst = self.forecast.transformation_forecast(as_of=as_of)
        resvar = self.variance.resource_variance(as_of=as_of)
        project_ids = {item.project_id for item in perf.breakdown}
        groups = self._groups(
            perf,
            fcst,
            resvar,
            project_ids,
            as_of,
            fcst_success=(fcst.success_score, fcst.success_label),
        )
        return ExecutiveKPIs(
            scope="transformation",
            scope_id=None,
            scope_label="Transformation",
            as_of=as_of,
            groups=groups,
        )

    def portfolio_kpis(
        self, portfolio_id: uuid.UUID, *, as_of: date | None = None
    ) -> ExecutiveKPIs:
        """Return a portfolio-scoped scorecard (raises 404 if unknown)."""
        as_of = as_of or utcnow().date()
        perf = self.performance.portfolio_performance(portfolio_id, as_of=as_of)
        fcst = self.forecast.portfolio_forecast(portfolio_id, as_of=as_of)
        project_ids = {item.project_id for item in perf.breakdown}
        groups = self._groups(perf, fcst, None, project_ids, as_of, fcst_success=None)
        return ExecutiveKPIs(
            scope="portfolio",
            scope_id=portfolio_id,
            scope_label=perf.scope_label,
            as_of=as_of,
            groups=groups,
        )

    # ------------------------------------------------------------------
    # Group assembly
    # ------------------------------------------------------------------
    def _groups(
        self,
        perf: RollupPerformance,
        fcst: RollupForecast | TransformationForecast,
        resvar: ResourceVarianceSummary | None,
        project_ids: set[uuid.UUID],
        as_of: date,
        *,
        fcst_success: tuple[int, str] | None,
    ) -> list[KPIGroup]:
        green, amber, red = self._rag_counts(perf)
        open_risks, high_risks = self._risk_counts(project_ids)
        open_issues = self._issue_count(project_ids)
        overdue = self._overdue_milestones(project_ids, as_of)

        delivery = [
            KPIItem(key="projects_total", label="Projects", value=str(perf.project_count)),
            KPIItem(
                key="projects_green",
                label="Green projects",
                value=str(green),
                rag="green",
            ),
            KPIItem(
                key="projects_amber",
                label="Amber projects",
                value=str(amber),
                rag="amber",
            ),
            KPIItem(
                key="projects_red",
                label="Red projects",
                value=str(red),
                rag="red" if red > 0 else "green",
            ),
        ]
        if fcst_success is not None:
            score, label = fcst_success
            delivery.append(
                KPIItem(
                    key="success_outlook",
                    label="Transformation success",
                    value=label,
                    unit=f"{score}/100",
                    rag=self._score_rag(score),
                )
            )

        financials = [
            KPIItem(key="budget", label="Budget (BAC)", value=perf.evm.bac, unit="currency"),
            KPIItem(
                key="forecast_cost",
                label="Forecast cost (EAC)",
                value=fcst.forecast_cost,
                unit="currency",
            ),
            KPIItem(
                key="actual_cost",
                label="Actual cost (AC)",
                value=perf.evm.ac,
                unit="currency",
            ),
            KPIItem(
                key="budget_overrun",
                label="Budget overrun",
                value=fcst.budget_overrun,
                unit="currency",
                rag=self._overrun_rag(fcst.budget_overrun),
            ),
            KPIItem(
                key="spi",
                label="SPI",
                value=self._fmt(perf.evm.spi),
                rag=evm.rag(perf.evm.spi, None, has_started=True),
            ),
            KPIItem(
                key="cpi",
                label="CPI",
                value=self._fmt(perf.evm.cpi),
                rag=evm.rag(None, perf.evm.cpi, has_started=True),
            ),
        ]

        schedule = [
            KPIItem(
                key="projects_slipping",
                label="Projects slipping",
                value=str(fcst.projects_slipping),
                rag="red" if fcst.projects_slipping > 0 else "green",
            ),
            KPIItem(
                key="worst_slippage_days",
                label="Worst slippage",
                value=str(fcst.worst_slippage_days or 0),
                unit="days",
            ),
        ]

        risk_issues = [
            KPIItem(key="open_risks", label="Open risks", value=str(open_risks)),
            KPIItem(
                key="high_risks",
                label="High/critical risks",
                value=str(high_risks),
                rag="red" if high_risks > 0 else "green",
            ),
            KPIItem(key="open_issues", label="Open issues", value=str(open_issues)),
            KPIItem(
                key="overdue_milestones",
                label="Overdue milestones",
                value=str(overdue),
                rag="amber" if overdue > 0 else "green",
            ),
        ]

        groups = [
            KPIGroup(name="Delivery", items=delivery),
            KPIGroup(name="Financials", items=financials),
            KPIGroup(name="Schedule", items=schedule),
            KPIGroup(name="Risk & Issues", items=risk_issues),
        ]
        if resvar is not None:
            groups.append(
                KPIGroup(
                    name="Resources",
                    items=[
                        KPIItem(
                            key="over_allocated",
                            label="Over-allocated resources",
                            value=str(resvar.over_allocated),
                            rag="red" if resvar.over_allocated > 0 else "green",
                        ),
                        KPIItem(
                            key="under_utilized",
                            label="Under-utilised resources",
                            value=str(resvar.under_utilized),
                        ),
                        KPIItem(
                            key="balanced",
                            label="Balanced resources",
                            value=str(resvar.balanced),
                        ),
                    ],
                )
            )
        return groups

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _rag_counts(perf: RollupPerformance) -> tuple[int, int, int]:
        green = sum(1 for b in perf.breakdown if b.rag == "green")
        amber = sum(1 for b in perf.breakdown if b.rag == "amber")
        red = sum(1 for b in perf.breakdown if b.rag == "red")
        return green, amber, red

    def _risk_counts(self, project_ids: set[uuid.UUID]) -> tuple[int, int]:
        risks = self.risks.search(self._org_id, limit=10000)
        open_risks = [
            r for r in risks if r.status != RiskStatus.CLOSED and r.project_id in project_ids
        ]
        high = sum(
            1 for r in open_risks if r.severity in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)
        )
        return len(open_risks), high

    def _issue_count(self, project_ids: set[uuid.UUID]) -> int:
        issues = self.issues.search(self._org_id, limit=10000)
        return sum(
            1
            for i in issues
            if i.status in (IssueStatus.OPEN, IssueStatus.IN_PROGRESS)
            and i.project_id in project_ids
        )

    def _overdue_milestones(self, project_ids: set[uuid.UUID], as_of: date) -> int:
        return sum(
            self.milestones.overdue_count(self._org_id, pid, as_of=as_of) for pid in project_ids
        )

    @staticmethod
    def _score_rag(score: int) -> str:
        if score >= 70:
            return "green"
        if score >= 40:
            return "amber"
        return "red"

    @staticmethod
    def _overrun_rag(amount: str) -> str:
        """Red when the projected overrun is positive (over budget)."""
        return "green" if amount.startswith("-") or amount == "0.00" else "red"

    @staticmethod
    def _fmt(index: float | None) -> str:
        return f"{index:.2f}" if index is not None else "n/a"
