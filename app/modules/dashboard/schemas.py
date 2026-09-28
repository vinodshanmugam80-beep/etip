"""Pydantic v2 schemas for the Dashboards module."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.dashboard.models import WidgetType
from app.modules.report.models import ReportType


def _clean_title(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) < 2:
        raise ValueError("Must be at least 2 characters.")
    return cleaned


class DashboardCreateRequest(BaseModel):
    """Payload to create a dashboard."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Delivery overview",
                "description": "My at-a-glance delivery board",
                "is_shared": False,
                "layout": {"columns": 12},
            }
        }
    )

    name: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=2000)
    is_shared: bool = False
    layout: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        return _clean_title(value)


class DashboardUpdateRequest(BaseModel):
    """Partial update for a dashboard."""

    name: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    is_shared: bool | None = None
    layout: dict[str, Any] | None = None


class DashboardResponse(BaseModel):
    """Dashboard representation (without widgets)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_by: uuid.UUID | None
    name: str
    description: str
    is_shared: bool
    is_default: bool
    layout: dict[str, Any]
    created_date: datetime
    version: int


class PaginatedDashboards(BaseModel):
    """A page of dashboards with total-count metadata."""

    items: list[DashboardResponse]
    total: int
    limit: int
    offset: int


class WidgetCreateRequest(BaseModel):
    """Payload to add a widget to a dashboard."""

    title: str = Field(min_length=2, max_length=300)
    widget_type: WidgetType
    report_type: ReportType | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    content: str = Field(default="", max_length=8000)
    position: int = Field(default=0, ge=0)
    width: int = Field(default=6, ge=1, le=12)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        return _clean_title(value)

    @model_validator(mode="after")
    def _report_needs_type(self) -> WidgetCreateRequest:
        if self.widget_type == WidgetType.REPORT and self.report_type is None:
            raise ValueError("A report widget requires a report_type.")
        return self


class WidgetUpdateRequest(BaseModel):
    """Partial update for a widget."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    report_type: ReportType | None = None
    parameters: dict[str, Any] | None = None
    content: str | None = Field(default=None, max_length=8000)
    position: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1, le=12)


class WidgetResponse(BaseModel):
    """Widget representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dashboard_id: uuid.UUID
    title: str
    widget_type: WidgetType
    report_type: ReportType | None
    parameters: dict[str, Any]
    content: str
    position: int
    width: int


class RenderedWidget(BaseModel):
    """A widget plus the result of rendering it."""

    id: uuid.UUID
    title: str
    widget_type: WidgetType
    position: int
    width: int
    report_type: ReportType | None = None
    content: str | None = None
    data: dict[str, Any] | None = None
    error: str | None = None


class DashboardRenderResponse(BaseModel):
    """A dashboard together with its rendered widgets."""

    dashboard: DashboardResponse
    generated_at: datetime
    widgets: list[RenderedWidget]


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
