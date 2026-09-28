"""Pydantic v2 schemas for the Stage-Gate / Workflow / Approval engine."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.workflow.models import ApprovalDecision, WorkflowStatus


# --- Definitions -----------------------------------------------------------
class WorkflowDefinitionCreateRequest(BaseModel):
    """Payload to create a workflow definition."""

    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    entity_type: str = Field(default="", max_length=100)
    is_active: bool = True


class WorkflowDefinitionUpdateRequest(BaseModel):
    """Payload to update a workflow definition."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    entity_type: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class WorkflowDefinitionResponse(BaseModel):
    """A workflow definition."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str
    entity_type: str
    is_active: bool
    created_date: datetime
    version: int


class PaginatedWorkflowDefinitions(BaseModel):
    """A page of workflow definitions."""

    items: list[WorkflowDefinitionResponse]
    total: int
    limit: int
    offset: int


# --- Stages ----------------------------------------------------------------
class WorkflowStageCreateRequest(BaseModel):
    """Payload to add a stage to a definition."""

    name: str = Field(min_length=2, max_length=200)
    sequence: int = Field(ge=1)
    requires_approval: bool = False


class WorkflowStageUpdateRequest(BaseModel):
    """Payload to update a stage."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    sequence: int | None = Field(default=None, ge=1)
    requires_approval: bool | None = None


class WorkflowStageResponse(BaseModel):
    """A stage of a workflow definition."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    definition_id: uuid.UUID
    name: str
    sequence: int
    requires_approval: bool
    created_date: datetime
    version: int


# --- Instances -------------------------------------------------------------
class WorkflowInstanceStartRequest(BaseModel):
    """Payload to start a workflow instance against a subject."""

    definition_id: uuid.UUID
    entity_type: str = Field(min_length=1, max_length=100)
    entity_id: uuid.UUID


class WorkflowDecisionRequest(BaseModel):
    """Payload to record a gate decision."""

    decision: ApprovalDecision
    comment: str = Field(default="", max_length=2000)


class WorkflowInstanceResponse(BaseModel):
    """A running (or finished) workflow instance."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    definition_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    current_stage_id: uuid.UUID | None
    status: WorkflowStatus
    started_by: uuid.UUID | None
    created_date: datetime
    version: int


class PaginatedWorkflowInstances(BaseModel):
    """A page of workflow instances."""

    items: list[WorkflowInstanceResponse]
    total: int
    limit: int
    offset: int


class GateApprovalResponse(BaseModel):
    """A recorded gate decision."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    instance_id: uuid.UUID
    stage_id: uuid.UUID | None
    decision: ApprovalDecision
    approver_user_id: uuid.UUID | None
    comment: str
    created_date: datetime


# --- Governance overview (dashboard read model) ----------------------------
class GateView(BaseModel):
    """One SDLC gate within a governance instance, with its approval state.

    ``state`` is one of: ``approved`` (signed off at an approval gate),
    ``passed`` (a non-approval stage already traversed), ``pending`` (an
    approval gate awaiting a decision — this is the "gating approval"),
    ``in_progress`` (a non-approval stage currently active), ``rejected``,
    ``upcoming`` (not yet reached), ``blocked`` (after a rejection) or
    ``cancelled``.
    """

    stage_id: uuid.UUID
    name: str
    sequence: int
    requires_approval: bool
    state: str
    decision: ApprovalDecision | None = None
    approver_user_id: uuid.UUID | None = None
    approver_name: str | None = None
    comment: str = ""
    decided_at: datetime | None = None


class GovernanceItem(BaseModel):
    """A subject (e.g. a project) under stage-gate governance."""

    instance_id: uuid.UUID
    definition_id: uuid.UUID
    definition_name: str
    entity_type: str
    entity_id: uuid.UUID
    entity_label: str
    status: WorkflowStatus
    current_stage_name: str | None
    progress_percent: int
    gates: list[GateView]
    awaiting_my_approval: bool


class GovernanceSummary(BaseModel):
    """Portfolio-wide roll-up of governance state."""

    instances_in_progress: int
    instances_completed: int
    instances_rejected: int
    pending_gates: int
    approved_gates: int
    awaiting_my_approval: int


class GovernanceOverview(BaseModel):
    """The full stage-gate governance picture for the dashboard."""

    definition_ready: bool
    definition_id: uuid.UUID | None
    summary: GovernanceSummary
    items: list[GovernanceItem]
