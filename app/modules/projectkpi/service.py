"""Per-project KPI service.

Manages KPIs defined directly on a project and derives their attainment. A KPI's
*attainment* measures progress from its baseline toward its target in the
direction that counts as improvement; *on_target* is whether the current value
has reached (or passed) the target.
"""

from __future__ import annotations

import uuid

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.project.repository import ProjectRepository
from app.modules.projectkpi.models import KPIDirection, ProjectKPI
from app.modules.projectkpi.repository import ProjectKPIRepository
from app.modules.projectkpi.schemas import (
    ProjectKPICreateRequest,
    ProjectKPIResponse,
    ProjectKPISummary,
    ProjectKPIUpdateRequest,
)

logger = get_logger(__name__)


def compute_attainment(kpi: ProjectKPI) -> tuple[float | None, bool]:
    """Return ``(attainment_percent, on_target)`` for a KPI.

    Attainment is progress from baseline to target along the improving direction,
    as a percentage (0 at baseline, 100 at target; it may exceed 100 when the
    current value overshoots the target). When baseline equals target the ramp is
    undefined, so attainment is reported as ``None`` and only ``on_target`` is
    meaningful.
    """
    baseline = kpi.baseline_value
    current = kpi.current_value
    target = kpi.target_value
    if kpi.direction == KPIDirection.INCREASE:
        on_target = current >= target
        span = target - baseline
    else:
        on_target = current <= target
        span = baseline - target
    if span == 0:
        return None, on_target
    progress = (
        (current - baseline) if kpi.direction == KPIDirection.INCREASE else (baseline - current)
    )
    percent = float(progress / span) * 100.0
    return round(max(0.0, percent), 1), on_target


class ProjectKPIService:
    """Manage per-project KPIs within a tenant."""

    def __init__(self, uow: UnitOfWork, *, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.kpis = ProjectKPIRepository(session)
        self.projects = ProjectRepository(session)

    def _require_project(self, project_id: uuid.UUID) -> None:
        if self.projects.get(project_id, organization_id=self._org_id) is None:
            raise NotFoundError("Project not found.")

    def _get_or_404(self, kpi_id: uuid.UUID) -> ProjectKPI:
        kpi = self.kpis.get(kpi_id, organization_id=self._org_id)
        if kpi is None:
            raise NotFoundError("Project KPI not found.")
        return kpi

    def to_response(self, kpi: ProjectKPI) -> ProjectKPIResponse:
        """Build a response with derived attainment fields."""
        response = ProjectKPIResponse.model_validate(kpi)
        response.attainment_percent, response.on_target = compute_attainment(kpi)
        return response

    def create(self, project_id: uuid.UUID, payload: ProjectKPICreateRequest) -> ProjectKPI:
        """Create a KPI on a project."""
        self._require_project(project_id)
        kpi = ProjectKPI(
            organization_id=self._org_id,
            project_id=project_id,
            name=payload.name,
            description=payload.description,
            unit=payload.unit,
            direction=payload.direction,
            baseline_value=payload.baseline_value,
            current_value=payload.current_value,
            target_value=payload.target_value,
            created_by=self._actor_id,
        )
        self.kpis.add(kpi)
        self._uow.record_audit(
            "ProjectKPI",
            kpi.id,
            "create",
            f"Created KPI '{kpi.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return kpi

    def list_for_project(
        self, project_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ProjectKPI], int]:
        """Return a project's KPIs and the total count."""
        self._require_project(project_id)
        items = list(
            self.kpis.list_for_project(self._org_id, project_id, limit=limit, offset=offset)
        )
        total = self.kpis.count_for_project(self._org_id, project_id)
        return items, total

    def update(self, kpi_id: uuid.UUID, payload: ProjectKPIUpdateRequest) -> ProjectKPI:
        """Apply a partial update to a KPI (e.g. record the current value)."""
        kpi = self._get_or_404(kpi_id)
        for attr in (
            "name",
            "description",
            "unit",
            "direction",
            "baseline_value",
            "current_value",
            "target_value",
        ):
            value = getattr(payload, attr)
            if value is not None:
                setattr(kpi, attr, value)
        kpi.modified_by = self._actor_id
        self.kpis.update(kpi)
        self._uow.record_audit(
            "ProjectKPI",
            kpi.id,
            "update",
            f"Updated KPI '{kpi.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return kpi

    def delete(self, kpi_id: uuid.UUID) -> None:
        """Soft-delete a KPI."""
        kpi = self._get_or_404(kpi_id)
        self.kpis.soft_delete(kpi, actor_id=self._actor_id)
        self._uow.record_audit(
            "ProjectKPI",
            kpi.id,
            "delete",
            f"Deleted KPI '{kpi.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    def summary(self, project_id: uuid.UUID) -> ProjectKPISummary:
        """Return the aggregated KPI position for a project."""
        self._require_project(project_id)
        items = list(self.kpis.list_for_project(self._org_id, project_id, limit=1000))
        on_target = 0
        attainments: list[float] = []
        for kpi in items:
            percent, ok = compute_attainment(kpi)
            if ok:
                on_target += 1
            if percent is not None:
                attainments.append(percent)
        avg = round(sum(attainments) / len(attainments), 1) if attainments else None
        return ProjectKPISummary(
            project_id=project_id,
            total=len(items),
            on_target=on_target,
            off_target=len(items) - on_target,
            average_attainment=avg,
        )
