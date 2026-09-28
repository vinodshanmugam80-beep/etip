"""HTTP routes for the Sprint Management module.

Thin adapters over :class:`SprintService`. Reads require ``sprint:read``;
create/update/delete require the corresponding ``sprint:*`` permission. Task
assignment to a sprint is a sprint mutation and requires ``sprint:update``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import SprintServiceDep, UowDep, require_permission
from app.modules.sprint.models import SprintStatus
from app.modules.sprint.schemas import (
    MessageResponse,
    PaginatedSprints,
    SprintCreateRequest,
    SprintResponse,
    SprintTasksResponse,
    SprintUpdateRequest,
)
from app.modules.task.schemas import TaskResponse

router = APIRouter(prefix="/sprints", tags=["Sprint Management"])


@router.post(
    "",
    response_model=SprintResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("sprint:create"))],
    summary="Create a sprint",
)
def create_sprint(
    payload: SprintCreateRequest, service: SprintServiceDep, uow: UowDep
) -> SprintResponse:
    """Create a sprint within a project."""
    sprint = service.create_sprint(
        project_id=payload.project_id,
        name=payload.name,
        goal=payload.goal,
        start_date=payload.start_date,
        end_date=payload.end_date,
        capacity_hours=payload.capacity_hours,
    )
    uow.commit()
    return SprintResponse.model_validate(sprint)


@router.get(
    "",
    response_model=PaginatedSprints,
    dependencies=[Depends(require_permission("sprint:read"))],
    summary="List and search sprints",
)
def list_sprints(
    service: SprintServiceDep,
    project_id: uuid.UUID | None = Query(default=None),
    status_filter: SprintStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedSprints:
    """Return a filtered, paginated page of sprints."""
    items, total = service.search_sprints(
        project_id=project_id, status=status_filter, limit=limit, offset=offset
    )
    return PaginatedSprints(
        items=[SprintResponse.model_validate(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{sprint_id}",
    response_model=SprintResponse,
    dependencies=[Depends(require_permission("sprint:read"))],
    summary="Get a sprint",
)
def get_sprint(sprint_id: uuid.UUID, service: SprintServiceDep) -> SprintResponse:
    """Return a single sprint by id."""
    return SprintResponse.model_validate(service.get_sprint(sprint_id))


@router.patch(
    "/{sprint_id}",
    response_model=SprintResponse,
    dependencies=[Depends(require_permission("sprint:update"))],
    summary="Update a sprint",
)
def update_sprint(
    sprint_id: uuid.UUID,
    payload: SprintUpdateRequest,
    service: SprintServiceDep,
    uow: UowDep,
) -> SprintResponse:
    """Apply a partial update, including a validated status transition."""
    sprint = service.update_sprint(
        sprint_id,
        name=payload.name,
        goal=payload.goal,
        status=payload.status,
        start_date=payload.start_date,
        end_date=payload.end_date,
        capacity_hours=payload.capacity_hours,
    )
    uow.commit()
    return SprintResponse.model_validate(sprint)


@router.delete(
    "/{sprint_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("sprint:delete"))],
    summary="Delete a sprint",
)
def delete_sprint(sprint_id: uuid.UUID, service: SprintServiceDep, uow: UowDep) -> MessageResponse:
    """Soft-delete a sprint and unassign its tasks."""
    service.delete_sprint(sprint_id)
    uow.commit()
    return MessageResponse(detail="Sprint deleted.")


# --- Task assignment -------------------------------------------------------
@router.get(
    "/{sprint_id}/tasks",
    response_model=SprintTasksResponse,
    dependencies=[Depends(require_permission("sprint:read"))],
    summary="List a sprint's tasks",
)
def list_sprint_tasks(sprint_id: uuid.UUID, service: SprintServiceDep) -> SprintTasksResponse:
    """Return the tasks assigned to a sprint."""
    tasks = service.list_tasks(sprint_id)
    return SprintTasksResponse(
        sprint_id=sprint_id,
        tasks=[TaskResponse.model_validate(t) for t in tasks],
    )


@router.post(
    "/{sprint_id}/tasks/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(require_permission("sprint:update"))],
    summary="Assign a task to a sprint",
)
def assign_task(
    sprint_id: uuid.UUID,
    task_id: uuid.UUID,
    service: SprintServiceDep,
    uow: UowDep,
) -> TaskResponse:
    """Assign a task to a sprint (must be in the sprint's project)."""
    task = service.assign_task(sprint_id, task_id)
    uow.commit()
    return TaskResponse.model_validate(task)


@router.delete(
    "/{sprint_id}/tasks/{task_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("sprint:update"))],
    summary="Remove a task from a sprint",
)
def remove_task(
    sprint_id: uuid.UUID,
    task_id: uuid.UUID,
    service: SprintServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Remove a task from a sprint (the task stays in its project)."""
    service.remove_task(sprint_id, task_id)
    uow.commit()
    return MessageResponse(detail="Task removed from sprint.")
