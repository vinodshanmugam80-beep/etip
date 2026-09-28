"""Change Request Management service.

Business rules for formal change control. Each request belongs to a project and
gets a per-project number. The status follows an approval workflow; moving a
request to ``approved`` or ``rejected`` is done only through the dedicated
approve/reject operations (gated by ``change:approve``), never a plain field
update — a basic separation of duties between raising and deciding a change.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core.exceptions import NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.change.models import (
    ChangePriority,
    ChangeRequest,
    ChangeStatus,
    ChangeType,
)
from app.modules.change.repository import ChangeRequestRepository
from app.modules.change.schemas import ChangeSummaryResponse, StatusCount
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository

logger = get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[ChangeStatus, set[ChangeStatus]] = {
    ChangeStatus.DRAFT: {ChangeStatus.SUBMITTED, ChangeStatus.CANCELLED},
    ChangeStatus.SUBMITTED: {
        ChangeStatus.UNDER_REVIEW,
        ChangeStatus.APPROVED,
        ChangeStatus.REJECTED,
        ChangeStatus.CANCELLED,
    },
    ChangeStatus.UNDER_REVIEW: {
        ChangeStatus.APPROVED,
        ChangeStatus.REJECTED,
        ChangeStatus.CANCELLED,
    },
    ChangeStatus.APPROVED: {ChangeStatus.IMPLEMENTED, ChangeStatus.CANCELLED},
    ChangeStatus.REJECTED: set(),
    ChangeStatus.IMPLEMENTED: set(),
    ChangeStatus.CANCELLED: set(),
}

_DECISION_STATUSES = {ChangeStatus.APPROVED, ChangeStatus.REJECTED}


class ChangeRequestService:
    """Coordinates change-control use cases within a tenant."""

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
        self.changes = ChangeRequestRepository(session)
        self.projects = ProjectRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, change_id: uuid.UUID) -> ChangeRequest:
        change = self.changes.get(change_id, organization_id=self._org_id)
        if change is None:
            raise NotFoundError("Change request not found.")
        return change

    def _require_project(self, project_id: uuid.UUID) -> Project:
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    def _require_approver(self, approver_user_id: uuid.UUID | None) -> None:
        if approver_user_id is None:
            return
        if self.users.get(approver_user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Approver does not belong to this organization.",
                details={"approver_user_id": str(approver_user_id)},
            )

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_change_request(
        self,
        *,
        project_id: uuid.UUID,
        title: str,
        description: str,
        reason: str,
        change_type: ChangeType,
        priority: ChangePriority,
        schedule_impact_days: int | None,
        cost_impact: Decimal | None,
        impact_summary: str,
        approver_user_id: uuid.UUID | None,
        target_date: date | None,
    ) -> ChangeRequest:
        """Raise a change request against a project (starts as a draft)."""
        self._require_project(project_id)
        self._require_approver(approver_user_id)
        change = ChangeRequest(
            organization_id=self._org_id,
            project_id=project_id,
            requested_by_user_id=self._actor_id,
            approver_user_id=approver_user_id,
            number=self.changes.next_number(project_id),
            title=title,
            description=description,
            reason=reason,
            change_type=change_type,
            priority=priority,
            status=ChangeStatus.DRAFT,
            schedule_impact_days=schedule_impact_days,
            cost_impact=cost_impact,
            impact_summary=impact_summary,
            target_date=target_date,
            created_by=self._actor_id,
        )
        self.changes.add(change)
        self._uow.record_audit(
            "ChangeRequest",
            change.id,
            "create",
            f"Raised change request '{title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return change

    def get_change_request(self, change_id: uuid.UUID) -> ChangeRequest:
        """Return a single change request by id."""
        return self._get_or_404(change_id)

    def search_change_requests(
        self,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: ChangeStatus | None,
        change_type: ChangeType | None,
        priority: ChangePriority | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ChangeRequest], int]:
        """Return a filtered page of change requests and the total count."""
        items = list(
            self.changes.search(
                self._org_id,
                query=query,
                project_id=project_id,
                status=status,
                change_type=change_type,
                priority=priority,
                limit=limit,
                offset=offset,
            )
        )
        total = self.changes.count(
            self._org_id,
            query=query,
            project_id=project_id,
            status=status,
            change_type=change_type,
            priority=priority,
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / decide / delete
    # ------------------------------------------------------------------
    def update_change_request(
        self,
        change_id: uuid.UUID,
        *,
        title: str | None,
        description: str | None,
        reason: str | None,
        change_type: ChangeType | None,
        priority: ChangePriority | None,
        status: ChangeStatus | None,
        schedule_impact_days: int | None,
        cost_impact: Decimal | None,
        impact_summary: str | None,
        approver_user_id: uuid.UUID | None,
        target_date: date | None,
    ) -> ChangeRequest:
        """Apply a partial update and non-decision status transitions.

        Transitions to ``approved`` / ``rejected`` are rejected here — callers
        must use :meth:`approve` / :meth:`reject`.
        """
        change = self._get_or_404(change_id)

        if status is not None and status != change.status:
            if status in _DECISION_STATUSES:
                raise ValidationError(
                    "Use the approve or reject endpoint to decide a change request.",
                    code="use_decision_endpoint",
                )
            validate_status_transition(_ALLOWED_TRANSITIONS, change.status, status)
            change.status = status
        if approver_user_id is not None:
            self._require_approver(approver_user_id)
            change.approver_user_id = approver_user_id
        for attr, value in (
            ("title", title),
            ("description", description),
            ("reason", reason),
            ("change_type", change_type),
            ("priority", priority),
            ("schedule_impact_days", schedule_impact_days),
            ("cost_impact", cost_impact),
            ("impact_summary", impact_summary),
            ("target_date", target_date),
        ):
            if value is not None:
                setattr(change, attr, value)

        change.modified_by = self._actor_id
        self.changes.update(change)
        self._uow.record_audit(
            "ChangeRequest",
            change.id,
            "update",
            f"Updated change request '{change.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return change

    def _decide(
        self, change_id: uuid.UUID, target: ChangeStatus, decision_notes: str
    ) -> ChangeRequest:
        """Approve or reject a change request (privileged)."""
        change = self._get_or_404(change_id)
        validate_status_transition(_ALLOWED_TRANSITIONS, change.status, target)
        change.status = target
        change.approver_user_id = self._actor_id
        change.decision_notes = decision_notes
        change.decided_date = utcnow().date()
        change.modified_by = self._actor_id
        self.changes.update(change)
        self._uow.record_audit(
            "ChangeRequest",
            change.id,
            target.value,
            f"{target.value.capitalize()} change request '{change.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return change

    def approve(self, change_id: uuid.UUID, *, decision_notes: str) -> ChangeRequest:
        """Approve a change request (must be submitted or under review)."""
        return self._decide(change_id, ChangeStatus.APPROVED, decision_notes)

    def reject(self, change_id: uuid.UUID, *, decision_notes: str) -> ChangeRequest:
        """Reject a change request (must be submitted or under review)."""
        return self._decide(change_id, ChangeStatus.REJECTED, decision_notes)

    def delete_change_request(self, change_id: uuid.UUID) -> None:
        """Soft-delete a change request."""
        change = self._get_or_404(change_id)
        self.changes.soft_delete(change, actor_id=self._actor_id)
        self._uow.record_audit(
            "ChangeRequest",
            change.id,
            "delete",
            f"Deleted change request '{change.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def get_summary(self, project_id: uuid.UUID) -> ChangeSummaryResponse:
        """Return the aggregated change-control position of a project."""
        self._require_project(project_id)
        by_status = [
            StatusCount(status=st, count=count)
            for st, count in self.changes.count_by_status(self._org_id, project_id)
        ]
        return ChangeSummaryResponse(
            project_id=project_id,
            pending_count=self.changes.pending_count(self._org_id, project_id),
            total_count=self.changes.total_count(self._org_id, project_id),
            by_status=by_status,
        )
