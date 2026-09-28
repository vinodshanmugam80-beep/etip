"""Stage-Gate / Workflow / Approval service.

Manages workflow definitions and their ordered stages, and runs instances
through those stages. Non-approval stages are advanced directly; approval gates
require a recorded decision, and separation of duties is enforced (the approver
must differ from whoever started the instance). Records audit entries on
mutations.
"""

from __future__ import annotations

import uuid

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.workflow.models import (
    ApprovalDecision,
    GateApproval,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStage,
    WorkflowStatus,
)
from app.modules.workflow.repository import (
    GateApprovalRepository,
    WorkflowDefinitionRepository,
    WorkflowInstanceRepository,
    WorkflowStageRepository,
)
from app.modules.workflow.schemas import (
    GateView,
    GovernanceItem,
    GovernanceOverview,
    GovernanceSummary,
    WorkflowDecisionRequest,
    WorkflowDefinitionCreateRequest,
    WorkflowDefinitionUpdateRequest,
    WorkflowInstanceStartRequest,
    WorkflowStageCreateRequest,
    WorkflowStageUpdateRequest,
)

logger = get_logger(__name__)

# The canonical software-delivery lifecycle, expressed as stage gates. Every
# phase ends with a governance sign-off, so each stage requires an approval
# decision before the subject can advance to the next phase.
SDLC_DEFINITION_NAME = "SDLC Stage Gates"
SDLC_STAGES: tuple[str, ...] = (
    "Requirements Sign-off",
    "Design & Architecture Review",
    "Development / Code Complete",
    "QA & Test Sign-off",
    "UAT / Business Acceptance",
    "Go-Live / Release Approval",
)

# Deliverable-acceptance gate for financial (billing) milestones. Approving the
# gate accepts the deliverable; the milestone module then releases the payment.
ACCEPTANCE_DEFINITION_NAME = "Deliverable Acceptance"
ACCEPTANCE_STAGES: tuple[str, ...] = (
    "Deliverable Review",
    "Business Acceptance",
)


