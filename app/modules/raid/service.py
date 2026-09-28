"""RAID Log service.

Owns the Actions and Decisions quadrants and produces a consolidated per-project
RAID summary by also reading the Risks and Issues registers. Actions and
decisions each get a per-project number and a small status lifecycle; completing
an action or deciding a decision stamps the corresponding date.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.core.exceptions import NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.issue.repository import IssueRepository
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.raid.models import (
    Action,
    ActionPriority,
    ActionStatus,
    Decision,
    DecisionStatus,
)
from app.modules.raid.repository import ActionRepository, DecisionRepository
from app.modules.raid.schemas import QuadrantSummary, RaidSummaryResponse
from app.modules.risk.repository import RiskRepository

logger = get_logger(__name__)

_ACTION_TRANSITIONS: dict[ActionStatus, set[ActionStatus]] = {
    ActionStatus.OPEN: {
        ActionStatus.IN_PROGRESS,
        ActionStatus.DONE,
        ActionStatus.CANCELLED,
    },
    ActionStatus.IN_PROGRESS: {
        ActionStatus.OPEN,
        ActionStatus.DONE,
        ActionStatus.CANCELLED,
    },
    ActionStatus.DONE: {ActionStatus.IN_PROGRESS},  # reopen
    ActionStatus.CANCELLED: set(),
}

_DECISION_TRANSITIONS: dict[DecisionStatus, set[DecisionStatus]] = {
    DecisionStatus.PROPOSED: {DecisionStatus.DECIDED, DecisionStatus.REJECTED},
    DecisionStatus.DECIDED: {DecisionStatus.SUPERSEDED},
    DecisionStatus.SUPERSEDED: set(),
    DecisionStatus.REJECTED: set(),
}


class RaidService:
    """Coordinates RAID action/decision use cases within a tenant."""

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
        self.actions = ActionRepository(session)
        self.decisions = DecisionRepository(session)
        self.risks = RiskRepository(session)
        self.issues = IssueRepository(session)
        self.projects = ProjectRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _require_project(self, project_id: uuid.UUID) -> Project:
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    def _require_user(self, user_id: uuid.UUID | None, *, label: str) -> None:
        if user_id is None:
            return
        if self.users.get(user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                f"{label} does not belong to this organization.",
                details={"user_id": str(user_id)},
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _get_action_or_404(self, action_id: uuid.UUID) -> Action:
        action = self.actions.get(action_id, organization_id=self._org_id)
        if action is None:
            raise NotFoundError("Action not found.")
        return action

    def create_action(
        self,
        *,
        project_id: uuid.UUID,
        title: str,
        description: str,
        priority: ActionPriority,
        owner_user_id: uuid.UUID | None,
        due_date: date | None,
    ) -> Action:
        """Raise an action item against a project."""
        self._require_project(project_id)
        self._require_user(owner_user_id, label="Owner")
        action = Action(
            organization_id=self._org_id,
            project_id=project_id,
            number=self.actions.next_number(project_id),
            title=title,
            description=description,
            status=ActionStatus.OPEN,
            priority=priority,
            owner_user_id=owner_user_id,
            due_date=due_date,
            created_by=self._actor_id,
        )
        self.actions.add(action)
        self._uow.record_audit(
            "Action",
            action.id,
            "create",
            f"Raised action '{title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return action

    def get_action(self, action_id: uuid.UUID) -> Action:
        """Return a single action by id."""
        return self._get_action_or_404(action_id)

    def search_actions(
        self,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: ActionStatus | None,
        owner_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Action], int]:
        """Return a filtered page of actions and the total matching count."""
        items = list(
            self.actions.search(
                self._org_id,
                query=query,
                project_id=project_id,
                status=status,
                owner_user_id=owner_user_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.actions.count(
            self._org_id,
            query=query,
            project_id=project_id,
            status=status,
            owner_user_id=owner_user_id,
        )
        return items, total

    def update_action(
        self,
        action_id: uuid.UUID,
        *,
        title: str | None,
        description: str | None,
        status: ActionStatus | None,
        priority: ActionPriority | None,
        owner_user_id: uuid.UUID | None,
        due_date: date | None,
    ) -> Action:
        """Apply a partial update, managing the action workflow."""
        action = self._get_action_or_404(action_id)
        if status is not None and status != action.status:
            validate_status_transition(_ACTION_TRANSITIONS, action.status, status)
            action.status = status
            if status == ActionStatus.DONE:
                action.completed_date = utcnow().date()
            elif status in (ActionStatus.OPEN, ActionStatus.IN_PROGRESS):
                action.completed_date = None
        if owner_user_id is not None:
            self._require_user(owner_user_id, label="Owner")
            action.owner_user_id = owner_user_id
        for attr, value in (
            ("title", title),
            ("description", description),
            ("priority", priority),
            ("due_date", due_date),
        ):
            if value is not None:
                setattr(action, attr, value)
        action.modified_by = self._actor_id
        self.actions.update(action)
        self._uow.record_audit(
            "Action",
            action.id,
            "update",
            f"Updated action '{action.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return action

    def delete_action(self, action_id: uuid.UUID) -> None:
        """Soft-delete an action item."""
        action = self._get_action_or_404(action_id)
        self.actions.soft_delete(action, actor_id=self._actor_id)
        self._uow.record_audit(
            "Action",
            action.id,
            "delete",
            f"Deleted action '{action.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------
    def _get_decision_or_404(self, decision_id: uuid.UUID) -> Decision:
        decision = self.decisions.get(decision_id, organization_id=self._org_id)
        if decision is None:
            raise NotFoundError("Decision not found.")
        return decision

    def create_decision(
        self,
        *,
        project_id: uuid.UUID,
        title: str,
        description: str,
        rationale: str,
        decided_by_user_id: uuid.UUID | None,
    ) -> Decision:
        """Log a decision (starts in the proposed state)."""
        self._require_project(project_id)
        self._require_user(decided_by_user_id, label="Decider")
        decision = Decision(
            organization_id=self._org_id,
            project_id=project_id,
            number=self.decisions.next_number(project_id),
            title=title,
            description=description,
            rationale=rationale,
            status=DecisionStatus.PROPOSED,
            decided_by_user_id=decided_by_user_id,
            created_by=self._actor_id,
        )
        self.decisions.add(decision)
        self._uow.record_audit(
            "Decision",
            decision.id,
            "create",
            f"Logged decision '{title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return decision

    def get_decision(self, decision_id: uuid.UUID) -> Decision:
        """Return a single decision by id."""
        return self._get_decision_or_404(decision_id)

    def search_decisions(
        self,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: DecisionStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Decision], int]:
        """Return a filtered page of decisions and the total matching count."""
        items = list(
            self.decisions.search(
                self._org_id,
                query=query,
                project_id=project_id,
                status=status,
                limit=limit,
                offset=offset,
            )
        )
        total = self.decisions.count(
            self._org_id, query=query, project_id=project_id, status=status
        )
        return items, total

    def update_decision(
        self,
        decision_id: uuid.UUID,
        *,
        title: str | None,
        description: str | None,
        rationale: str | None,
        status: DecisionStatus | None,
        decided_by_user_id: uuid.UUID | None,
    ) -> Decision:
        """Apply a partial update, managing the decision lifecycle."""
        decision = self._get_decision_or_404(decision_id)
        if status is not None and status != decision.status:
            validate_status_transition(_DECISION_TRANSITIONS, decision.status, status)
            decision.status = status
            if status == DecisionStatus.DECIDED:
                decision.decision_date = utcnow().date()
        if decided_by_user_id is not None:
            self._require_user(decided_by_user_id, label="Decider")
            decision.decided_by_user_id = decided_by_user_id
        for attr, value in (
            ("title", title),
            ("description", description),
            ("rationale", rationale),
        ):
            if value is not None:
                setattr(decision, attr, value)
        decision.modified_by = self._actor_id
        self.decisions.update(decision)
        self._uow.record_audit(
            "Decision",
            decision.id,
            "update",
            f"Updated decision '{decision.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return decision

    def delete_decision(self, decision_id: uuid.UUID) -> None:
        """Soft-delete a decision."""
        decision = self._get_decision_or_404(decision_id)
        self.decisions.soft_delete(decision, actor_id=self._actor_id)
        self._uow.record_audit(
            "Decision",
            decision.id,
            "delete",
            f"Deleted decision '{decision.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Consolidated summary
    # ------------------------------------------------------------------
    def get_summary(self, project_id: uuid.UUID) -> RaidSummaryResponse:
        """Return open/total counts across all four RAID quadrants."""
        self._require_project(project_id)
        return RaidSummaryResponse(
            project_id=project_id,
            risks=QuadrantSummary(
                open_count=self.risks.open_count(self._org_id, project_id),
                total_count=self.risks.count(self._org_id, project_id=project_id),
            ),
            actions=QuadrantSummary(
                open_count=self.actions.open_count(self._org_id, project_id),
                total_count=self.actions.total_count(self._org_id, project_id),
            ),
            issues=QuadrantSummary(
                open_count=self.issues.open_count(self._org_id, project_id),
                total_count=self.issues.total_count(self._org_id, project_id),
            ),
            decisions=QuadrantSummary(
                open_count=self.decisions.open_count(self._org_id, project_id),
                total_count=self.decisions.total_count(self._org_id, project_id),
            ),
        )
