"""Pydantic v2 schemas for AI Delivery."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.aidelivery.models import (
    BuildStatus,
    BuildTargetType,
    DeploymentStatus,
    Environment,
    PipelineStage,
    RunStatus,
)


class BuildRequestCreate(BaseModel):
    """Payload to open a build request."""

    title: str = Field(min_length=2, max_length=300)
    target_type: BuildTargetType = BuildTargetType.WEB_APP
    spec: str = Field(default="", max_length=8000)
    tech_stack: str = Field(default="", max_length=50)
    repository_url: str = Field(default="", max_length=1000)
    project_id: uuid.UUID | None = None
    gate_min_coverage: int | None = Field(default=None, ge=0, le=100)
    gate_max_p95_ms: int | None = Field(default=None, ge=0)
    gate_require_tests: bool = False


class BuildRequestUpdate(BaseModel):
    """Payload to update a build request (all optional)."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    target_type: BuildTargetType | None = None
    spec: str | None = Field(default=None, max_length=8000)
    tech_stack: str | None = Field(default=None, max_length=50)
    repository_url: str | None = Field(default=None, max_length=1000)
    status: BuildStatus | None = None
    gate_min_coverage: int | None = Field(default=None, ge=0, le=100)
    gate_max_p95_ms: int | None = Field(default=None, ge=0)
    gate_require_tests: bool | None = None


class BuildRequestResponse(BaseModel):
    """A build request."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    target_type: BuildTargetType
    spec: str
    tech_stack: str
    repository_url: str
    status: BuildStatus
    gate_min_coverage: int | None
    gate_max_p95_ms: int | None
    gate_require_tests: bool
    created_date: datetime
    version: int


class PaginatedBuildRequests(BaseModel):
    """A page of build requests."""

    items: list[BuildRequestResponse]
    total: int
    limit: int
    offset: int


class PipelineRunCreate(BaseModel):
    """Payload for an external AI tool / CI system to report a stage run."""

    stage: PipelineStage
    status: RunStatus = RunStatus.RUNNING
    provider: str = Field(default="", max_length=100)
    external_ref: str = Field(default="", max_length=300)
    logs_url: str = Field(default="", max_length=1000)
    message: str = Field(default="", max_length=2000)
    metrics: dict[str, Any] = Field(default_factory=dict)


class PipelineRunResponse(BaseModel):
    """A reported pipeline-stage run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    build_request_id: uuid.UUID
    stage: PipelineStage
    status: RunStatus
    provider: str
    external_ref: str
    logs_url: str
    message: str
    metrics: dict[str, Any]
    started_date: datetime | None
    finished_date: datetime | None
    created_date: datetime


class DeploymentCreate(BaseModel):
    """Payload to record a deployment to an environment."""

    environment: Environment
    status: DeploymentStatus = DeploymentStatus.DEPLOYED
    version: str = Field(default="", max_length=100)
    url: str = Field(default="", max_length=1000)
    provider: str = Field(default="", max_length=100)


class DeploymentResponse(BaseModel):
    """A deployment record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    build_request_id: uuid.UUID
    environment: Environment
    status: DeploymentStatus
    release_version: str
    url: str
    provider: str
    deployed_date: datetime | None
    created_date: datetime


class FilesUpdate(BaseModel):
    """Payload to save edited source files."""

    files: dict[str, str]


class BuildFilesResponse(BaseModel):
    """The current source files stored on a build."""

    build_request_id: uuid.UUID
    files: dict[str, str]


class GeneratedArtifactResponse(BaseModel):
    """The output of an ETIP-run generation."""

    build_request_id: uuid.UUID
    status: BuildStatus
    provider: str
    summary: str
    files: dict[str, str]


class GateCheck(BaseModel):
    """One quality-gate check."""

    name: str
    required: str
    actual: float | str | None
    ok: bool


class GateResult(BaseModel):
    """The evaluated quality gate for a build."""

    passed: bool
    checks: list[GateCheck]


class DetectStackRequest(BaseModel):
    """A repository's file list, for stack detection."""

    filenames: list[str] = Field(default_factory=list)


class DetectStackResponse(BaseModel):
    """The detected tech stack (and its test framework), if recognised."""

    stack: str | None
    framework: str | None


class TestPlanResponse(BaseModel):
    """The test framework and command for a build's tech stack."""

    tech_stack: str
    framework: str | None
    command: str | None