class WorkflowService:
    """Manage governance workflows, scoped to the caller's tenant."""

    def __init__(self, uow: UnitOfWork, *, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.definitions = WorkflowDefinitionRepository(session)
        self.stages = WorkflowStageRepository(session)
        self.instances = WorkflowInstanceRepository(session)
        self.approvals = GateApprovalRepository(session)

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------
    def create_definition(self, payload: WorkflowDefinitionCreateRequest) -> WorkflowDefinition:
        """Create a workflow definition."""
        definition = WorkflowDefinition(
            organization_id=self._org_id,
            name=payload.name,
            description=payload.description,
            entity_type=payload.entity_type,
            is_active=payload.is_active,
            created_by=self._actor_id,
        )
        definition = self.definitions.add(definition)
        self._audit(
            "WorkflowDefinition",
            definition.id,
            "create",
            f"Created workflow '{definition.name}'",
        )
        return definition

    def update_definition(
        self, definition_id: uuid.UUID, payload: WorkflowDefinitionUpdateRequest
    ) -> WorkflowDefinition:
        """Update a workflow definition."""
        definition = self._get_definition_or_404(definition_id)
        for field in ("name", "description", "entity_type", "is_active"):
            value = getattr(payload, field)
            if value is not None:
                setattr(definition, field, value)
        definition.modified_by = self._actor_id
        definition = self.definitions.update(definition)
        self._audit(
            "WorkflowDefinition",
            definition.id,
            "update",
            f"Updated '{definition.name}'",
        )
        return definition

    def delete_definition(self, definition_id: uuid.UUID) -> None:
        """Soft-delete a definition and its stages and instances."""
        definition = self._get_definition_or_404(definition_id)
        for stage in self.stages.list_for_definition(self._org_id, definition_id):
            self.stages.soft_delete(stage, actor_id=self._actor_id)
        for instance in self.instances.search(
            self._org_id, definition_id=definition_id, limit=1000
        ):
            self.instances.soft_delete(instance, actor_id=self._actor_id)
        self.definitions.soft_delete(definition, actor_id=self._actor_id)
        self._audit(
            "WorkflowDefinition",
            definition.id,
            "delete",
            f"Deleted '{definition.name}'",
        )

    def get_definition(self, definition_id: uuid.UUID) -> WorkflowDefinition:
        """Return a definition or raise ``NotFoundError``."""
        return self._get_definition_or_404(definition_id)

    def search_definitions(
        self,
        *,
        entity_type: str | None,
        is_active: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[WorkflowDefinition], int]:
        """Return a filtered page of definitions and the total count."""
        items = list(
            self.definitions.search(
                self._org_id,
                entity_type=entity_type,
                is_active=is_active,
                limit=limit,
                offset=offset,
            )
        )
        total = self.definitions.count(self._org_id, entity_type=entity_type, is_active=is_active)
        return items, total

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------
    def add_stage(
        self, definition_id: uuid.UUID, payload: WorkflowStageCreateRequest
    ) -> WorkflowStage:
        """Add an ordered stage to a definition."""
        self._get_definition_or_404(definition_id)
        stage = WorkflowStage(
            organization_id=self._org_id,
            definition_id=definition_id,
            name=payload.name,
            sequence=payload.sequence,
            requires_approval=payload.requires_approval,
            created_by=self._actor_id,
        )
        stage = self.stages.add(stage)
        self._audit("WorkflowStage", stage.id, "create", f"Added stage '{stage.name}'")
        return stage

    def update_stage(
        self, stage_id: uuid.UUID, payload: WorkflowStageUpdateRequest
    ) -> WorkflowStage:
        """Update a stage."""
        stage = self._get_stage_or_404(stage_id)
        for field in ("name", "sequence", "requires_approval"):
            value = getattr(payload, field)
            if value is not None:
                setattr(stage, field, value)
        stage.modified_by = self._actor_id
        stage = self.stages.update(stage)
        self._audit("WorkflowStage", stage.id, "update", f"Updated stage '{stage.name}'")
        return stage

    def delete_stage(self, stage_id: uuid.UUID) -> None:
        """Soft-delete a stage."""
        stage = self._get_stage_or_404(stage_id)
        self.stages.soft_delete(stage, actor_id=self._actor_id)
        self._audit("WorkflowStage", stage.id, "delete", f"Deleted stage '{stage.name}'")

    def list_stages(self, definition_id: uuid.UUID) -> list[WorkflowStage]:
        """Return a definition's stages, ordered."""
        self._get_definition_or_404(definition_id)
        return list(self.stages.list_for_definition(self._org_id, definition_id))

    # ------------------------------------------------------------------
    # Instances
    # ------------------------------------------------------------------
    def start_instance(self, payload: WorkflowInstanceStartRequest) -> WorkflowInstance:
        """Start a workflow instance at the first stage of a definition."""
        definition = self._get_definition_or_404(payload.definition_id)
        if not definition.is_active:
            raise ValidationError("Workflow definition is not active.")
        stages = self.stages.list_for_definition(self._org_id, definition.id)
        if not stages:
            raise ValidationError("Workflow definition has no stages.")
        instance = WorkflowInstance(
            organization_id=self._org_id,
            definition_id=definition.id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            current_stage_id=stages[0].id,
            status=WorkflowStatus.IN_PROGRESS,
            started_by=self._actor_id,
            created_by=self._actor_id,
        )
        instance = self.instances.add(instance)
        self._audit(
            "WorkflowInstance",
            instance.id,
            "start",
            f"Started workflow '{definition.name}'",
        )
        return instance

    def advance_instance(self, instance_id: uuid.UUID) -> WorkflowInstance:
        """Advance past a non-approval stage."""
        instance = self._active_instance(instance_id)
        stage = self._current_stage(instance)
        if stage.requires_approval:
            raise ConflictError("This stage requires an approval decision, not a direct advance.")
        return self._move_forward(instance, stage)

    def record_decision(
        self, instance_id: uuid.UUID, payload: WorkflowDecisionRequest
    ) -> WorkflowInstance:
        """Record an approve/reject decision at an approval gate."""
        instance = self._active_instance(instance_id)
        stage = self._current_stage(instance)
        if not stage.requires_approval:
            raise ConflictError("The current stage does not require approval.")
        if instance.started_by is not None and instance.started_by == self._actor_id:
            raise ConflictError(
                "Separation of duties: the approver must differ from the initiator."
            )
        approval = GateApproval(
            organization_id=self._org_id,
            instance_id=instance.id,
            stage_id=stage.id,
            decision=payload.decision,
            approver_user_id=self._actor_id,
            comment=payload.comment,
            created_by=self._actor_id,
        )
        self.approvals.add(approval)

        if payload.decision == ApprovalDecision.REJECTED:
            instance.status = WorkflowStatus.REJECTED
            instance.modified_by = self._actor_id
            instance = self.instances.update(instance)
            self._audit("WorkflowInstance", instance.id, "reject", f"Rejected at '{stage.name}'")
            return instance
        self._audit("WorkflowInstance", instance.id, "approve", f"Approved at '{stage.name}'")
        self._uow.add_event(
            "workflow.approved",
            {
                "instance_id": str(instance.id),
                "entity_type": instance.entity_type,
                "entity_id": str(instance.entity_id),
                "stage": stage.name,
            },
            organization_id=self._org_id,
        )
        return self._move_forward(instance, stage)

    def cancel_instance(self, instance_id: uuid.UUID) -> WorkflowInstance:
        """Cancel an in-progress instance."""
        instance = self._active_instance(instance_id)
        instance.status = WorkflowStatus.CANCELLED
        instance.modified_by = self._actor_id
        instance = self.instances.update(instance)
        self._audit("WorkflowInstance", instance.id, "cancel", "Cancelled workflow")
        return instance

    def get_instance(self, instance_id: uuid.UUID) -> WorkflowInstance:
        """Return an instance or raise ``NotFoundError``."""
        return self._get_instance_or_404(instance_id)

    def search_instances(
        self,
        *,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        status: WorkflowStatus | None,
        definition_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[WorkflowInstance], int]:
        """Return a filtered page of instances and the total count."""
        items = list(
            self.instances.search(
                self._org_id,
                entity_type=entity_type,
                entity_id=entity_id,
                status=status,
                definition_id=definition_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.instances.count(
            self._org_id,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            definition_id=definition_id,
        )
        return items, total

    def list_approvals(self, instance_id: uuid.UUID) -> list[GateApproval]:
        """Return an instance's decision history."""
        self._get_instance_or_404(instance_id)
        return list(self.approvals.list_for_instance(self._org_id, instance_id))

    # ------------------------------------------------------------------
    # SDLC stage-gate governance
    # ------------------------------------------------------------------
    def _ensure_definition(
        self, *, name: str, entity_type: str, description: str, stages: tuple[str, ...]
    ) -> WorkflowDefinition:
        """Return a named definition for an entity type, creating it if absent.

        Idempotent: matches by name and ``entity_type`` and returns the existing
        definition rather than creating a duplicate.
        """
        existing = next(
            (
                d
                for d in self.definitions.search(
                    self._org_id, entity_type=entity_type, is_active=True, limit=200
                )
                if d.name == name
            ),
            None,
        )
        if existing is not None:
            return existing
        definition = self.create_definition(
            WorkflowDefinitionCreateRequest(
                name=name,
                description=description,
                entity_type=entity_type,
                is_active=True,
            )
        )
        for index, stage_name in enumerate(stages, start=1):
            self.add_stage(
                definition.id,
                WorkflowStageCreateRequest(name=stage_name, sequence=index, requires_approval=True),
            )
        return definition

    def ensure_sdlc_definition(self) -> WorkflowDefinition:
        """Return the canonical SDLC stage-gate definition, creating it if absent."""
        return self._ensure_definition(
            name=SDLC_DEFINITION_NAME,
            entity_type="Project",
            description=(
                "Standard software-delivery lifecycle gates: each phase requires a "
                "governance sign-off before the project may advance."
            ),
            stages=SDLC_STAGES,
        )

    def ensure_acceptance_definition(self) -> WorkflowDefinition:
        """Return the deliverable-acceptance definition (for billing milestones)."""
        return self._ensure_definition(
            name=ACCEPTANCE_DEFINITION_NAME,
            entity_type="Milestone",
            description=(
                "Deliverable acceptance gate for financial milestones: the payment "
                "is released only once the deliverable is reviewed and accepted."
            ),
            stages=ACCEPTANCE_STAGES,
        )

    def governance_overview(self, *, limit: int = 100) -> GovernanceOverview:
        """Build the stage-gate governance picture across the tenant.

        For every recent workflow instance this resolves the ordered stages, maps
        each recorded gate decision onto its stage, and classifies each gate's
        state relative to the instance's current position — yielding the per-gate
        approval view the dashboard renders plus a portfolio roll-up.
        """
        definition = next(
            (
                d
                for d in self.definitions.search(
                    self._org_id, entity_type="Project", is_active=True, limit=200
                )
                if d.name == SDLC_DEFINITION_NAME
            ),
            None,
        )
        # The SDLC governance view is about projects; milestone-acceptance
        # instances are surfaced by the milestone module's own overview.
        instances = list(
            self.instances.search(self._org_id, entity_type="Project", limit=limit, offset=0)
        )
        labels = self._entity_labels(instances)
        names = self._user_names()
        stages_cache: dict[uuid.UUID, list[WorkflowStage]] = {}
        def_names: dict[uuid.UUID, str] = {}

        items: list[GovernanceItem] = []
        pending_gates = approved_gates = awaiting_me = 0
        for inst in instances:
            if inst.definition_id not in stages_cache:
                stages_cache[inst.definition_id] = list(
                    self.stages.list_for_definition(self._org_id, inst.definition_id)
                )
                d = self.definitions.get(inst.definition_id, organization_id=self._org_id)
                def_names[inst.definition_id] = d.name if d else "Workflow"
            stages = stages_cache[inst.definition_id]
            decisions = {
                a.stage_id: a
                for a in self.approvals.list_for_instance(self._org_id, inst.id)
                if a.stage_id is not None
            }
            current_seq = self._sequence_of(inst.current_stage_id, stages)
            gates: list[GateView] = []
            done = 0
            for stage in stages:
                approval = decisions.get(stage.id)
                state = self._gate_state(inst, stage, approval, current_seq)
                if state in ("approved", "passed"):
                    done += 1
                if state == "approved":
                    approved_gates += 1
                if state == "pending":
                    pending_gates += 1
                gates.append(
                    GateView(
                        stage_id=stage.id,
                        name=stage.name,
                        sequence=stage.sequence,
                        requires_approval=stage.requires_approval,
                        state=state,
                        decision=approval.decision if approval else None,
                        approver_user_id=(approval.approver_user_id if approval else None),
                        approver_name=(
                            names.get(approval.approver_user_id)
                            if approval and approval.approver_user_id is not None
                            else None
                        ),
                        comment=approval.comment if approval else "",
                        decided_at=approval.created_date if approval else None,
                    )
                )
            current = next((s for s in stages if s.id == inst.current_stage_id), None)
            awaiting = (
                inst.status == WorkflowStatus.IN_PROGRESS
                and current is not None
                and current.requires_approval
                and inst.started_by != self._actor_id
            )
            if awaiting:
                awaiting_me += 1
            total = len(stages) or 1
            items.append(
                GovernanceItem(
                    instance_id=inst.id,
                    definition_id=inst.definition_id,
                    definition_name=def_names[inst.definition_id],
                    entity_type=inst.entity_type,
                    entity_id=inst.entity_id,
                    entity_label=labels.get((inst.entity_type, inst.entity_id))
                    or f"{inst.entity_type} {str(inst.entity_id)[:8]}",
                    status=inst.status,
                    current_stage_name=current.name if current else None,
                    progress_percent=round(done / total * 100),
                    gates=gates,
                    awaiting_my_approval=awaiting,
                )
            )

        summary = GovernanceSummary(
            instances_in_progress=sum(
                1 for i in instances if i.status == WorkflowStatus.IN_PROGRESS
            ),
            instances_completed=sum(1 for i in instances if i.status == WorkflowStatus.COMPLETED),
            instances_rejected=sum(1 for i in instances if i.status == WorkflowStatus.REJECTED),
            pending_gates=pending_gates,
            approved_gates=approved_gates,
            awaiting_my_approval=awaiting_me,
        )
        return GovernanceOverview(
            definition_ready=definition is not None,
            definition_id=definition.id if definition else None,
            summary=summary,
            items=items,
        )

    @staticmethod
    def _sequence_of(stage_id: uuid.UUID | None, stages: list[WorkflowStage]) -> int | None:
        if stage_id is None:
            return None
        return next((s.sequence for s in stages if s.id == stage_id), None)

    @staticmethod
    def _gate_state(
        instance: WorkflowInstance,
        stage: WorkflowStage,
        approval: GateApproval | None,
        current_seq: int | None,
    ) -> str:
        """Classify one gate's state for the governance view."""
        if approval is not None:
            return "approved" if approval.decision == ApprovalDecision.APPROVED else "rejected"
        if instance.status == WorkflowStatus.COMPLETED:
            return "passed"
        if instance.status == WorkflowStatus.CANCELLED:
            return "cancelled"
        if instance.status == WorkflowStatus.REJECTED:
            # No decision on this stage, but the instance died at current_seq.
            if current_seq is not None and stage.sequence < current_seq:
                return "passed"
            return "blocked"
        # In progress.
        if current_seq is None:
            return "upcoming"
        if stage.sequence < current_seq:
            return "passed"
        if stage.sequence == current_seq:
            return "pending" if stage.requires_approval else "in_progress"
        return "upcoming"

    def _entity_labels(self, instances: list[WorkflowInstance]) -> dict[tuple[str, uuid.UUID], str]:
        """Resolve human labels for instance subjects (Projects and Milestones)."""
        from app.modules.milestone.repository import MilestoneRepository
        from app.modules.project.repository import ProjectRepository

        labels: dict[tuple[str, uuid.UUID], str] = {}
        project_ids = {i.entity_id for i in instances if i.entity_type == "Project"}
        if project_ids:
            repo = ProjectRepository(self._uow.session)
            for pid in project_ids:
                project = repo.get(pid, organization_id=self._org_id)
                if project is not None:
                    labels[("Project", pid)] = f"{project.code} · {project.name}"
        milestone_ids = {i.entity_id for i in instances if i.entity_type == "Milestone"}
        if milestone_ids:
            mrepo = MilestoneRepository(self._uow.session)
            for mid in milestone_ids:
                milestone = mrepo.get(mid, organization_id=self._org_id)
                if milestone is not None:
                    labels[("Milestone", mid)] = milestone.name
        return labels

    def _user_names(self) -> dict[uuid.UUID, str]:
        """Return a map of user id → display name for the tenant."""
        from app.modules.auth.repository import UserRepository

        repo = UserRepository(self._uow.session)
        return {u.id: u.full_name for u in repo.list(organization_id=self._org_id, limit=500)}

    # ------------------------------------------------------------------
    # Progression helpers
    # ------------------------------------------------------------------
    def _move_forward(self, instance: WorkflowInstance, stage: WorkflowStage) -> WorkflowInstance:
        stages = list(self.stages.list_for_definition(self._org_id, instance.definition_id))
        nxt = next((s for s in stages if s.sequence > stage.sequence), None)
        if nxt is None:
            instance.status = WorkflowStatus.COMPLETED
            instance.current_stage_id = None
        else:
            instance.current_stage_id = nxt.id
        instance.modified_by = self._actor_id
        instance = self.instances.update(instance)
        return instance

    def _current_stage(self, instance: WorkflowInstance) -> WorkflowStage:
        if instance.current_stage_id is None:
            raise ConflictError("Instance has no current stage.")
        stage = self.stages.get(instance.current_stage_id, organization_id=self._org_id)
        if stage is None:
            raise NotFoundError("Current stage not found.")
        return stage

    def _active_instance(self, instance_id: uuid.UUID) -> WorkflowInstance:
        instance = self._get_instance_or_404(instance_id)
        if instance.status != WorkflowStatus.IN_PROGRESS:
            raise ConflictError(
                f"Instance is {instance.status.value}; no further action is possible."
            )
        return instance

    # ------------------------------------------------------------------
    # Lookups & audit
    # ------------------------------------------------------------------
    def _get_definition_or_404(self, definition_id: uuid.UUID) -> WorkflowDefinition:
        definition = self.definitions.get(definition_id, organization_id=self._org_id)
        if definition is None:
            raise NotFoundError("Workflow definition not found.")
        return definition

    def _get_stage_or_404(self, stage_id: uuid.UUID) -> WorkflowStage:
        stage = self.stages.get(stage_id, organization_id=self._org_id)
        if stage is None:
            raise NotFoundError("Workflow stage not found.")
        return stage

    def _get_instance_or_404(self, instance_id: uuid.UUID) -> WorkflowInstance:
        instance = self.instances.get(instance_id, organization_id=self._org_id)
        if instance is None:
            raise NotFoundError("Workflow instance not found.")
        return instance

    def _audit(self, entity_type: str, entity_id: uuid.UUID, action: str, summary: str) -> None:
        self._uow.record_audit(
            entity_type,
            entity_id,
            action,
            summary,
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
