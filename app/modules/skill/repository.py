"""Data access for the Skills Matrix."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.skill.models import ResourceSkill, Skill, SkillCategory
from app.repositories.base import BaseRepository


class SkillRepository(BaseRepository[Skill]):
    """Repository for :class:`Skill`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Skill)

    def get_by_name(self, organization_id: uuid.UUID, name: str) -> Skill | None:
        """Return a non-deleted skill by case-insensitive name."""
        stmt = self._base_query(organization_id).where(func.lower(Skill.name) == name.lower())
        return self.session.execute(stmt).scalars().first()

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        category: SkillCategory | None,
    ) -> Select[tuple[Skill]]:
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(Skill.name.ilike(f"%{query}%"))
        if category is not None:
            stmt = stmt.where(Skill.category == category)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        category: SkillCategory | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Skill]:
        """Return a filtered, paginated page of skills (by name)."""
        stmt = self._search_stmt(organization_id, query=query, category=category)
        stmt = stmt.order_by(Skill.name).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        category: SkillCategory | None = None,
    ) -> int:
        """Return the number of skills matching the filters."""
        inner = self._search_stmt(organization_id, query=query, category=category).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def list_all(self, organization_id: uuid.UUID) -> Sequence[Skill]:
        """Return every skill for the tenant, ordered by name."""
        stmt = self._base_query(organization_id).order_by(Skill.name)
        return self.session.execute(stmt).scalars().all()


class ResourceSkillRepository(BaseRepository[ResourceSkill]):
    """Repository for :class:`ResourceSkill`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ResourceSkill)

    def get_pair(
        self,
        organization_id: uuid.UUID,
        resource_id: uuid.UUID,
        skill_id: uuid.UUID,
    ) -> ResourceSkill | None:
        """Return the assignment for a (resource, skill) pair, if any."""
        stmt = self._base_query(organization_id).where(
            ResourceSkill.resource_id == resource_id,
            ResourceSkill.skill_id == skill_id,
        )
        return self.session.execute(stmt).scalars().first()

    def list_for_resource(
        self, organization_id: uuid.UUID, resource_id: uuid.UUID
    ) -> Sequence[ResourceSkill]:
        """Return all skill assignments for a resource."""
        stmt = self._base_query(organization_id).where(ResourceSkill.resource_id == resource_id)
        return self.session.execute(stmt).scalars().all()

    def list_for_skill(
        self,
        organization_id: uuid.UUID,
        skill_id: uuid.UUID,
        *,
        min_proficiency: int = 1,
    ) -> Sequence[ResourceSkill]:
        """Return assignments for a skill at or above a proficiency."""
        stmt = (
            self._base_query(organization_id)
            .where(
                ResourceSkill.skill_id == skill_id,
                ResourceSkill.proficiency >= min_proficiency,
            )
            .order_by(ResourceSkill.proficiency.desc())
        )
        return self.session.execute(stmt).scalars().all()

    def list_all(self, organization_id: uuid.UUID) -> Sequence[ResourceSkill]:
        """Return every assignment for the tenant."""
        stmt = self._base_query(organization_id)
        return self.session.execute(stmt).scalars().all()
