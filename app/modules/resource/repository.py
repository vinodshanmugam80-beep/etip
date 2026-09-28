"""Repositories for the Resource Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.resource.models import Resource, ResourceAllocation, ResourceType
from app.repositories.base import BaseRepository


class ResourceRepository(BaseRepository[Resource]):
    """Data access for :class:`Resource`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Resource)

    def get_by_user(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> Resource | None:
        """Return the resource linked to a user, if any."""
        stmt = self._base_query(organization_id).where(Resource.user_id == user_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        resource_type: ResourceType | None,
        department_id: uuid.UUID | None,
        is_active: bool | None,
    ) -> Select[tuple[Resource]]:
        """Build the filtered (unpaginated) resource query."""
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(func.lower(Resource.name).like(f"%{query.lower()}%"))
        if resource_type is not None:
            stmt = stmt.where(Resource.resource_type == resource_type)
        if department_id is not None:
            stmt = stmt.where(Resource.department_id == department_id)
        if is_active is not None:
            stmt = stmt.where(Resource.is_active.is_(is_active))
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        resource_type: ResourceType | None = None,
        department_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Resource]:
        """Return a filtered, paginated page of resources."""
        stmt = self._search_stmt(
            organization_id,
            query=query,
            resource_type=resource_type,
            department_id=department_id,
            is_active=is_active,
        )
        stmt = stmt.order_by(Resource.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        resource_type: ResourceType | None = None,
        department_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> int:
        """Return the total number of resources matching the filters."""
        inner = self._search_stmt(
            organization_id,
            query=query,
            resource_type=resource_type,
            department_id=department_id,
            is_active=is_active,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())


class AllocationRepository(BaseRepository[ResourceAllocation]):
    """Data access for :class:`ResourceAllocation`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ResourceAllocation)

    def list_for_resource(
        self, organization_id: uuid.UUID, resource_id: uuid.UUID
    ) -> Sequence[ResourceAllocation]:
        """Return all live allocations of a resource, earliest start first."""
        stmt = (
            self._base_query(organization_id)
            .where(ResourceAllocation.resource_id == resource_id)
            .order_by(ResourceAllocation.start_date.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def list_overlapping(
        self,
        organization_id: uuid.UUID,
        resource_id: uuid.UUID,
        start: date,
        end: date,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> list[ResourceAllocation]:
        """Return a resource's allocations overlapping ``[start, end]``.

        Two inclusive ranges overlap when ``existing.start <= end`` and
        ``existing.end >= start``.
        """
        stmt = self._base_query(organization_id).where(
            ResourceAllocation.resource_id == resource_id,
            ResourceAllocation.start_date <= end,
            ResourceAllocation.end_date >= start,
        )
        if exclude_id is not None:
            stmt = stmt.where(ResourceAllocation.id != exclude_id)
        return list(self.session.execute(stmt).scalars().all())

    def list_all(self, organization_id: uuid.UUID) -> list[ResourceAllocation]:
        """Return every live allocation for the tenant (for forecasting)."""
        return list(self.session.execute(self._base_query(organization_id)).scalars().all())

    def has_for_resource(self, organization_id: uuid.UUID, resource_id: uuid.UUID) -> bool:
        """Return ``True`` if the resource has any live allocation."""
        stmt = self._base_query(organization_id).where(
            ResourceAllocation.resource_id == resource_id
        )
        return self.session.execute(stmt.limit(1)).first() is not None

    def has_for_project(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> bool:
        """Return ``True`` if any live allocation targets the project."""
        stmt = self._base_query(organization_id).where(ResourceAllocation.project_id == project_id)
        return self.session.execute(stmt.limit(1)).first() is not None

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live allocation targeting a project."""
        stmt = self._base_query(organization_id).where(ResourceAllocation.project_id == project_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for allocation in rows:
            allocation.soft_delete(actor_id)
        self.session.flush()
        return len(rows)

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        resource_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ResourceAllocation]:
        """Return allocations filtered by resource and/or project."""
        stmt = self._base_query(organization_id)
        if resource_id is not None:
            stmt = stmt.where(ResourceAllocation.resource_id == resource_id)
        if project_id is not None:
            stmt = stmt.where(ResourceAllocation.project_id == project_id)
        stmt = stmt.order_by(ResourceAllocation.start_date.asc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()
