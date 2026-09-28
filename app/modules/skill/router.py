"""HTTP routes for the Skills Matrix.

Reads require ``skill:read``; mutations require ``skill:manage``. Literal routes
are declared before ``/{skill_id}`` so they are matched first.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import SkillServiceDep, UowDep, require_permission
from app.modules.skill.models import SkillCategory
from app.modules.skill.schemas import (
    PaginatedSkills,
    ResourceSkillCreateRequest,
    ResourceSkillResponse,
    ResourceSkillUpdateRequest,
    SkillCapacitySummary,
    SkillCoverage,
    SkillCreateRequest,
    SkillResponse,
    SkillsMatrix,
    SkillUpdateRequest,
)

router = APIRouter(prefix="/skills", tags=["Skills"])


# --- Catalogue -------------------------------------------------------------
@router.post(
    "",
    response_model=SkillResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("skill:manage"))],
    summary="Create a skill",
)
def create_skill(
    payload: SkillCreateRequest, service: SkillServiceDep, uow: UowDep
) -> SkillResponse:
    """Create a catalogue skill."""
    skill = service.create_skill(payload)
    uow.commit()
    return SkillResponse.model_validate(skill)


@router.get(
    "",
    response_model=PaginatedSkills,
    dependencies=[Depends(require_permission("skill:read"))],
    summary="Search skills",
)
def list_skills(
    service: SkillServiceDep,
    query: str | None = Query(default=None),
    category: SkillCategory | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedSkills:
    """Return a filtered, paginated page of skills."""
    items, total = service.search_skills(query=query, category=category, limit=limit, offset=offset)
    return PaginatedSkills(
        items=[SkillResponse.model_validate(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# --- Matrix / capacity (literal routes before /{skill_id}) -----------------
@router.get(
    "/matrix",
    response_model=SkillsMatrix,
    dependencies=[Depends(require_permission("skill:read"))],
    summary="Skills matrix (resources x skills)",
)
def skills_matrix(service: SkillServiceDep) -> SkillsMatrix:
    """Return the resources x skills proficiency matrix."""
    return service.matrix()


@router.get(
    "/capacity",
    response_model=SkillCapacitySummary,
    dependencies=[Depends(require_permission("skill:read"))],
    summary="Skill capacity supply",
)
def skill_capacity(service: SkillServiceDep) -> SkillCapacitySummary:
    """Return capacity supply (resources + weekly hours) per skill."""
    return service.capacity_summary()


# --- Assignments -----------------------------------------------------------
@router.post(
    "/assignments",
    response_model=ResourceSkillResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("skill:manage"))],
    summary="Assign a skill to a resource",
)
def assign_skill(
    payload: ResourceSkillCreateRequest, service: SkillServiceDep, uow: UowDep
) -> ResourceSkillResponse:
    """Assign a skill to a resource with a proficiency."""
    assignment = service.assign(payload)
    uow.commit()
    return ResourceSkillResponse.model_validate(assignment)


@router.patch(
    "/assignments/{assignment_id}",
    response_model=ResourceSkillResponse,
    dependencies=[Depends(require_permission("skill:manage"))],
    summary="Update a skill assignment",
)
def update_assignment(
    assignment_id: uuid.UUID,
    payload: ResourceSkillUpdateRequest,
    service: SkillServiceDep,
    uow: UowDep,
) -> ResourceSkillResponse:
    """Update a resource-skill assignment."""
    assignment = service.update_assignment(assignment_id, payload)
    uow.commit()
    return ResourceSkillResponse.model_validate(assignment)


@router.delete(
    "/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("skill:manage"))],
    summary="Remove a skill assignment",
)
def remove_assignment(assignment_id: uuid.UUID, service: SkillServiceDep, uow: UowDep) -> None:
    """Soft-delete a resource-skill assignment."""
    service.remove_assignment(assignment_id)
    uow.commit()


@router.get(
    "/resources/{resource_id}",
    response_model=list[ResourceSkillResponse],
    dependencies=[Depends(require_permission("skill:read"))],
    summary="A resource's skills",
)
def resource_skills(
    resource_id: uuid.UUID, service: SkillServiceDep
) -> list[ResourceSkillResponse]:
    """Return a resource's skill assignments."""
    return [ResourceSkillResponse.model_validate(a) for a in service.list_for_resource(resource_id)]


# --- Single skill + coverage -----------------------------------------------
@router.get(
    "/{skill_id}",
    response_model=SkillResponse,
    dependencies=[Depends(require_permission("skill:read"))],
    summary="Get a skill",
)
def get_skill(skill_id: uuid.UUID, service: SkillServiceDep) -> SkillResponse:
    """Return a single skill."""
    return SkillResponse.model_validate(service.get_skill(skill_id))


@router.patch(
    "/{skill_id}",
    response_model=SkillResponse,
    dependencies=[Depends(require_permission("skill:manage"))],
    summary="Update a skill",
)
def update_skill(
    skill_id: uuid.UUID,
    payload: SkillUpdateRequest,
    service: SkillServiceDep,
    uow: UowDep,
) -> SkillResponse:
    """Update a catalogue skill."""
    skill = service.update_skill(skill_id, payload)
    uow.commit()
    return SkillResponse.model_validate(skill)


@router.delete(
    "/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("skill:manage"))],
    summary="Delete a skill",
)
def delete_skill(skill_id: uuid.UUID, service: SkillServiceDep, uow: UowDep) -> None:
    """Soft-delete a skill and its assignments."""
    service.delete_skill(skill_id)
    uow.commit()


@router.get(
    "/{skill_id}/resources",
    response_model=SkillCoverage,
    dependencies=[Depends(require_permission("skill:read"))],
    summary="Skill coverage (resources holding a skill)",
)
def skill_coverage(
    skill_id: uuid.UUID,
    service: SkillServiceDep,
    min_proficiency: int = Query(default=1, ge=1, le=5),
) -> SkillCoverage:
    """Return resources holding a skill at or above a proficiency."""
    return service.coverage(skill_id, min_proficiency=min_proficiency)
