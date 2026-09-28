"""Pydantic v2 schemas for the Skills Matrix."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.skill.models import SkillCategory


# --- Skill catalogue -------------------------------------------------------
class SkillCreateRequest(BaseModel):
    """Payload to create a skill."""

    name: str = Field(min_length=2, max_length=200)
    category: SkillCategory = SkillCategory.OTHER
    description: str = Field(default="", max_length=2000)


class SkillUpdateRequest(BaseModel):
    """Payload to update a skill (all fields optional)."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    category: SkillCategory | None = None
    description: str | None = Field(default=None, max_length=2000)


class SkillResponse(BaseModel):
    """A skill catalogue entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    category: SkillCategory
    description: str
    created_date: datetime
    version: int


class PaginatedSkills(BaseModel):
    """A page of skills with total-count metadata."""

    items: list[SkillResponse]
    total: int
    limit: int
    offset: int


# --- Resource-skill assignments --------------------------------------------
class ResourceSkillCreateRequest(BaseModel):
    """Payload to assign a skill to a resource."""

    resource_id: uuid.UUID
    skill_id: uuid.UUID
    proficiency: int = Field(ge=1, le=5)
    years_experience: Decimal | None = Field(default=None, ge=0, max_digits=4, decimal_places=1)


class ResourceSkillUpdateRequest(BaseModel):
    """Payload to update a resource-skill assignment."""

    proficiency: int | None = Field(default=None, ge=1, le=5)
    years_experience: Decimal | None = Field(default=None, ge=0, max_digits=4, decimal_places=1)


class ResourceSkillResponse(BaseModel):
    """A resource's proficiency in a skill."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    resource_id: uuid.UUID
    skill_id: uuid.UUID
    proficiency: int
    years_experience: Decimal | None
    created_date: datetime
    version: int


# --- Matrix / coverage / capacity ------------------------------------------
class MatrixCell(BaseModel):
    """One resource's proficiency in one skill."""

    skill_id: uuid.UUID
    skill_name: str
    proficiency: int


class MatrixRow(BaseModel):
    """A resource and its skill proficiencies."""

    resource_id: uuid.UUID
    resource_name: str
    skills: list[MatrixCell]


class SkillsMatrix(BaseModel):
    """The resources x skills proficiency matrix."""

    skills: list[SkillResponse]
    rows: list[MatrixRow]


class SkillCoverageItem(BaseModel):
    """A resource that holds a given skill, with proficiency."""

    resource_id: uuid.UUID
    resource_name: str
    proficiency: int
    years_experience: Decimal | None


class SkillCoverage(BaseModel):
    """Resources holding a skill (staffing view)."""

    skill_id: uuid.UUID
    skill_name: str
    min_proficiency: int
    resource_count: int
    resources: list[SkillCoverageItem]


class SkillCapacityItem(BaseModel):
    """Supply of capacity for a single skill."""

    skill_id: uuid.UUID
    skill_name: str
    category: SkillCategory
    resource_count: int
    total_capacity_hours: Decimal
    average_proficiency: float | None


class SkillCapacitySummary(BaseModel):
    """Capacity supply across the skills catalogue."""

    as_of: str
    items: list[SkillCapacityItem]
