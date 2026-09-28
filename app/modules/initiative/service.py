"""Strategic Initiatives service.

Manages strategic initiatives, their business goals, and the KPIs on those
goals, plus KPI measurement recording and attainment rollups. Validates
portfolio/sponsor/initiative/goal references via repositories (never services)
and records audit entries on mutations.
"""

from __future__ import annotations

import uuid

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.initiative.logic import attainment_percent, target_met
from app.modules.initiative.models import (
    BusinessGoal,
    GoalKPI,
    InitiativeStatus,
    StrategicInitiative,
)
from app.modules.initiative.repository import (
    GoalKPIRepository,
    GoalRepository,
    InitiativeRepository,
)
from app.modules.initiative.schemas import (
    GoalCreateRequest,
    GoalKPISummary,
    GoalUpdateRequest,
    InitiativeCreateRequest,
    InitiativeSummary,
    InitiativeUpdateRequest,
    KPICreateRequest,
    KPIMeasurementRequest,
    KPIUpdateRequest,
)
from app.modules.portfolio.repository import PortfolioRepository

logger = get_logger(__name__)


class InitiativeService:
    """Manage the strategic layer, scoped to the caller's tenant."""

    def __init__(self, uow: UnitOfWork, *, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.initiatives = InitiativeRepository(session)
        self.goals = GoalRepository(session)
        self.kpis = GoalKPIRepository(session)
        self.portfolios = PortfolioRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Initiatives
    # ------------------------------------------------------------------
    def create_initiative(self, payload: InitiativeCreateRequest) -> StrategicInitiative:
        """Create a strategic initiative."""
        self._validate_portfolio(payload.portfolio_id)
        self._validate_sponsor(payload.sponsor_user_id)
        initiative = StrategicInitiative(
            organization_id=self._org_id,
            portfolio_id=payload.portfolio_id,
            sponsor_user_id=payload.sponsor_user_id,
            name=payload.name,
            description=payload.description,
            status=payload.status,
            priority=payload.priority,
            start_date=payload.start_date,
            target_date=payload.target_date,
            created_by=self._actor_id,
        )
        initiative = self.initiatives.add(initiative)
        self._audit(
            "StrategicInitiative",
            initiative.id,
            "create",
            f"Created initiative '{initiative.name}'",
        )
        return initiative

    def update_initiative(
        self, initiative_id: uuid.UUID, payload: InitiativeUpdateRequest
    ) -> StrategicInitiative:
        """Update a strategic initiative."""
        initiative = self._get_initiative_or_404(initiative_id)
        if payload.portfolio_id is not None:
            self._validate_portfolio(payload.portfolio_id)
            initiative.portfolio_id = payload.portfolio_id
        if payload.sponsor_user_id is not None:
            self._validate_sponsor(payload.sponsor_user_id)
            initiative.sponsor_user_id = payload.sponsor_user_id
        for field in (
            "name",
            "description",
            "status",
            "priority",
            "start_date",
            "target_date",
        ):
            value = getattr(payload, field)
            if value is not None:
                setattr(initiative, field, value)
        initiative.modified_by = self._actor_id
        initiative = self.initiatives.update(initiative)
        self._audit(
            "StrategicInitiative",
            initiative.id,
            "update",
            f"Updated '{initiative.name}'",
        )
        return initiative

    def delete_initiative(self, initiative_id: uuid.UUID) -> None:
        """Soft-delete an initiative and its goals and KPIs."""
        initiative = self._get_initiative_or_404(initiative_id)
        for goal in self.goals.list_for_initiative(self._org_id, initiative_id):
            self._cascade_goal(goal)
        self.initiatives.soft_delete(initiative, actor_id=self._actor_id)
        self._audit(
            "StrategicInitiative",
            initiative.id,
            "delete",
            f"Deleted '{initiative.name}'",
        )

    def get_initiative(self, initiative_id: uuid.UUID) -> StrategicInitiative:
        """Return an initiative or raise ``NotFoundError``."""
        return self._get_initiative_or_404(initiative_id)

    def search_initiatives(
        self,
        *,
        status: InitiativeStatus | None,
        portfolio_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[StrategicInitiative], int]:
        """Return a filtered page of initiatives and the total count."""
        items = list(
            self.initiatives.search(
                self._org_id,
                status=status,
                portfolio_id=portfolio_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.initiatives.count(self._org_id, status=status, portfolio_id=portfolio_id)
        return items, total

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------
    def create_goal(self, payload: GoalCreateRequest) -> BusinessGoal:
        """Create a business goal under an initiative."""
        self._get_initiative_or_404(payload.initiative_id)
        goal = BusinessGoal(
            organization_id=self._org_id,
            initiative_id=payload.initiative_id,
            title=payload.title,
            description=payload.description,
            category=payload.category,
            status=payload.status,
            target_date=payload.target_date,
            created_by=self._actor_id,
        )
        goal = self.goals.add(goal)
        self._audit("BusinessGoal", goal.id, "create", f"Created goal '{goal.title}'")
        return goal

    def update_goal(self, goal_id: uuid.UUID, payload: GoalUpdateRequest) -> BusinessGoal:
        """Update a business goal."""
        goal = self._get_goal_or_404(goal_id)
        for field in ("title", "description", "category", "status", "target_date"):
            value = getattr(payload, field)
            if value is not None:
                setattr(goal, field, value)
        goal.modified_by = self._actor_id
        goal = self.goals.update(goal)
        self._audit("BusinessGoal", goal.id, "update", f"Updated goal '{goal.title}'")
        return goal

    def delete_goal(self, goal_id: uuid.UUID) -> None:
        """Soft-delete a goal and its KPIs."""
        goal = self._get_goal_or_404(goal_id)
        self._cascade_goal(goal)
        self._audit("BusinessGoal", goal.id, "delete", f"Deleted goal '{goal.title}'")

    def get_goal(self, goal_id: uuid.UUID) -> BusinessGoal:
        """Return a goal or raise ``NotFoundError``."""
        return self._get_goal_or_404(goal_id)

    def list_goals(self, initiative_id: uuid.UUID) -> list[BusinessGoal]:
        """Return the goals under an initiative."""
        self._get_initiative_or_404(initiative_id)
        return list(self.goals.list_for_initiative(self._org_id, initiative_id))

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------
    def create_kpi(self, payload: KPICreateRequest) -> GoalKPI:
        """Create a KPI on a goal."""
        self._get_goal_or_404(payload.goal_id)
        kpi = GoalKPI(
            organization_id=self._org_id,
            goal_id=payload.goal_id,
            name=payload.name,
            unit=payload.unit,
            direction=payload.direction,
            baseline_value=payload.baseline_value,
            current_value=payload.current_value,
            target_value=payload.target_value,
            created_by=self._actor_id,
        )
        kpi = self.kpis.add(kpi)
        self._audit("GoalKPI", kpi.id, "create", f"Created KPI '{kpi.name}'")
        return kpi

    def update_kpi(self, kpi_id: uuid.UUID, payload: KPIUpdateRequest) -> GoalKPI:
        """Update a KPI's definition."""
        kpi = self._get_kpi_or_404(kpi_id)
        for field in ("name", "unit", "direction", "baseline_value", "target_value"):
            value = getattr(payload, field)
            if value is not None:
                setattr(kpi, field, value)
        kpi.modified_by = self._actor_id
        kpi = self.kpis.update(kpi)
        self._audit("GoalKPI", kpi.id, "update", f"Updated KPI '{kpi.name}'")
        return kpi

    def record_kpi(self, kpi_id: uuid.UUID, payload: KPIMeasurementRequest) -> GoalKPI:
        """Record a KPI's current value."""
        kpi = self._get_kpi_or_404(kpi_id)
        kpi.current_value = payload.current_value
        kpi.modified_by = self._actor_id
        kpi = self.kpis.update(kpi)
        self._audit(
            "GoalKPI",
            kpi.id,
            "measure",
            f"Recorded {kpi.current_value} for '{kpi.name}'",
        )
        return kpi

    def delete_kpi(self, kpi_id: uuid.UUID) -> None:
        """Soft-delete a KPI."""
        kpi = self._get_kpi_or_404(kpi_id)
        self.kpis.soft_delete(kpi, actor_id=self._actor_id)
        self._audit("GoalKPI", kpi.id, "delete", f"Deleted KPI '{kpi.name}'")

    def get_kpi(self, kpi_id: uuid.UUID) -> GoalKPI:
        """Return a KPI or raise ``NotFoundError``."""
        return self._get_kpi_or_404(kpi_id)

    def list_kpis(self, goal_id: uuid.UUID) -> list[GoalKPI]:
        """Return the KPIs under a goal."""
        self._get_goal_or_404(goal_id)
        return list(self.kpis.list_for_goal(self._org_id, goal_id))

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------
    def initiative_summary(self, initiative_id: uuid.UUID) -> InitiativeSummary:
        """Return an attainment rollup across an initiative's goals and KPIs."""
        initiative = self._get_initiative_or_404(initiative_id)
        goals = list(self.goals.list_for_initiative(self._org_id, initiative_id))
        goal_ids = [g.id for g in goals]
        kpis = list(self.kpis.list_for_goals(self._org_id, goal_ids))
        kpis_by_goal: dict[uuid.UUID, list[GoalKPI]] = {}
        for kpi in kpis:
            kpis_by_goal.setdefault(kpi.goal_id, []).append(kpi)

        goal_summaries: list[GoalKPISummary] = []
        total_attainment: list[float] = []
        total_met = 0
        for goal in goals:
            g_kpis = kpis_by_goal.get(goal.id, [])
            met, attainments = self._kpi_stats(g_kpis)
            total_met += met
            total_attainment.extend(attainments)
            goal_summaries.append(
                GoalKPISummary(
                    goal_id=goal.id,
                    title=goal.title,
                    status=goal.status,
                    kpi_count=len(g_kpis),
                    kpis_met=met,
                    average_attainment=(
                        round(sum(attainments) / len(attainments), 2) if attainments else None
                    ),
                )
            )
        return InitiativeSummary(
            initiative_id=initiative.id,
            name=initiative.name,
            status=initiative.status,
            goal_count=len(goals),
            kpi_count=len(kpis),
            kpis_met=total_met,
            average_attainment=(
                round(sum(total_attainment) / len(total_attainment), 2)
                if total_attainment
                else None
            ),
            goals=goal_summaries,
        )

    def goal_summary(self, goal_id: uuid.UUID) -> GoalKPISummary:
        """Return a KPI attainment rollup for a single goal."""
        goal = self._get_goal_or_404(goal_id)
        g_kpis = list(self.kpis.list_for_goal(self._org_id, goal_id))
        met, attainments = self._kpi_stats(g_kpis)
        return GoalKPISummary(
            goal_id=goal.id,
            title=goal.title,
            status=goal.status,
            kpi_count=len(g_kpis),
            kpis_met=met,
            average_attainment=(
                round(sum(attainments) / len(attainments), 2) if attainments else None
            ),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _kpi_stats(kpis: list[GoalKPI]) -> tuple[int, list[float]]:
        met = 0
        attainments: list[float] = []
        for kpi in kpis:
            if target_met(kpi.current_value, kpi.target_value, kpi.direction):
                met += 1
            value = attainment_percent(
                kpi.baseline_value, kpi.current_value, kpi.target_value, kpi.direction
            )
            if value is not None:
                attainments.append(value)
        return met, attainments

    def _cascade_goal(self, goal: BusinessGoal) -> None:
        for kpi in self.kpis.list_for_goal(self._org_id, goal.id):
            self.kpis.soft_delete(kpi, actor_id=self._actor_id)
        self.goals.soft_delete(goal, actor_id=self._actor_id)

    def _get_initiative_or_404(self, initiative_id: uuid.UUID) -> StrategicInitiative:
        initiative = self.initiatives.get(initiative_id, organization_id=self._org_id)
        if initiative is None:
            raise NotFoundError("Initiative not found.")
        return initiative

    def _get_goal_or_404(self, goal_id: uuid.UUID) -> BusinessGoal:
        goal = self.goals.get(goal_id, organization_id=self._org_id)
        if goal is None:
            raise NotFoundError("Goal not found.")
        return goal

    def _get_kpi_or_404(self, kpi_id: uuid.UUID) -> GoalKPI:
        kpi = self.kpis.get(kpi_id, organization_id=self._org_id)
        if kpi is None:
            raise NotFoundError("KPI not found.")
        return kpi

    def _validate_portfolio(self, portfolio_id: uuid.UUID | None) -> None:
        if portfolio_id is None:
            return
        if self.portfolios.get(portfolio_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Portfolio does not belong to this organization.",
                details={"portfolio_id": str(portfolio_id)},
            )

    def _validate_sponsor(self, sponsor_user_id: uuid.UUID | None) -> None:
        if sponsor_user_id is None:
            return
        if self.users.get(sponsor_user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Sponsor does not belong to this organization.",
                details={"sponsor_user_id": str(sponsor_user_id)},
            )

    def _audit(self, entity_type: str, entity_id: uuid.UUID, action: str, summary: str) -> None:
        self._uow.record_audit(
            entity_type,
            entity_id,
            action,
            summary,
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
