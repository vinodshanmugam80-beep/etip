"""Milestone Management service.

Business rules for project schedule checkpoints. Each milestone belongs to a
project, gets a per-project number, and follows a small status lifecycle;
achieving a milestone stamps its ``actual_date`` (cleared if it is reopened or
marked missed). A milestone is *overdue* when it is still open (planned or in
progress) and its target date has passed.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.finance.models import CostCategory, FinancialEntryType
from app.modules.finance.service import FinanceService
from app.modules.milestone.models import (
    Milestone,
    MilestonePaymentStatus,
    MilestoneStatus,
    MilestoneType,
)
from app.modules.milestone.repository import MilestoneRepository
from app.modules.milestone.schemas import (
    FinancialMilestoneItem,
    FinancialMilestoneOverview,
    FinancialMilestoneSummary,
    MilestoneSummaryResponse,
    StatusCount,
)
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.task.repository import TaskRepository
from app.modules.workflow.models import WorkflowStatus
from app.modules.workflow.repository import WorkflowInstanceRepository
from app.modules.workflow.schemas import WorkflowInstanceStartRequest
from app.modules.workflow.service import WorkflowService

logger = get_logger(__name__)

_OPEN_STATUSES = {MilestoneStatus.PLANNED, MilestoneStatus.IN_PROGRESS}
_CLEAR_ACTUAL = {
    MilestoneStatus.PLANNED,
    MilestoneStatus.IN_PROGRESS,
    MilestoneStatus.MISSED,
}

_ALLOWED_TRANSITIONS: dict[MilestoneStatus, set[MilestoneStatus]] = {
    MilestoneStatus.PLANNED: {
        MilestoneStatus.IN_PROGRESS,
        MilestoneStatus.ACHIEVED,
        MilestoneStatus.MISSED,
        MilestoneStatus.CANCELLED,
    },
    MilestoneStatus.IN_PROGRESS: {
        MilestoneStatus.PLANNED,
        MilestoneStatus.ACHIEVED,
        MilestoneStatus.MISSED,
        MilestoneStatus.CANCELLED,
    },
    MilestoneStatus.ACHIEVED: {MilestoneStatus.IN_PROGRESS},  # reopen
    MilestoneStatus.MISSED: {MilestoneStatus.IN_PROGRESS, MilestoneStatus.ACHIEVED},
    MilestoneStatus.CANCELLED: set(),
}


def milestone_is_overdue(milestone: Milestone, as_of: date) -> bool:
    """Return whether a milestone is open and past its target date."""
    return milestone.status in _OPEN_STATUSES and milestone.target_date < as_of


class MilestoneService:
    """Coordinates milestone use cases within a tenant."""

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
        self.milestones = MilestoneRepository(session)
        self.projects = ProjectRepository(session)
        self.tasks = TaskRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, milestone_id: uuid.UUID) -> Milestone:
        milestone = self.milestones.get(milestone_id, organization_id=self._org_id)
        if milestone is None:
            raise NotFoundError("Milestone not found.")
        return milestone

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

    def _require_task_in_project(self, task_id: uuid.UUID | None, project_id: uuid.UUID) -> None:
        if task_id is None:
            return
        task = self.tasks.get(task_id, organization_id=self._org_id)
        if task is None:
            raise NotFoundError("Task not found.")
        if task.project_id != project_id:
            raise ValidationError(
                "Task must belong to the same project as the milestone.",
                code="task_project_mismatch",
            )

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_milestone(
        self,
        *,
        project_id: uuid.UUID,
        name: str,
        description: str,
        milestone_type: MilestoneType,
        target_date: date,
        owner_user_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        is_key: bool,
        deliverable: str = "",
        payment_amount: Decimal | None = None,
        currency: str = "USD",
    ) -> Milestone:
        """Create a milestone on a project.

        When ``payment_amount`` is supplied the milestone is a financial (billing)
        milestone: its payment starts ``PENDING`` and is released only after the
        named ``deliverable`` is accepted at the acceptance gate.
        """
        project = self._get_project_or_404(project_id)
        self._require_task_in_project(task_id, project_id)
        self._require_owner(owner_user_id)
        is_financial = payment_amount is not None
        if is_financial and currency != project.currency:
            raise ValidationError(
                "Milestone payment currency must match the project currency.",
                code="currency_mismatch",
                details={"expected": project.currency, "got": currency},
            )
        milestone = Milestone(
            organization_id=self._org_id,
            project_id=project_id,
            task_id=task_id,
            owner_user_id=owner_user_id,
            number=self.milestones.next_number(project_id),
            name=name,
            description=description,
            milestone_type=milestone_type,
            status=MilestoneStatus.PLANNED,
            target_date=target_date,
            is_key=is_key,
            deliverable=deliverable,
            payment_amount=payment_amount,
            currency=currency,
            payment_status=(
                MilestonePaymentStatus.PENDING
                if is_financial
                else MilestonePaymentStatus.NOT_APPLICABLE
            ),
            created_by=self._actor_id,
        )
        self.milestones.add(milestone)
        self._uow.record_audit(
            "Milestone",
            milestone.id,
            "create",
            f"Created milestone '{name}' (target {target_date.isoformat()})",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return milestone

    def get_milestone(self, milestone_id: uuid.UUID) -> Milestone:
        """Return a single milestone by id."""
        return self._get_or_404(milestone_id)

    def search_milestones(
        self,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: MilestoneStatus | None,
        milestone_type: MilestoneType | None,
        is_key: bool | None,
        owner_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Milestone], int]:
        """Return a filtered page of milestones and the total matching count."""
        items = list(
            self.milestones.search(
                self._org_id,
                query=query,
                project_id=project_id,
                status=status,
                milestone_type=milestone_type,
                is_key=is_key,
                owner_user_id=owner_user_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.milestones.count(
            self._org_id,
            query=query,
            project_id=project_id,
            status=status,
            milestone_type=milestone_type,
            is_key=is_key,
            owner_user_id=owner_user_id,
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_milestone(
        self,
        milestone_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
        milestone_type: MilestoneType | None,
        status: MilestoneStatus | None,
        target_date: date | None,
        actual_date: date | None,
        owner_user_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        is_key: bool | None,
        deliverable: str | None = None,
        payment_amount: Decimal | None = None,
        currency: str | None = None,
    ) -> Milestone:
        """Apply a partial update, managing status and actual-date stamping."""
        milestone = self._get_or_404(milestone_id)

        if payment_amount is not None or currency is not None:
            if milestone.payment_status == MilestonePaymentStatus.RELEASED:
                raise ConflictError("Payment has been released; the amount cannot be changed.")
        if payment_amount is not None:
            milestone.payment_amount = payment_amount
            if milestone.payment_status == MilestonePaymentStatus.NOT_APPLICABLE:
                milestone.payment_status = MilestonePaymentStatus.PENDING
        if currency is not None:
            project = self._get_project_or_404(milestone.project_id)
            if currency != project.currency:
                raise ValidationError(
                    "Milestone payment currency must match the project currency.",
                    code="currency_mismatch",
                    details={"expected": project.currency, "got": currency},
                )
            milestone.currency = currency
        if deliverable is not None:
            milestone.deliverable = deliverable

        if status is not None and status != milestone.status:
            validate_status_transition(_ALLOWED_TRANSITIONS, milestone.status, status)
            milestone.status = status
            if status == MilestoneStatus.ACHIEVED and milestone.actual_date is None:
                milestone.actual_date = utcnow().date()
            elif status in _CLEAR_ACTUAL:
                milestone.actual_date = None
        if owner_user_id is not None:
            self._require_owner(owner_user_id)
            milestone.owner_user_id = owner_user_id
        if task_id is not None:
            self._require_task_in_project(task_id, milestone.project_id)
            milestone.task_id = task_id
        for attr, value in (
            ("name", name),
            ("description", description),
            ("milestone_type", milestone_type),
            ("target_date", target_date),
            ("actual_date", actual_date),
            ("is_key", is_key),
        ):
            if value is not None:
                setattr(milestone, attr, value)

        milestone.modified_by = self._actor_id
        self.milestones.update(milestone)
        self._uow.record_audit(
            "Milestone",
            milestone.id,
            "update",
            f"Updated milestone '{milestone.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return milestone

    def delete_milestone(self, milestone_id: uuid.UUID) -> None:
        """Soft-delete a milestone."""
        milestone = self._get_or_404(milestone_id)
        self.milestones.soft_delete(milestone, actor_id=self._actor_id)
        self._uow.record_audit(
            "Milestone",
            milestone.id,
            "delete",
            f"Deleted milestone '{milestone.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Financial milestone: deliverable acceptance → payment release
    # ------------------------------------------------------------------
    def _workflow(self) -> WorkflowService:
        return WorkflowService(
            self._uow, organization_id=self._org_id, actor_id=self._actor_id
        )

    def submit_for_acceptance(self, milestone_id: uuid.UUID) -> Milestone:
        """Open the deliverable-acceptance gate for a financial milestone.

        Starts a workflow instance (``entity_type='Milestone'``) against the
        canonical acceptance definition. The current actor becomes the initiator,
        so — by the workflow engine's separation-of-duties rule — a *different*
        user must accept the deliverable at the gate.
        """
        milestone = self._get_or_404(milestone_id)
        if milestone.payment_amount is None:
            raise ValidationError("Only financial milestones can be submitted for acceptance.")
        if not milestone.deliverable.strip():
            raise ValidationError("Name the deliverable before submitting it for acceptance.")
        if milestone.acceptance_instance_id is not None:
            existing = WorkflowInstanceRepository(self._uow.session).get(
                milestone.acceptance_instance_id, organization_id=self._org_id
            )
            if existing is not None and existing.status == WorkflowStatus.IN_PROGRESS:
                raise ConflictError("This deliverable is already awaiting acceptance.")
        if milestone.payment_status == MilestonePaymentStatus.RELEASED:
            raise ConflictError("Payment has already been released for this milestone.")

        workflow = self._workflow()
        definition = workflow.ensure_acceptance_definition()
        instance = workflow.start_instance(
            WorkflowInstanceStartRequest(
                definition_id=definition.id,
                entity_type="Milestone",
                entity_id=milestone.id,
            )
        )
        milestone.acceptance_instance_id = instance.id
        milestone.payment_status = MilestonePaymentStatus.PENDING
        if milestone.status == MilestoneStatus.PLANNED:
            milestone.status = MilestoneStatus.IN_PROGRESS
        milestone.modified_by = self._actor_id
        self.milestones.update(milestone)
        self._uow.record_audit(
            "Milestone",
            milestone.id,
            "submit_acceptance",
            f"Submitted deliverable '{milestone.deliverable}' for acceptance",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return milestone

    def release_payment(self, milestone_id: uuid.UUID) -> Milestone:
        """Release a financial milestone's payment once its deliverable is accepted.

        Requires the acceptance gate to have completed (all gates approved). Posts
        an *actual* cost line to the project ledger for the payment amount, marks
        the payment ``RELEASED`` and the milestone ``ACHIEVED``.
        """
        milestone = self._get_or_404(milestone_id)
        if milestone.payment_amount is None:
            raise ValidationError("This milestone has no payment to release.")
        if milestone.payment_status == MilestonePaymentStatus.RELEASED:
            raise ConflictError("Payment has already been released.")
        if milestone.acceptance_instance_id is None:
            raise ConflictError("Submit the deliverable for acceptance first.")
        instance = WorkflowInstanceRepository(self._uow.session).get(
            milestone.acceptance_instance_id, organization_id=self._org_id
        )
        if instance is None or instance.status != WorkflowStatus.COMPLETED:
            raise ConflictError(
                "The deliverable must be fully accepted at the gate before payment is released."
            )

        finance = FinanceService(
            self._uow, organization_id=self._org_id, actor_id=self._actor_id
        )
        today = utcnow().date()
        finance.create_entry(
            project_id=milestone.project_id,
            entry_type=FinancialEntryType.ACTUAL,
            category=CostCategory.SERVICES,
            amount=milestone.payment_amount,
            currency=milestone.currency,
            entry_date=today,
            description=f"Milestone payment: {milestone.name} — {milestone.deliverable}",
            vendor="",
        )
        milestone.payment_status = MilestonePaymentStatus.RELEASED
        milestone.paid_date = today
        if milestone.status != MilestoneStatus.ACHIEVED:
            milestone.status = MilestoneStatus.ACHIEVED
            milestone.actual_date = today
        milestone.modified_by = self._actor_id
        self.milestones.update(milestone)
        self._uow.record_audit(
            "Milestone",
            milestone.id,
            "release_payment",
            f"Released payment {milestone.payment_amount} {milestone.currency} "
            f"for '{milestone.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        self._uow.add_event(
            "milestone.payment_released",
            {
                "milestone_id": str(milestone.id),
                "project_id": str(milestone.project_id),
                "amount": str(milestone.payment_amount),
                "currency": milestone.currency,
            },
            organization_id=self._org_id,
        )
        return milestone

    def financial_overview(self) -> FinancialMilestoneOverview:
        """Return the financial-milestone / deliverable-acceptance dashboard model."""
        milestones = [
            m
            for m in self.milestones.search(
                self._org_id, query=None, project_id=None, status=None,
                milestone_type=None, is_key=None, owner_user_id=None,
                limit=1000, offset=0,
            )
            if m.payment_amount is not None
        ]
        wf_repo = WorkflowInstanceRepository(self._uow.session)
        wf = self._workflow()
        project_labels = self._project_labels({m.project_id for m in milestones})

        items: list[FinancialMilestoneItem] = []
        total = released = pending = Decimal("0")
        awaiting = awaiting_me = ready = 0
        for m in milestones:
            amount = m.payment_amount or Decimal("0")
            total += amount
            if m.payment_status == MilestonePaymentStatus.RELEASED:
                released += amount
            else:
                pending += amount

            acceptance_status = "not_submitted"
            current_gate: str | None = None
            awaiting_my = False
            can_release = False
            if m.acceptance_instance_id is not None:
                inst = wf_repo.get(m.acceptance_instance_id, organization_id=self._org_id)
                if inst is not None:
                    if inst.status == WorkflowStatus.IN_PROGRESS:
                        acceptance_status = "pending"
                        stage = next(
                            (
                                s
                                for s in wf.stages.list_for_definition(
                                    self._org_id, inst.definition_id
                                )
                                if s.id == inst.current_stage_id
                            ),
                            None,
                        )
                        current_gate = stage.name if stage else None
                        if stage is not None and stage.requires_approval:
                            awaiting = awaiting + 1
                            if inst.started_by != self._actor_id:
                                awaiting_my = True
                                awaiting_me += 1
                    elif inst.status == WorkflowStatus.COMPLETED:
                        acceptance_status = "accepted"
                        if m.payment_status != MilestonePaymentStatus.RELEASED:
                            can_release = True
                            ready += 1
                    elif inst.status == WorkflowStatus.REJECTED:
                        acceptance_status = "rejected"

            items.append(
                FinancialMilestoneItem(
                    milestone_id=m.id,
                    project_id=m.project_id,
                    project_label=project_labels.get(m.project_id, "Project"),
                    name=m.name,
                    deliverable=m.deliverable,
                    payment_amount=amount,
                    currency=m.currency,
                    status=m.status,
                    payment_status=m.payment_status,
                    target_date=m.target_date,
                    acceptance_status=acceptance_status,
                    acceptance_instance_id=m.acceptance_instance_id,
                    current_gate=current_gate,
                    awaiting_my_acceptance=awaiting_my,
                    can_release=can_release,
                    paid_date=m.paid_date,
                )
            )

        items.sort(
            key=lambda i: (
                i.payment_status == MilestonePaymentStatus.RELEASED,
                i.target_date,
            )
        )
        summary = FinancialMilestoneSummary(
            total_value=total,
            released_value=released,
            pending_value=pending,
            count=len(items),
            awaiting_acceptance=awaiting,
            awaiting_my_acceptance=awaiting_me,
            ready_to_release=ready,
        )
        return FinancialMilestoneOverview(summary=summary, items=items)

    def _project_labels(self, project_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        labels: dict[uuid.UUID, str] = {}
        for pid in project_ids:
            project = self.projects.get(pid, organization_id=self._org_id)
            if project is not None:
                labels[pid] = f"{project.code} · {project.name}"
        return labels

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def get_summary(self, project_id: uuid.UUID) -> MilestoneSummaryResponse:
        """Return the aggregated milestone position of a project."""
        self._get_project_or_404(project_id)
        today = utcnow().date()
        by_status = [
            StatusCount(status=st, count=count)
            for st, count in self.milestones.count_by_status(self._org_id, project_id)
        ]
        return MilestoneSummaryResponse(
            project_id=project_id,
            total_count=self.milestones.total_count(self._org_id, project_id),
            key_count=self.milestones.key_count(self._org_id, project_id),
            overdue_count=self.milestones.overdue_count(self._org_id, project_id, as_of=today),
            by_status=by_status,
        )
