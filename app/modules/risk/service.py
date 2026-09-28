"""Risk Management service.

Business rules for the project risk register. Each risk belongs to a project and
gets a per-project number. Exposure is scored as ``probability × impact`` and
bucketed into a severity band (both derived on write). The owning project's
``risk_score`` rollup is kept equal to the highest score among its open
(non-closed) risks. The status follows a lifecycle enforced by the shared
transition validator.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.core.exceptions import NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.risk.models import (
    Risk,
    RiskCategory,
    RiskResponse,
    RiskSeverity,
    RiskStatus,
    severity_for_score,
)
from app.modules.risk.repository import RiskRepository
from app.modules.risk.schemas import (
    RiskSummaryResponse,
    SeverityCount,
)

logger = get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[RiskStatus, set[RiskStatus]] = {
    RiskStatus.IDENTIFIED: {
        RiskStatus.ANALYZING,
        RiskStatus.MITIGATING,
        RiskStatus.MONITORING,
        RiskStatus.CLOSED,
    },
    RiskStatus.ANALYZING: {
        RiskStatus.MITIGATING,
        RiskStatus.MONITORING,
        RiskStatus.CLOSED,
    },
    RiskStatus.MITIGATING: {RiskStatus.MONITORING, RiskStatus.CLOSED},
    RiskStatus.MONITORING: {RiskStatus.MITIGATING, RiskStatus.CLOSED},
    RiskStatus.CLOSED: set(),
}


class RiskService:
    """Coordinates risk register use cases within a tenant."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.risks = RiskRepository(session)
        self.projects = ProjectRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, risk_id: uuid.UUID) -> Risk:
        risk = self.risks.get(risk_id, organization_id=self._org_id)
        if risk is None:
            raise NotFoundError("Risk not found.")
        return risk

    def _get_project_or_404(self, project_id: uuid.UUID) -> Project:
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    def _require_owner(self, owner_user_id: uuid.UUID | None) -> None:
        if owner_user_id is None:
            return
        if self.users.get(owner_user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Owner does not belong to this organization.",
                details={"owner_user_id": str(owner_user_id)},
            )

    @staticmethod
    def _apply_score(risk: Risk) -> None:
        """Recompute a risk's score and severity from probability × impact."""
        risk.risk_score = risk.probability * risk.impact
        risk.severity = severity_for_score(risk.risk_score)

    def _sync_project_rollup(self, project_id: uuid.UUID) -> None:
        """Set the project's risk_score to its highest open risk score."""
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            return
        project.risk_score = self.risks.max_open_score(self._org_id, project_id)
        project.modified_by = self._actor_id
        self.projects.update(project)

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_risk(
        self,
        *,
        project_id: uuid.UUID,
        title: str,
        description: str,
        category: RiskCategory,
        probability: int,
        impact: int,
        response_strategy: RiskResponse | None,
        owner_user_id: uuid.UUID | None,
        mitigation_plan: str,
        target_date: date | None,
    ) -> Risk:
        """Raise a risk against a project and refresh the project rollup."""
        self._get_project_or_404(project_id)
        self._require_owner(owner_user_id)
        risk = Risk(
            organization_id=self._org_id,
            project_id=project_id,
            number=self.risks.next_number(project_id),
            title=title,
            description=description,
            category=category,
            status=RiskStatus.IDENTIFIED,
            probability=probability,
            impact=impact,
            response_strategy=response_strategy,
            owner_user_id=owner_user_id,
            mitigation_plan=mitigation_plan,
            target_date=target_date,
            created_by=self._actor_id,
        )
        self._apply_score(risk)
        self.risks.add(risk)
        self._sync_project_rollup(project_id)
        self._uow.record_audit(
            "Risk",
            risk.id,
            "create",
            f"Raised risk '{title}' (score {risk.risk_score})",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        self._uow.add_event(
            "risk.raised",
            {
                "risk_id": str(risk.id),
                "project_id": str(risk.project_id),
                "title": risk.title,
                "severity": risk.severity.value,
                "score": risk.risk_score,
            },
            organization_id=self._org_id,
        )
        return risk

    def get_risk(self, risk_id: uuid.UUID) -> Risk:
        """Return a single risk by id."""
        return self._get_or_404(risk_id)

    def search_risks(
        self,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: RiskStatus | None,
        category: RiskCategory | None,
        severity: RiskSeverity | None,
        owner_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Risk], int]:
        """Return a filtered page of risks and the total matching count."""
        items = list(
            self.risks.search(
                self._org_id,
                query=query,
                project_id=project_id,
                status=status,
                category=category,
                severity=severity,
                owner_user_id=owner_user_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.risks.count(
            self._org_id,
            query=query,
            project_id=project_id,
            status=status,
            category=category,
            severity=severity,
            owner_user_id=owner_user_id,
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_risk(
        self,
        risk_id: uuid.UUID,
        *,
        title: str | None,
        description: str | None,
        category: RiskCategory | None,
        status: RiskStatus | None,
        probability: int | None,
        impact: int | None,
        response_strategy: RiskResponse | None,
        owner_user_id: uuid.UUID | None,
        mitigation_plan: str | None,
        target_date: date | None,
    ) -> Risk:
        """Apply a partial update, re-scoring and refreshing the rollup."""
        risk = self._get_or_404(risk_id)

        if status is not None:
            validate_status_transition(_ALLOWED_TRANSITIONS, risk.status, status)
            risk.status = status
        if owner_user_id is not None:
            self._require_owner(owner_user_id)
            risk.owner_user_id = owner_user_id
        for attr, value in (
            ("title", title),
            ("description", description),
            ("category", category),
            ("probability", probability),
            ("impact", impact),
            ("response_strategy", response_strategy),
            ("mitigation_plan", mitigation_plan),
            ("target_date", target_date),
        ):
            if value is not None:
                setattr(risk, attr, value)

        if probability is not None or impact is not None:
            self._apply_score(risk)

        risk.modified_by = self._actor_id
        self.risks.update(risk)
        self._sync_project_rollup(risk.project_id)
        self._uow.record_audit(
            "Risk",
            risk.id,
            "update",
            f"Updated risk '{risk.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return risk

    def delete_risk(self, risk_id: uuid.UUID) -> None:
        """Soft-delete a risk and refresh the project rollup."""
        risk = self._get_or_404(risk_id)
        project_id = risk.project_id
        self.risks.soft_delete(risk, actor_id=self._actor_id)
        self._sync_project_rollup(project_id)
        self._uow.record_audit(
            "Risk",
            risk.id,
            "delete",
            f"Deleted risk '{risk.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def get_summary(self, project_id: uuid.UUID) -> RiskSummaryResponse:
        """Return the aggregated open-risk position of a project."""
        self._get_project_or_404(project_id)
        by_severity = [
            SeverityCount(severity=sev, count=count)
            for sev, count in self.risks.open_by_severity(self._org_id, project_id)
        ]
        return RiskSummaryResponse(
            project_id=project_id,
            open_count=self.risks.open_count(self._org_id, project_id),
            max_score=self.risks.max_open_score(self._org_id, project_id),
            by_severity=by_severity,
        )
