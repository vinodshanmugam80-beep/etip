"""Early-warning intelligence.

Rule-based *leading indicators* that flag a project as at-risk before it turns red
on the RAG dashboard — schedule/cost drift while still amber, spending ahead of
progress, high open-risk exposure, stalls, and deadline pressure. These are
transparent heuristics (not a black-box prediction), each with a recommended
action, so a PM can act early.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.modules.intelligence import evm
from app.modules.intelligence.schemas import (
    EarlyWarningReport,
    EarlyWarningSignal,
    ProjectEarlyWarning,
)
from app.modules.project.models import Project, ProjectStatus
from app.modules.project.repository import ProjectRepository

_ACTIVE = {ProjectStatus.PROPOSED, ProjectStatus.ACTIVE, ProjectStatus.ON_HOLD}
_RISK_THRESHOLD = 12  # probability x impact band considered high exposure
_DEADLINE_DAYS = 21


class EarlyWarningEngine:
    """Compute leading-indicator warnings across projects."""

    def __init__(self, session: Session, organization_id: uuid.UUID) -> None:
        self._org_id = organization_id
        self.projects = ProjectRepository(session)

    def _signals(self, project: Project, as_of: date) -> list[EarlyWarningSignal]:
        signals: list[EarlyWarningSignal] = []
        raw = evm.raw_for_project(project, as_of)
        spi, cpi = evm.indices(raw)
        progress = project.progress_percent or 0

        if spi is not None and 0.80 <= spi < 0.95:
            signals.append(
                EarlyWarningSignal(
                    type="schedule_drift",
                    severity="warning",
                    message=f"Schedule slipping early (SPI {spi}).",
                    recommendation="Re-plan near-term tasks or add capacity before it turns red.",
                )
            )
        elif spi is not None and 0.95 <= spi < 1.0:
            signals.append(
                EarlyWarningSignal(
                    type="schedule_drift",
                    severity="watch",
                    message=f"Slightly behind schedule (SPI {spi}).",
                    recommendation="Watch the next reporting period.",
                )
            )
        if cpi is not None and 0.80 <= cpi < 0.95:
            signals.append(
                EarlyWarningSignal(
                    type="cost_drift",
                    severity="warning",
                    message=f"Cost efficiency dropping (CPI {cpi}).",
                    recommendation="Review scope and rate assumptions.",
                )
            )
        if project.budget and progress < 90:
            burn = float(project.actual_cost) / float(project.budget)
            if burn > (progress / 100) + 0.15:
                signals.append(
                    EarlyWarningSignal(
                        type="burn_ahead",
                        severity="warning",
                        message=(
                            f"Spending ahead of progress ({round(burn * 100)}% spent, "
                            f"{progress}% done)."
                        ),
                        recommendation=(
                            "Investigate cost drivers; reforecast the estimate at completion."
                        ),
                    )
                )
        if project.risk_score and project.risk_score >= _RISK_THRESHOLD:
            signals.append(
                EarlyWarningSignal(
                    type="risk_exposure",
                    severity="warning",
                    message=f"High open-risk exposure (score {project.risk_score}).",
                    recommendation="Prioritise mitigation of the top risks.",
                )
            )
        if (
            project.status is ProjectStatus.PROPOSED
            and project.baseline_start_date
            and project.baseline_start_date < as_of
        ):
            signals.append(
                EarlyWarningSignal(
                    type="stalled",
                    severity="warning",
                    message="Not started yet, but past its baseline start date.",
                    recommendation="Confirm the start or re-baseline.",
                )
            )
        if (
            project.baseline_end_date
            and as_of <= project.baseline_end_date <= as_of + timedelta(days=_DEADLINE_DAYS)
            and progress < 75
        ):
            days = (project.baseline_end_date - as_of).days
            signals.append(
                EarlyWarningSignal(
                    type="deadline_pressure",
                    severity="warning",
                    message=f"Deadline in {days} day(s) with only {progress}% complete.",
                    recommendation="Escalate, de-scope, or move the date now.",
                )
            )
        return signals

    @staticmethod
    def _level(signals: list[EarlyWarningSignal]) -> str:
        if any(s.severity == "warning" for s in signals):
            return "warning"
        if signals:
            return "watch"
        return "clear"

    def transformation(self, *, as_of: date | None = None) -> EarlyWarningReport:
        """Return early-warning signals across all active projects."""
        as_of = as_of or utcnow().date()
        projects = [
            p for p in self.projects.search(self._org_id, limit=1000) if p.status in _ACTIVE
        ]
        items: list[ProjectEarlyWarning] = []
        warning = watch = 0
        for project in projects:
            signals = self._signals(project, as_of)
            if not signals:
                continue
            level = self._level(signals)
            warning += level == "warning"
            watch += level == "watch"
            items.append(
                ProjectEarlyWarning(
                    project_id=project.id,
                    code=project.code,
                    name=project.name,
                    level=level,
                    signals=signals,
                )
            )
        items.sort(key=lambda i: 0 if i.level == "warning" else 1)
        return EarlyWarningReport(
            as_of=as_of,
            projects_total=len(projects),
            projects_warning=warning,
            projects_watch=watch,
            items=items,
        )

    def project(self, project_id: uuid.UUID, *, as_of: date | None = None) -> ProjectEarlyWarning:
        """Return early-warning signals for one project."""
        as_of = as_of or utcnow().date()
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            from app.core.exceptions import NotFoundError

            raise NotFoundError("Project not found.")
        signals = self._signals(project, as_of)
        return ProjectEarlyWarning(
            project_id=project.id,
            code=project.code,
            name=project.name,
            level=self._level(signals),
            signals=signals,
        )
