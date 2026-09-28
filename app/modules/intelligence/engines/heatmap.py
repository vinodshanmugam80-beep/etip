"""The Heat Map Engine.

A service-independent intelligence engine that renders RAG heat maps so leaders
can spot hot areas at a glance. Pure read; no schema change.

It produces:
* **dimensional heat maps** (portfolio / program / transformation): each project
  scored green/amber/red across Schedule, Cost, Budget and Overall, derived from
  the shared EVM primitives;
* the **risk matrix**: the classic probability × impact grid of open-risk counts;
* the **resource heat map**: each active resource by capacity utilisation.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.base import utcnow
from app.modules.intelligence import evm
from app.modules.intelligence.schemas import (
    HeatCell,
    HeatMap,
    RiskHeatCell,
    RiskHeatMap,
)
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.program.repository import ProgramRepository
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.resource.repository import AllocationRepository, ResourceRepository
from app.modules.risk.models import RiskStatus, severity_for_score
from app.modules.risk.repository import RiskRepository

_COLUMNS = ["Schedule", "Cost", "Budget", "Overall"]


class HeatMapEngine:
    """Builds dimensional, risk and resource heat maps."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self.projects = ProjectRepository(session)
        self.programs = ProgramRepository(session)
        self.portfolios = PortfolioRepository(session)
        self.risks = RiskRepository(session)
        self.resources = ResourceRepository(session)
        self.allocations = AllocationRepository(session)

    # ------------------------------------------------------------------
    # Dimensional heat maps
    # ------------------------------------------------------------------
    def portfolio_heatmap(self, portfolio_id: uuid.UUID, *, as_of: date | None = None) -> HeatMap:
        """Project × dimension RAG grid for a portfolio."""
        as_of = as_of or utcnow().date()
        portfolio = self.portfolios.get(portfolio_id, organization_id=self._org_id)
        if portfolio is None:
            raise NotFoundError("Portfolio not found.")
        projects = self.projects.search(self._org_id, portfolio_id=portfolio_id, limit=500)
        return self._grid(
            projects, as_of, scope="portfolio", scope_id=portfolio_id, label=portfolio.name
        )

    def program_heatmap(self, program_id: uuid.UUID, *, as_of: date | None = None) -> HeatMap:
        """Project × dimension RAG grid for a program."""
        as_of = as_of or utcnow().date()
        program = self.programs.get(program_id, organization_id=self._org_id)
        if program is None:
            raise NotFoundError("Program not found.")
        projects = self.projects.search(self._org_id, program_id=program_id, limit=500)
        return self._grid(projects, as_of, scope="program", scope_id=program_id, label=program.name)

    def transformation_heatmap(self, *, as_of: date | None = None) -> HeatMap:
        """Project × dimension RAG grid across the whole organization."""
        as_of = as_of or utcnow().date()
        projects = self.projects.search(self._org_id, limit=1000)
        return self._grid(
            projects, as_of, scope="transformation", scope_id=None, label="Transformation"
        )

    def _grid(
        self,
        projects: Sequence[Project],
        as_of: date,
        *,
        scope: str,
        scope_id: uuid.UUID | None,
        label: str,
    ) -> HeatMap:
        cells: list[HeatCell] = []
        summary = {"green": 0, "amber": 0, "red": 0, "not_started": 0, "unknown": 0}
        for project in projects:
            row_cells, overall = self._project_cells(project, as_of)
            cells.extend(row_cells)
            summary[overall] = summary.get(overall, 0) + 1
        return HeatMap(
            scope=scope,
            scope_id=scope_id,
            scope_label=label,
            as_of=as_of,
            columns=_COLUMNS,
            cells=cells,
            summary=summary,
        )

    def _project_cells(self, project: Project, as_of: date) -> tuple[list[HeatCell], str]:
        raw = evm.raw_for_project(project, as_of)
        spi, cpi = evm.indices(raw)
        has_started = evm.started(raw)
        schedule = evm.rag(spi, None, has_started=has_started)
        cost = evm.rag(None, cpi, has_started=has_started)
        overall = evm.rag(spi, cpi, has_started=has_started)
        budget = self._budget_rag(raw, has_started)
        rags = {"Schedule": schedule, "Cost": cost, "Budget": budget, "Overall": overall}
        details = {
            "Schedule": f"SPI {spi:.2f}" if spi is not None else None,
            "Cost": f"CPI {cpi:.2f}" if cpi is not None else None,
            "Budget": None,
            "Overall": None,
        }
        cells = [
            HeatCell(
                row_key=str(project.id),
                row_label=project.code,
                column=column,
                rag=rags[column],
                detail=details[column],
            )
            for column in _COLUMNS
        ]
        return cells, overall

    @staticmethod
    def _budget_rag(raw: evm.RawEVM, has_started: bool) -> str:
        if not has_started:
            return "not_started"
        if raw.bac <= 0:
            return "unknown"
        overrun_percent = float((evm.eac(raw) - raw.bac) / raw.bac) * 100
        if overrun_percent <= 0:
            return "green"
        if overrun_percent <= 10:
            return "amber"
        return "red"

    # ------------------------------------------------------------------
    # Risk matrix
    # ------------------------------------------------------------------
    def risk_heatmap(self, *, as_of: date | None = None) -> RiskHeatMap:
        """Probability × impact matrix of open-risk counts."""
        as_of = as_of or utcnow().date()
        risks = self.risks.search(self._org_id, limit=10000)
        counts: dict[tuple[int, int], int] = {}
        total = 0
        for risk in risks:
            if risk.status == RiskStatus.CLOSED:
                continue
            key = (risk.probability, risk.impact)
            counts[key] = counts.get(key, 0) + 1
            total += 1
        cells = [
            RiskHeatCell(
                probability=probability,
                impact=impact,
                count=count,
                severity=severity_for_score(probability * impact).value,
            )
            for (probability, impact), count in sorted(counts.items())
        ]
        return RiskHeatMap(
            as_of=as_of,
            max_probability=5,
            max_impact=5,
            total_open=total,
            cells=cells,
        )

    # ------------------------------------------------------------------
    # Resource utilisation heat map
    # ------------------------------------------------------------------
    def resource_heatmap(self, *, as_of: date | None = None) -> HeatMap:
        """Each active resource rated by capacity utilisation."""
        as_of = as_of or utcnow().date()
        resources = self.resources.search(self._org_id, is_active=True, limit=1000)
        cells: list[HeatCell] = []
        summary = {"green": 0, "amber": 0, "red": 0}
        for resource in resources:
            allocations = self.allocations.list_for_resource(self._org_id, resource.id)
            allocated = sum(
                a.allocation_percent for a in allocations if a.start_date <= as_of <= a.end_date
            )
            if allocated > 100:
                rag = "red"
            elif allocated < 100:
                rag = "amber"
            else:
                rag = "green"
            summary[rag] += 1
            cells.append(
                HeatCell(
                    row_key=str(resource.id),
                    row_label=resource.name,
                    column="Utilization",
                    rag=rag,
                    detail=f"{allocated}% allocated",
                )
            )
        return HeatMap(
            scope="resource",
            scope_id=None,
            scope_label="Resource utilisation",
            as_of=as_of,
            columns=["Utilization"],
            cells=cells,
            summary=summary,
        )
