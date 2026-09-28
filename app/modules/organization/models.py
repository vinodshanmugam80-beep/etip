"""ORM models for the Organization Management module.

Extends the tenant root (:class:`app.modules.auth.models.Organization`) with
its internal structure:

* :class:`BusinessUnit` — a top-level grouping within an organization.
* :class:`Department` — an org unit, optionally nested under a business unit
  and/or a parent department (self-referential hierarchy).
* :class:`OrganizationSettings` — one-to-one operational settings for a tenant.
* :class:`DepartmentMembership` — assignment of a user to a department.

User references are held as foreign-key columns (``*_user_id``) rather than ORM
relationships to keep this bounded context decoupled from the auth module;
existence is validated in the service layer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseEntity, TenantMixin


class BusinessUnit(BaseEntity, TenantMixin):
    """A top-level organizational grouping (e.g. *Technology*, *Finance*).

    ``code`` is unique per organization and is the stable human-facing
    identifier used in reports and integrations.
    """

    __tablename__ = "business_units"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_business_unit_code"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    lead_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    departments: Mapped[list[Department]] = relationship(back_populates="business_unit")


class Department(BaseEntity, TenantMixin):
    """An organizational unit within a tenant.

    A department may belong to a :class:`BusinessUnit` and may itself be nested
    beneath a parent department, forming a hierarchy. ``code`` is unique per
    organization. Cycle prevention on the parent relationship is enforced in
    the service layer.
    """

    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_department_code"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    head_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    business_unit: Mapped[BusinessUnit | None] = relationship(back_populates="departments")
    parent: Mapped[Department | None] = relationship(
        back_populates="children", remote_side="Department.id"
    )
    children: Mapped[list[Department]] = relationship(back_populates="parent")
    memberships: Mapped[list[DepartmentMembership]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )


class OrganizationSettings(BaseEntity, TenantMixin):
    """Operational settings for a tenant (one row per organization)."""

    __tablename__ = "organization_settings"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_settings_organization"),)

    currency: Mapped[str] = mapped_column(String(3), default="USD")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    date_format: Mapped[str] = mapped_column(String(32), default="YYYY-MM-DD")
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=1)
    week_start_day: Mapped[int] = mapped_column(Integer, default=1)


class DepartmentMembership(BaseEntity, TenantMixin):
    """Assignment of a user to a department.

    A user may belong to several departments but to at most one as their
    ``is_primary`` department; that invariant is enforced in the service layer.
    """

    __tablename__ = "department_memberships"
    __table_args__ = (UniqueConstraint("department_id", "user_id", name="uq_department_member"),)

    department_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    department: Mapped[Department] = relationship(back_populates="memberships")
