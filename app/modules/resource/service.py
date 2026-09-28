"""Resource Management service.

Business rules for resources and their project allocations. The centrepiece is
**over-allocation detection**: when an allocation is created or changed, a
sweep-line over the day boundaries of the new allocation and every overlapping
existing allocation verifies that the resource's committed percentage never
exceeds 100% at any point in time.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.organization.repository import DepartmentRepository
from app.modules.project.repository import ProjectRepository
from app.modules.resource.models import Resource, ResourceAllocation, ResourceType
from app.modules.resource.repository import AllocationRepository, ResourceRepository

logger = get_logger(__name__)

_MAX_ALLOCATION = 100


class ResourceService:
    """Coordinates resource and allocation use cases within a tenant."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.resources = ResourceRepository(session)
        self.allocations = AllocationRepository(session)
        self.projects = ProjectRepository(session)
        self.departments = DepartmentRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_resource_or_404(self, resource_id: uuid.UUID) -> Resource:
        resource = self.resources.get(resource_id, organization_id=self._org_id)
        if resource is None:
            raise NotFoundError("Resource not found.")
        return resource

    def _get_allocation_or_404(self, allocation_id: uuid.UUID) -> ResourceAllocation:
        allocation = self.allocations.get(allocation_id, organization_id=self._org_id)
        if allocation is None:
            raise NotFoundError("Allocation not found.")
        return allocation

    def _require_department(self, department_id: uuid.UUID | None) -> None:
        if department_id is None:
            return
        if self.departments.get(department_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Department does not belong to this organization.",
                details={"department_id": str(department_id)},
            )

    def _validate_user_link(self, user_id: uuid.UUID | None) -> None:
        """Validate a user link exists in the tenant and is not already used."""
        if user_id is None:
            return
        if self.users.get(user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "User does not belong to this organization.",
                details={"user_id": str(user_id)},
            )
        if self.resources.get_by_user(self._org_id, user_id) is not None:
            raise ConflictError(
                "This user is already registered as a resource.",
                details={"user_id": str(user_id)},
            )

    def _check_over_allocation(
        self,
        resource: Resource,
        start: date,
        end: date,
        percent: int,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        """Reject an allocation that would exceed 100% at any point in time.

        Builds day-boundary deltas for the candidate allocation and every
        overlapping existing allocation, then sweeps chronologically: an
        interval's committed total is the running sum after applying that day's
        deltas (an allocation ends inclusively, so its removal lands on the day
        after ``end_date``).
        """
        overlapping = self.allocations.list_overlapping(
            self._org_id, resource.id, start, end, exclude_id=exclude_id
        )
        deltas: dict[date, int] = defaultdict(int)
        intervals = [(start, end, percent)] + [
            (a.start_date, a.end_date, a.allocation_percent) for a in overlapping
        ]
        for interval_start, interval_end, interval_pct in intervals:
            deltas[interval_start] += interval_pct
            deltas[interval_end + timedelta(days=1)] -= interval_pct

        running = 0
        for boundary in sorted(deltas):
            running += deltas[boundary]
            if running > _MAX_ALLOCATION:
                raise ValidationError(
                    "Resource would be over-allocated beyond 100% "
                    f"(peaks at {running}% on {boundary.isoformat()}).",
                    code="over_allocation",
                    details={"peak_percent": running, "on": boundary.isoformat()},
                )

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------
    def create_resource(
        self,
        *,
        name: str,
        user_id: uuid.UUID | None,
        department_id: uuid.UUID | None,
        resource_type: ResourceType,
        capacity_hours_per_week: Decimal,
        cost_rate: Decimal,
        currency: str,
        skills: list[str],
    ) -> Resource:
        """Create a resource, validating an optional user link and department."""
        self._validate_user_link(user_id)
        self._require_department(department_id)
        resource = Resource(
            organization_id=self._org_id,
            user_id=user_id,
            department_id=department_id,
            name=name,
            resource_type=resource_type,
            capacity_hours_per_week=capacity_hours_per_week,
            cost_rate=cost_rate,
            currency=currency,
            skills=skills,
            created_by=self._actor_id,
        )
        self.resources.add(resource)
        self._uow.record_audit(
            "Resource",
            resource.id,
            "create",
            f"Created resource '{name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return resource

    def get_resource(self, resource_id: uuid.UUID) -> Resource:
        """Return a single resource by id."""
        return self._get_resource_or_404(resource_id)

    def search_resources(
        self,
        *,
        query: str | None,
        resource_type: ResourceType | None,
        department_id: uuid.UUID | None,
        is_active: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Resource], int]:
        """Return a filtered page of resources and the total matching count."""
        items = list(
            self.resources.search(
                self._org_id,
                query=query,
                resource_type=resource_type,
                department_id=department_id,
                is_active=is_active,
                limit=limit,
                offset=offset,
            )
        )
        total = self.resources.count(
            self._org_id,
            query=query,
            resource_type=resource_type,
            department_id=department_id,
            is_active=is_active,
        )
        return items, total

    def update_resource(
        self,
        resource_id: uuid.UUID,
        *,
        name: str | None,
        department_id: uuid.UUID | None,
        resource_type: ResourceType | None,
        capacity_hours_per_week: Decimal | None,
        cost_rate: Decimal | None,
        currency: str | None,
        skills: list[str] | None,
        is_active: bool | None,
    ) -> Resource:
        """Apply a partial update to a resource."""
        resource = self._get_resource_or_404(resource_id)
        if department_id is not None:
            self._require_department(department_id)
            resource.department_id = department_id
        for attr, value in (
            ("name", name),
            ("resource_type", resource_type),
            ("capacity_hours_per_week", capacity_hours_per_week),
            ("cost_rate", cost_rate),
            ("currency", currency),
            ("skills", skills),
            ("is_active", is_active),
        ):
            if value is not None:
                setattr(resource, attr, value)
        resource.modified_by = self._actor_id
        self.resources.update(resource)
        self._uow.record_audit(
            "Resource",
            resource.id,
            "update",
            f"Updated resource '{resource.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return resource

    def delete_resource(self, resource_id: uuid.UUID) -> None:
        """Soft-delete a resource, blocking if it still has allocations."""
        resource = self._get_resource_or_404(resource_id)
        if self.allocations.has_for_resource(self._org_id, resource_id):
            raise ConflictError(
                "Cannot delete a resource that still has allocations.",
                code="resource_in_use",
            )
        self.resources.soft_delete(resource, actor_id=self._actor_id)
        self._uow.record_audit(
            "Resource",
            resource.id,
            "delete",
            f"Deleted resource '{resource.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Allocations
    # ------------------------------------------------------------------
    def create_allocation(
        self,
        resource_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        start_date: date,
        end_date: date,
        allocation_percent: int,
        role_label: str,
        notes: str,
    ) -> ResourceAllocation:
        """Allocate a resource to a project, enforcing the 100% ceiling."""
        resource = self._get_resource_or_404(resource_id)
        if self.projects.get(project_id, organization_id=self._org_id) is None:
            raise NotFoundError("Project not found.")
        self._check_over_allocation(resource, start_date, end_date, allocation_percent)
        allocation = ResourceAllocation(
            organization_id=self._org_id,
            resource_id=resource_id,
            project_id=project_id,
            start_date=start_date,
            end_date=end_date,
            allocation_percent=allocation_percent,
            role_label=role_label,
            notes=notes,
            created_by=self._actor_id,
        )
        self.allocations.add(allocation)
        self._uow.record_audit(
            "ResourceAllocation",
            allocation.id,
            "create",
            f"Allocated '{resource.name}' at {allocation_percent}%",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return allocation

    def get_allocation(self, allocation_id: uuid.UUID) -> ResourceAllocation:
        """Return a single allocation by id."""
        return self._get_allocation_or_404(allocation_id)

    def list_allocations(
        self,
        *,
        resource_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> Sequence[ResourceAllocation]:
        """Return allocations filtered by resource and/or project."""
        return self.allocations.search(
            self._org_id,
            resource_id=resource_id,
            project_id=project_id,
            limit=limit,
            offset=offset,
        )

    def update_allocation(
        self,
        allocation_id: uuid.UUID,
        *,
        start_date: date | None,
        end_date: date | None,
        allocation_percent: int | None,
        role_label: str | None,
        notes: str | None,
    ) -> ResourceAllocation:
        """Apply a partial update, re-checking the over-allocation ceiling."""
        allocation = self._get_allocation_or_404(allocation_id)
        new_start = start_date if start_date is not None else allocation.start_date
        new_end = end_date if end_date is not None else allocation.end_date
        new_pct = (
            allocation_percent if allocation_percent is not None else allocation.allocation_percent
        )
        if new_end < new_start:
            raise ValidationError("end_date must not be before start_date.")

        resource = self._get_resource_or_404(allocation.resource_id)
        self._check_over_allocation(resource, new_start, new_end, new_pct, exclude_id=allocation.id)

        allocation.start_date = new_start
        allocation.end_date = new_end
        allocation.allocation_percent = new_pct
        if role_label is not None:
            allocation.role_label = role_label
        if notes is not None:
            allocation.notes = notes
        allocation.modified_by = self._actor_id
        self.allocations.update(allocation)
        self._uow.record_audit(
            "ResourceAllocation",
            allocation.id,
            "update",
            "Updated allocation",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return allocation

    def delete_allocation(self, allocation_id: uuid.UUID) -> None:
        """Soft-delete an allocation."""
        allocation = self._get_allocation_or_404(allocation_id)
        self.allocations.soft_delete(allocation, actor_id=self._actor_id)
        self._uow.record_audit(
            "ResourceAllocation",
            allocation.id,
            "delete",
            "Deleted allocation",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
