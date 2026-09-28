"""The Performance Engine.

A service- and framework-independent helper (like the report engine) that
computes Earned Value Management (EVM) metrics and derived RAG health for a
project, and aggregates them into program / portfolio / transformation rollups.
It reads repositories only and never imports a service, so the Intelligence
Layer stays decoupled from the Project module and the architecture acyclic.

EVM primitives are shared with the other intelligence engines via
:mod:`app.modules.intelligence.evm` — no schema change; all inputs already exist.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.base import utcnow
from app.modules.intelligence import evm
from app.modules.intelligence.evm import RawEVM
from app.modules.intelligence.schemas import (
    EffortMetrics,
    EVMMetrics,
    HealthResult,
    PerformanceBreakdownItem,
    ProjectPerformance,
    RollupPerformance,
)
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.program.repository import ProgramRepository
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.task.repository import TaskRepository

# RAG thresholds on the worst available performance index.
_GREEN = 0.95
_AMBER = 0.85


class PerformanceEngine:
    """Computes EVM performance and health for projects and rollups."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self.projects = ProjectRepository(session)
        self.programs = ProgramRepository(session)
        self.portfolios = PortfolioRepository(session)
        self.tasks = TaskRepository(session)

    # ------------------------------------------------------------------
    # Public: single project
    # ------------------------------------------------------------------
    def project_performance(
        self, project_id: uuid.UUID, *, as_of: date | None = None
    ) -> ProjectPerformance:
        """Return a full EVM + health snapshot for one project."""
        as_of = as_of or utcnow().date()
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        raw = evm.raw_for_project(project, as_of)
        spi, cpi = evm.indices(raw)
        return ProjectPerformance(
            project_id=project.id,
            code=project.code,
            name=project.name,
            as_of=as_of,
            evm=self._metrics(raw),
            effort=self._effort(project.id),
            health=self._health(spi, cpi, started=evm.started(raw)),
            risk_score=project.risk_score,
            issue_count=project.issue_count,
        )

    # ------------------------------------------------------------------
    # Public: rollups
    # ------------------------------------------------------------------
    def program_performance(
        self, program_id: uuid.UUID, *, as_of: date | None = None
    ) -> RollupPerformance:
        """Aggregate EVM across a program's projects."""
        as_of = as_of or utcnow().date()
        program = self.programs.get(program_id, organization_id=self._org_id)
        if program is None:
            raise NotFoundError("Program not found.")
        projects = self.projects.search(self._org_id, program_id=program_id, limit=500)
        return self._aggregate(
            projects, as_of, scope="program", scope_id=program_id, label=program.name
        )

    def portfolio_performance(
        self, portfolio_id: uuid.UUID, *, as_of: date | None = None
    ) -> RollupPerformance:
        """Aggregate EVM across a portfolio's projects."""
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

    def transformation_performance(self, *, as_of: date | None = None) -> RollupPerformance:
        """Aggregate EVM across every project in the organization."""
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
    # Metrics
    # ------------------------------------------------------------------
    def _metrics(self, raw: RawEVM) -> EVMMetrics:
        spi, cpi = evm.indices(raw)
        cv = raw.ev - raw.ac
        sv = raw.ev - raw.pv if raw.pv is not None else None
        eac = evm.eac(raw)
        etc = eac - raw.ac
        vac = raw.bac - eac
        denom = raw.bac - raw.ac
        tcpi = round(float((raw.bac - raw.ev) / denom), 3) if denom != 0 else None
        return EVMMetrics(
            bac=evm.money(raw.bac),
            pv=evm.money(raw.pv) if raw.pv is not None else None,
            ev=evm.money(raw.ev),
            ac=evm.money(raw.ac),
            sv=evm.money(sv) if sv is not None else None,
            cv=evm.money(cv),
            spi=spi,
            cpi=cpi,
            eac=evm.money(eac),
            etc=evm.money(etc),
            vac=evm.money(vac),
            tcpi=tcpi,
            planned_percent=(
                round(raw.planned_percent, 4) if raw.planned_percent is not None else None
            ),
            actual_percent=round(raw.actual_percent, 4),
        )

    # ------------------------------------------------------------------
    # Effort & health
    # ------------------------------------------------------------------
    def _effort(self, project_id: uuid.UUID) -> EffortMetrics:
        tasks = self.tasks.list_for_project(self._org_id, project_id)
        estimate = sum((t.estimate_hours for t in tasks), evm.ZERO)
        logged = sum((t.logged_hours for t in tasks), evm.ZERO)
        ratio = round(float(logged / estimate), 3) if estimate > 0 else None
        return EffortMetrics(
            estimate_hours=evm.money(estimate),
            logged_hours=evm.money(logged),
            effort_burn_ratio=ratio,
        )

    @staticmethod
    def _health(spi: float | None, cpi: float | None, *, started: bool) -> HealthResult:
        rag = evm.rag(spi, cpi, has_started=started)
        if rag == "not_started":
            return HealthResult(rag=rag, drivers=["No cost or progress yet."])
        if rag == "unknown":
            return HealthResult(
                rag=rag,
                drivers=["No baseline schedule or actual cost to assess."],
            )
        drivers: list[str] = []
        for name, idx in (("SPI", spi), ("CPI", cpi)):
            if idx is None:
                continue
            label = "on track" if idx >= _GREEN else ("slipping" if idx >= _AMBER else "off track")
            drivers.append(f"{name} {idx:.2f} ({label})")
        return HealthResult(rag=rag, drivers=drivers)

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
    ) -> RollupPerformance:
        total_bac = evm.ZERO
        total_ev = evm.ZERO
        total_ac = evm.ZERO
        total_pv = evm.ZERO
        pv_available = False
        breakdown: list[PerformanceBreakdownItem] = []
        for project in projects:
            raw = evm.raw_for_project(project, as_of)
            total_bac += raw.bac
            total_ev += raw.ev
            total_ac += raw.ac
            if raw.pv is not None:
                total_pv += raw.pv
                pv_available = True
            spi, cpi = evm.indices(raw)
            eac_i = evm.eac(raw)
            breakdown.append(
                PerformanceBreakdownItem(
                    project_id=project.id,
                    code=project.code,
                    rag=self._health(spi, cpi, started=evm.started(raw)).rag,
                    spi=spi,
                    cpi=cpi,
                    bac=evm.money(raw.bac),
                    ac=evm.money(raw.ac),
                    eac=evm.money(eac_i),
                    etc=evm.money(eac_i - raw.ac),
                )
            )
        agg = RawEVM(
            bac=total_bac,
            pv=total_pv if pv_available else None,
            ev=total_ev,
            ac=total_ac,
            planned_percent=(
                round(float(total_pv / total_bac), 4) if pv_available and total_bac > 0 else None
            ),
            actual_percent=(round(float(total_ev / total_bac), 4) if total_bac > 0 else 0.0),
        )
        spi, cpi = evm.indices(agg)
        return RollupPerformance(
            scope=scope,
            scope_id=scope_id,
            scope_label=label,
            as_of=as_of,
            project_count=len(breakdown),
            evm=self._metrics(agg),
            health=self._health(spi, cpi, started=evm.started(agg)),
            breakdown=breakdown,
        )
