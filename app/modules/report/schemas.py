"""Pydantic v2 schemas for the Reports module."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.report.models import ReportType


class ReportDefinitionCreateRequest(BaseModel):
    """Payload to save a report definition."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Weekly project status",
                "description": "Status snapshot for the Atlas project",
                "report_type": "project_status",
                "parameters": {"project_id": "00000000-0000-0000-0000-000000000000"},
                "is_shared": True,
            }
        }
    )

    name: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=2000)
    report_type: ReportType
    parameters: dict[str, Any] = Field(default_factory=dict)
    is_shared: bool = False

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Name must be at least 2 characters.")
        return cleaned


class ReportDefinitionUpdateRequest(BaseModel):
    """Partial update for a report definition."""

    name: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    parameters: dict[str, Any] | None = None
    is_shared: bool | None = None


class ReportDefinitionResponse(BaseModel):
    """Report definition representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_by: uuid.UUID | None
    name: str
    description: str
    report_type: ReportType
    parameters: dict[str, Any]
    is_shared: bool
    last_run_date: datetime | None
    created_date: datetime
    version: int


class PaginatedReportDefinitions(BaseModel):
    """A page of report definitions with total-count metadata."""

    items: list[ReportDefinitionResponse]
    total: int
    limit: int
    offset: int


class AdHocRunRequest(BaseModel):
    """Payload to run a report without saving a definition."""

    report_type: ReportType
    parameters: dict[str, Any] = Field(default_factory=dict)


class ReportResult(BaseModel):
    """The assembled result of running a report."""

    report_type: ReportType
    generated_at: datetime
    parameters: dict[str, Any]
    data: dict[str, Any]


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
