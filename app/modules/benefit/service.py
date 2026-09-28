"""Benefits Realization service.

Framework-agnostic; validates the owning project and optional owner, enforces
status transitions, records audit entries on mutations, and provides program /
portfolio realisation rollups by delegating to the project repository for scope
membership (never another service).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core.exceptions import NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.benefit.models import Benefit, BenefitCategory, BenefitStatus
from app.modules.benefit.repository import BenefitRepository
from app.modules.benefit.schemas import (
    BenefitCreateRequest,
    BenefitRealizationRequest,
    BenefitSummaryResponse,
    BenefitUpdateRequest,
)
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.program.repository import ProgramRepository
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository

logger = get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[BenefitStatus, set[BenefitStatus]] = {
    BenefitStatus.PLANNED: {
        BenefitStatus.IN_PROGRESS,
        BenefitStatus.PARTIALLY_REALIZED,
        BenefitStatus.REALIZED,
        BenefitStatus.AT_RISK,
        BenefitStatus.MISSED,
    },
    BenefitStatus.IN_PROGRESS: {
        BenefitStatus.PARTIALLY_REALIZED,
        BenefitStatus.REALIZED,
        BenefitStatus.AT_RISK,
        BenefitStatus.MISSED,
    },
    BenefitStatus.PARTIALLY_REALIZED: {
        BenefitStatus.REALIZED,
        BenefitStatus.AT_RISK,
        BenefitStatus.MISSED,
    },
    BenefitStatus.AT_RISK: {
        BenefitStatus.IN_PROGRESS,
        BenefitStatus.PARTIALLY_REALIZED,
        BenefitStatus.REALIZED,
        BenefitStatus.MISSED,
    },
    BenefitStatus.REALIZED: set(),
    BenefitStatus.MISSED: set(),
}


class BenefitService:
    """Manage benefits and their realisation, scoped to the caller's tenant."""

    def __init__(self, uow: UnitOfWork, *, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.benefits = BenefitRepository(session)
        self.projects = ProjectRepository(session)
        self.programs = ProgramRepository(session)
        self.portfolios = PortfolioRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def create(self, payload: BenefitCreateRequest) -> Benefit:
        """Create a benefit under a project."""
        self._get_project_or_404(payload.project_id)
        self._require_owner(payload.owner_user_id)
        benefit = Benefit(
            organization_id=self._org_id,
            project_id=payload.project_id,
            owner_user_id=payload.owner_user_id,
            title=payload.title,
            description=payload.description,
            category=payload.category,
            status=payload.status,
            target_value=payload.target_value,
            realized_value=payload.realized_value,
            investment_cost=payload.investment_cost,
            target_date=payload.target_date,
            realized_date=payload.realized_date,
            created_by=self._actor_id,
        )
        benefit = self.benefits.add(benefit)
        self._audit(benefit, "create", f"Created benefit '{benefit.title}'")
        return benefit

    def update(self, benefit_id: uuid.UUID, payload: BenefitUpdateRequest) -> Benefit:
        """Update a benefit's descriptive fields, target or status."""
        benefit = self._get_or_404(benefit_id)
        if payload.status is not None:
            validate_status_transition(_ALLOWED_TRANSITIONS, benefit.status, payload.status)
            benefit.status = payload.status
        if payload.title is not None:
            benefit.title = payload.title
        if payload.description is not None:
            benefit.description = payload.description
        if payload.category is not None:
            benefit.category = payload.category
        if payload.target_value is not None:
            benefit.target_value = payload.target_value
        if payload.investment_cost is not None:
            benefit.investment_cost = payload.investment_cost
        if payload.target_date is not None:
            benefit.target_date = payload.target_date
        if payload.owner_user_id is not None:
            self._require_owner(payload.owner_user_id)
            benefit.owner_user_id = payload.owner_user_id
        benefit.modified_by = self._actor_id
        benefit = self.benefits.update(benefit)
        self._audit(benefit, "update", f"Updated benefit '{benefit.title}'")
        return benefit

    def record_realization(
        self, benefit_id: uuid.UUID, payload: BenefitRealizationRequest
    ) -> Benefit:
        """Record realised value; auto-advances status unless one is supplied."""
        benefit = self._get_or_404(benefit_id)
        benefit.realized_value = payload.realized_value
        benefit.realized_date = payload.realized_date or date.today()
        target_status = payload.status or self._infer_status(benefit)
        if target_status != benefit.status:
            validate_status_transition(_ALLOWED_TRANSITIONS, benefit.status, target_status)
            benefit.status = target_status
        benefit.modified_by = self._actor_id
        benefit = self.benefits.update(benefit)
        self._audit(
            benefit,
            "realize",
            f"Recorded realised value {benefit.realized_value} for '{benefit.title}'",
        )
        if benefit.status == BenefitStatus.REALIZED:
            self._uow.add_event(
                "benefit.realized",
                {
                    "benefit_id": str(benefit.id),
                    "project_id": str(benefit.project_id),
                    "title": benefit.title,
                    "realized_value": str(benefit.realized_value),
                },
                organization_id=self._org_id,
            )
        return benefit

    def delete(self, benefit_id: uuid.UUID) -> None:
        """Soft-delete a benefit."""
        benefit = self._get_or_404(benefit_id)
        self.benefits.soft_delete(benefit, actor_id=self._actor_id)
        self._audit(benefit, "delete", f"Deleted benefit '{benefit.title}'")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get(self, benefit_id: uuid.UUID) -> Benefit:
        """Return a benefit or raise ``NotFoundError``."""
        return self._get_or_404(benefit_id)

    def search(
        self,
        *,
        project_id: uuid.UUID | None,
        category: BenefitCategory | None,
        status: BenefitStatus | None,
        owner_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Benefit], int]:
        """Return a filtered page of benefits and the total count."""
        items = list(
            self.benefits.search(
                self._org_id,
                project_id=project_id,
                category=category,
                status=status,
                owner_user_id=owner_user_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.benefits.count(
            self._org_id,
            project_id=project_id,
            category=category,
            status=status,
            owner_user_id=owner_user_id,
        )
        return items, total

    def project_summary(self, project_id: uuid.UUID) -> BenefitSummaryResponse:
        """Return a realisation rollup for one project."""
        self._get_project_or_404(project_id)
        return self._summary("project", project_id, [project_id])

    def program_summary(self, program_id: uuid.UUID) -> BenefitSummaryResponse:
        """Return a realisation rollup across a program's projects."""
        if self.programs.get(program_id, organization_id=self._org_id) is None:
            raise NotFoundError("Program not found.")
        project_ids = [
            p.id for p in self.projects.search(self._org_id, program_id=program_id, limit=500)
        ]
        return self._summary("program", program_id, project_ids)

    def portfolio_summary(self, portfolio_id: uuid.UUID) -> BenefitSummaryResponse:
        """Return a realisation rollup across a portfolio's projects."""
        if self.portfolios.get(portfolio_id, organization_id=self._org_id) is None:
            raise NotFoundError("Portfolio not found.")
        project_ids = [
            p.id for p in self.projects.search(self._org_id, portfolio_id=portfolio_id, limit=500)
        ]
        return self._summary("portfolio", portfolio_id, project_ids)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _summary(
        self, scope: str, scope_id: uuid.UUID, project_ids: list[uuid.UUID]
    ) -> BenefitSummaryResponse:
        target, realized, investment, count = self.benefits.totals_for_projects(
            self._org_id, project_ids
        )
        realization = round(float(realized / target) * 100, 2) if target > 0 else None
        roi = (
            round(float((realized - investment) / investment) * 100, 2) if investment > 0 else None
        )
        by_status: dict[str, int] = {}
        for benefit in self.benefits.list_for_projects(self._org_id, project_ids):
            by_status[benefit.status.value] = by_status.get(benefit.status.value, 0) + 1
        return BenefitSummaryResponse(
            scope=scope,
            scope_id=scope_id,
            benefit_count=count,
            total_target=target,
            total_realized=realized,
            total_investment=investment,
            realization_percent=realization,
            roi_percent=roi,
            variance=realized - target,
            count_by_status=by_status,
        )

    @staticmethod
    def _infer_status(benefit: Benefit) -> BenefitStatus:
        if benefit.target_value <= 0:
            return benefit.status
        if benefit.realized_value >= benefit.target_value:
            return BenefitStatus.REALIZED
        if benefit.realized_value > Decimal("0.00"):
            return BenefitStatus.PARTIALLY_REALIZED
        return benefit.status

    def _get_or_404(self, benefit_id: uuid.UUID) -> Benefit:
        benefit = self.benefits.get(benefit_id, organization_id=self._org_id)
        if benefit is None:
            raise NotFoundError("Benefit not found.")
        return benefit

    def _get_project_or_404(self, project_id: uuid.UUID) -> Project:
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    def _require_owner(self, owner_user_id: uuid.UUID | None) -> None:
        if owner_user_id is None:
            return
        if self.users.get(owner_user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Owner does not belong to this organization.",
                details={"owner_user_id": str(owner_user_id)},
            )

    def _audit(self, benefit: Benefit, action: str, summary: str) -> None:
        self._uow.record_audit(
            "Benefit",
            benefit.id,
            action,
            summary,
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
