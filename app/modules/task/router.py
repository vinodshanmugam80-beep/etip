"""HTTP routes for the Task Management module.

Thin adapters over :class:`TaskService`. Reads require ``task:read``; create and
delete require ``task:create`` / ``task:delete``; updates require ``task:update``
(assignees hold this so they can progress their own work).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import TaskServiceDep, UowDep, require_permission
from app.modules.task.models import TaskPriority, TaskStatus
from app.modules.task.schemas import (
    MessageResponse,
    PaginatedTasks,
    TaskCreateRequest,
    TaskResponse,
    TaskUpdateRequest,
)

router = APIRouter(prefix="/tasks", tags=["Task Management"])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("task:create"))],
    summary="Create a task",
)
def create_task(payload: TaskCreateRequest, service: TaskServiceDep, uow: UowDep) -> TaskResponse:
    """Create a task within a project."""
    task = service.create_task(
        project_id=payload.project_id,
        title=payload.title,
        description=payload.description,
        assignee_user_id=payload.assignee_user_id,
        parent_task_id=payload.parent_task_id,
        priority=payload.priority,
        estimate_hours=payload.estimate_hours,
        start_date=payload.start_date,
        due_date=payload.due_date,
    )
    uow.commit()
    return TaskResponse.model_validate(task)


@router.get(
    "",
    response_model=PaginatedTasks,
    dependencies=[Depends(require_permission("task:read"))],
    summary="List and search tasks",
)
def list_tasks(
    service: TaskServiceDep,
    q: str | None = Query(default=None, description="Search title"),
    project_id: uuid.UUID | None = Query(default=None),
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = Query(default=None),
    assignee_user_id: uuid.UUID | None = Query(default=None),
    parent_task_id: uuid.UUID | None = Query(default=None),
    sprint_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedTasks:
    """Return a filtered, paginated page of tasks (ordered by position)."""
    items, total = service.search_tasks(
        query=q,
        project_id=project_id,
        status=status_filter,
        priority=priority,
        assignee_user_id=assignee_user_id,
        parent_task_id=parent_task_id,
        sprint_id=sprint_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedTasks(
        items=[TaskResponse.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(require_permission("task:read"))],
    summary="Get a task",
)
def get_task(task_id: uuid.UUID, service: TaskServiceDep) -> TaskResponse:
    """Return a single task by id."""
    return TaskResponse.model_validate(service.get_task(task_id))


@router.get(
    "/{task_id}/subtasks",
    response_model=list[TaskResponse],
    dependencies=[Depends(require_permission("task:read"))],
    summary="List subtasks",
)
def list_subtasks(task_id: uuid.UUID, service: TaskServiceDep) -> list[TaskResponse]:
    """Return the direct subtasks of a task."""
    items, _ = service.search_tasks(
        query=None,
        project_id=None,
        status=None,
        priority=None,
        assignee_user_id=None,
        parent_task_id=task_id,
        sprint_id=None,
        limit=200,
        offset=0,
    )
    return [TaskResponse.model_validate(t) for t in items]


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(require_permission("task:update"))],
    summary="Update a task",
)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdateRequest,
    service: TaskServiceDep,
    uow: UowDep,
) -> TaskResponse:
    """Apply a partial update, including a validated status transition."""
    task = service.update_task(
        task_id,
        title=payload.title,
        description=payload.description,
        assignee_user_id=payload.assignee_user_id,
        parent_task_id=payload.parent_task_id,
        status=payload.status,
        priority=payload.priority,
        estimate_hours=payload.estimate_hours,
        logged_hours=payload.logged_hours,
        start_date=payload.start_date,
        due_date=payload.due_date,
        position=payload.position,
    )
    uow.commit()
    return TaskResponse.model_validate(task)


@router.delete(
    "/{task_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("task:delete"))],
    summary="Delete a task",
)
def delete_task(task_id: uuid.UUID, service: TaskServiceDep, uow: UowDep) -> MessageResponse:
    """Soft-delete a task (blocked if it still has subtasks)."""
    service.delete_task(task_id)
    uow.commit()
    return MessageResponse(detail="Task deleted.")
