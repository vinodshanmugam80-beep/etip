"""HTTP routes for AI Delivery (build requests + pipeline runs).

Reads require ``build:read``; creating/updating builds and reporting runs require
``build:manage``. External AI / CI-CD tools typically authenticate with an API key
and call ``POST /builds/{id}/runs`` to report progress.
"""

from __future__ import annotations

import json as _json
import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import AiDeliveryServiceDep, UowDep, require_permission
from app.modules.aidelivery.codegen import TECH_STACKS, detect_stack, framework_for_stack
from app.modules.aidelivery.models import BuildStatus, BuildTargetType
from app.modules.aidelivery.schemas import (
    BuildFilesResponse,
    BuildRequestCreate,
    BuildRequestResponse,
    BuildRequestUpdate,
    DeploymentCreate,
    DeploymentResponse,
    DetectStackRequest,
    DetectStackResponse,
    FilesUpdate,
    GateResult,
    GeneratedArtifactResponse,
    PaginatedBuildRequests,
    PipelineRunCreate,
    PipelineRunResponse,
    TestPlanResponse,
)

router = APIRouter(prefix="/builds", tags=["AI Delivery"])
_READ = Depends(require_permission("build:read"))
_MANAGE = Depends(require_permission("build:manage"))


@router.post(
    "",
    response_model=BuildRequestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Open a build request",
)
def create_build(
    payload: BuildRequestCreate, service: AiDeliveryServiceDep, uow: UowDep
) -> BuildRequestResponse:
    """Open an AI-assisted build request."""
    build = service.create(payload)
    uow.commit()
    return BuildRequestResponse.model_validate(build)


