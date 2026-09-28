"""HTTP routes for the Resource Management module.

Thin adapters over :class:`ResourceService`. Reads require ``resource:read``;
mutations require the corresponding ``resource:*`` permission. Allocation
operations are resource mutations and require ``resource:update``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import ResourceServiceDep, UowDep, require_permission
from app.modules.resource.models import ResourceType
from app.modules.resource.schemas import (
    AllocationCreateRequest,
    AllocationResponse,
    AllocationUpdateRequest,
    MessageResponse,
    PaginatedResources,
    ResourceCreateRequest,
    ResourceResponse,
    ResourceUpdateRequest,
)

router = APIRouter(tags=["Resource Management"])


# --- Resources -------------------------------------------------------------
@router.post(
    "/resources",
    response_model=ResourceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("resource:create"))],
    summary="Create a resource",
)
def create_resource(
    payload: ResourceCreateRequest, service: ResourceServiceDep, uow: UowDep
) -> ResourceResponse:
    """Create an allocatable resource."""
    resource = service.create_resource(
        name=payload.name,
        user_id=payload.user_id,
        department_id=payload.department_id,
        resource_type=payload.resource_type,
        capacity_hours_per_week=payload.capacity_hours_per_week,
        cost_rate=payload.cost_rate,
        currency=payload.currency,
        skills=payload.skills,
    )
    uow.commit()
    return ResourceResponse.model_validate(resource)


@router.get(
    "/resources",
    response_model=PaginatedResources,
    dependencies=[Depends(require_permission("resource:read"))],
    summary="List and search resources",
)
def list_resources(
    service: ResourceServiceDep,
    q: str | None = Query(default=None, description="Search name"),
    resource_type: ResourceType | None = Query(default=None),
    department_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedResources:
    """Return a filtered, paginated page of resources."""
    items, total = service.search_resources(
        query=q,
        resource_type=resource_type,
        department_id=department_id,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return PaginatedResources(
        items=[ResourceResponse.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/resources/{resource_id}",
    response_model=ResourceResponse,
    dependencies=[Depends(require_permission("resource:read"))],
    summary="Get a resource",
)
def get_resource(resource_id: uuid.UUID, service: ResourceServiceDep) -> ResourceResponse:
    """Return a single resource by id."""
    return ResourceResponse.model_validate(service.get_resource(resource_id))


@router.patch(
    "/resources/{resource_id}",
    response_model=ResourceResponse,
    dependencies=[Depends(require_permission("resource:update"))],
    summary="Update a resource",
)
def update_resource(
    resource_id: uuid.UUID,
    payload: ResourceUpdateRequest,
    service: ResourceServiceDep,
    uow: UowDep,
) -> ResourceResponse:
    """Apply a partial update to a resource."""
    resource = service.update_resource(
        resource_id,
        name=payload.name,
        department_id=payload.department_id,
        resource_type=payload.resource_type,
        capacity_hours_per_week=payload.capacity_hours_per_week,
        cost_rate=payload.cost_rate,
        currency=payload.currency,
        skills=payload.skills,
        is_active=payload.is_active,
    )
    uow.commit()
    return ResourceResponse.model_validate(resource)


@router.delete(
    "/resources/{resource_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("resource:delete"))],
    summary="Delete a resource",
)
def delete_resource(
    resource_id: uuid.UUID, service: ResourceServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a resource (blocked if it still has allocations)."""
    service.delete_resource(resource_id)
    uow.commit()
    return MessageResponse(detail="Resource deleted.")


# --- Allocations -----------------------------------------------------------
@router.post(
    "/resources/{resource_id}/allocations",
    response_model=AllocationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("resource:update"))],
    summary="Allocate a resource to a project",
)
def create_allocation(
    resource_id: uuid.UUID,
    payload: AllocationCreateRequest,
    service: ResourceServiceDep,
    uow: UowDep,
) -> AllocationResponse:
    """Create an allocation (rejected if it would exceed 100% capacity)."""
    allocation = service.create_allocation(
        resource_id,
        project_id=payload.project_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        allocation_percent=payload.allocation_percent,
        role_label=payload.role_label,
        notes=payload.notes,
    )
    uow.commit()
    return AllocationResponse.model_validate(allocation)


@router.get(
    "/allocations",
    response_model=list[AllocationResponse],
    dependencies=[Depends(require_permission("resource:read"))],
    summary="List allocations",
)
def list_allocations(
    service: ResourceServiceDep,
    resource_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[AllocationResponse]:
    """Return allocations filtered by resource and/or project."""
    allocations = service.list_allocations(
        resource_id=resource_id, project_id=project_id, limit=limit, offset=offset
    )
    return [AllocationResponse.model_validate(a) for a in allocations]


@router.get(
    "/allocations/{allocation_id}",
    response_model=AllocationResponse,
    dependencies=[Depends(require_permission("resource:read"))],
    summary="Get an allocation",
)
def get_allocation(allocation_id: uuid.UUID, service: ResourceServiceDep) -> AllocationResponse:
    """Return a single allocation by id."""
    return AllocationResponse.model_validate(service.get_allocation(allocation_id))


@router.patch(
    "/allocations/{allocation_id}",
    response_model=AllocationResponse,
    dependencies=[Depends(require_permission("resource:update"))],
    summary="Update an allocation",
)
def update_allocation(
    allocation_id: uuid.UUID,
    payload: AllocationUpdateRequest,
    service: ResourceServiceDep,
    uow: UowDep,
) -> AllocationResponse:
    """Apply a partial update, re-checking the over-allocation ceiling."""
    allocation = service.update_allocation(
        allocation_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        allocation_percent=payload.allocation_percent,
        role_label=payload.role_label,
        notes=payload.notes,
    )
    uow.commit()
    return AllocationResponse.model_validate(allocation)


@router.delete(
    "/allocations/{allocation_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("resource:update"))],
    summary="Delete an allocation",
)
def delete_allocation(
    allocation_id: uuid.UUID, service: ResourceServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete an allocation."""
    service.delete_allocation(allocation_id)
    uow.commit()
    return MessageResponse(detail="Allocation deleted.")
