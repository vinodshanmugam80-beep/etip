"""Issue Management service.

Business rules for the project issue tracker. Each issue belongs to a project
and may link to a task in that same project. The reporter is the acting user;
the status follows a workflow that supports reopening, and resolving stamps a
resolution date (cleared on reopen). The owning project's ``issue_count`` rollup
is kept equal to the number of open (non-closed) issues.

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
from app.modules.issue.models import (
    Issue,
    IssuePriority,
    IssueSeverity,
    IssueStatus,
    IssueType,
)
from app.modules.issue.repository import IssueRepository
from app.modules.issue.schemas import IssueSummaryResponse, StatusCount
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.task.repository import TaskRepository

logger = get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[IssueStatus, set[IssueStatus]] = {
    IssueStatus.OPEN: {
        IssueStatus.IN_PROGRESS,
        IssueStatus.RESOLVED,
        IssueStatus.CLOSED,
    },
    IssueStatus.IN_PROGRESS: {
        IssueStatus.OPEN,
        IssueStatus.RESOLVED,
        IssueStatus.CLOSED,
    },
    IssueStatus.RESOLVED: {IssueStatus.IN_PROGRESS, IssueStatus.CLOSED},
    IssueStatus.CLOSED: {IssueStatus.IN_PROGRESS},  # reopen
}


class IssueService:
    """Coordinates issue tracker use cases within a tenant."""

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
        self.issues = IssueRepository(session)
        self.projects = ProjectRepository(session)
        self.tasks = TaskRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, issue_id: uuid.UUID) -> Issue:
        issue = self.issues.get(issue_id, organization_id=self._org_id)
        if issue is None:
            raise NotFoundError("Issue not found.")
        return issue

    def _get_project_or_404(self, project_id: uuid.UUID) -> Project:
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    def _require_assignee(self, assignee_user_id: uuid.UUID | None) -> None:
        if assignee_user_id is None:
            return
        if self.users.get(assignee_user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Assignee does not belong to this organization.",
                details={"assignee_user_id": str(assignee_user_id)},
            )

    def _require_task_in_project(self, task_id: uuid.UUID | None, project_id: uuid.UUID) -> None:
        if task_id is None:
            return
        task = self.tasks.get(task_id, organization_id=self._org_id)
        if task is None:
            raise NotFoundError("Task not found.")
        if task.project_id != project_id:
            raise ValidationError(
                "Task must belong to the same project as the issue.",
                code="task_project_mismatch",
            )

    def _sync_project_rollup(self, project_id: uuid.UUID) -> None:
        """Set the project's issue_count to its number of open issues."""
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            return
        project.issue_count = self.issues.open_count(self._org_id, project_id)
        project.modified_by = self._actor_id
        self.projects.update(project)

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_issue(
        self,
        *,
        project_id: uuid.UUID,
        task_id: uuid.UUID | None,
        title: str,
        description: str,
        issue_type: IssueType,
        severity: IssueSeverity,
        priority: IssuePriority,
        assignee_user_id: uuid.UUID | None,
        due_date: date | None,
    ) -> Issue:
        """Raise an issue against a project and refresh the project rollup."""
        self._get_project_or_404(project_id)
        self._require_task_in_project(task_id, project_id)
        self._require_assignee(assignee_user_id)
        issue = Issue(
            organization_id=self._org_id,
            project_id=project_id,
            task_id=task_id,
            number=self.issues.next_number(project_id),
            title=title,
            description=description,
            issue_type=issue_type,
            severity=severity,
            priority=priority,
            status=IssueStatus.OPEN,
            assignee_user_id=assignee_user_id,
            reporter_user_id=self._actor_id,
            due_date=due_date,
            created_by=self._actor_id,
        )
        self.issues.add(issue)
        self._sync_project_rollup(project_id)
        self._uow.record_audit(
            "Issue",
            issue.id,
            "create",
            f"Raised issue '{title}' (#{issue.number})",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return issue

    def get_issue(self, issue_id: uuid.UUID) -> Issue:
        """Return a single issue by id."""
        return self._get_or_404(issue_id)

    def search_issues(
        self,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        status: IssueStatus | None,
        issue_type: IssueType | None,
        severity: IssueSeverity | None,
        priority: IssuePriority | None,
        assignee_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Issue], int]:
        """Return a filtered page of issues and the total matching count."""
        items = list(
            self.issues.search(
                self._org_id,
                query=query,
                project_id=project_id,
                task_id=task_id,
                status=status,
                issue_type=issue_type,
                severity=severity,
                priority=priority,
                assignee_user_id=assignee_user_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.issues.count(
            self._org_id,
            query=query,
            project_id=project_id,
            task_id=task_id,
            status=status,
            issue_type=issue_type,
            severity=severity,
            priority=priority,
            assignee_user_id=assignee_user_id,
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_issue(
        self,
        issue_id: uuid.UUID,
        *,
        title: str | None,
        description: str | None,
        task_id: uuid.UUID | None,
        issue_type: IssueType | None,
        severity: IssueSeverity | None,
        priority: IssuePriority | None,
        status: IssueStatus | None,
        assignee_user_id: uuid.UUID | None,
        resolution: str | None,
        due_date: date | None,
    ) -> Issue:
        """Apply a partial update, managing the workflow and project rollup."""
        issue = self._get_or_404(issue_id)

        if status is not None and status != issue.status:
            validate_status_transition(_ALLOWED_TRANSITIONS, issue.status, status)
            issue.status = status
            if status == IssueStatus.RESOLVED:
                issue.resolved_date = utcnow().date()
            elif status in (IssueStatus.OPEN, IssueStatus.IN_PROGRESS):
                issue.resolved_date = None
        if task_id is not None:
            self._require_task_in_project(task_id, issue.project_id)
            issue.task_id = task_id
        if assignee_user_id is not None:
            self._require_assignee(assignee_user_id)
            issue.assignee_user_id = assignee_user_id
        for attr, value in (
            ("title", title),
            ("description", description),
            ("issue_type", issue_type),
            ("severity", severity),
            ("priority", priority),
            ("resolution", resolution),
            ("due_date", due_date),
        ):
            if value is not None:
                setattr(issue, attr, value)

        issue.modified_by = self._actor_id
        self.issues.update(issue)
        self._sync_project_rollup(issue.project_id)
        self._uow.record_audit(
            "Issue",
            issue.id,
            "update",
            f"Updated issue '{issue.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return issue

    def delete_issue(self, issue_id: uuid.UUID) -> None:
        """Soft-delete an issue and refresh the project rollup."""
        issue = self._get_or_404(issue_id)
        project_id = issue.project_id
        self.issues.soft_delete(issue, actor_id=self._actor_id)
        self._sync_project_rollup(project_id)
        self._uow.record_audit(
            "Issue",
            issue.id,
            "delete",
            f"Deleted issue '{issue.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def get_summary(self, project_id: uuid.UUID) -> IssueSummaryResponse:
        """Return the aggregated issue position of a project."""
        self._get_project_or_404(project_id)
        by_status = [
            StatusCount(status=st, count=count)
            for st, count in self.issues.count_by_status(self._org_id, project_id)
        ]
        return IssueSummaryResponse(
            project_id=project_id,
            open_count=self.issues.open_count(self._org_id, project_id),
            total_count=self.issues.total_count(self._org_id, project_id),
            by_status=by_status,
        )
