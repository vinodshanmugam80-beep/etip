"""AI Delivery models — the control plane for AI-assisted software delivery.

ETIP is the system-of-record and governance layer for build → AI-test → CI/CD
deploy pipelines. It does not itself generate code or deploy; external AI codegen
tools, AI test tools and CI/CD systems authenticate (via API keys) and report
progress by creating :class:`PipelineRun` records against a :class:`BuildRequest`.
ETIP advances the request's lifecycle and fires webhooks on deploy / failure.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class BuildTargetType(enum.StrEnum):
    """What the AI pipeline is asked to build."""

    WEB_APP = "web_app"
    WEBSITE = "website"
    MOBILE_APP = "mobile_app"
    API_SERVICE = "api_service"
    OTHER = "other"


class BuildStatus(enum.StrEnum):
    """Lifecycle of an AI-assisted build across the full SDLC."""

    REQUESTED = "requested"
    GENERATING = "generating"
    GENERATED = "generated"
    BUILDING = "building"
    BUILT = "built"
    TESTING = "testing"
    TESTED = "tested"
    QA_REVIEW = "qa_review"
    QA_PASSED = "qa_passed"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    PERF_TESTING = "perf_testing"
    VALIDATED = "validated"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStage(enum.StrEnum):
    """A stage of the AI delivery / SDLC pipeline."""

    GENERATE = "generate"
    BUILD = "build"
    UNIT_TEST = "unit_test"
    QA = "qa"
    DEPLOY = "deploy"
    PERF_TEST = "perf_test"


class RunStatus(enum.StrEnum):
    """Outcome of a pipeline-stage run reported by an external tool."""

    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


class Environment(enum.StrEnum):
    """A deployment target environment."""

    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class DeploymentStatus(enum.StrEnum):
    """Outcome of a deployment to an environment."""

    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class BuildRequest(BaseEntity, TenantMixin):
    """A request to build something with AI-assisted tooling."""

    __tablename__ = "build_requests"

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    target_type: Mapped[BuildTargetType] = mapped_column(
        enum_column(BuildTargetType), default=BuildTargetType.WEB_APP, index=True
    )
    spec: Mapped[str] = mapped_column(String(8000), default="")
    tech_stack: Mapped[str] = mapped_column(String(50), default="")
    repository_url: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[BuildStatus] = mapped_column(
        enum_column(BuildStatus), default=BuildStatus.REQUESTED, index=True
    )
    generated_output: Mapped[str] = mapped_column(Text, default="")
    gate_min_coverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gate_max_p95_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gate_require_tests: Mapped[bool] = mapped_column(Boolean, default=False)


class PipelineRun(BaseEntity, TenantMixin):
    """A stage execution reported by an AI tool or CI/CD system."""

    __tablename__ = "pipeline_runs"

    build_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("build_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[PipelineStage] = mapped_column(enum_column(PipelineStage), index=True)
    status: Mapped[RunStatus] = mapped_column(enum_column(RunStatus), default=RunStatus.RUNNING)
    provider: Mapped[str] = mapped_column(String(100), default="")
    external_ref: Mapped[str] = mapped_column(String(300), default="")
    logs_url: Mapped[str] = mapped_column(String(1000), default="")
    message: Mapped[str] = mapped_column(String(2000), default="")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Deployment(BaseEntity, TenantMixin):
    """A deployment of a build to a specific environment."""

    __tablename__ = "deployments"

    build_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("build_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment: Mapped[Environment] = mapped_column(enum_column(Environment), index=True)
    status: Mapped[DeploymentStatus] = mapped_column(
        enum_column(DeploymentStatus), default=DeploymentStatus.DEPLOYED, index=True
    )
    release_version: Mapped[str] = mapped_column(String(100), default="")
    url: Mapped[str] = mapped_column(String(1000), default="")
    provider: Mapped[str] = mapped_column(String(100), default="")
    deployed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
