"""Pydantic v2 schemas for the Risk Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.risk.models import (
    RiskCategory,
    RiskResponse,
    RiskSeverity,
    RiskStatus,
)


class RiskCreateRequest(BaseModel):
    """Payload to raise a risk against a project."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "title": "Key vendor may miss integration deadline",
                "description": "Third-party API not yet stable",
                "category": "external",
                "probability": 4,
                "impact": 5,
                "response_strategy": "mitigate",
                "owner_user_id": None,
                "mitigation_plan": "Build a fallback adapter",
                "target_date": "2026-05-01",
            }
        }
    )

    project_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    category: RiskCategory = RiskCategory.OTHER
    probability: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    response_strategy: RiskResponse | None = None
    owner_user_id: uuid.UUID | None = None
    mitigation_plan: str = Field(default="", max_length=4000)
    target_date: date | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Title must be at least 2 characters.")
        return cleaned


class RiskUpdateRequest(BaseModel):
    """Partial update for a risk; unset fields are left unchanged."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    category: RiskCategory | None = None
    status: RiskStatus | None = None
    probability: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    response_strategy: RiskResponse | None = None
    owner_user_id: uuid.UUID | None = None
    mitigation_plan: str | None = Field(default=None, max_length=4000)
    target_date: date | None = None


class RiskResponseModel(BaseModel):
    """Risk representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    owner_user_id: uuid.UUID | None
    number: int
    title: str
    description: str
    category: RiskCategory
    status: RiskStatus
    response_strategy: RiskResponse | None
    probability: int
    impact: int
    risk_score: int
    severity: RiskSeverity
    mitigation_plan: str
    target_date: date | None
    created_date: datetime
    version: int


class PaginatedRisks(BaseModel):
    """A page of risks with total-count metadata."""

    items: list[RiskResponseModel]
    total: int
    limit: int
    offset: int


class SeverityCount(BaseModel):
    """Count of open risks in a severity band."""

    severity: RiskSeverity
    count: int


class RiskSummaryResponse(BaseModel):
    """Aggregated risk position for a project (open risks only)."""

    project_id: uuid.UUID
    open_count: int
    max_score: int
    by_severity: list[SeverityCount]


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
