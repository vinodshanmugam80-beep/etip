"""Sprint Management service.

Business rules for sprints: each sprint belongs to a project (validated), has a
per-project running number, follows a planned→active→completed lifecycle, and a
project may have **at most one active sprint** at a time. Tasks are assigned to
a sprint only if they belong to the same project. Deleting a sprint unassigns
its tasks (the tasks themselves belong to the project, not the sprint).

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.project.repository import ProjectRepository
from app.modules.sprint.models import Sprint, SprintStatus
from app.modules.sprint.repository import SprintRepository
from app.modules.task.models import Task
from app.modules.task.repository import TaskRepository

logger = get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[SprintStatus, set[SprintStatus]] = {
    SprintStatus.PLANNED: {SprintStatus.ACTIVE, SprintStatus.CANCELLED},
    SprintStatus.ACTIVE: {SprintStatus.COMPLETED, SprintStatus.CANCELLED},
    SprintStatus.COMPLETED: set(),
    SprintStatus.CANCELLED: set(),
}


class SprintService:
    """Coordinates sprint use cases within a tenant."""

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
        self.sprints = SprintRepository(session)
        self.projects = ProjectRepository(session)
        self.tasks = TaskRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, sprint_id: uuid.UUID) -> Sprint:
        sprint = self.sprints.get(sprint_id, organization_id=self._org_id)
        if sprint is None:
            raise NotFoundError("Sprint not found.")
        return sprint

    def _require_project(self, project_id: uuid.UUID) -> None:
        if self.projects.get(project_id, organization_id=self._org_id) is None:
            raise NotFoundError("Project not found.")

    @staticmethod
    def _validate_dates(start: date | None, end: date | None) -> None:
        if start and end and end < start:
            raise ValidationError("end_date must not be before start_date.")

    def _assert_single_active(self, sprint: Sprint) -> None:
        """Ensure the project has no other active sprint."""
        active = self.sprints.get_active_for_project(self._org_id, sprint.project_id)
        if active is not None and active.id != sprint.id:
            raise ConflictError(
                "This project already has an active sprint.",
                code="active_sprint_exists",
                details={"active_sprint_id": str(active.id)},
            )

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_sprint(
        self,
        *,
        project_id: uuid.UUID,
        name: str,
        goal: str,
        start_date: date | None,
        end_date: date | None,
        capacity_hours: Decimal,
    ) -> Sprint:
        """Create a sprint within a project (starts in the planned state)."""
        self._require_project(project_id)
        self._validate_dates(start_date, end_date)
        sprint = Sprint(
            organization_id=self._org_id,
            project_id=project_id,
            number=self.sprints.next_number(project_id),
            name=name,
            goal=goal,
            status=SprintStatus.PLANNED,
            start_date=start_date,
            end_date=end_date,
            capacity_hours=capacity_hours,
            created_by=self._actor_id,
        )
        self.sprints.add(sprint)
        self._uow.record_audit(
            "Sprint",
            sprint.id,
            "create",
            f"Created sprint '{name}' (#{sprint.number})",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return sprint

    def get_sprint(self, sprint_id: uuid.UUID) -> Sprint:
        """Return a single sprint by id."""
        return self._get_or_404(sprint_id)

    def search_sprints(
        self,
        *,
        project_id: uuid.UUID | None,
        status: SprintStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Sprint], int]:
        """Return a filtered page of sprints and the total matching count."""
        items = list(
            self.sprints.search(
                self._org_id,
                project_id=project_id,
                status=status,
                limit=limit,
                offset=offset,
            )
        )
        total = self.sprints.count(self._org_id, project_id=project_id, status=status)
        return items, total

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_sprint(
        self,
        sprint_id: uuid.UUID,
        *,
        name: str | None,
        goal: str | None,
        status: SprintStatus | None,
        start_date: date | None,
        end_date: date | None,
        capacity_hours: Decimal | None,
    ) -> Sprint:
        """Apply a partial update, enforcing the lifecycle and single-active rule."""
        sprint = self._get_or_404(sprint_id)

        if status is not None and status != sprint.status:
            validate_status_transition(_ALLOWED_TRANSITIONS, sprint.status, status)
            sprint.status = status
            if status == SprintStatus.ACTIVE:
                self._assert_single_active(sprint)
        if name is not None:
            sprint.name = name
        if goal is not None:
            sprint.goal = goal
        if start_date is not None:
            sprint.start_date = start_date
        if end_date is not None:
            sprint.end_date = end_date
        if capacity_hours is not None:
            sprint.capacity_hours = capacity_hours

        self._validate_dates(sprint.start_date, sprint.end_date)

        sprint.modified_by = self._actor_id
        self.sprints.update(sprint)
        self._uow.record_audit(
            "Sprint",
            sprint.id,
            "update",
            f"Updated sprint '{sprint.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return sprint

    def delete_sprint(self, sprint_id: uuid.UUID) -> None:
        """Soft-delete a sprint and unassign its tasks."""
        sprint = self._get_or_404(sprint_id)
        self.tasks.clear_sprint(self._org_id, sprint_id)
        self.sprints.soft_delete(sprint, actor_id=self._actor_id)
        self._uow.record_audit(
            "Sprint",
            sprint.id,
            "delete",
            f"Deleted sprint '{sprint.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Task assignment
    # ------------------------------------------------------------------
    def assign_task(self, sprint_id: uuid.UUID, task_id: uuid.UUID) -> Task:
        """Assign a task to a sprint (task must be in the sprint's project)."""
        sprint = self._get_or_404(sprint_id)
        task = self.tasks.get(task_id, organization_id=self._org_id)
        if task is None:
            raise NotFoundError("Task not found.")
        if task.project_id != sprint.project_id:
            raise ValidationError(
                "Task must belong to the same project as the sprint.",
                code="task_project_mismatch",
            )
        task.sprint_id = sprint_id
        self.tasks.update(task)
        self._uow.record_audit(
            "Task",
            task.id,
            "assign_sprint",
            f"Assigned to sprint '{sprint.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return task

    def remove_task(self, sprint_id: uuid.UUID, task_id: uuid.UUID) -> None:
        """Remove a task from a sprint (leaving the task in its project)."""
        self._get_or_404(sprint_id)
        task = self.tasks.get(task_id, organization_id=self._org_id)
        if task is None or task.sprint_id != sprint_id:
            raise NotFoundError("Task is not assigned to this sprint.")
        task.sprint_id = None
        self.tasks.update(task)
        self._uow.record_audit(
            "Task",
            task.id,
            "remove_sprint",
            "Removed from sprint",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    def list_tasks(self, sprint_id: uuid.UUID) -> Sequence[Task]:
        """Return the tasks assigned to a sprint."""
        self._get_or_404(sprint_id)
        return self.tasks.list_for_sprint(self._org_id, sprint_id)
