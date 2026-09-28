"""Repository for the Task Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.task.models import Task, TaskPriority, TaskStatus
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    """Data access for :class:`Task`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Task)

    def next_number(self, project_id: uuid.UUID) -> int:
        """Return the next running task number within a project."""
        stmt = select(func.coalesce(func.max(Task.number), 0)).where(Task.project_id == project_id)
        return int(self.session.execute(stmt).scalar_one()) + 1

    def has_subtasks(self, organization_id: uuid.UUID, task_id: uuid.UUID) -> bool:
        """Return ``True`` if any live task names this task as its parent."""
        stmt = self._base_query(organization_id).where(Task.parent_task_id == task_id)
        return self.session.execute(stmt.limit(1)).first() is not None

    def list_for_project(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> Sequence[Task]:
        """Return all live tasks belonging to a project."""
        stmt = self._base_query(organization_id).where(Task.project_id == project_id)
        return self.session.execute(stmt).scalars().all()

    def list_for_sprint(self, organization_id: uuid.UUID, sprint_id: uuid.UUID) -> Sequence[Task]:
        """Return all live tasks assigned to a sprint, ordered for a board."""
        stmt = (
            self._base_query(organization_id)
            .where(Task.sprint_id == sprint_id)
            .order_by(Task.position.asc(), Task.number.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def clear_sprint(self, organization_id: uuid.UUID, sprint_id: uuid.UUID) -> int:
        """Unassign every task from a sprint; return the count affected."""
        tasks = list(self.list_for_sprint(organization_id, sprint_id))
        for task in tasks:
            task.sprint_id = None
        self.session.flush()
        return len(tasks)

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: TaskStatus | None,
        priority: TaskPriority | None,
        assignee_user_id: uuid.UUID | None,
        parent_task_id: uuid.UUID | None,
        sprint_id: uuid.UUID | None,
    ) -> Select[tuple[Task]]:
        """Build the filtered (unpaginated) task query."""
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(func.lower(Task.title).like(f"%{query.lower()}%"))
        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if priority is not None:
            stmt = stmt.where(Task.priority == priority)
        if assignee_user_id is not None:
            stmt = stmt.where(Task.assignee_user_id == assignee_user_id)
        if parent_task_id is not None:
            stmt = stmt.where(Task.parent_task_id == parent_task_id)
        if sprint_id is not None:
            stmt = stmt.where(Task.sprint_id == sprint_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_user_id: uuid.UUID | None = None,
        parent_task_id: uuid.UUID | None = None,
        sprint_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Task]:
        """Return a filtered, paginated page of tasks ordered by position."""
        stmt = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            priority=priority,
            assignee_user_id=assignee_user_id,
            parent_task_id=parent_task_id,
            sprint_id=sprint_id,
        )
        stmt = stmt.order_by(Task.position.asc(), Task.number.asc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_user_id: uuid.UUID | None = None,
        parent_task_id: uuid.UUID | None = None,
        sprint_id: uuid.UUID | None = None,
    ) -> int:
        """Return the total number of tasks matching the filters."""
        inner = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            priority=priority,
            assignee_user_id=assignee_user_id,
            parent_task_id=parent_task_id,
            sprint_id=sprint_id,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live task of a project; return the count affected."""
        tasks = self.list_for_project(organization_id, project_id)
        for task in tasks:
            task.soft_delete(actor_id)
        self.session.flush()
        return len(list(tasks))
