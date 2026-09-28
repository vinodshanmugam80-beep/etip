"""HTTP routes for the Issue Management module.

Thin adapters over :class:`IssueService`. Reads require ``issue:read``; create
and update require ``issue:create`` / ``issue:update`` (team members hold these
so they can raise and work issues); delete requires ``issue:delete``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import IssueServiceDep, UowDep, require_permission
from app.modules.issue.models import (
    IssuePriority,
    IssueSeverity,
    IssueStatus,
    IssueType,
)
from app.modules.issue.schemas import (
    IssueCreateRequest,
    IssueResponse,
    IssueSummaryResponse,
    IssueUpdateRequest,
    MessageResponse,
    PaginatedIssues,
)

router = APIRouter(tags=["Issue Management"])


@router.post(
    "/issues",
    response_model=IssueResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("issue:create"))],
    summary="Raise an issue",
)
def create_issue(
    payload: IssueCreateRequest, service: IssueServiceDep, uow: UowDep
) -> IssueResponse:
    """Raise an issue against a project (optionally linked to a task)."""
    issue = service.create_issue(
        project_id=payload.project_id,
        task_id=payload.task_id,
        title=payload.title,
        description=payload.description,
        issue_type=payload.issue_type,
        severity=payload.severity,
        priority=payload.priority,
        assignee_user_id=payload.assignee_user_id,
        due_date=payload.due_date,
    )
    uow.commit()
    return IssueResponse.model_validate(issue)


@router.get(
    "/issues",
    response_model=PaginatedIssues,
    dependencies=[Depends(require_permission("issue:read"))],
    summary="List and search issues",
)
def list_issues(
    service: IssueServiceDep,
    q: str | None = Query(default=None, description="Search title"),
    project_id: uuid.UUID | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    status_filter: IssueStatus | None = Query(default=None, alias="status"),
    issue_type: IssueType | None = Query(default=None),
    severity: IssueSeverity | None = Query(default=None),
    priority: IssuePriority | None = Query(default=None),
    assignee_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedIssues:
    """Return a filtered, paginated page of issues (newest number first)."""
    items, total = service.search_issues(
        query=q,
        project_id=project_id,
        task_id=task_id,
        status=status_filter,
        issue_type=issue_type,
        severity=severity,
        priority=priority,
        assignee_user_id=assignee_user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedIssues(
        items=[IssueResponse.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/issues/{issue_id}",
    response_model=IssueResponse,
    dependencies=[Depends(require_permission("issue:read"))],
    summary="Get an issue",
)
def get_issue(issue_id: uuid.UUID, service: IssueServiceDep) -> IssueResponse:
    """Return a single issue by id."""
    return IssueResponse.model_validate(service.get_issue(issue_id))


@router.patch(
    "/issues/{issue_id}",
    response_model=IssueResponse,
    dependencies=[Depends(require_permission("issue:update"))],
    summary="Update an issue",
)
def update_issue(
    issue_id: uuid.UUID,
    payload: IssueUpdateRequest,
    service: IssueServiceDep,
    uow: UowDep,
) -> IssueResponse:
    """Apply a partial update, including a validated status transition."""
    issue = service.update_issue(
        issue_id,
        title=payload.title,
        description=payload.description,
        task_id=payload.task_id,
        issue_type=payload.issue_type,
        severity=payload.severity,
        priority=payload.priority,
        status=payload.status,
        assignee_user_id=payload.assignee_user_id,
        resolution=payload.resolution,
        due_date=payload.due_date,
    )
    uow.commit()
    return IssueResponse.model_validate(issue)


@router.delete(
    "/issues/{issue_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("issue:delete"))],
    summary="Delete an issue",
)
def delete_issue(issue_id: uuid.UUID, service: IssueServiceDep, uow: UowDep) -> MessageResponse:
    """Soft-delete an issue and refresh the project rollup."""
    service.delete_issue(issue_id)
    uow.commit()
    return MessageResponse(detail="Issue deleted.")


@router.get(
    "/projects/{project_id}/issue-summary",
    response_model=IssueSummaryResponse,
    dependencies=[Depends(require_permission("issue:read"))],
    summary="Get a project's issue summary",
)
def get_summary(project_id: uuid.UUID, service: IssueServiceDep) -> IssueSummaryResponse:
    """Return the aggregated issue position of a project."""
    return service.get_summary(project_id)
