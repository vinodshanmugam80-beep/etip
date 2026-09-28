"""HTTP routes for the Dependency Management module.

Thin adapters over :class:`DependencyService`. Reads require ``dependency:read``;
mutations require the corresponding ``dependency:*`` permission.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import DependencyServiceDep, UowDep, require_permission
from app.modules.dependency.models import DependencyEntityType
from app.modules.dependency.schemas import (
    DependencyCreateRequest,
    DependencyResponse,
    DependencyUpdateRequest,
    EntityDependenciesResponse,
    MessageResponse,
    PaginatedDependencies,
)

router = APIRouter(tags=["Dependency Management"])


@router.post(
    "/dependencies",
    response_model=DependencyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("dependency:create"))],
    summary="Create a dependency",
)
def create_dependency(
    payload: DependencyCreateRequest, service: DependencyServiceDep, uow: UowDep
) -> DependencyResponse:
    """Create a dependency (rejected if it would create a cycle)."""
    dependency = service.create_dependency(
        entity_type=payload.entity_type,
        predecessor_id=payload.predecessor_id,
        successor_id=payload.successor_id,
        dependency_type=payload.dependency_type,
        lag_days=payload.lag_days,
    )
    uow.commit()
    return DependencyResponse.model_validate(dependency)


@router.get(
    "/dependencies",
    response_model=PaginatedDependencies,
    dependencies=[Depends(require_permission("dependency:read"))],
    summary="List and filter dependencies",
)
def list_dependencies(
    service: DependencyServiceDep,
    entity_type: DependencyEntityType | None = Query(default=None),
    predecessor_id: uuid.UUID | None = Query(default=None),
    successor_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedDependencies:
    """Return a filtered, paginated page of dependencies."""
    items, total = service.search_dependencies(
        entity_type=entity_type,
        predecessor_id=predecessor_id,
        successor_id=successor_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedDependencies(
        items=[DependencyResponse.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/dependencies/{dependency_id}",
    response_model=DependencyResponse,
    dependencies=[Depends(require_permission("dependency:read"))],
    summary="Get a dependency",
)
def get_dependency(dependency_id: uuid.UUID, service: DependencyServiceDep) -> DependencyResponse:
    """Return a single dependency by id."""
    return DependencyResponse.model_validate(service.get_dependency(dependency_id))


@router.patch(
    "/dependencies/{dependency_id}",
    response_model=DependencyResponse,
    dependencies=[Depends(require_permission("dependency:update"))],
    summary="Update a dependency",
)
def update_dependency(
    dependency_id: uuid.UUID,
    payload: DependencyUpdateRequest,
    service: DependencyServiceDep,
    uow: UowDep,
) -> DependencyResponse:
    """Update a dependency's type or lag (endpoints are immutable)."""
    dependency = service.update_dependency(
        dependency_id,
        dependency_type=payload.dependency_type,
        lag_days=payload.lag_days,
    )
    uow.commit()
    return DependencyResponse.model_validate(dependency)


@router.delete(
    "/dependencies/{dependency_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("dependency:delete"))],
    summary="Delete a dependency",
)
def delete_dependency(
    dependency_id: uuid.UUID, service: DependencyServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a dependency."""
    service.delete_dependency(dependency_id)
    uow.commit()
    return MessageResponse(detail="Dependency deleted.")


@router.get(
    "/tasks/{task_id}/dependencies",
    response_model=EntityDependenciesResponse,
    dependencies=[Depends(require_permission("dependency:read"))],
    summary="List a task's dependencies",
)
def task_dependencies(
    task_id: uuid.UUID, service: DependencyServiceDep
) -> EntityDependenciesResponse:
    """Return the predecessor and successor links of a task."""
    predecessors, successors = service.list_for_entity(DependencyEntityType.TASK, task_id)
    return EntityDependenciesResponse(
        entity_type=DependencyEntityType.TASK,
        entity_id=task_id,
        predecessors=[DependencyResponse.model_validate(d) for d in predecessors],
        successors=[DependencyResponse.model_validate(d) for d in successors],
    )


@router.get(
    "/projects/{project_id}/dependencies",
    response_model=EntityDependenciesResponse,
    dependencies=[Depends(require_permission("dependency:read"))],
    summary="List a project's dependencies",
)
def project_dependencies(
    project_id: uuid.UUID, service: DependencyServiceDep
) -> EntityDependenciesResponse:
    """Return the predecessor and successor links of a project."""
    predecessors, successors = service.list_for_entity(DependencyEntityType.PROJECT, project_id)
    return EntityDependenciesResponse(
        entity_type=DependencyEntityType.PROJECT,
        entity_id=project_id,
        predecessors=[DependencyResponse.model_validate(d) for d in predecessors],
        successors=[DependencyResponse.model_validate(d) for d in successors],
    )
