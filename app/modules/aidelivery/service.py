"""AI Delivery service.

Manages build requests and ingests pipeline-stage runs reported by external AI
codegen / AI test / CI-CD tools. Reporting a run advances the build's lifecycle;
a passing/failing *deploy* run fires ``build.deployed`` / ``build.failed`` events
onto the transactional outbox (delivered to webhook subscribers out-of-band).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.db.base import utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.aidelivery.codegen import GeneratedArtifact, get_codegen_provider
from app.modules.aidelivery.models import (
    BuildRequest,
    BuildStatus,
    BuildTargetType,
    Deployment,
    DeploymentStatus,
    Environment,
    PipelineRun,
    PipelineStage,
    RunStatus,
)
from app.modules.aidelivery.repository import (
    BuildRequestRepository,
    DeploymentRepository,
    PipelineRunRepository,
)
from app.modules.aidelivery.schemas import BuildRequestCreate, BuildRequestUpdate, PipelineRunCreate
from app.modules.project.repository import ProjectRepository

# How a reported (stage, status) advances the build lifecycle.
_RUNNING = {
    PipelineStage.GENERATE: BuildStatus.GENERATING,
    PipelineStage.BUILD: BuildStatus.BUILDING,
    PipelineStage.UNIT_TEST: BuildStatus.TESTING,
    PipelineStage.QA: BuildStatus.QA_REVIEW,
    PipelineStage.DEPLOY: BuildStatus.DEPLOYING,
    PipelineStage.PERF_TEST: BuildStatus.PERF_TESTING,
}
_PASSED = {
    PipelineStage.GENERATE: BuildStatus.GENERATED,
    PipelineStage.BUILD: BuildStatus.BUILT,
    PipelineStage.UNIT_TEST: BuildStatus.TESTED,
    PipelineStage.QA: BuildStatus.QA_PASSED,
    PipelineStage.DEPLOY: BuildStatus.DEPLOYED,
    PipelineStage.PERF_TEST: BuildStatus.VALIDATED,
}
# Terminal states that reject further runs. DEPLOYED is NOT terminal — perf tests
# and re-deploys to other environments can follow.
_TERMINAL = {BuildStatus.FAILED, BuildStatus.CANCELLED}


class AiDeliveryService:
    """Control-plane service for AI-assisted software delivery."""

    def __init__(self, uow: UnitOfWork, *, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.builds = BuildRequestRepository(session)
        self.runs = PipelineRunRepository(session)
        self.deployments = DeploymentRepository(session)
        self.projects = ProjectRepository(session)

    # ------------------------------------------------------------------
    # Build requests
    # ------------------------------------------------------------------
    def create(self, payload: BuildRequestCreate) -> BuildRequest:
        """Open a build request."""
        if (
            payload.project_id is not None
            and self.projects.get(payload.project_id, organization_id=self._org_id) is None
        ):
            raise ValidationError(
                "Project not found.", details={"project_id": str(payload.project_id)}
            )
        build = BuildRequest(
            organization_id=self._org_id,
            project_id=payload.project_id,
            title=payload.title,
            target_type=payload.target_type,
            spec=payload.spec,
            repository_url=payload.repository_url,
            status=BuildStatus.REQUESTED,
            tech_stack=payload.tech_stack,
            gate_min_coverage=payload.gate_min_coverage,
            gate_max_p95_ms=payload.gate_max_p95_ms,
            gate_require_tests=payload.gate_require_tests,
            created_by=self._actor_id,
        )
        build = self.builds.add(build)
        self._audit(build.id, "create", f"Opened build request '{build.title}'")
        return build

    def update(self, build_id: uuid.UUID, payload: BuildRequestUpdate) -> BuildRequest:
        """Update a build request's metadata or status."""
        build = self._get_or_404(build_id)
        for field in (
            "title",
            "target_type",
            "spec",
            "tech_stack",
            "repository_url",
            "status",
            "gate_min_coverage",
            "gate_max_p95_ms",
            "gate_require_tests",
        ):
            value = getattr(payload, field)
            if value is not None:
                setattr(build, field, value)
        build.modified_by = self._actor_id
        build = self.builds.update(build)
        self._audit(build.id, "update", f"Updated build request '{build.title}'")
        return build

    def cancel(self, build_id: uuid.UUID) -> BuildRequest:
        """Cancel a build request (if not already in a terminal state)."""
        build = self._get_or_404(build_id)
        if build.status in _TERMINAL:
            raise ConflictError(f"Build is already {build.status.value}.")
        build.status = BuildStatus.CANCELLED
        build.modified_by = self._actor_id
        build = self.builds.update(build)
        self._audit(build.id, "cancel", f"Cancelled build request '{build.title}'")
        return build

    def get(self, build_id: uuid.UUID) -> BuildRequest:
        """Return a build request or raise ``NotFoundError``."""
        return self._get_or_404(build_id)

    def search(
        self,
        *,
        status: BuildStatus | None,
        target_type: BuildTargetType | None,
        project_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[BuildRequest], int]:
        """Return a filtered page of build requests and the total count."""
        items = list(
            self.builds.search(
                self._org_id,
                status=status,
                target_type=target_type,
                project_id=project_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.builds.count(
            self._org_id, status=status, target_type=target_type, project_id=project_id
        )
        return items, total

    # ------------------------------------------------------------------
    # Pipeline runs (reported by external AI / CI-CD tools)
    # ------------------------------------------------------------------
    def record_run(self, build_id: uuid.UUID, payload: PipelineRunCreate) -> PipelineRun:
        """Record a stage run and advance the build lifecycle accordingly."""
        build = self._get_or_404(build_id)
        if build.status in _TERMINAL:
            raise ConflictError(f"Build is {build.status.value}; no further runs accepted.")
        now = utcnow()
        run = PipelineRun(
            organization_id=self._org_id,
            build_request_id=build.id,
            stage=payload.stage,
            status=payload.status,
            provider=payload.provider,
            external_ref=payload.external_ref,
            logs_url=payload.logs_url,
            message=payload.message,
            metrics=payload.metrics,
            started_date=now,
            finished_date=now if payload.status is not RunStatus.RUNNING else None,
            created_by=self._actor_id,
        )
        run = self.runs.add(run)
        self._advance(build, payload.stage, payload.status)
        self._audit(
            build.id,
            "run",
            f"{payload.stage.value} run {payload.status.value} ({payload.provider or 'tool'})",
        )
        return run

    def list_runs(self, build_id: uuid.UUID) -> list[PipelineRun]:
        """Return the runs recorded against a build request."""
        self._get_or_404(build_id)
        return list(self.runs.list_for_build(self._org_id, build_id))

    def record_deployment(
        self,
        build_id: uuid.UUID,
        *,
        environment: Environment,
        status: DeploymentStatus,
        version: str,
        url: str,
        provider: str,
    ) -> Deployment:
        """Record a deployment of a build to a specific environment."""
        build = self._get_or_404(build_id)
        if environment is Environment.PRODUCTION and status is DeploymentStatus.DEPLOYED:
            gate = self.evaluate_gate(build_id)
            if not gate["passed"]:
                failed = ", ".join(c["name"] for c in gate["checks"] if not c["ok"])
                raise ConflictError(f"Quality gate failed for production ({failed}).")
        deployment = Deployment(
            organization_id=self._org_id,
            build_request_id=build.id,
            environment=environment,
            status=status,
            release_version=version,
            url=url,
            provider=provider,
            deployed_date=utcnow() if status is DeploymentStatus.DEPLOYED else None,
            created_by=self._actor_id,
        )
        deployment = self.deployments.add(deployment)
        if status is DeploymentStatus.DEPLOYED and build.status not in _TERMINAL:
            build.status = BuildStatus.DEPLOYED
            build.modified_by = self._actor_id
            self.builds.update(build)
            self._uow.add_event(
                "build.deployed",
                {
                    "build_request_id": str(build.id),
                    "title": build.title,
                    "environment": environment.value,
                    "url": url,
                },
                organization_id=self._org_id,
            )
        self._audit(build.id, "deploy", f"Deployed to {environment.value} ({status.value})")
        return deployment

    def list_deployments(self, build_id: uuid.UUID) -> list[Deployment]:
        """Return a build's deployments across environments."""
        self._get_or_404(build_id)
        return list(self.deployments.list_for_build(self._org_id, build_id))

    def _latest_metric(self, build_id: uuid.UUID, stage: PipelineStage, key: str) -> float | None:
        runs = [
            r
            for r in self.runs.list_for_build(self._org_id, build_id)
            if r.stage is stage and r.status is RunStatus.PASSED and key in r.metrics
        ]
        return float(runs[-1].metrics[key]) if runs else None

    def evaluate_gate(self, build_id: uuid.UUID) -> dict[str, Any]:
        """Evaluate the build's quality gate against its latest test/perf metrics."""
        build = self._get_or_404(build_id)
        checks: list[dict[str, Any]] = []
        if build.gate_min_coverage is not None:
            cov = self._latest_metric(build_id, PipelineStage.UNIT_TEST, "coverage")
            checks.append(
                {
                    "name": "coverage",
                    "required": f">= {build.gate_min_coverage}%",
                    "actual": cov,
                    "ok": cov is not None and cov >= build.gate_min_coverage,
                }
            )
        if build.gate_max_p95_ms is not None:
            p95 = self._latest_metric(build_id, PipelineStage.PERF_TEST, "p95_ms")
            checks.append(
                {
                    "name": "p95_ms",
                    "required": f"<= {build.gate_max_p95_ms}ms",
                    "actual": p95,
                    "ok": p95 is not None and p95 <= build.gate_max_p95_ms,
                }
            )
        if build.gate_require_tests:
            passed = self._latest_run_passed(build_id, PipelineStage.UNIT_TEST)
            checks.append(
                {
                    "name": "tests",
                    "required": "unit tests passed",
                    "actual": "passed" if passed else "not passed",
                    "ok": passed,
                }
            )
        return {"passed": all(c["ok"] for c in checks), "checks": checks}

    def _latest_run_passed(self, build_id: uuid.UUID, stage: PipelineStage) -> bool:
        runs = [r for r in self.runs.list_for_build(self._org_id, build_id) if r.stage is stage]
        return bool(runs) and runs[-1].status is RunStatus.PASSED

    def test_plan(self, build_id: uuid.UUID) -> dict[str, Any]:
        """Return the test framework + command a CI runner uses for this build's stack."""
        from app.modules.aidelivery.codegen import framework_for_stack, test_command_for

        build = self._get_or_404(build_id)
        framework = framework_for_stack(build.tech_stack)
        return {
            "tech_stack": build.tech_stack,
            "framework": framework,
            "command": test_command_for(framework),
        }

    def save_files(self, build_id: uuid.UUID, files: dict[str, str]) -> BuildRequest:
        """Persist edited source files onto the build (from the code editor)."""
        build = self._get_or_404(build_id)
        build.generated_output = json.dumps(files)
        build.modified_by = self._actor_id
        build = self.builds.update(build)
        self._audit(build.id, "edit", f"Edited {len(files)} source file(s)")
        return build

    def generate(self, build_id: uuid.UUID) -> tuple[BuildRequest, GeneratedArtifact]:
        """Run the configured code-generation provider for this build.

        ETIP performs the *generate* stage itself: the template provider by
        default, or a configured LLM when ``codegen_api_key`` is set. The output
        is stored on the build, a generate run is recorded, and the build advances.
        """
        build = self._get_or_404(build_id)
        if build.status in _TERMINAL:
            raise ConflictError(f"Build is {build.status.value}; cannot generate.")
        provider = get_codegen_provider(get_settings())
        artifact = provider.generate(build.spec, build.target_type, build.tech_stack or "")
        build.generated_output = json.dumps(artifact.files)
        now = utcnow()
        self.runs.add(
            PipelineRun(
                organization_id=self._org_id,
                build_request_id=build.id,
                stage=PipelineStage.GENERATE,
                status=RunStatus.PASSED,
                provider=artifact.provider,
                message=artifact.summary,
                started_date=now,
                finished_date=now,
                created_by=self._actor_id,
            )
        )
        build.status = BuildStatus.GENERATED
        build.modified_by = self._actor_id
        self.builds.update(build)
        self._audit(build.id, "generate", f"Generated via {artifact.provider}: {artifact.summary}")
        return build, artifact

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _advance(self, build: BuildRequest, stage: PipelineStage, status: RunStatus) -> None:
        if status is RunStatus.RUNNING:
            build.status = _RUNNING[stage]
        elif status is RunStatus.PASSED:
            build.status = _PASSED[stage]
            if stage is PipelineStage.DEPLOY:
                self._emit(build, "build.deployed")
        else:  # FAILED
            build.status = BuildStatus.FAILED
            self._emit(build, "build.failed")
        build.modified_by = self._actor_id
        self.builds.update(build)

    def _emit(self, build: BuildRequest, event_type: str) -> None:
        self._uow.add_event(
            event_type,
            {
                "build_request_id": str(build.id),
                "title": build.title,
                "target_type": build.target_type.value,
                "repository_url": build.repository_url,
                "project_id": str(build.project_id) if build.project_id else None,
            },
            organization_id=self._org_id,
        )

    def _get_or_404(self, build_id: uuid.UUID) -> BuildRequest:
        build = self.builds.get(build_id, organization_id=self._org_id)
        if build is None:
            raise NotFoundError("Build request not found.")
        return build

    def _audit(self, entity_id: uuid.UUID, action: str, summary: str) -> None:
        self._uow.record_audit(
            "BuildRequest",
            entity_id,
            action,
            summary,
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
