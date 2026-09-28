"""Declarative base and the mandatory audit / tenancy mixins.

Every persistent entity in the platform inherits from :class:`BaseEntity`,
which guarantees the columns required by the data standard:

* ``id`` .............. UUID primary key
* ``created_by`` / ``created_date``
* ``modified_by`` / ``modified_date``
* ``deleted_date`` / ``is_deleted`` .... soft delete
* ``version`` ........ optimistic concurrency control

Tenant-scoped entities additionally inherit :class:`TenantMixin`, which adds
the ``organization_id`` discriminator used for row-level data isolation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
)


def utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def ensure_aware(value: datetime) -> datetime:
    """Return ``value`` as a UTC-aware datetime.

    PostgreSQL preserves timezone information, but some backends (notably
    SQLite, used in tests) return naive datetimes for ``TIMESTAMP`` columns.
    Coercing naive values to UTC keeps comparisons correct across backends.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class Base(DeclarativeBase):
    """Root declarative base for all ORM models."""


class BaseEntity(Base):
    """Abstract base providing identity, audit and concurrency columns.

    The ``__mapper_args__`` configure SQLAlchemy's built-in optimistic
    concurrency control against the ``version`` column: any ``UPDATE`` that
    does not match the in-memory version raises ``StaleDataError``, which the
    repository layer translates into :class:`OptimisticLockError`.
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    modified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    modified_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    deleted_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(default=False, index=True)

    version: Mapped[int] = mapped_column(default=1, nullable=False)

    __mapper_args__ = {"version_id_col": version}

    def soft_delete(self, actor_id: uuid.UUID | None = None) -> None:
        """Mark the row as deleted without removing it from the database."""
        self.is_deleted = True
        self.deleted_date = utcnow()
        if actor_id is not None:
            self.modified_by = actor_id


class TenantMixin:
    """Mixin adding the ``organization_id`` tenant discriminator.

    Declared as a mixin (rather than on :class:`BaseEntity`) because a small
    number of tables — the ``organizations`` table itself and the global
    permission catalogue — are not tenant-scoped.
    """

    @declared_attr
    def organization_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            Uuid,
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


class AuditLog(Base):
    """Append-only record of every mutating operation.

    Populated by the service layer via the Unit of Work. Rows are never
    updated or deleted, giving a tamper-evident history for compliance.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(String(500), default="")
    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )


class OutboxEvent(Base):
    """Transactional outbox — a domain event to be delivered out-of-band.

    Written by the service layer via the Unit of Work in the same transaction as
    the domain change (so an event is never lost or emitted for rolled-back work),
    then dispatched to webhook subscribers by a separate worker / endpoint.
    """

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True
    )
    dispatched_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
