"""ORM model for the Dependency Management module.

A :class:`Dependency` links a **predecessor** to a **successor** of the same
kind — task→task or project→project — with a scheduling relationship
(finish-to-start, etc.) and an optional lag. Because the two endpoints are
polymorphic (they reference tasks *or* projects depending on ``entity_type``),
they are stored as plain UUID columns and validated in the service rather than
via database foreign keys. The service also guarantees the dependency graph
stays acyclic.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class DependencyEntityType(enum.StrEnum):
    """The kind of entity a dependency links."""

    TASK = "task"
    PROJECT = "project"


class DependencyType(enum.StrEnum):
    """Scheduling relationship between predecessor and successor."""

    FINISH_TO_START = "finish_to_start"
    START_TO_START = "start_to_start"
    FINISH_TO_FINISH = "finish_to_finish"
    START_TO_FINISH = "start_to_finish"


class Dependency(BaseEntity, TenantMixin):
    """A directed dependency: ``successor`` depends on ``predecessor``.

    The ``(organization_id, entity_type, predecessor_id, successor_id)`` tuple is
    unique, preventing duplicate links. Endpoint existence, same-type and
    same-project (for tasks) rules, and acyclicity are enforced in the service.
    """

    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_type",
            "predecessor_id",
            "successor_id",
            name="uq_dependency_edge",
        ),
    )

    entity_type: Mapped[DependencyEntityType] = mapped_column(
        enum_column(DependencyEntityType), nullable=False, index=True
    )
    predecessor_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    successor_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    dependency_type: Mapped[DependencyType] = mapped_column(
        enum_column(DependencyType), default=DependencyType.FINISH_TO_START
    )
    lag_days: Mapped[int] = mapped_column(Integer, default=0)
