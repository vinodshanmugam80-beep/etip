"""The Variance Engine.

A service-independent intelligence engine that derives variances from the same
EVM primitives the Performance Engine uses, plus project budget/forecast and
resource capacity/allocation data. Pure read; no schema change.

Per project it reports four variances — schedule (SV = EV-PV), cost
(CV = EV-AC), budget (budget - forecast) and forecast (forecast - EAC) — and
aggregates them across programs, portfolios, departments and the whole
transformation. It also reports resource capacity variance (allocation vs 100%).

Benefits variance and KPI variance are intentionally **not** produced here: they
require the Benefits Realization module (roadmap Phase 2a) and the Executive KPI
engine (Phase 1d) respectively, and this engine never fabricates their inputs.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.base import utcnow
from app.modules.benefit.repository import BenefitRepository
from app.modules.initiative.logic import attainment_percent, target_met
from app.modules.initiative.models import GoalKPI
from app.modules.initiative.repository import (
    GoalKPIRepository,
    GoalRepository,
    InitiativeRepository,
)
from app.modules.intelligence import evm
from app.modules.intelligence.schemas import (
    BenefitsVariance,
    KPIVariance,
    KPIVarianceItem,
    ProjectVariance,
    ResourceVarianceItem,
    ResourceVarianceSummary,
    RollupVariance,
    VarianceBreakdownItem,
    VarianceItem,
)
from app.modules.organization.repository import DepartmentRepository
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.program.repository import ProgramRepository
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.resource.repository import AllocationRepository, ResourceRepository


class VarianceEngine:
    """Computes schedule / cost / budget / forecast and resource variance."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self.projects = ProjectRepository(session)
        self.programs = ProgramRepository(session)
        self.portfolios = PortfolioRepository(session)
        self.departments = DepartmentRepository(session)
        self.resources = ResourceRepository(session)
        self.allocations = AllocationRepository(session)
        self.benefits = BenefitRepository(session)
        self.goals = GoalRepository(session)
        self.kpis = GoalKPIRepository(session)
        self.initiatives = InitiativeRepository(session)

    # ------------------------------------------------------------------
    # Single project
    # ------------------------------------------------------------------
    def project_variance(
        self, project_id: uuid.UUID, *, as_of: date | None = None
    ) -> ProjectVariance:
        """Return the four variances for a single project."""
        as_of = as_of or utcnow().date()
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        schedule, cost, budget, forecast = self._project_items(project, as_of)
        return ProjectVariance(
            project_id=project.id,
            code=project.code,
            name=project.name,
            as_of=as_of,
            schedule=schedule,
            cost=cost,
            budget=budget,
            forecast=forecast,
        )

    # ------------------------------------------------------------------
    # Rollups
    # ------------------------------------------------------------------
    def program_variance(
        self, program_id: uuid.UUID, *, as_of: date | None = None
    ) -> RollupVariance:
        """Aggregate variance across a program's projects."""
        as_of = as_of or utcnow().date()
        program = self.programs.get(program_id, organization_id=self._org_id)
        if program is None:
            raise NotFoundError("Program not found.")
        projects = self.projects.search(self._org_id, program_id=program_id, limit=500)
        return self._aggregate(
            projects, as_of, scope="program", scope_id=program_id, label=program.name
        )

    def portfolio_variance(
        self, portfolio_id: uuid.UUID, *, as_of: date | None = None
    ) -> RollupVariance:
        """Aggregate variance across a portfolio's projects."""
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

    def department_variance(
        self, department_id: uuid.UUID, *, as_of: date | None = None
    ) -> RollupVariance:
        """Aggregate variance across the projects of a department."""
        as_of = as_of or utcnow().date()
        department = self.departments.get(department_id, organization_id=self._org_id)
        if department is None:
            raise NotFoundError("Department not found.")
        projects = [
            project
            for project in self.projects.search(self._org_id, limit=1000)
            if project.department_id == department_id
        ]
        return self._aggregate(
            projects,
            as_of,
            scope="department",
            scope_id=department_id,
            label=department.name,
        )

    def transformation_variance(self, *, as_of: date | None = None) -> RollupVariance:
        """Aggregate variance across every project in the organization."""
        as_of = as_of or utcnow().date()
        projects = self.projects.search(self._org_id, limit=1000)
        return self._aggregate(
            projects,
            as_of,
            scope="transformation",
            scope_id=None,
            label="Transformation",
        )

    # ------------------------------------------------------------------
    # Resource capacity variance
    # ------------------------------------------------------------------
    def resource_variance(self, *, as_of: date | None = None) -> ResourceVarianceSummary:
        """Return capacity-vs-allocation variance for active resources."""
        as_of = as_of or utcnow().date()
        resources = self.resources.search(self._org_id, is_active=True, limit=1000)
        items: list[ResourceVarianceItem] = []
        over = under = balanced = 0
        for resource in resources:
            allocations = self.allocations.list_for_resource(self._org_id, resource.id)
            allocated = sum(
                a.allocation_percent for a in allocations if a.start_date <= as_of <= a.end_date
            )
            variance = 100 - allocated
            if allocated > 100:
                status = "over_allocated"
                over += 1
            elif allocated < 100:
                status = "under_utilized"
                under += 1
            else:
                status = "balanced"
                balanced += 1
            items.append(
                ResourceVarianceItem(
                    resource_id=resource.id,
                    name=resource.name,
                    capacity_percent=100,
                    allocated_percent=allocated,
                    variance_percent=variance,
                    status=status,
                )
            )
        return ResourceVarianceSummary(
            as_of=as_of,
            resource_count=len(items),
            over_allocated=over,
            under_utilized=under,
            balanced=balanced,
            items=items,
        )

    # ------------------------------------------------------------------
    # Benefits variance (Phase 2a data)
    # ------------------------------------------------------------------
    def benefits_variance_project(self, project_id: uuid.UUID) -> BenefitsVariance:
        """Realised-vs-target benefits variance for a project."""
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return self._benefits_variance("project", project_id, project.name, [project_id])

    def benefits_variance_portfolio(self, portfolio_id: uuid.UUID) -> BenefitsVariance:
        """Realised-vs-target benefits variance across a portfolio's projects."""
        portfolio = self.portfolios.get(portfolio_id, organization_id=self._org_id)
        if portfolio is None:
            raise NotFoundError("Portfolio not found.")
        project_ids = [
            p.id for p in self.projects.search(self._org_id, portfolio_id=portfolio_id, limit=500)
        ]
        return self._benefits_variance("portfolio", portfolio_id, portfolio.name, project_ids)

    def benefits_variance_transformation(self) -> BenefitsVariance:
        """Realised-vs-target benefits variance across the organization."""
        project_ids = [p.id for p in self.projects.search(self._org_id, limit=1000)]
        return self._benefits_variance("transformation", None, "Transformation", project_ids)

    def _benefits_variance(
        self,
        scope: str,
        scope_id: uuid.UUID | None,
        label: str,
        project_ids: list[uuid.UUID],
    ) -> BenefitsVariance:
        target, realized, _investment, count = self.benefits.totals_for_projects(
            self._org_id, project_ids
        )
        variance = realized - target
        realization = round(float(realized / target) * 100, 2) if target > 0 else None
        return BenefitsVariance(
            scope=scope,
            scope_id=scope_id,
            scope_label=label,
            benefit_count=count,
            total_target=target,
            total_realized=realized,
            variance=variance,
            realization_percent=realization,
            favourable=variance >= 0,
        )

    # ------------------------------------------------------------------
    # KPI variance (Phase 2c data)
    # ------------------------------------------------------------------
    def kpi_variance_transformation(self) -> KPIVariance:
        """KPI target attainment across every KPI in the organization."""
        kpis = list(self.kpis.list_all(self._org_id))
        return self._kpi_variance("transformation", None, "Transformation", kpis)

    def kpi_variance_initiative(self, initiative_id: uuid.UUID) -> KPIVariance:
        """KPI target attainment across an initiative's goals."""
        initiative = self.initiatives.get(initiative_id, organization_id=self._org_id)
        if initiative is None:
            raise NotFoundError("Initiative not found.")
        goal_ids = [g.id for g in self.goals.list_for_initiative(self._org_id, initiative_id)]
        kpis = list(self.kpis.list_for_goals(self._org_id, goal_ids))
        return self._kpi_variance("initiative", initiative_id, initiative.name, kpis)

    def kpi_variance_portfolio(self, portfolio_id: uuid.UUID) -> KPIVariance:
        """KPI target attainment across the initiatives mapped to a portfolio."""
        portfolio = self.portfolios.get(portfolio_id, organization_id=self._org_id)
        if portfolio is None:
            raise NotFoundError("Portfolio not found.")
        initiatives = self.initiatives.search(self._org_id, portfolio_id=portfolio_id, limit=500)
        goal_ids: list[uuid.UUID] = []
        for initiative in initiatives:
            goal_ids.extend(
                g.id for g in self.goals.list_for_initiative(self._org_id, initiative.id)
            )
        kpis = list(self.kpis.list_for_goals(self._org_id, goal_ids))
        return self._kpi_variance("portfolio", portfolio_id, portfolio.name, kpis)

    def _kpi_variance(
        self,
        scope: str,
        scope_id: uuid.UUID | None,
        label: str,
        kpis: list[GoalKPI],
    ) -> KPIVariance:
        items: list[KPIVarianceItem] = []
        on_target = 0
        attainments: list[float] = []
        for kpi in kpis:
            met = target_met(kpi.current_value, kpi.target_value, kpi.direction)
            attainment = attainment_percent(
                kpi.baseline_value,
                kpi.current_value,
                kpi.target_value,
                kpi.direction,
            )
            if met:
                on_target += 1
            if attainment is not None:
                attainments.append(attainment)
            items.append(
                KPIVarianceItem(
                    kpi_id=kpi.id,
                    name=kpi.name,
                    unit=kpi.unit,
                    current_value=kpi.current_value,
                    target_value=kpi.target_value,
                    variance=kpi.current_value - kpi.target_value,
                    attainment_percent=attainment,
                    on_target=met,
                )
            )
        return KPIVariance(
            scope=scope,
            scope_id=scope_id,
            scope_label=label,
            kpi_count=len(items),
            kpis_on_target=on_target,
            kpis_off_target=len(items) - on_target,
            average_attainment=(
                round(sum(attainments) / len(attainments), 2) if attainments else None
            ),
            items=items,
        )

    # ------------------------------------------------------------------
    # Computation helpers
    # ------------------------------------------------------------------
    def _project_items(
        self, project: Project, as_of: date
    ) -> tuple[VarianceItem, VarianceItem, VarianceItem, VarianceItem]:
        raw = evm.raw_for_project(project, as_of)
        eac = evm.eac(raw)
        sv = raw.ev - raw.pv if raw.pv is not None else None
        cv = raw.ev - raw.ac
        budget_var = project.budget - project.forecast
        forecast_var = project.forecast - eac

        schedule = self._item("Schedule variance (SV = EV - PV)", sv, raw.pv if raw.pv else None)
        cost = self._item("Cost variance (CV = EV - AC)", cv, raw.ev if raw.ev > 0 else None)
        budget = self._item(
            "Budget variance (budget - forecast)",
            budget_var,
            project.budget if project.budget > 0 else None,
        )
        forecast = self._item(
            "Forecast variance (forecast - EAC)",
            forecast_var,
            project.forecast if project.forecast > 0 else None,
        )
        return schedule, cost, budget, forecast

    @staticmethod
    def _item(label: str, amount: Decimal | None, base: Decimal | None) -> VarianceItem:
        if amount is None:
            return VarianceItem(label=label, amount=None, percent=None, favourable=True)
        percent = round(float(amount / base) * 100, 2) if base is not None and base != 0 else None
        return VarianceItem(
            label=label,
            amount=evm.money(amount),
            percent=percent,
            favourable=amount >= 0,
        )

    def _aggregate(
        self,
        projects: Sequence[Project],
        as_of: date,
        *,
        scope: str,
        scope_id: uuid.UUID | None,
        label: str,
    ) -> RollupVariance:
        total_sv = evm.ZERO
        total_pv = evm.ZERO
        pv_available = False
        total_cv = evm.ZERO
        total_ev = evm.ZERO
        total_budget = evm.ZERO
        total_forecast = evm.ZERO
        total_eac = evm.ZERO
        breakdown: list[VarianceBreakdownItem] = []
        for project in projects:
            raw = evm.raw_for_project(project, as_of)
            sv = raw.ev - raw.pv if raw.pv is not None else None
            if raw.pv is not None and sv is not None:
                total_sv += sv
                total_pv += raw.pv
                pv_available = True
            cv = raw.ev - raw.ac
            total_cv += cv
            total_ev += raw.ev
            total_budget += project.budget
            total_forecast += project.forecast
            total_eac += evm.eac(raw)
            breakdown.append(
                VarianceBreakdownItem(
                    project_id=project.id,
                    code=project.code,
                    schedule_amount=evm.money(sv) if sv is not None else None,
                    cost_amount=evm.money(cv),
                    budget_amount=evm.money(project.budget - project.forecast),
                )
            )
        schedule = self._item(
            "Schedule variance (SV = EV - PV)",
            total_sv if pv_available else None,
            total_pv if pv_available else None,
        )
        cost = self._item(
            "Cost variance (CV = EV - AC)", total_cv, total_ev if total_ev > 0 else None
        )
        budget = self._item(
            "Budget variance (budget - forecast)",
            total_budget - total_forecast,
            total_budget if total_budget > 0 else None,
        )
        forecast = self._item(
            "Forecast variance (forecast - EAC)",
            total_forecast - total_eac,
            total_forecast if total_forecast > 0 else None,
        )
        return RollupVariance(
            scope=scope,
            scope_id=scope_id,
            scope_label=label,
            as_of=as_of,
            project_count=len(breakdown),
            schedule=schedule,
            cost=cost,
            budget=budget,
            forecast=forecast,
            breakdown=breakdown,
        )
