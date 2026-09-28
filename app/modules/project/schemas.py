"""Pydantic v2 schemas for the Project Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.project.models import (
    ProjectHealth,
    ProjectPriority,
    ProjectStage,
    ProjectStatus,
)

_CODE_MAX = 50


class _ScheduleMixin(BaseModel):
    """Validates actual and baseline date ranges when both endpoints are set."""

    @model_validator(mode="after")
    def _check_ranges(self) -> _ScheduleMixin:
        pairs = (
            ("start_date", "end_date"),
            ("baseline_start_date", "baseline_end_date"),
        )
        for start_attr, end_attr in pairs:
            start = getattr(self, start_attr, None)
            end = getattr(self, end_attr, None)
            if start and end and end < start:
                raise ValueError(f"{end_attr} must not be before {start_attr}.")
        return self


class ProjectCreateRequest(_ScheduleMixin):
    """Payload to create a project."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Billing Platform Rebuild",
                "code": "BILL",
                "description": "Replace the legacy billing engine",
                "portfolio_id": None,
                "program_id": None,
                "department_id": None,
                "sponsor_user_id": None,
                "manager_user_id": None,
                "stage": "planning",
                "priority": "high",
                "budget": "750000.00",
                "forecast": "780000.00",
                "currency": "USD",
                "start_date": "2026-03-01",
                "end_date": "2026-12-15",
                "tags": ["finance", "modernization"],
                "custom_fields": {"cost_center": "CC-4471"},
            }
        }
    )

    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    description: str = Field(default="", max_length=2000)

    portfolio_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    sponsor_user_id: uuid.UUID | None = None
    manager_user_id: uuid.UUID | None = None

    stage: ProjectStage = ProjectStage.INITIATION
    priority: ProjectPriority = ProjectPriority.MEDIUM

    budget: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    forecast: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)

    start_date: date | None = None
    end_date: date | None = None
    baseline_start_date: date | None = None
    baseline_end_date: date | None = None

    tags: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def _normalise_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Code must not be empty.")
        return cleaned

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        cleaned = [tag.strip() for tag in value if tag.strip()]
        return list(dict.fromkeys(cleaned))  # de-duplicate, preserve order


class ProjectUpdateRequest(_ScheduleMixin):
    """Partial update for a project; unset fields are left unchanged."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    department_id: uuid.UUID | None = None
    sponsor_user_id: uuid.UUID | None = None
    manager_user_id: uuid.UUID | None = None
    status: ProjectStatus | None = None
    stage: ProjectStage | None = None
    priority: ProjectPriority | None = None
    health: ProjectHealth | None = None
    budget: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    forecast: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    actual_cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    start_date: date | None = None
    end_date: date | None = None
    baseline_start_date: date | None = None
    baseline_end_date: date | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    tags: list[str] | None = None
    custom_fields: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class ProjectTeamMemberAddRequest(BaseModel):
    """Payload to add a team member to a project."""

    user_id: uuid.UUID
    role_label: str = Field(default="Member", max_length=100)
    allocation_percent: int = Field(default=100, ge=0, le=100)


class ProjectTeamMemberResponse(BaseModel):
    """Project team-member representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    role_label: str
    allocation_percent: int


class ProjectCommentCreateRequest(BaseModel):
    """Payload to post a comment on a project."""

    body: str = Field(min_length=1, max_length=4000)


class ProjectCommentResponse(BaseModel):
    """Project comment representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    author_user_id: uuid.UUID
    body: str
    created_date: datetime


class ProjectResponse(BaseModel):
    """Full project representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    number: int
    code: str
    name: str
    description: str
    portfolio_id: uuid.UUID | None
    program_id: uuid.UUID | None
    department_id: uuid.UUID | None
    sponsor_user_id: uuid.UUID | None
    manager_user_id: uuid.UUID | None
    status: ProjectStatus
    stage: ProjectStage
    priority: ProjectPriority
    health: ProjectHealth | None
    budget: Decimal
    forecast: Decimal
    actual_cost: Decimal
    currency: str
    start_date: date | None
    end_date: date | None
    baseline_start_date: date | None
    baseline_end_date: date | None
    progress_percent: int
    risk_score: int
    issue_count: int
    tags: list[str]
    custom_fields: dict[str, Any]
    team_members: list[ProjectTeamMemberResponse]
    created_date: datetime
    version: int


class PaginatedProjects(BaseModel):
    """A page of projects with total-count metadata."""

    items: list[ProjectResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
