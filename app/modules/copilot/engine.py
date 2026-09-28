"""The copilot engine.

Turns a natural-language question into a **grounded** answer by (1) classifying
intent, (2) resolving the target project/portfolio, (3) executing against the
shared :class:`ReportEngine`, and (4) composing a deterministic answer from the
returned data, which is also attached as ``grounding`` (provenance).

Classification and phrasing are deliberately rule-based and deterministic here.
An LLM would slot in behind two seams without changing the rest of the module:
``classify_intent`` (intent + parameter extraction) and ``_compose`` (phrasing).
Keeping data access grounded in real repositories means answers can never invent
figures — the numbers always come from the database.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.base import utcnow
from app.modules.copilot.models import CopilotIntent
from app.modules.copilot.schemas import AnswerResult
from app.modules.intelligence import evm
from app.modules.portfolio.models import Portfolio
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.report.engine import ReportEngine
from app.modules.report.models import ReportType

# Intent keyword rules, evaluated in order (first match wins).
_INTENT_RULES: list[tuple[CopilotIntent, tuple[str, ...]]] = [
    (CopilotIntent.HELP, ("help", "what can you", "capabilities", "what do you")),
    (CopilotIntent.PORTFOLIO_OVERVIEW, ("portfolio",)),
    (CopilotIntent.RAID_SUMMARY, ("risk", "issue", "action", "raid", "decision")),
    (CopilotIntent.MILESTONE_STATUS, ("milestone", "overdue", "deadline")),
    (CopilotIntent.TIMESHEET_HOURS, ("hour", "timesheet", "logged", "time spent")),
    (CopilotIntent.FINANCIAL_SUMMARY, ("budget", "cost", "financ", "spend", "money")),
    (
        CopilotIntent.PROJECT_STATUS,
        ("status", "health", "how is", "how's", "doing", "summary", "progress"),
    ),
]

_INTENT_TO_REPORT: dict[CopilotIntent, ReportType] = {
    CopilotIntent.PROJECT_STATUS: ReportType.PROJECT_STATUS,
    CopilotIntent.RAID_SUMMARY: ReportType.RAID_SUMMARY,
    CopilotIntent.MILESTONE_STATUS: ReportType.MILESTONE_STATUS,
    CopilotIntent.TIMESHEET_HOURS: ReportType.TIMESHEET_HOURS,
    CopilotIntent.FINANCIAL_SUMMARY: ReportType.FINANCIAL_SUMMARY,
}

_HELP_TEXT = (
    "I can answer questions grounded in your live project data. Try asking about: "
    "project status ('how is ATLAS doing?'), risks and issues ('open risks for "
    "ATLAS'), milestones ('is ATLAS overdue?'), logged hours ('hours on ATLAS'), "
    "budget and cost ('ATLAS budget'), or a portfolio ('overview of the GROWTH "
    "portfolio'). Name a project or portfolio by its code."
)

_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,49}")


class CopilotEngine:
    """Answers natural-language questions from grounded platform data."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self._reports = ReportEngine(session, organization_id)
        self.projects = ProjectRepository(session)
        self.portfolios = PortfolioRepository(session)

    # ------------------------------------------------------------------
    # Classification (LLM seam #1)
    # ------------------------------------------------------------------
    @staticmethod
    def classify_intent(question: str) -> CopilotIntent:
        """Classify a question into an intent by keyword rules."""
        text = question.lower()
        for intent, keywords in _INTENT_RULES:
            if any(keyword in text for keyword in keywords):
                return intent
        return CopilotIntent.UNKNOWN

    # ------------------------------------------------------------------
    # Entity resolution
    # ------------------------------------------------------------------
    def _resolve_project(self, question: str, context: dict[str, Any]) -> Project | None:
        raw_id = context.get("project_id")
        if raw_id is not None:
            try:
                return self.projects.get(uuid.UUID(str(raw_id)), organization_id=self._org_id)
            except ValueError:
                return None
        code = context.get("project_code")
        if isinstance(code, str) and code:
            return self.projects.get_by_code(self._org_id, code.upper())
        for token in _CODE_RE.findall(question):
            found = self.projects.get_by_code(self._org_id, token.upper())
            if found is not None:
                return found
        return None

    def _resolve_portfolio(self, question: str, context: dict[str, Any]) -> Portfolio | None:
        raw_id = context.get("portfolio_id")
        if raw_id is not None:
            try:
                return self.portfolios.get(uuid.UUID(str(raw_id)), organization_id=self._org_id)
            except ValueError:
                return None
        code = context.get("portfolio_code")
        if isinstance(code, str) and code:
            return self.portfolios.get_by_code(self._org_id, code.upper())
        for token in _CODE_RE.findall(question):
            found = self.portfolios.get_by_code(self._org_id, token.upper())
            if found is not None:
                return found
        return None

    # ------------------------------------------------------------------
    # Answering
    # ------------------------------------------------------------------
    def answer(self, question: str, context: dict[str, Any] | None = None) -> AnswerResult:
        """Produce a grounded answer to a question."""
        context = context or {}
        intent = self.classify_intent(question)

        if intent == CopilotIntent.HELP:
            return AnswerResult(intent=intent, answer=_HELP_TEXT, grounding={})

        if intent == CopilotIntent.UNKNOWN:
            return AnswerResult(
                intent=intent,
                answer=("I couldn't tell what you're asking. " + _HELP_TEXT),
                grounding={"reason": "unclassified_question"},
            )

        if intent == CopilotIntent.PORTFOLIO_OVERVIEW:
            portfolio = self._resolve_portfolio(question, context)
            if portfolio is None:
                return AnswerResult(
                    intent=CopilotIntent.NEEDS_PORTFOLIO,
                    answer="Which portfolio? Please name it by its code.",
                    grounding={"reason": "unresolved_portfolio"},
                )
            params = {"portfolio_id": str(portfolio.id)}
            return self._run(intent, ReportType.PORTFOLIO_OVERVIEW, params, portfolio.code)

        # All remaining intents are project-scoped.
        project = self._resolve_project(question, context)
        if project is None:
            return AnswerResult(
                intent=CopilotIntent.NEEDS_PROJECT,
                answer="Which project? Please name it by its code (e.g. 'ATLAS').",
                grounding={"reason": "unresolved_project"},
            )
        params = {"project_id": str(project.id)}
        return self._run(intent, _INTENT_TO_REPORT[intent], params, project.code, project)

    def _run(
        self,
        intent: CopilotIntent,
        report_type: ReportType,
        params: dict[str, Any],
        code: str,
        project: Project | None = None,
    ) -> AnswerResult:
        try:
            data = self._reports.assemble(report_type, params).data
        except AppError as exc:
            return AnswerResult(
                intent=intent,
                answer=f"I couldn't complete that: {exc.message}",
                grounding={"error": exc.message, "parameters": params},
            )
        if project is not None and intent == CopilotIntent.PROJECT_STATUS:
            data = {**data, **self._evm_health(project)}
        return AnswerResult(
            intent=intent,
            answer=self._compose(intent, code, data),
            grounding={"intent": intent.value, "parameters": params, "data": data},
        )

    @staticmethod
    def _evm_health(project: Project) -> dict[str, Any]:
        """Compute earned-value SPI/CPI/RAG so the copilot matches the dashboard."""
        raw = evm.raw_for_project(project, utcnow().date())
        spi, cpi = evm.indices(raw)
        rag = evm.rag(spi, cpi, has_started=evm.started(raw))
        return {"spi": spi, "cpi": cpi, "rag": rag}

    # ------------------------------------------------------------------
    # Composition (LLM seam #2)
    # ------------------------------------------------------------------
    @staticmethod
    def _compose(intent: CopilotIntent, code: str, data: dict[str, Any]) -> str:
        if intent == CopilotIntent.PROJECT_STATUS:
            rag = data.get("rag")
            health = rag if rag else (data["health"] or "unset")
            spi, cpi = data.get("spi"), data.get("cpi")
            evm_txt = f" SPI {spi}, CPI {cpi}." if spi is not None and cpi is not None else ""
            return (
                f"{code} ({data['name']}) is {data['status']} — earned-value health "
                f"is {health}.{evm_txt} Budget {data['budget']}, actual cost "
                f"{data['actual_cost']} (variance {data['cost_variance']}). "
                f"Risk score {data['risk_score']}, {data['issue_count']} open issue(s)."
            )
        if intent == CopilotIntent.RAID_SUMMARY:
            r, i, a, d = (
                data["risks"],
                data["issues"],
                data["actions"],
                data["decisions"],
            )
            return (
                f"For {code}: {r['open']} open risk(s) of {r['total']}, "
                f"{i['open']} open issue(s) of {i['total']}, "
                f"{a['open']} open action(s) of {a['total']}, "
                f"{d['open']} open decision(s) of {d['total']}."
            )
        if intent == CopilotIntent.MILESTONE_STATUS:
            return (
                f"{code} has {data['total']} milestone(s): {data['key']} key, "
                f"{data['overdue']} overdue."
            )
        if intent == CopilotIntent.TIMESHEET_HOURS:
            return (
                f"{code} has {data['total_hours']} logged hour(s), of which "
                f"{data['billable_hours']} are billable."
            )
        if intent == CopilotIntent.FINANCIAL_SUMMARY:
            return (
                f"{code}: budget {data['budget']}, forecast {data['forecast']}, "
                f"actual {data['actual_cost']} (variance {data['cost_variance']})."
            )
        if intent == CopilotIntent.PORTFOLIO_OVERVIEW:
            return (
                f"Portfolio {code} has {data['project_count']} project(s). "
                f"Total budget {data['total_budget']}, total actual "
                f"{data['total_actual_cost']}."
            )
        return ""  # pragma: no cover - all data intents handled above
