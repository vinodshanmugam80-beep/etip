"""Dependency Management service.

Business rules for the dependency graph. A dependency links a predecessor to a
successor of the same kind (task→task or project→project); task dependencies
must be within a single project. Endpoints are validated against the tenant,
duplicate edges are rejected, and — the core rule — an edge that would create a
**cycle** in the dependency graph is refused.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.dependency.models import (
    Dependency,
    DependencyEntityType,
    DependencyType,
)
from app.modules.dependency.repository import DependencyRepository
from app.modules.project.repository import ProjectRepository
from app.modules.task.repository import TaskRepository

logger = get_logger(__name__)


class DependencyService:
    """Coordinates dependency-graph use cases within a tenant."""

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
        self.dependencies = DependencyRepository(session)
        self.tasks = TaskRepository(session)
        self.projects = ProjectRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, dependency_id: uuid.UUID) -> Dependency:
        dependency = self.dependencies.get(dependency_id, organization_id=self._org_id)
        if dependency is None:
            raise NotFoundError("Dependency not found.")
        return dependency

    def _validate_endpoints(
        self,
        entity_type: DependencyEntityType,
        predecessor_id: uuid.UUID,
        successor_id: uuid.UUID,
    ) -> None:
        """Ensure both endpoints exist and satisfy the same-project rule."""
        if entity_type is DependencyEntityType.TASK:
            predecessor = self.tasks.get(predecessor_id, organization_id=self._org_id)
            successor = self.tasks.get(successor_id, organization_id=self._org_id)
            if predecessor is None or successor is None:
                raise NotFoundError("Predecessor or successor task not found.")
            if predecessor.project_id != successor.project_id:
                raise ValidationError(
                    "Task dependencies must be within the same project.",
                    code="cross_project_dependency",
                )
        else:
            predecessor_p = self.projects.get(predecessor_id, organization_id=self._org_id)
            successor_p = self.projects.get(successor_id, organization_id=self._org_id)
            if predecessor_p is None or successor_p is None:
                raise NotFoundError("Predecessor or successor project not found.")

    def _would_create_cycle(
        self,
        entity_type: DependencyEntityType,
        predecessor_id: uuid.UUID,
        successor_id: uuid.UUID,
    ) -> bool:
        """Return ``True`` if adding predecessor→successor closes a cycle.

        A cycle forms when the successor can already reach the predecessor by
        following existing edges. We traverse the graph forward from the
        successor; reaching the predecessor means the new edge would loop.
        """
        adjacency: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for pred, succ in self.dependencies.all_edges(self._org_id, entity_type):
            adjacency[pred].add(succ)

        stack = [successor_id]
        seen: set[uuid.UUID] = set()
        while stack:
            node = stack.pop()
            if node == predecessor_id:
                return True
            if node in seen:
                continue
            seen.add(node)
            stack.extend(adjacency.get(node, ()))
        return False

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_dependency(
        self,
        *,
        entity_type: DependencyEntityType,
        predecessor_id: uuid.UUID,
        successor_id: uuid.UUID,
        dependency_type: DependencyType,
        lag_days: int,
    ) -> Dependency:
        """Create a dependency, enforcing existence, uniqueness and acyclicity."""
        if predecessor_id == successor_id:
            raise ValidationError("A dependency cannot link an entity to itself.")
        self._validate_endpoints(entity_type, predecessor_id, successor_id)
        if self.dependencies.get_edge(self._org_id, entity_type, predecessor_id, successor_id):
            raise ConflictError("This dependency already exists.", code="duplicate_dependency")
        if self._would_create_cycle(entity_type, predecessor_id, successor_id):
            raise ConflictError("This dependency would create a cycle.", code="cycle_detected")
        dependency = Dependency(
            organization_id=self._org_id,
            entity_type=entity_type,
            predecessor_id=predecessor_id,
            successor_id=successor_id,
            dependency_type=dependency_type,
            lag_days=lag_days,
            created_by=self._actor_id,
        )
        self.dependencies.add(dependency)
        self._uow.record_audit(
            "Dependency",
            dependency.id,
            "create",
            f"Linked {entity_type.value} {predecessor_id} -> {successor_id}",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return dependency

    def get_dependency(self, dependency_id: uuid.UUID) -> Dependency:
        """Return a single dependency by id."""
        return self._get_or_404(dependency_id)

    def search_dependencies(
        self,
        *,
        entity_type: DependencyEntityType | None,
        predecessor_id: uuid.UUID | None,
        successor_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Dependency], int]:
        """Return a filtered page of dependencies and the total count."""
        items = list(
            self.dependencies.search(
                self._org_id,
                entity_type=entity_type,
                predecessor_id=predecessor_id,
                successor_id=successor_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.dependencies.count(
            self._org_id,
            entity_type=entity_type,
            predecessor_id=predecessor_id,
            successor_id=successor_id,
        )
        return items, total

    def list_for_entity(
        self, entity_type: DependencyEntityType, entity_id: uuid.UUID
    ) -> tuple[list[Dependency], list[Dependency]]:
        """Return the (predecessor-links, successor-links) of an entity."""
        predecessors = list(self.dependencies.predecessors_of(self._org_id, entity_type, entity_id))
        successors = list(self.dependencies.successors_of(self._org_id, entity_type, entity_id))
        return predecessors, successors

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_dependency(
        self,
        dependency_id: uuid.UUID,
        *,
        dependency_type: DependencyType | None,
        lag_days: int | None,
    ) -> Dependency:
        """Update a dependency's type or lag (endpoints are immutable)."""
        dependency = self._get_or_404(dependency_id)
        if dependency_type is not None:
            dependency.dependency_type = dependency_type
        if lag_days is not None:
            dependency.lag_days = lag_days
        dependency.modified_by = self._actor_id
        self.dependencies.update(dependency)
        self._uow.record_audit(
            "Dependency",
            dependency.id,
            "update",
            "Updated dependency",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return dependency

    def delete_dependency(self, dependency_id: uuid.UUID) -> None:
        """Soft-delete a dependency."""
        dependency = self._get_or_404(dependency_id)
        self.dependencies.soft_delete(dependency, actor_id=self._actor_id)
        self._uow.record_audit(
            "Dependency",
            dependency.id,
            "delete",
            "Deleted dependency",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    def dependencies_for_entities(
        self, entity_type: DependencyEntityType, entity_ids: Sequence[uuid.UUID]
    ) -> int:
        """Soft-delete dependencies touching any of the given entities."""
        return self.dependencies.soft_delete_for_entities(
            self._org_id, entity_type, entity_ids, actor_id=self._actor_id
        )
