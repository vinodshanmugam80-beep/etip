"""Timesheet Management service.

Business rules for logging and approving time. A time entry is logged *for the
calling user* against a project (optionally a task in that project). Draft and
rejected entries are editable; submitted and approved entries are locked.
Approving/rejecting is a privileged operation (``timesheet:approve``) distinct
from logging or editing, giving separation of duties. Approved hours against a
task are rolled up into the task's ``logged_hours``.

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
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.task.repository import TaskRepository
from app.modules.timesheet.models import (
    ActivityType,
    TimeEntry,
    TimeEntryStatus,
)
from app.modules.timesheet.repository import TimeEntryRepository
from app.modules.timesheet.schemas import (
    StatusHours,
    TimesheetSummaryResponse,
)

logger = get_logger(__name__)

_EDITABLE = {TimeEntryStatus.DRAFT, TimeEntryStatus.REJECTED}
_DECISION_STATUSES = {TimeEntryStatus.APPROVED, TimeEntryStatus.REJECTED}

_ALLOWED_TRANSITIONS: dict[TimeEntryStatus, set[TimeEntryStatus]] = {
    TimeEntryStatus.DRAFT: {TimeEntryStatus.SUBMITTED},
    TimeEntryStatus.SUBMITTED: {
        TimeEntryStatus.DRAFT,  # recall
        TimeEntryStatus.APPROVED,
        TimeEntryStatus.REJECTED,
    },
    TimeEntryStatus.APPROVED: set(),
    TimeEntryStatus.REJECTED: {TimeEntryStatus.DRAFT},  # fix and resubmit
}


class TimesheetService:
    """Coordinates time-logging and approval use cases within a tenant."""

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
        self.entries = TimeEntryRepository(session)
        self.projects = ProjectRepository(session)
        self.tasks = TaskRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, entry_id: uuid.UUID) -> TimeEntry:
        entry = self.entries.get(entry_id, organization_id=self._org_id)
        if entry is None:
            raise NotFoundError("Time entry not found.")
        return entry

    def _get_project_or_404(self, project_id: uuid.UUID) -> Project:
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    def _require_task_in_project(self, task_id: uuid.UUID | None, project_id: uuid.UUID) -> None:
        if task_id is None:
            return
        task = self.tasks.get(task_id, organization_id=self._org_id)
        if task is None:
            raise NotFoundError("Task not found.")
        if task.project_id != project_id:
            raise ValidationError(
                "Task must belong to the same project as the time entry.",
                code="task_project_mismatch",
            )

    def _sync_task_hours(self, task_id: uuid.UUID | None) -> None:
        """Set a task's logged_hours to the sum of its approved time entries."""
        if task_id is None:
            return
        task = self.tasks.get(task_id, organization_id=self._org_id)
        if task is None:
            return
        task.logged_hours = self.entries.approved_hours_for_task(self._org_id, task_id)
        task.modified_by = self._actor_id
        self.tasks.update(task)

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_entry(
        self,
        *,
        project_id: uuid.UUID,
        task_id: uuid.UUID | None,
        work_date: date,
        hours: Decimal,
        billable: bool,
        activity_type: ActivityType,
        description: str,
    ) -> TimeEntry:
        """Log a draft time entry for the calling user."""
        self._get_project_or_404(project_id)
        self._require_task_in_project(task_id, project_id)
        entry = TimeEntry(
            organization_id=self._org_id,
            project_id=project_id,
            task_id=task_id,
            user_id=self._actor_id,
            work_date=work_date,
            hours=hours,
            billable=billable,
            activity_type=activity_type,
            description=description,
            status=TimeEntryStatus.DRAFT,
            created_by=self._actor_id,
        )
        self.entries.add(entry)
        self._uow.record_audit(
            "TimeEntry",
            entry.id,
            "create",
            f"Logged {hours}h on {work_date.isoformat()}",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return entry

    def get_entry(self, entry_id: uuid.UUID) -> TimeEntry:
        """Return a single time entry by id."""
        return self._get_or_404(entry_id)

    def search_entries(
        self,
        *,
        project_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        status: TimeEntryStatus | None,
        billable: bool | None,
        activity_type: ActivityType | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[TimeEntry], int]:
        """Return a filtered page of time entries and the total count."""
        items = list(
            self.entries.search(
                self._org_id,
                project_id=project_id,
                task_id=task_id,
                user_id=user_id,
                status=status,
                billable=billable,
                activity_type=activity_type,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
            )
        )
        total = self.entries.count(
            self._org_id,
            project_id=project_id,
            task_id=task_id,
            user_id=user_id,
            status=status,
            billable=billable,
            activity_type=activity_type,
            date_from=date_from,
            date_to=date_to,
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / decide / delete
    # ------------------------------------------------------------------
    def update_entry(
        self,
        entry_id: uuid.UUID,
        *,
        task_id: uuid.UUID | None,
        work_date: date | None,
        hours: Decimal | None,
        billable: bool | None,
        activity_type: ActivityType | None,
        description: str | None,
        status: TimeEntryStatus | None,
    ) -> TimeEntry:
        """Edit a draft/rejected entry and move it between draft and submitted."""
        entry = self._get_or_404(entry_id)

        wants_field_edit = any(
            value is not None
            for value in (
                task_id,
                work_date,
                hours,
                billable,
                activity_type,
                description,
            )
        )
        if wants_field_edit and entry.status not in _EDITABLE:
            raise ValidationError(
                "Only draft or rejected time entries can be edited.",
                code="entry_locked",
            )

        if status is not None and status != entry.status:
            if status in _DECISION_STATUSES:
                raise ValidationError(
                    "Use the approve or reject endpoint to decide a time entry.",
                    code="use_decision_endpoint",
                )
            validate_status_transition(_ALLOWED_TRANSITIONS, entry.status, status)
            entry.status = status

        if task_id is not None:
            self._require_task_in_project(task_id, entry.project_id)
            entry.task_id = task_id
        for attr, value in (
            ("work_date", work_date),
            ("hours", hours),
            ("billable", billable),
            ("activity_type", activity_type),
            ("description", description),
        ):
            if value is not None:
                setattr(entry, attr, value)

        entry.modified_by = self._actor_id
        self.entries.update(entry)
        self._uow.record_audit(
            "TimeEntry",
            entry.id,
            "update",
            "Updated time entry",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return entry

    def _decide(
        self, entry_id: uuid.UUID, target: TimeEntryStatus, decision_notes: str
    ) -> TimeEntry:
        """Approve or reject a submitted time entry (privileged)."""
        entry = self._get_or_404(entry_id)
        validate_status_transition(_ALLOWED_TRANSITIONS, entry.status, target)
        entry.status = target
        entry.approver_user_id = self._actor_id
        entry.decision_notes = decision_notes
        entry.decided_date = utcnow().date()
        entry.modified_by = self._actor_id
        self.entries.update(entry)
        # Approving/rejecting changes the approved-hours rollup on the task.
        self._sync_task_hours(entry.task_id)
        self._uow.record_audit(
            "TimeEntry",
            entry.id,
            target.value,
            f"{target.value.capitalize()} time entry",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return entry

    def approve(self, entry_id: uuid.UUID, *, decision_notes: str) -> TimeEntry:
        """Approve a submitted time entry."""
        return self._decide(entry_id, TimeEntryStatus.APPROVED, decision_notes)

    def reject(self, entry_id: uuid.UUID, *, decision_notes: str) -> TimeEntry:
        """Reject a submitted time entry."""
        return self._decide(entry_id, TimeEntryStatus.REJECTED, decision_notes)

    def delete_entry(self, entry_id: uuid.UUID) -> None:
        """Soft-delete a time entry, refreshing the task rollup if needed."""
        entry = self._get_or_404(entry_id)
        task_id = entry.task_id
        was_approved = entry.status == TimeEntryStatus.APPROVED
        self.entries.soft_delete(entry, actor_id=self._actor_id)
        if was_approved:
            self._sync_task_hours(task_id)
        self._uow.record_audit(
            "TimeEntry",
            entry.id,
            "delete",
            "Deleted time entry",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def get_summary(
        self,
        *,
        project_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
    ) -> TimesheetSummaryResponse:
        """Return aggregated hours over a filtered set of time entries."""
        total = self.entries.sum_hours(
            self._org_id,
            project_id=project_id,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
        )
        billable = self.entries.sum_hours(
            self._org_id,
            project_id=project_id,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            billable=True,
        )
        approved = self.entries.sum_hours(
            self._org_id,
            project_id=project_id,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            status=TimeEntryStatus.APPROVED,
        )
        rows = self.entries.hours_by_status(
            self._org_id,
            project_id=project_id,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
        )
        entry_count = sum(count for _, _, count in rows)
        by_status = [StatusHours(status=st, hours=hours, count=count) for st, hours, count in rows]
        return TimesheetSummaryResponse(
            total_hours=total,
            billable_hours=billable,
            approved_hours=approved,
            entry_count=entry_count,
            by_status=by_status,
        )
