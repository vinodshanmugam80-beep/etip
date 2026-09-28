"""The report engine.

A framework- and service-independent helper that assembles report results by
reading aggregates across other modules. It is deliberately *not* a service: it
holds only repositories and pure logic, so any service (Reports, Dashboards, …)
can use it without importing another service — keeping the architecture acyclic.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.db.base import utcnow
from app.modules.finance.repository import FinancialEntryRepository
from app.modules.issue.repository import IssueRepository
from app.modules.milestone.repository import MilestoneRepository
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.raid.repository import ActionRepository, DecisionRepository
from app.modules.report.models import ReportType
from app.modules.report.schemas import ReportResult
from app.modules.risk.repository import RiskRepository
from app.modules.timesheet.repository import TimeEntryRepository


class ReportEngine:
    """Assembles a :class:`ReportResult` for a report type and parameters."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self.projects = ProjectRepository(session)
        self.portfolios = PortfolioRepository(session)
        self.risks = RiskRepository(session)
        self.issues = IssueRepository(session)
        self.actions = ActionRepository(session)
        self.decisions = DecisionRepository(session)
        self.milestones = MilestoneRepository(session)
        self.time_entries = TimeEntryRepository(session)
        self.financials = FinancialEntryRepository(session)

    # ------------------------------------------------------------------
    def assemble(self, report_type: ReportType, parameters: dict[str, Any]) -> ReportResult:
        """Assemble a fresh report result from current data."""
        builders = {
            ReportType.PROJECT_STATUS: self._project_status,
            ReportType.RAID_SUMMARY: self._raid_summary,
            ReportType.TIMESHEET_HOURS: self._timesheet_hours,
            ReportType.MILESTONE_STATUS: self._milestone_status,
            ReportType.FINANCIAL_SUMMARY: self._financial_summary,
            ReportType.PORTFOLIO_OVERVIEW: self._portfolio_overview,
        }
        data = builders[report_type](parameters)
        return ReportResult(
            report_type=report_type,
            generated_at=utcnow(),
            parameters=parameters,
            data=data,
        )

    # -- parameter helpers ---------------------------------------------
    def _uuid_param(self, parameters: dict[str, Any], key: str) -> uuid.UUID:
        raw = parameters.get(key)
        if raw is None:
            raise ValidationError(
                f"Missing required parameter '{key}'.",
                code="missing_parameter",
                details={"parameter": key},
            )
        try:
            return uuid.UUID(str(raw))
        except ValueError as exc:
            raise ValidationError(
                f"Parameter '{key}' is not a valid id.",
                code="invalid_parameter",
                details={"parameter": key},
            ) from exc

    def _date_param(self, parameters: dict[str, Any], key: str) -> date | None:
        raw = parameters.get(key)
        if raw is None:
            return None
        try:
            return date.fromisoformat(str(raw))
        except ValueError as exc:
            raise ValidationError(
                f"Parameter '{key}' is not a valid date (YYYY-MM-DD).",
                code="invalid_parameter",
                details={"parameter": key},
            ) from exc

    def _require_project(self, project_id: uuid.UUID) -> Project:
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    @staticmethod
    def _money(value: Decimal) -> str:
        return f"{value:.2f}"

    @staticmethod
    def _dt(value: datetime | date | None) -> str | None:
        return value.isoformat() if value is not None else None

    # -- builders ------------------------------------------------------
    def _project_status(self, parameters: dict[str, Any]) -> dict[str, Any]:
        project = self._require_project(self._uuid_param(parameters, "project_id"))
        variance = project.budget - project.actual_cost
        return {
            "project_id": str(project.id),
            "code": project.code,
            "name": project.name,
            "status": project.status.value,
            "stage": project.stage.value,
            "health": project.health.value if project.health else None,
            "budget": self._money(project.budget),
            "forecast": self._money(project.forecast),
            "actual_cost": self._money(project.actual_cost),
            "cost_variance": self._money(variance),
            "risk_score": project.risk_score,
            "issue_count": project.issue_count,
            "baseline_start": self._dt(project.baseline_start_date),
            "baseline_end": self._dt(project.baseline_end_date),
            "start_date": self._dt(project.start_date),
            "end_date": self._dt(project.end_date),
        }

    def _raid_summary(self, parameters: dict[str, Any]) -> dict[str, Any]:
        project = self._require_project(self._uuid_param(parameters, "project_id"))
        pid = project.id
        return {
            "project_id": str(pid),
            "risks": {
                "open": self.risks.open_count(self._org_id, pid),
                "total": self.risks.count(self._org_id, project_id=pid),
                "max_open_score": self.risks.max_open_score(self._org_id, pid),
            },
            "actions": {
                "open": self.actions.open_count(self._org_id, pid),
                "total": self.actions.total_count(self._org_id, pid),
            },
            "issues": {
                "open": self.issues.open_count(self._org_id, pid),
                "total": self.issues.total_count(self._org_id, pid),
            },
            "decisions": {
                "open": self.decisions.open_count(self._org_id, pid),
                "total": self.decisions.total_count(self._org_id, pid),
            },
        }

    def _timesheet_hours(self, parameters: dict[str, Any]) -> dict[str, Any]:
        project_id = (
            self._uuid_param(parameters, "project_id")
            if parameters.get("project_id") is not None
            else None
        )
        user_id = (
            self._uuid_param(parameters, "user_id")
            if parameters.get("user_id") is not None
            else None
        )
        if project_id is None and user_id is None:
            raise ValidationError(
                "Provide at least one of 'project_id' or 'user_id'.",
                code="missing_parameter",
            )
        date_from = self._date_param(parameters, "date_from")
        date_to = self._date_param(parameters, "date_to")
        total = self.time_entries.sum_hours(
            self._org_id,
            project_id=project_id,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
        )
        billable = self.time_entries.sum_hours(
            self._org_id,
            project_id=project_id,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            billable=True,
        )
        by_status = {
            st.value: self._money(hours)
            for st, hours, _ in self.time_entries.hours_by_status(
                self._org_id,
                project_id=project_id,
                user_id=user_id,
                date_from=date_from,
                date_to=date_to,
            )
        }
        return {
            "project_id": str(project_id) if project_id else None,
            "user_id": str(user_id) if user_id else None,
            "total_hours": self._money(total),
            "billable_hours": self._money(billable),
            "by_status": by_status,
        }

    def _milestone_status(self, parameters: dict[str, Any]) -> dict[str, Any]:
        project = self._require_project(self._uuid_param(parameters, "project_id"))
        pid = project.id
        by_status = {
            st.value: count for st, count in self.milestones.count_by_status(self._org_id, pid)
        }
        return {
            "project_id": str(pid),
            "total": self.milestones.total_count(self._org_id, pid),
            "key": self.milestones.key_count(self._org_id, pid),
            "overdue": self.milestones.overdue_count(self._org_id, pid, as_of=utcnow().date()),
            "by_status": by_status,
        }

    def _financial_summary(self, parameters: dict[str, Any]) -> dict[str, Any]:
        project = self._require_project(self._uuid_param(parameters, "project_id"))
        pid = project.id
        by_category = {
            category.value: self._money(total)
            for category, total in self.financials.actual_by_category(self._org_id, pid)
        }
        return {
            "project_id": str(pid),
            "budget": self._money(project.budget),
            "forecast": self._money(project.forecast),
            "actual_cost": self._money(project.actual_cost),
            "cost_variance": self._money(project.budget - project.actual_cost),
            "actual_by_category": by_category,
        }

    def _portfolio_overview(self, parameters: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = self._uuid_param(parameters, "portfolio_id")
        portfolio = self.portfolios.get(portfolio_id, organization_id=self._org_id)
        if portfolio is None:
            raise NotFoundError("Portfolio not found.")
        projects = list(self.projects.search(self._org_id, portfolio_id=portfolio_id, limit=200))
        by_status: dict[str, int] = {}
        by_health: dict[str, int] = {}
        total_budget = Decimal("0.00")
        total_actual = Decimal("0.00")
        for project in projects:
            by_status[project.status.value] = by_status.get(project.status.value, 0) + 1
            health = project.health.value if project.health else "unset"
            by_health[health] = by_health.get(health, 0) + 1
            total_budget += project.budget
            total_actual += project.actual_cost
        return {
            "portfolio_id": str(portfolio_id),
            "portfolio_code": portfolio.code,
            "project_count": len(projects),
            "by_status": by_status,
            "by_health": by_health,
            "total_budget": self._money(total_budget),
            "total_actual_cost": self._money(total_actual),
        }
