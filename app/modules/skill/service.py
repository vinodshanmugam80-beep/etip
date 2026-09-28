"""Skills Matrix service.

Manages the skill catalogue and per-resource proficiency assignments, and
derives the skills matrix, skill coverage (staffing) and skill capacity supply.
Validates resources via the resource repository (never its service); records
audit entries on mutations.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.resource.models import Resource
from app.modules.resource.repository import ResourceRepository
from app.modules.skill.models import ResourceSkill, Skill, SkillCategory
from app.modules.skill.repository import ResourceSkillRepository, SkillRepository
from app.modules.skill.schemas import (
    MatrixCell,
    MatrixRow,
    ResourceSkillCreateRequest,
    ResourceSkillUpdateRequest,
    SkillCapacityItem,
    SkillCapacitySummary,
    SkillCoverage,
    SkillCoverageItem,
    SkillCreateRequest,
    SkillResponse,
    SkillsMatrix,
    SkillUpdateRequest,
)

logger = get_logger(__name__)


class SkillService:
    """Manage skills and the skills matrix, scoped to the caller's tenant."""

    def __init__(self, uow: UnitOfWork, *, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.skills = SkillRepository(session)
        self.resource_skills = ResourceSkillRepository(session)
        self.resources = ResourceRepository(session)

    # ------------------------------------------------------------------
    # Skill catalogue
    # ------------------------------------------------------------------
    def create_skill(self, payload: SkillCreateRequest) -> Skill:
        """Create a catalogue skill (unique name per tenant)."""
        if self.skills.get_by_name(self._org_id, payload.name) is not None:
            raise ConflictError("A skill with that name already exists.")
        skill = Skill(
            organization_id=self._org_id,
            name=payload.name,
            category=payload.category,
            description=payload.description,
            created_by=self._actor_id,
        )
        skill = self.skills.add(skill)
        self._audit("Skill", skill.id, "create", f"Created skill '{skill.name}'")
        return skill

    def update_skill(self, skill_id: uuid.UUID, payload: SkillUpdateRequest) -> Skill:
        """Update a catalogue skill."""
        skill = self._get_skill_or_404(skill_id)
        if payload.name is not None and payload.name.lower() != skill.name.lower():
            if self.skills.get_by_name(self._org_id, payload.name) is not None:
                raise ConflictError("A skill with that name already exists.")
            skill.name = payload.name
        if payload.category is not None:
            skill.category = payload.category
        if payload.description is not None:
            skill.description = payload.description
        skill.modified_by = self._actor_id
        skill = self.skills.update(skill)
        self._audit("Skill", skill.id, "update", f"Updated skill '{skill.name}'")
        return skill

    def delete_skill(self, skill_id: uuid.UUID) -> None:
        """Soft-delete a skill and its assignments."""
        skill = self._get_skill_or_404(skill_id)
        for assignment in self.resource_skills.list_for_skill(
            self._org_id, skill_id, min_proficiency=1
        ):
            self.resource_skills.soft_delete(assignment, actor_id=self._actor_id)
        self.skills.soft_delete(skill, actor_id=self._actor_id)
        self._audit("Skill", skill.id, "delete", f"Deleted skill '{skill.name}'")

    def get_skill(self, skill_id: uuid.UUID) -> Skill:
        """Return a skill or raise ``NotFoundError``."""
        return self._get_skill_or_404(skill_id)

    def search_skills(
        self,
        *,
        query: str | None,
        category: SkillCategory | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Skill], int]:
        """Return a filtered page of skills and the total count."""
        items = list(
            self.skills.search(
                self._org_id,
                query=query,
                category=category,
                limit=limit,
                offset=offset,
            )
        )
        total = self.skills.count(self._org_id, query=query, category=category)
        return items, total

    # ------------------------------------------------------------------
    # Assignments
    # ------------------------------------------------------------------
    def assign(self, payload: ResourceSkillCreateRequest) -> ResourceSkill:
        """Assign a skill to a resource with a proficiency."""
        self._get_resource_or_404(payload.resource_id)
        self._get_skill_or_404(payload.skill_id)
        if (
            self.resource_skills.get_pair(self._org_id, payload.resource_id, payload.skill_id)
            is not None
        ):
            raise ConflictError("This resource already has that skill assigned.")
        assignment = ResourceSkill(
            organization_id=self._org_id,
            resource_id=payload.resource_id,
            skill_id=payload.skill_id,
            proficiency=payload.proficiency,
            years_experience=payload.years_experience,
            created_by=self._actor_id,
        )
        assignment = self.resource_skills.add(assignment)
        self._audit("ResourceSkill", assignment.id, "create", "Assigned skill to resource")
        return assignment

    def update_assignment(
        self, assignment_id: uuid.UUID, payload: ResourceSkillUpdateRequest
    ) -> ResourceSkill:
        """Update a resource-skill assignment's proficiency or experience."""
        assignment = self._get_assignment_or_404(assignment_id)
        if payload.proficiency is not None:
            assignment.proficiency = payload.proficiency
        if payload.years_experience is not None:
            assignment.years_experience = payload.years_experience
        assignment.modified_by = self._actor_id
        assignment = self.resource_skills.update(assignment)
        self._audit("ResourceSkill", assignment.id, "update", "Updated skill assignment")
        return assignment

    def remove_assignment(self, assignment_id: uuid.UUID) -> None:
        """Soft-delete a resource-skill assignment."""
        assignment = self._get_assignment_or_404(assignment_id)
        self.resource_skills.soft_delete(assignment, actor_id=self._actor_id)
        self._audit("ResourceSkill", assignment.id, "delete", "Removed skill assignment")

    def list_for_resource(self, resource_id: uuid.UUID) -> list[ResourceSkill]:
        """Return a resource's skill assignments."""
        self._get_resource_or_404(resource_id)
        return list(self.resource_skills.list_for_resource(self._org_id, resource_id))

    # ------------------------------------------------------------------
    # Matrix / coverage / capacity
    # ------------------------------------------------------------------
    def matrix(self) -> SkillsMatrix:
        """Return the resources x skills proficiency matrix."""
        skills = list(self.skills.list_all(self._org_id))
        skill_names = {s.id: s.name for s in skills}
        resources = {r.id: r for r in self.resources.search(self._org_id, limit=1000)}
        by_resource: dict[uuid.UUID, list[MatrixCell]] = {}
        for assignment in self.resource_skills.list_all(self._org_id):
            if assignment.resource_id not in resources:
                continue
            by_resource.setdefault(assignment.resource_id, []).append(
                MatrixCell(
                    skill_id=assignment.skill_id,
                    skill_name=skill_names.get(assignment.skill_id, "?"),
                    proficiency=assignment.proficiency,
                )
            )
        rows = [
            MatrixRow(
                resource_id=resource.id,
                resource_name=resource.name,
                skills=by_resource.get(resource.id, []),
            )
            for resource in resources.values()
        ]
        return SkillsMatrix(skills=[SkillResponse.model_validate(s) for s in skills], rows=rows)

    def coverage(self, skill_id: uuid.UUID, *, min_proficiency: int) -> SkillCoverage:
        """Return resources holding a skill at or above a proficiency."""
        skill = self._get_skill_or_404(skill_id)
        resources = {r.id: r for r in self.resources.search(self._org_id, limit=1000)}
        items: list[SkillCoverageItem] = []
        for assignment in self.resource_skills.list_for_skill(
            self._org_id, skill_id, min_proficiency=min_proficiency
        ):
            resource = resources.get(assignment.resource_id)
            if resource is None:
                continue
            items.append(
                SkillCoverageItem(
                    resource_id=resource.id,
                    resource_name=resource.name,
                    proficiency=assignment.proficiency,
                    years_experience=assignment.years_experience,
                )
            )
        return SkillCoverage(
            skill_id=skill.id,
            skill_name=skill.name,
            min_proficiency=min_proficiency,
            resource_count=len(items),
            resources=items,
        )

    def capacity_summary(self) -> SkillCapacitySummary:
        """Return capacity supply (resources + weekly hours) per skill."""
        skills = list(self.skills.list_all(self._org_id))
        resources = {r.id: r for r in self.resources.search(self._org_id, limit=1000)}
        assignments = list(self.resource_skills.list_all(self._org_id))
        by_skill: dict[uuid.UUID, list[ResourceSkill]] = {}
        for assignment in assignments:
            by_skill.setdefault(assignment.skill_id, []).append(assignment)

        items: list[SkillCapacityItem] = []
        for skill in skills:
            skill_assignments = [
                a for a in by_skill.get(skill.id, []) if a.resource_id in resources
            ]
            total_hours = sum(
                (resources[a.resource_id].capacity_hours_per_week for a in skill_assignments),
                Decimal("0.00"),
            )
            avg = (
                round(
                    sum(a.proficiency for a in skill_assignments) / len(skill_assignments),
                    2,
                )
                if skill_assignments
                else None
            )
            items.append(
                SkillCapacityItem(
                    skill_id=skill.id,
                    skill_name=skill.name,
                    category=skill.category,
                    resource_count=len(skill_assignments),
                    total_capacity_hours=total_hours,
                    average_proficiency=avg,
                )
            )
        return SkillCapacitySummary(as_of=utcnow().date().isoformat(), items=items)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_skill_or_404(self, skill_id: uuid.UUID) -> Skill:
        skill = self.skills.get(skill_id, organization_id=self._org_id)
        if skill is None:
            raise NotFoundError("Skill not found.")
        return skill

    def _get_assignment_or_404(self, assignment_id: uuid.UUID) -> ResourceSkill:
        assignment = self.resource_skills.get(assignment_id, organization_id=self._org_id)
        if assignment is None:
            raise NotFoundError("Skill assignment not found.")
        return assignment

    def _get_resource_or_404(self, resource_id: uuid.UUID) -> Resource:
        resource = self.resources.get(resource_id, organization_id=self._org_id)
        if resource is None:
            raise NotFoundError("Resource not found.")
        return resource

    def _audit(self, entity_type: str, entity_id: uuid.UUID, action: str, summary: str) -> None:
        self._uow.record_audit(
            entity_type,
            entity_id,
            action,
            summary,
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