@router.get(
    "", response_model=PaginatedBuildRequests, dependencies=[_READ], summary="List build requests"
)
def list_builds(
    service: AiDeliveryServiceDep,
    build_status: BuildStatus | None = Query(default=None, alias="status"),
    target_type: BuildTargetType | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedBuildRequests:
    """Return a filtered, paginated page of build requests."""
    items, total = service.search(
        status=build_status,
        target_type=target_type,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedBuildRequests(
        items=[BuildRequestResponse.model_validate(b) for b in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tech-stacks",
    dependencies=[_READ],
    summary="List the programming technologies AI codegen can target",
)
def list_tech_stacks() -> list[dict[str, object]]:
    """Return the catalogue of supported tech stacks (grouped by category)."""
    return TECH_STACKS


@router.post(
    "/detect-stack",
    response_model=DetectStackResponse,
    dependencies=[_READ],
    summary="Detect a tech stack from a repository's file list",
)
def detect_repo_stack(payload: DetectStackRequest) -> DetectStackResponse:
    """Infer the tech stack (and its test framework) from repo marker files."""
    stack = detect_stack(payload.filenames)
    return DetectStackResponse(stack=stack, framework=framework_for_stack(stack))


@router.get(
    "/{build_id}/test-plan",
    response_model=TestPlanResponse,
    dependencies=[_READ],
    summary="The test framework + command for this build's tech stack",
)
def build_test_plan(build_id: uuid.UUID, service: AiDeliveryServiceDep) -> TestPlanResponse:
    """Return how a CI runner should run this build's generated tests."""
    return TestPlanResponse.model_validate(service.test_plan(build_id))


@router.get(
    "/{build_id}",
    response_model=BuildRequestResponse,
    dependencies=[_READ],
    summary="Get a build request",
)
def get_build(build_id: uuid.UUID, service: AiDeliveryServiceDep) -> BuildRequestResponse:
    """Return a single build request."""
    return BuildRequestResponse.model_validate(service.get(build_id))


@router.patch(
    "/{build_id}",
    response_model=BuildRequestResponse,
    dependencies=[_MANAGE],
    summary="Update a build request",
)
def update_build(
    build_id: uuid.UUID, payload: BuildRequestUpdate, service: AiDeliveryServiceDep, uow: UowDep
) -> BuildRequestResponse:
    """Update a build request's metadata or status."""
    build = service.update(build_id, payload)
    uow.commit()
    return BuildRequestResponse.model_validate(build)


@router.post(
    "/{build_id}/cancel",
    response_model=BuildRequestResponse,
    dependencies=[_MANAGE],
    summary="Cancel a build request",
)
def cancel_build(
    build_id: uuid.UUID, service: AiDeliveryServiceDep, uow: UowDep
) -> BuildRequestResponse:
    """Cancel a build request."""
    build = service.cancel(build_id)
    uow.commit()
    return BuildRequestResponse.model_validate(build)


@router.post(
    "/{build_id}/generate",
    response_model=GeneratedArtifactResponse,
    dependencies=[_MANAGE],
    summary="Run ETIP's code generation for a build",
)
def generate_build(
    build_id: uuid.UUID, service: AiDeliveryServiceDep, uow: UowDep
) -> GeneratedArtifactResponse:
    """Generate source for this build via the configured provider (template or LLM)."""
    build, artifact = service.generate(build_id)
    uow.commit()
    return GeneratedArtifactResponse(
        build_request_id=build.id,
        status=build.status,
        provider=artifact.provider,
        summary=artifact.summary,
        files=artifact.files,
    )


@router.post(
    "/{build_id}/runs",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Report a pipeline-stage run",
)
def record_run(
    build_id: uuid.UUID, payload: PipelineRunCreate, service: AiDeliveryServiceDep, uow: UowDep
) -> PipelineRunResponse:
    """Record a generate / test / deploy run (called by AI or CI-CD tools)."""
    run = service.record_run(build_id, payload)
    uow.commit()
    return PipelineRunResponse.model_validate(run)


@router.get(
    "/{build_id}/runs",
    response_model=list[PipelineRunResponse],
    dependencies=[_READ],
    summary="List a build's runs",
)
def list_runs(build_id: uuid.UUID, service: AiDeliveryServiceDep) -> list[PipelineRunResponse]:
    """Return the pipeline runs recorded against a build request."""
    return [PipelineRunResponse.model_validate(r) for r in service.list_runs(build_id)]


@router.post(
    "/{build_id}/deployments",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Record a deployment to an environment",
)
def record_deployment(
    build_id: uuid.UUID, payload: DeploymentCreate, service: AiDeliveryServiceDep, uow: UowDep
) -> DeploymentResponse:
    """Record a deployment of a build to dev / staging / production."""
    deployment = service.record_deployment(
        build_id,
        environment=payload.environment,
        status=payload.status,
        version=payload.version,
        url=payload.url,
        provider=payload.provider,
    )
    uow.commit()
    return DeploymentResponse.model_validate(deployment)


@router.get(
    "/{build_id}/deployments",
    response_model=list[DeploymentResponse],
    dependencies=[_READ],
    summary="List a build's deployments",
)
def list_deployments(
    build_id: uuid.UUID, service: AiDeliveryServiceDep
) -> list[DeploymentResponse]:
    """Return the build's deployments across environments."""
    return [DeploymentResponse.model_validate(d) for d in service.list_deployments(build_id)]


@router.get(
    "/{build_id}/files",
    response_model=BuildFilesResponse,
    dependencies=[_READ],
    summary="Get a build's current source files",
)
def get_files(build_id: uuid.UUID, service: AiDeliveryServiceDep) -> BuildFilesResponse:
    """Return the source files stored on the build (for the code editor)."""
    build = service.get(build_id)
    files = _json.loads(build.generated_output) if build.generated_output else {}
    return BuildFilesResponse(build_request_id=build.id, files=files)


@router.put(
    "/{build_id}/files",
    response_model=BuildFilesResponse,
    dependencies=[_MANAGE],
    summary="Save edited source files",
)
def save_files(
    build_id: uuid.UUID, payload: FilesUpdate, service: AiDeliveryServiceDep, uow: UowDep
) -> BuildFilesResponse:
    """Save edited source files from the in-dashboard code editor."""
    build = service.save_files(build_id, payload.files)
    uow.commit()
    return BuildFilesResponse(build_request_id=build.id, files=payload.files)


@router.get(
    "/{build_id}/gate",
    response_model=GateResult,
    dependencies=[_READ],
    summary="Evaluate the build's quality gate",
)
def evaluate_gate(build_id: uuid.UUID, service: AiDeliveryServiceDep) -> GateResult:
    """Evaluate coverage / performance thresholds against the build's latest metrics."""
    return GateResult.model_validate(service.evaluate_gate(build_id))
