"""ORM models for the Resource Management module.

A :class:`Resource` is an allocatable person or asset within a tenant — usually
tied to a :class:`~app.modules.auth.models.User`, but a named external resource
(contractor, equipment) without an account is also supported. Each resource has
a weekly capacity, a cost rate and a set of skills.

A :class:`ResourceAllocation` books a resource onto a project for a date range
at some percentage of capacity. The service enforces that a resource is never
booked beyond 100% at any point across overlapping allocations.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class ResourceType(enum.StrEnum):
    """Category of an allocatable resource."""

    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"
    VENDOR = "vendor"
    EQUIPMENT = "equipment"


class Resource(BaseEntity, TenantMixin):
    """An allocatable resource (person or asset) within a tenant."""

    __tablename__ = "resources"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_type: Mapped[ResourceType] = mapped_column(
        enum_column(ResourceType), default=ResourceType.EMPLOYEE
    )

    capacity_hours_per_week: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("40.00")
    )
    cost_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    allocations: Mapped[list[ResourceAllocation]] = relationship(
        back_populates="resource", cascade="all, delete-orphan"
    )


class ResourceAllocation(BaseEntity, TenantMixin):
    """A booking of a resource onto a project over a date range.

    ``allocation_percent`` is the share (1–100) of the resource's capacity
    committed for the ``[start_date, end_date]`` window (both inclusive).
    """

    __tablename__ = "resource_allocations"

    resource_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    allocation_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    role_label: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(String(500), default="")

    resource: Mapped[Resource] = relationship(back_populates="allocations")
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
