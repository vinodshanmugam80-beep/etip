"""ORM models for authentication, tenancy and access control.

The aggregate consists of:

* :class:`Organization` — the tenant root; all other entities are scoped to it.
* :class:`User` — a person who authenticates within an organization.
* :class:`Role` — a named bundle of permissions, org-scoped (system roles are
  seeded per organization).
* :class:`Permission` — a global catalogue entry (``resource:action``).
* :class:`RefreshToken` — a persisted, rotatable refresh-token record.

Association tables wire users to roles and roles to permissions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseEntity, TenantMixin

# --- Association tables ----------------------------------------------------
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        Uuid,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Organization(BaseEntity):
    """A tenant. Owns all users, roles and (in later modules) projects."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    users: Mapped[list[User]] = relationship(back_populates="organization")
    roles: Mapped[list[Role]] = relationship(back_populates="organization")


class Permission(BaseEntity):
    """A global permission expressed as ``resource:action`` (e.g. ``project:create``).

    Permissions are not tenant-scoped: the catalogue is identical for every
    organization, and access is granted by assigning permissions to roles.
    """

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="")

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )


class Role(BaseEntity, TenantMixin):
    """A named, tenant-scoped bundle of permissions.

    ``is_system`` roles (e.g. *Organization Admin*) are seeded on organization
    creation and cannot be deleted through the API.
    """

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    organization: Mapped[Organization] = relationship(back_populates="roles")
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )
    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="roles")


class User(BaseEntity, TenantMixin):
    """An authenticating principal within an organization.

    Email is unique per organization (not globally), allowing the same address
    to exist as separate accounts across tenants.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)

    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)

    failed_login_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="users")
    roles: Mapped[list[Role]] = relationship(
        secondary=user_roles, back_populates="users", lazy="selectin"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def permission_codes(self) -> set[str]:
        """Return the flattened set of permission codes granted to the user."""
        return {perm.code for role in self.roles for perm in role.permissions}


class RefreshToken(BaseEntity, TenantMixin):
    """A persisted refresh token enabling rotation and revocation.

    The ``jti`` (JWT id) is stored rather than the token string. On refresh the
    current token is revoked and a new one issued (rotation); a replayed,
    already-revoked token signals theft and triggers family revocation.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    jti: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
