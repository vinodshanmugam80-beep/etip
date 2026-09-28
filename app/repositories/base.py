"""Generic repository base class.

Implements the Repository pattern over a SQLAlchemy session. Concrete
repositories subclass :class:`BaseRepository`, binding the ORM model, and add
query methods specific to their aggregate. All read methods exclude
soft-deleted rows by default and enforce tenant scoping when an
``organization_id`` is supplied.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import OptimisticLockError
from app.db.base import BaseEntity

ModelT = TypeVar("ModelT", bound=BaseEntity)


class BaseRepository(Generic[ModelT]):
    """Reusable CRUD implementation for a single aggregate root.

    :param session: The active SQLAlchemy session (owned by the Unit of Work).
    :param model: The ORM model class this repository manages.
    """

    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model
        self._tenant_scoped = hasattr(model, "organization_id")

    def _base_query(self, organization_id: uuid.UUID | None) -> Select[tuple[ModelT]]:
        stmt = select(self.model).where(self.model.is_deleted.is_(False))
        if self._tenant_scoped and organization_id is not None:
            # Dynamic access: the tenant column only exists on TenantMixin
            # subclasses, which the generic ModelT cannot express statically.
            tenant_column = getattr(self.model, "organization_id")  # noqa: B009
            stmt = stmt.where(tenant_column == organization_id)
        return stmt

    def get(
        self, entity_id: uuid.UUID, *, organization_id: uuid.UUID | None = None
    ) -> ModelT | None:
        """Return a single non-deleted entity by id, or ``None``."""
        stmt = self._base_query(organization_id).where(self.model.id == entity_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list(
        self,
        *,
        organization_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ModelT]:
        """Return a page of non-deleted entities ordered by creation time."""
        stmt = (
            self._base_query(organization_id)
            .order_by(self.model.created_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.session.execute(stmt).scalars().all()

    def add(self, entity: ModelT) -> ModelT:
        """Stage a new entity for insertion and flush to assign its id."""
        self.session.add(entity)
        self.session.flush()
        return entity

    def update(self, entity: ModelT) -> ModelT:
        """Flush pending changes, translating stale-version conflicts."""
        try:
            self.session.flush()
        except StaleDataError as exc:  # pragma: no cover - defensive
            raise OptimisticLockError("The record was modified by another operation.") from exc
        return entity

    def soft_delete(self, entity: ModelT, *, actor_id: uuid.UUID | None = None) -> None:
        """Soft-delete an entity and flush the change."""
        entity.soft_delete(actor_id)
        self.session.flush()
