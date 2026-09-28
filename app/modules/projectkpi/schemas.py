"""Pydantic v2 schemas for the per-project KPI register."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.projectkpi.models import KPIDirection


class ProjectKPICreateRequest(BaseModel):
    """Payload to create a KPI on a project."""

    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=1000)
    unit: str = Field(default="", max_length=50)
    direction: KPIDirection = KPIDirection.INCREASE
    baseline_value: Decimal = Decimal("0")
    current_value: Decimal = Decimal("0")
    target_value: Decimal = Decimal("0")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Name must be at least 2 characters.")
        return cleaned


class ProjectKPIUpdateRequest(BaseModel):
    """Partial update; unset fields are left unchanged."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    unit: str | None = Field(default=None, max_length=50)
    direction: KPIDirection | None = None
    baseline_value: Decimal | None = None
    current_value: Decimal | None = None
    target_value: Decimal | None = None


class ProjectKPIResponse(BaseModel):
    """A project KPI with derived attainment and on-target status."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    unit: str
    direction: KPIDirection
    baseline_value: Decimal
    current_value: Decimal
    target_value: Decimal
    attainment_percent: float | None = None
    on_target: bool = False
    created_date: datetime
    version: int


class PaginatedProjectKPIs(BaseModel):
    """A page of project KPIs."""

    items: list[ProjectKPIResponse]
    total: int
    limit: int
    offset: int


class ProjectKPISummary(BaseModel):
    """Aggregated KPI position for one project."""

    project_id: uuid.UUID
    total: int
    on_target: int
    off_target: int
    average_attainment: float | None


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
