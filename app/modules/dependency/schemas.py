"""Pydantic v2 schemas for the Dependency Management module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.dependency.models import DependencyEntityType, DependencyType


class DependencyCreateRequest(BaseModel):
    """Payload to create a dependency between two same-type entities."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity_type": "task",
                "predecessor_id": "00000000-0000-0000-0000-000000000000",
                "successor_id": "11111111-1111-1111-1111-111111111111",
                "dependency_type": "finish_to_start",
                "lag_days": 2,
            }
        }
    )

    entity_type: DependencyEntityType
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID
    dependency_type: DependencyType = DependencyType.FINISH_TO_START
    lag_days: int = 0

    @model_validator(mode="after")
    def _distinct_endpoints(self) -> DependencyCreateRequest:
        if self.predecessor_id == self.successor_id:
            raise ValueError("A dependency cannot link an entity to itself.")
        return self


class DependencyUpdateRequest(BaseModel):
    """Partial update for a dependency (endpoints are immutable)."""

    dependency_type: DependencyType | None = None
    lag_days: int | None = None


class DependencyResponse(BaseModel):
    """Dependency representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    entity_type: DependencyEntityType
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID
    dependency_type: DependencyType
    lag_days: int
    created_date: datetime
    version: int


class PaginatedDependencies(BaseModel):
    """A page of dependencies with total-count metadata."""

    items: list[DependencyResponse]
    total: int
    limit: int
    offset: int


class EntityDependenciesResponse(BaseModel):
    """The predecessors and successors of a single entity."""

    entity_type: DependencyEntityType
    entity_id: uuid.UUID
    predecessors: list[DependencyResponse]
    successors: list[DependencyResponse]


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
