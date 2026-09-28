"""Pydantic v2 schemas for the Issue Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.issue.models import (
    IssuePriority,
    IssueSeverity,
    IssueStatus,
    IssueType,
)


class IssueCreateRequest(BaseModel):
    """Payload to raise an issue against a project."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "task_id": None,
                "title": "Checkout page 500s under load",
                "description": "Reproducible above ~200 rps",
                "issue_type": "bug",
                "severity": "high",
                "priority": "high",
                "assignee_user_id": None,
                "due_date": "2026-04-10",
            }
        }
    )

    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    issue_type: IssueType = IssueType.BUG
    severity: IssueSeverity = IssueSeverity.MEDIUM
    priority: IssuePriority = IssuePriority.MEDIUM
    assignee_user_id: uuid.UUID | None = None
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Title must be at least 2 characters.")
        return cleaned


class IssueUpdateRequest(BaseModel):
    """Partial update for an issue; unset fields are left unchanged."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    task_id: uuid.UUID | None = None
    issue_type: IssueType | None = None
    severity: IssueSeverity | None = None
    priority: IssuePriority | None = None
    status: IssueStatus | None = None
    assignee_user_id: uuid.UUID | None = None
    resolution: str | None = Field(default=None, max_length=4000)
    due_date: date | None = None


class IssueResponse(BaseModel):
    """Issue representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    assignee_user_id: uuid.UUID | None
    reporter_user_id: uuid.UUID | None
    number: int
    title: str
    description: str
    issue_type: IssueType
    severity: IssueSeverity
    priority: IssuePriority
    status: IssueStatus
    resolution: str
    resolved_date: date | None
    due_date: date | None
    created_date: datetime
    version: int


class PaginatedIssues(BaseModel):
    """A page of issues with total-count metadata."""

    items: list[IssueResponse]
    total: int
    limit: int
    offset: int


class StatusCount(BaseModel):
    """Count of issues in a workflow state."""

    status: IssueStatus
    count: int


class IssueSummaryResponse(BaseModel):
    """Aggregated issue position for a project."""

    project_id: uuid.UUID
    open_count: int
    total_count: int
    by_status: list[StatusCount]


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
