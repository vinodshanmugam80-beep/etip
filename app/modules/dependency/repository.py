"""Repository for the Dependency Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.modules.dependency.models import Dependency, DependencyEntityType
from app.repositories.base import BaseRepository


class DependencyRepository(BaseRepository[Dependency]):
    """Data access for :class:`Dependency`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Dependency)

    def get_edge(
        self,
        organization_id: uuid.UUID,
        entity_type: DependencyEntityType,
        predecessor_id: uuid.UUID,
        successor_id: uuid.UUID,
    ) -> Dependency | None:
        """Return an existing dependency for a specific edge, if any."""
        stmt = self._base_query(organization_id).where(
            Dependency.entity_type == entity_type,
            Dependency.predecessor_id == predecessor_id,
            Dependency.successor_id == successor_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def all_edges(
        self, organization_id: uuid.UUID, entity_type: DependencyEntityType
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Return every ``(predecessor_id, successor_id)`` edge of a type.

        Used to build the graph for cycle detection.
        """
        stmt = select(Dependency.predecessor_id, Dependency.successor_id).where(
            Dependency.organization_id == organization_id,
            Dependency.entity_type == entity_type,
            Dependency.is_deleted.is_(False),
        )
        return [(row[0], row[1]) for row in self.session.execute(stmt).all()]

    def predecessors_of(
        self,
        organization_id: uuid.UUID,
        entity_type: DependencyEntityType,
        entity_id: uuid.UUID,
    ) -> Sequence[Dependency]:
        """Return dependencies where the entity is the successor."""
        stmt = self._base_query(organization_id).where(
            Dependency.entity_type == entity_type,
            Dependency.successor_id == entity_id,
        )
        return self.session.execute(stmt).scalars().all()

    def successors_of(
        self,
        organization_id: uuid.UUID,
        entity_type: DependencyEntityType,
        entity_id: uuid.UUID,
    ) -> Sequence[Dependency]:
        """Return dependencies where the entity is the predecessor."""
        stmt = self._base_query(organization_id).where(
            Dependency.entity_type == entity_type,
            Dependency.predecessor_id == entity_id,
        )
        return self.session.execute(stmt).scalars().all()

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: DependencyEntityType | None,
        predecessor_id: uuid.UUID | None,
        successor_id: uuid.UUID | None,
    ) -> Select[tuple[Dependency]]:
        """Build the filtered (unpaginated) dependency query."""
        stmt = self._base_query(organization_id)
        if entity_type is not None:
            stmt = stmt.where(Dependency.entity_type == entity_type)
        if predecessor_id is not None:
            stmt = stmt.where(Dependency.predecessor_id == predecessor_id)
        if successor_id is not None:
            stmt = stmt.where(Dependency.successor_id == successor_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: DependencyEntityType | None = None,
        predecessor_id: uuid.UUID | None = None,
        successor_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Dependency]:
        """Return a filtered, paginated page of dependencies."""
        stmt = self._search_stmt(
            organization_id,
            entity_type=entity_type,
            predecessor_id=predecessor_id,
            successor_id=successor_id,
        )
        stmt = stmt.order_by(Dependency.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: DependencyEntityType | None = None,
        predecessor_id: uuid.UUID | None = None,
        successor_id: uuid.UUID | None = None,
    ) -> int:
        """Return the number of dependencies matching the filters."""
        inner = self._search_stmt(
            organization_id,
            entity_type=entity_type,
            predecessor_id=predecessor_id,
            successor_id=successor_id,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def soft_delete_for_entities(
        self,
        organization_id: uuid.UUID,
        entity_type: DependencyEntityType,
        entity_ids: Sequence[uuid.UUID],
        *,
        actor_id: uuid.UUID,
    ) -> int:
        """Soft-delete dependencies touching any of the given entities."""
        if not entity_ids:
            return 0
        ids = list(entity_ids)
        stmt = self._base_query(organization_id).where(
            Dependency.entity_type == entity_type,
            or_(
                Dependency.predecessor_id.in_(ids),
                Dependency.successor_id.in_(ids),
            ),
        )
        rows = list(self.session.execute(stmt).scalars().all())
        for dep in rows:
            dep.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
