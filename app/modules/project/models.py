"""ORM models for the Project Management module.

The :class:`Project` is the operational heart of the PPM domain. A project may
belong to a portfolio and/or a program and to a department, and carries the
full set of planning and tracking attributes: an auto-assigned per-tenant
number, a unique code, sponsor and manager, status/stage lifecycle, budget /
forecast / actual cost, baseline and actual dates, progress, and rollup fields
(``risk_score`` / ``issue_count``) maintained by later modules.

Tags and custom fields are stored as portable JSON. The aggregate also owns two
child collections: :class:`ProjectTeamMember` and :class:`ProjectComment`.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class ProjectStatus(enum.StrEnum):
    """Lifecycle state of a project."""

    PROPOSED = "proposed"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ProjectStage(enum.StrEnum):
    """Delivery stage (phase) of a project."""

    INITIATION = "initiation"
    PLANNING = "planning"
    EXECUTION = "execution"
    MONITORING = "monitoring"
    CLOSING = "closing"


class ProjectPriority(enum.StrEnum):
    """Relative priority of a project."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProjectHealth(enum.StrEnum):
    """Health indicator for a project."""

    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OFF_TRACK = "off_track"


class Project(BaseEntity, TenantMixin):
    """A project: the primary unit of delivery in the platform.

    ``number`` is an auto-assigned, per-organization running number; ``code``
    is a unique, human-supplied identifier. Both are unique within a tenant.
    """

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_project_code"),
        UniqueConstraint("organization_id", "number", name="uq_project_number"),
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="")

    # Hierarchy / ownership references.
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("portfolios.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("programs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    sponsor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Classification.
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus), default=ProjectStatus.PROPOSED
    )
    stage: Mapped[ProjectStage] = mapped_column(
        enum_column(ProjectStage), default=ProjectStage.INITIATION
    )
    priority: Mapped[ProjectPriority] = mapped_column(
        enum_column(ProjectPriority), default=ProjectPriority.MEDIUM
    )
    health: Mapped[ProjectHealth | None] = mapped_column(enum_column(ProjectHealth), nullable=True)

    # Financials.
    budget: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    forecast: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    actual_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Schedule (actual and baseline).
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Progress and rollups (rollups maintained by risk/issue modules).
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)

    # Flexible attributes.
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Children.
    team_members: Mapped[list[ProjectTeamMember]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    comments: Mapped[list[ProjectComment]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectTeamMember(BaseEntity, TenantMixin):
    """Assignment of a user to a project with a role and allocation."""

    __tablename__ = "project_team_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_label: Mapped[str] = mapped_column(String(100), default="Member")
    allocation_percent: Mapped[int] = mapped_column(Integer, default=100)

    project: Mapped[Project] = relationship(back_populates="team_members")


class ProjectComment(BaseEntity, TenantMixin):
    """A comment posted against a project."""

    __tablename__ = "project_comments"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(String(4000), nullable=False)

    project: Mapped[Project] = relationship(back_populates="comments")
