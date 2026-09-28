"""Pydantic v2 schemas for the Portfolio Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.portfolio.models import (
    PortfolioHealth,
    PortfolioPriority,
    PortfolioStatus,
)

_CODE_MAX = 50


class _DateRangeMixin(BaseModel):
    """Validates that ``end_date`` is not before ``start_date`` when both set."""

    @model_validator(mode="after")
    def _check_dates(self) -> _DateRangeMixin:
        start = getattr(self, "start_date", None)
        end = getattr(self, "end_date", None)
        if start and end and end < start:
            raise ValueError("end_date must not be before start_date.")
        return self


class PortfolioCreateRequest(_DateRangeMixin):
    """Payload to create a portfolio."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Digital Transformation",
                "code": "DX",
                "description": "Enterprise-wide digital initiatives",
                "owner_user_id": None,
                "priority": "high",
                "planned_budget": "2500000.00",
                "currency": "USD",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            }
        }
    )

    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    description: str = Field(default="", max_length=1000)
    owner_user_id: uuid.UUID | None = None
    priority: PortfolioPriority = PortfolioPriority.MEDIUM
    planned_budget: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    start_date: date | None = None
    end_date: date | None = None

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


class PortfolioUpdateRequest(_DateRangeMixin):
    """Partial update for a portfolio; unset fields are left unchanged."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    owner_user_id: uuid.UUID | None = None
    status: PortfolioStatus | None = None
    priority: PortfolioPriority | None = None
    health: PortfolioHealth | None = None
    planned_budget: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class PortfolioObjectiveCreateRequest(BaseModel):
    """Payload to add a strategic objective to a portfolio."""

    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=500)
    weight: int = Field(default=0, ge=0, le=100)


class PortfolioObjectiveResponse(BaseModel):
    """A strategic objective representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    title: str
    description: str
    weight: int


class PortfolioResponse(BaseModel):
    """Portfolio representation including its objectives."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    description: str
    owner_user_id: uuid.UUID | None
    status: PortfolioStatus
    priority: PortfolioPriority
    health: PortfolioHealth | None
    planned_budget: Decimal
    currency: str
    start_date: date | None
    end_date: date | None
    objectives: list[PortfolioObjectiveResponse]
    created_date: datetime
    version: int


class PaginatedPortfolios(BaseModel):
    """A page of portfolios with total-count metadata."""

    items: list[PortfolioResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
