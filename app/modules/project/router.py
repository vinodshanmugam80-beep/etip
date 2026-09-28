"""HTTP routes for the Project Management module.

Thin adapters over :class:`ProjectService`. Reads require ``project:read``;
mutations require the corresponding ``project:*`` permission. Posting a comment
requires only ``project:read`` (participants may comment); removing one requires
``project:update``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import ProjectServiceDep, UowDep, require_permission
from app.modules.project.models import ProjectStage, ProjectStatus
from app.modules.project.schemas import (
    MessageResponse,
    PaginatedProjects,
    ProjectCommentCreateRequest,
    ProjectCommentResponse,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectTeamMemberAddRequest,
    ProjectTeamMemberResponse,
    ProjectUpdateRequest,
)

router = APIRouter(prefix="/projects", tags=["Project Management"])


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("project:create"))],
    summary="Create a project",
)
def create_project(
    payload: ProjectCreateRequest, service: ProjectServiceDep, uow: UowDep
) -> ProjectResponse:
    """Create a project within the caller's organization."""
    project = service.create_project(
        name=payload.name,
        code=payload.code,
        description=payload.description,
        portfolio_id=payload.portfolio_id,
        program_id=payload.program_id,
        department_id=payload.department_id,
        sponsor_user_id=payload.sponsor_user_id,
        manager_user_id=payload.manager_user_id,
        stage=payload.stage,
        priority=payload.priority,
        budget=payload.budget,
        forecast=payload.forecast,
        currency=payload.currency,
        start_date=payload.start_date,
        end_date=payload.end_date,
        baseline_start_date=payload.baseline_start_date,
        baseline_end_date=payload.baseline_end_date,
        tags=payload.tags,
        custom_fields=payload.custom_fields,
    )
    uow.commit()
    return ProjectResponse.model_validate(project)


@router.get(
    "",
    response_model=PaginatedProjects,
    dependencies=[Depends(require_permission("project:read"))],
    summary="List and search projects",
)
def list_projects(
    service: ProjectServiceDep,
    q: str | None = Query(default=None, description="Search name or code"),
    status_filter: ProjectStatus | None = Query(default=None, alias="status"),
    stage: ProjectStage | None = Query(default=None),
    portfolio_id: uuid.UUID | None = Query(default=None),
    program_id: uuid.UUID | None = Query(default=None),
    manager_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedProjects:
    """Return a filtered, paginated page of projects (newest number first)."""
    items, total = service.search_projects(
        query=q,
        status=status_filter,
        stage=stage,
        portfolio_id=portfolio_id,
        program_id=program_id,
        manager_user_id=manager_user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedProjects(
        items=[ProjectResponse.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    dependencies=[Depends(require_permission("project:read"))],
    summary="Get a project",
)
def get_project(project_id: uuid.UUID, service: ProjectServiceDep) -> ProjectResponse:
    """Return a single project by id."""
    return ProjectResponse.model_validate(service.get_project(project_id))


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    dependencies=[Depends(require_permission("project:update"))],
    summary="Update a project",
)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    service: ProjectServiceDep,
    uow: UowDep,
) -> ProjectResponse:
    """Apply a partial update, including a validated status transition."""
    project = service.update_project(
        project_id,
        name=payload.name,
        description=payload.description,
        department_id=payload.department_id,
        sponsor_user_id=payload.sponsor_user_id,
        manager_user_id=payload.manager_user_id,
        status=payload.status,
        stage=payload.stage,
        priority=payload.priority,
        health=payload.health,
        budget=payload.budget,
        forecast=payload.forecast,
        actual_cost=payload.actual_cost,
        currency=payload.currency,
        start_date=payload.start_date,
        end_date=payload.end_date,
        baseline_start_date=payload.baseline_start_date,
        baseline_end_date=payload.baseline_end_date,
        progress_percent=payload.progress_percent,
        tags=payload.tags,
        custom_fields=payload.custom_fields,
    )
    uow.commit()
    return ProjectResponse.model_validate(project)


@router.delete(
    "/{project_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("project:delete"))],
    summary="Delete a project",
)
def delete_project(
    project_id: uuid.UUID, service: ProjectServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a project and its team members and comments."""
    service.delete_project(project_id)
    uow.commit()
    return MessageResponse(detail="Project deleted.")


# --- Team members ----------------------------------------------------------
@router.post(
    "/{project_id}/team",
    response_model=ProjectTeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("project:update"))],
    summary="Add a team member",
)
def add_team_member(
    project_id: uuid.UUID,
    payload: ProjectTeamMemberAddRequest,
    service: ProjectServiceDep,
    uow: UowDep,
) -> ProjectTeamMemberResponse:
    """Add a user to the project team."""
    member = service.add_team_member(
        project_id,
        user_id=payload.user_id,
        role_label=payload.role_label,
        allocation_percent=payload.allocation_percent,
    )
    uow.commit()
    return ProjectTeamMemberResponse.model_validate(member)


@router.get(
    "/{project_id}/team",
    response_model=list[ProjectTeamMemberResponse],
    dependencies=[Depends(require_permission("project:read"))],
    summary="List team members",
)
def list_team_members(
    project_id: uuid.UUID, service: ProjectServiceDep
) -> list[ProjectTeamMemberResponse]:
    """Return the team members of a project."""
    members = service.list_team_members(project_id)
    return [ProjectTeamMemberResponse.model_validate(m) for m in members]


@router.delete(
    "/{project_id}/team/{user_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("project:update"))],
    summary="Remove a team member",
)
def remove_team_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    service: ProjectServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Remove a user from the project team."""
    service.remove_team_member(project_id, user_id)
    uow.commit()
    return MessageResponse(detail="Team member removed.")


# --- Comments --------------------------------------------------------------
@router.post(
    "/{project_id}/comments",
    response_model=ProjectCommentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("project:read"))],
    summary="Post a comment",
)
def add_comment(
    project_id: uuid.UUID,
    payload: ProjectCommentCreateRequest,
    service: ProjectServiceDep,
    uow: UowDep,
) -> ProjectCommentResponse:
    """Post a comment on a project (authored by the current user)."""
    comment = service.add_comment(project_id, body=payload.body)
    uow.commit()
    return ProjectCommentResponse.model_validate(comment)


@router.get(
    "/{project_id}/comments",
    response_model=list[ProjectCommentResponse],
    dependencies=[Depends(require_permission("project:read"))],
    summary="List comments",
)
def list_comments(
    project_id: uuid.UUID, service: ProjectServiceDep
) -> list[ProjectCommentResponse]:
    """Return the comments of a project (newest first)."""
    comments = service.list_comments(project_id)
    return [ProjectCommentResponse.model_validate(c) for c in comments]


@router.delete(
    "/{project_id}/comments/{comment_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("project:update"))],
    summary="Remove a comment",
)
def remove_comment(
    project_id: uuid.UUID,
    comment_id: uuid.UUID,
    service: ProjectServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Remove a comment from a project."""
    service.remove_comment(project_id, comment_id)
    uow.commit()
    return MessageResponse(detail="Comment removed.")
