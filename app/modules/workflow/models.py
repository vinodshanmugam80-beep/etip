"""Stage-Gate / Workflow / Approval models.

A generic, reusable governance workflow that any record can attach to. A
``WorkflowDefinition`` owns ordered ``WorkflowStage`` gates; a
``WorkflowInstance`` runs a definition against a polymorphic subject
(``entity_type`` + ``entity_id``); a ``GateApproval`` records each approve/reject
decision. Separation of duties (approver != starter) is enforced in the service.

This generalises the bespoke approvals in the Change and Timesheet modules
without modifying them.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class WorkflowStatus(enum.StrEnum):
    """Lifecycle of a workflow instance."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ApprovalDecision(enum.StrEnum):
    """A gate decision."""

    APPROVED = "approved"
    REJECTED = "rejected"


class WorkflowDefinition(BaseEntity, TenantMixin):
    """A named, reusable stage-gate workflow template."""

    __tablename__ = "workflow_definitions"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(2000), default="")
    entity_type: Mapped[str] = mapped_column(String(100), default="", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkflowStage(BaseEntity, TenantMixin):
    """An ordered gate within a workflow definition."""

    __tablename__ = "workflow_stages"

    definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)


class WorkflowInstance(BaseEntity, TenantMixin):
    """A running workflow against a polymorphic subject."""

    __tablename__ = "workflow_instances"

    definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    current_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_stages.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[WorkflowStatus] = mapped_column(
        enum_column(WorkflowStatus), default=WorkflowStatus.IN_PROGRESS, index=True
    )
    started_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class GateApproval(BaseEntity, TenantMixin):
    """A recorded approve/reject decision at a gate of an instance."""

    __tablename__ = "gate_approvals"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_stages.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[ApprovalDecision] = mapped_column(enum_column(ApprovalDecision))
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    comment: Mapped[str] = mapped_column(String(2000), default="")
