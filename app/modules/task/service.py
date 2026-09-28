"""Task Management service.

Business rules for tasks: each task belongs to a project (validated), the
assignee must be in the tenant, a subtask's parent must be in the same project
with no cycle, the status follows a task-specific lifecycle, effort and dates
are validated, and each task gets a per-project running number. Deleting a task
that still has subtasks is blocked.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.dependency.models import DependencyEntityType
from app.modules.dependency.repository import DependencyRepository
from app.modules.project.repository import ProjectRepository
from app.modules.task.models import Task, TaskPriority, TaskStatus
from app.modules.task.repository import TaskRepository

logger = get_logger(__name__)

_MAX_DEPTH = 20

_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.TODO: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.IN_PROGRESS: {
        TaskStatus.IN_REVIEW,
        TaskStatus.BLOCKED,
        TaskStatus.DONE,
        TaskStatus.CANCELLED,
    },
    TaskStatus.IN_REVIEW: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.DONE,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.BLOCKED: {
        TaskStatus.TODO,
        TaskStatus.IN_PROGRESS,
        TaskStatus.CANCELLED,
    },
    TaskStatus.DONE: {TaskStatus.IN_PROGRESS},  # reopen
    TaskStatus.CANCELLED: set(),
}


class TaskService:
    """Coordinates task use cases within a tenant."""

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
        self.tasks = TaskRepository(session)
        self.dependencies = DependencyRepository(session)
        self.projects = ProjectRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, task_id: uuid.UUID) -> Task:
        task = self.tasks.get(task_id, organization_id=self._org_id)
        if task is None:
            raise NotFoundError("Task not found.")
        return task

    def _require_project(self, project_id: uuid.UUID) -> None:
        if self.projects.get(project_id, organization_id=self._org_id) is None:
            raise NotFoundError("Project not found.")

    def _require_assignee(self, assignee_user_id: uuid.UUID | None) -> None:
        if assignee_user_id is None:
            return
        if self.users.get(assignee_user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Assignee does not belong to this organization.",
                details={"assignee_user_id": str(assignee_user_id)},
            )

    def _resolve_parent(self, task: Task, parent_id: uuid.UUID, project_id: uuid.UUID) -> None:
        """Set a task's parent, enforcing same-project and no-cycle rules."""
        if parent_id == task.id:
            raise ValidationError("A task cannot be its own parent.")
        parent = self._get_or_404(parent_id)
        if parent.project_id != project_id:
            raise ValidationError("Parent task must be in the same project.")
        cursor: Task | None = parent
        depth = 0
        while cursor is not None:
            if cursor.id == task.id:
                raise ValidationError("Assigning this parent would create a subtask cycle.")
            if cursor.parent_task_id is None:
                break
            depth += 1
            if depth > _MAX_DEPTH:
                raise ValidationError("Task hierarchy is too deep.")
            cursor = self.tasks.get(cursor.parent_task_id, organization_id=self._org_id)
        task.parent_task_id = parent_id

    @staticmethod
    def _validate_dates(start: date | None, due: date | None) -> None:
        if start and due and due < start:
            raise ValidationError("due_date must not be before start_date.")

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_task(
        self,
        *,
        project_id: uuid.UUID,
        title: str,
        description: str,
        assignee_user_id: uuid.UUID | None,
        parent_task_id: uuid.UUID | None,
        priority: TaskPriority,
        estimate_hours: Decimal,
        start_date: date | None,
        due_date: date | None,
    ) -> Task:
        """Create a task within a project, validating references and hierarchy."""
        self._require_project(project_id)
        self._require_assignee(assignee_user_id)
        self._validate_dates(start_date, due_date)

        task = Task(
            organization_id=self._org_id,
            project_id=project_id,
            number=self.tasks.next_number(project_id),
            title=title,
            description=description,
            assignee_user_id=assignee_user_id,
            priority=priority,
            status=TaskStatus.TODO,
            estimate_hours=estimate_hours,
            start_date=start_date,
            due_date=due_date,
            created_by=self._actor_id,
        )
        if parent_task_id is not None:
            self._resolve_parent(task, parent_task_id, project_id)
        self.tasks.add(task)
        self._uow.record_audit(
            "Task",
            task.id,
            "create",
            f"Created task '{title}' (#{task.number})",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return task

    def get_task(self, task_id: uuid.UUID) -> Task:
        """Return a single task by id."""
        return self._get_or_404(task_id)

    def search_tasks(
        self,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: TaskStatus | None,
        priority: TaskPriority | None,
        assignee_user_id: uuid.UUID | None,
        parent_task_id: uuid.UUID | None,
        sprint_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        """Return a filtered page of tasks and the total matching count."""
        items = list(
            self.tasks.search(
                self._org_id,
                query=query,
                project_id=project_id,
                status=status,
                priority=priority,
                assignee_user_id=assignee_user_id,
                parent_task_id=parent_task_id,
                sprint_id=sprint_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.tasks.count(
            self._org_id,
            query=query,
            project_id=project_id,
            status=status,
            priority=priority,
            assignee_user_id=assignee_user_id,
            parent_task_id=parent_task_id,
            sprint_id=sprint_id,
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_task(
        self,
        task_id: uuid.UUID,
        *,
        title: str | None,
        description: str | None,
        assignee_user_id: uuid.UUID | None,
        parent_task_id: uuid.UUID | None,
        status: TaskStatus | None,
        priority: TaskPriority | None,
        estimate_hours: Decimal | None,
        logged_hours: Decimal | None,
        start_date: date | None,
        due_date: date | None,
        position: int | None,
    ) -> Task:
        """Apply a partial update, validating transitions, refs and hierarchy."""
        task = self._get_or_404(task_id)

        if status is not None:
            validate_status_transition(_ALLOWED_TRANSITIONS, task.status, status)
            task.status = status
        if assignee_user_id is not None:
            self._require_assignee(assignee_user_id)
            task.assignee_user_id = assignee_user_id
        if parent_task_id is not None:
            self._resolve_parent(task, parent_task_id, task.project_id)

        for attr, value in (
            ("title", title),
            ("description", description),
            ("priority", priority),
            ("estimate_hours", estimate_hours),
            ("logged_hours", logged_hours),
            ("start_date", start_date),
            ("due_date", due_date),
            ("position", position),
        ):
            if value is not None:
                setattr(task, attr, value)

        self._validate_dates(task.start_date, task.due_date)

        task.modified_by = self._actor_id
        self.tasks.update(task)
        self._uow.record_audit(
            "Task",
            task.id,
            "update",
            f"Updated task '{task.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return task

    def delete_task(self, task_id: uuid.UUID) -> None:
        """Soft-delete a task, blocking if it still has subtasks."""
        task = self._get_or_404(task_id)
        if self.tasks.has_subtasks(self._org_id, task_id):
            raise ConflictError(
                "Cannot delete a task that still has subtasks.",
                code="task_has_subtasks",
            )
        self.dependencies.soft_delete_for_entities(
            self._org_id, DependencyEntityType.TASK, [task_id], actor_id=self._actor_id
        )
        self.tasks.soft_delete(task, actor_id=self._actor_id)
        self._uow.record_audit(
            "Task",
            task.id,
            "delete",
            f"Deleted task '{task.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
