"""The Forecast Engine.

A service-independent intelligence engine that projects outcomes from the EVM
trajectory: forecast completion date and schedule slippage (from SPI), forecast
cost at completion and budget overrun (from CPI/EAC), a resource-shortage signal
(from over-allocation), and a heuristic transformation-success outlook. Pure
read; no schema change.

Honest scope: the charter also lists **critical-path delays** and **customer
escalation**. Neither is produced here — a credible critical-path forecast needs
proper CPM scheduling data, and customer escalation has no signal source in the
platform yet. This engine never fabricates predictions it cannot ground.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.base import utcnow
from app.modules.intelligence import evm
from app.modules.intelligence.schemas import (
    BudgetForecast,
    ForecastBreakdownItem,
    ProjectForecast,
    ResourceShortage,
    RollupForecast,
    ScheduleForecast,
    TransformationForecast,
)
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.program.repository import ProgramRepository
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.resource.repository import AllocationRepository, ResourceRepository


class ForecastEngine:
    """Projects completion, cost, resource shortage and success outlook."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self.projects = ProjectRepository(session)
        self.programs = ProgramRepository(session)
        self.portfolios = PortfolioRepository(session)
        self.resources = ResourceRepository(session)
        self.allocations = AllocationRepository(session)

    # ------------------------------------------------------------------
    # Single project
    # ------------------------------------------------------------------
    def project_forecast(
        self, project_id: uuid.UUID, *, as_of: date | None = None
    ) -> ProjectForecast:
        """Return the schedule and budget forecast for a project."""
        as_of = as_of or utcnow().date()
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        schedule, budget = self._project_forecast(project, as_of)
        return ProjectForecast(
            project_id=project.id,
            code=project.code,
            name=project.name,
            as_of=as_of,
            schedule=schedule,
            budget=budget,
        )

    # ------------------------------------------------------------------
    # Rollups
    # ------------------------------------------------------------------
    def program_forecast(
        self, program_id: uuid.UUID, *, as_of: date | None = None
    ) -> RollupForecast:
        """Aggregate forecast across a program's projects."""
        as_of = as_of or utcnow().date()
        program = self.programs.get(program_id, organization_id=self._org_id)
        if program is None:
            raise NotFoundError("Program not found.")
        projects = self.projects.search(self._org_id, program_id=program_id, limit=500)
        return self._aggregate(
            projects, as_of, scope="program", scope_id=program_id, label=program.name
        )

    def portfolio_forecast(
        self, portfolio_id: uuid.UUID, *, as_of: date | None = None
    ) -> RollupForecast:
        """Aggregate forecast across a portfolio's projects."""
        as_of = as_of or utcnow().date()
        portfolio = self.portfolios.get(portfolio_id, organization_id=self._org_id)
        if portfolio is None:
            raise NotFoundError("Portfolio not found.")
        projects = self.projects.search(self._org_id, portfolio_id=portfolio_id, limit=500)
        return self._aggregate(
            projects,
            as_of,
            scope="portfolio",
            scope_id=portfolio_id,
            label=portfolio.name,
        )

    def transformation_forecast(self, *, as_of: date | None = None) -> TransformationForecast:
        """Organization-wide forecast plus success outlook and resource shortage."""
        as_of = as_of or utcnow().date()
        projects = list(self.projects.search(self._org_id, limit=1000))
        rollup = self._aggregate(
            projects,
            as_of,
            scope="transformation",
            scope_id=None,
            label="Transformation",
        )
        score, label = self._success(projects, as_of)
        return TransformationForecast(
            as_of=as_of,
            project_count=rollup.project_count,
            bac=rollup.bac,
            forecast_cost=rollup.forecast_cost,
            budget_overrun=rollup.budget_overrun,
            projects_overrunning=rollup.projects_overrunning,
            projects_slipping=rollup.projects_slipping,
            worst_slippage_days=rollup.worst_slippage_days,
            success_score=score,
            success_label=label,
            resource_shortage=self._resource_shortage(as_of),
            breakdown=rollup.breakdown,
        )

    # ------------------------------------------------------------------
    # Per-project computation
    # ------------------------------------------------------------------
    def _project_forecast(
        self, project: Project, as_of: date
    ) -> tuple[ScheduleForecast, BudgetForecast]:
        raw = evm.raw_for_project(project, as_of)
        spi, _ = evm.indices(raw)
        return self._schedule(project, spi), self._budget(raw)

    @staticmethod
    def _schedule(project: Project, spi: float | None) -> ScheduleForecast:
        start, end = project.baseline_start_date, project.baseline_end_date
        if start is None or end is None or end <= start:
            return ScheduleForecast(
                baseline_end=end,
                forecast_completion=None,
                slippage_days=None,
                will_slip=False,
                basis="no baseline schedule",
            )
        if project.progress_percent >= 100:
            return ScheduleForecast(
                baseline_end=end,
                forecast_completion=end,
                slippage_days=0,
                will_slip=False,
                basis="completed",
            )
        if spi is None or spi <= 0:
            return ScheduleForecast(
                baseline_end=end,
                forecast_completion=None,
                slippage_days=None,
                will_slip=False,
                basis="insufficient data (no SPI)",
            )
        baseline_days = (end - start).days
        forecast_days = round(baseline_days / spi)
        forecast_completion = start + timedelta(days=forecast_days)
        slippage = (forecast_completion - end).days
        return ScheduleForecast(
            baseline_end=end,
            forecast_completion=forecast_completion,
            slippage_days=slippage,
            will_slip=slippage > 0,
            basis=f"SPI {spi:.2f}",
        )

    @staticmethod
    def _budget(raw: evm.RawEVM) -> BudgetForecast:
        eac = evm.eac(raw)
        overrun = eac - raw.bac
        percent = round(float(overrun / raw.bac) * 100, 2) if raw.bac > 0 else None
        return BudgetForecast(
            bac=evm.money(raw.bac),
            forecast_cost=evm.money(eac),
            overrun_amount=evm.money(overrun),
            overrun_percent=percent,
            will_overrun=overrun > 0,
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    def _aggregate(
        self,
        projects: Sequence[Project],
        as_of: date,
        *,
        scope: str,
        scope_id: uuid.UUID | None,
        label: str,
    ) -> RollupForecast:
        total_bac = evm.ZERO
        total_eac = evm.ZERO
        overrunning = 0
        slipping = 0
        worst_slip: int | None = None
        breakdown: list[ForecastBreakdownItem] = []
        for project in projects:
            schedule, budget = self._project_forecast(project, as_of)
            raw = evm.raw_for_project(project, as_of)
            eac = evm.eac(raw)
            total_bac += raw.bac
            total_eac += eac
            if budget.will_overrun:
                overrunning += 1
            if schedule.slippage_days is not None and schedule.slippage_days > 0:
                slipping += 1
            if schedule.slippage_days is not None:
                worst_slip = (
                    schedule.slippage_days
                    if worst_slip is None
                    else max(worst_slip, schedule.slippage_days)
                )
            breakdown.append(
                ForecastBreakdownItem(
                    project_id=project.id,
                    code=project.code,
                    forecast_completion=schedule.forecast_completion,
                    slippage_days=schedule.slippage_days,
                    overrun_amount=evm.money(eac - raw.bac),
                )
            )
        return RollupForecast(
            scope=scope,
            scope_id=scope_id,
            scope_label=label,
            as_of=as_of,
            project_count=len(breakdown),
            bac=evm.money(total_bac),
            forecast_cost=evm.money(total_eac),
            budget_overrun=evm.money(total_eac - total_bac),
            projects_overrunning=overrunning,
            projects_slipping=slipping,
            worst_slippage_days=worst_slip,
            breakdown=breakdown,
        )

    # ------------------------------------------------------------------
    # Success outlook & resource shortage
    # ------------------------------------------------------------------
    def _success(self, projects: Sequence[Project], as_of: date) -> tuple[int, str]:
        if not projects:
            return 0, "unknown"
        total_ev = evm.ZERO
        total_pv = evm.ZERO
        total_ac = evm.ZERO
        pv_available = False
        green = 0
        for project in projects:
            raw = evm.raw_for_project(project, as_of)
            total_ev += raw.ev
            total_ac += raw.ac
            if raw.pv is not None:
                total_pv += raw.pv
                pv_available = True
            spi, cpi = evm.indices(raw)
            if evm.rag(spi, cpi, has_started=evm.started(raw)) == "green":
                green += 1
        agg_spi = round(float(total_ev / total_pv), 3) if pv_available and total_pv > 0 else None
        agg_cpi = round(float(total_ev / total_ac), 3) if total_ac > 0 else None
        spi_component = min(max(agg_spi, 0.0), 1.2) / 1.2 if agg_spi is not None else 0.5
        cpi_component = min(max(agg_cpi, 0.0), 1.2) / 1.2 if agg_cpi is not None else 0.5
        green_ratio = green / len(projects)
        score = round((0.35 * spi_component + 0.35 * cpi_component + 0.30 * green_ratio) * 100)
        label = "likely" if score >= 70 else ("at_risk" if score >= 40 else "unlikely")
        return score, label

    def _resource_shortage(self, as_of: date) -> ResourceShortage:
        resources = self.resources.search(self._org_id, is_active=True, limit=1000)
        over = 0
        excess = 0
        for resource in resources:
            allocations = self.allocations.list_for_resource(self._org_id, resource.id)
            allocated = sum(
                a.allocation_percent for a in allocations if a.start_date <= as_of <= a.end_date
            )
            if allocated > 100:
                over += 1
                excess += allocated - 100
        return ResourceShortage(
            over_allocated=over,
            total_excess_percent=excess,
            shortage=over > 0,
        )
