"""Portfolio Management service.

Business rules for portfolios and their strategic objectives: per-organization
code uniqueness, owner validation against the tenant, a status **lifecycle
state machine** (illegal transitions are rejected), date-range and budget
integrity, and management of the objectives child collection.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.portfolio.models import (
    Portfolio,
    PortfolioHealth,
    PortfolioObjective,
    PortfolioPriority,
    PortfolioStatus,
)
from app.modules.portfolio.repository import (
    PortfolioObjectiveRepository,
    PortfolioRepository,
)
from app.modules.program.repository import ProgramRepository
from app.modules.project.repository import ProjectRepository

logger = get_logger(__name__)

# Allowed status transitions. CLOSED and CANCELLED are terminal states.
_ALLOWED_TRANSITIONS: dict[PortfolioStatus, set[PortfolioStatus]] = {
    PortfolioStatus.PROPOSED: {PortfolioStatus.ACTIVE, PortfolioStatus.CANCELLED},
    PortfolioStatus.ACTIVE: {
        PortfolioStatus.ON_HOLD,
        PortfolioStatus.CLOSED,
        PortfolioStatus.CANCELLED,
    },
    PortfolioStatus.ON_HOLD: {PortfolioStatus.ACTIVE, PortfolioStatus.CANCELLED},
    PortfolioStatus.CLOSED: set(),
    PortfolioStatus.CANCELLED: set(),
}


class PortfolioService:
    """Coordinates portfolio use cases within a tenant.

    :param uow: An open Unit of Work bound to the current transaction.
    :param organization_id: The caller's tenant, bound from the access token.
    :param actor_id: The acting user's id, used for audit stamping.
    """

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
        self.portfolios = PortfolioRepository(session)
        self.objectives = PortfolioObjectiveRepository(session)
        self.users = UserRepository(session)
        self.programs = ProgramRepository(session)
        self.projects = ProjectRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, portfolio_id: uuid.UUID) -> Portfolio:
        """Return a portfolio in the caller's tenant or raise NotFoundError."""
        portfolio = self.portfolios.get(portfolio_id, organization_id=self._org_id)
        if portfolio is None:
            raise NotFoundError("Portfolio not found.")
        return portfolio

    def _require_owner_in_org(self, owner_user_id: uuid.UUID | None) -> None:
        """Validate that an owner id, if given, belongs to the tenant."""
        if owner_user_id is None:
            return
        if self.users.get(owner_user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Owner does not belong to this organization.",
                details={"owner_user_id": str(owner_user_id)},
            )

    @staticmethod
    def _validate_transition(current: PortfolioStatus, target: PortfolioStatus) -> None:
        """Reject an illegal status transition."""
        validate_status_transition(_ALLOWED_TRANSITIONS, current, target)

    @staticmethod
    def _validate_date_range(start: date | None, end: date | None) -> None:
        """Reject an end date earlier than the start date."""
        if start and end and end < start:
            raise ValidationError("end_date must not be before start_date.")

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_portfolio(
        self,
        *,
        name: str,
        code: str,
        description: str,
        owner_user_id: uuid.UUID | None,
        priority: PortfolioPriority,
        planned_budget: Decimal,
        currency: str,
        start_date: date | None,
        end_date: date | None,
    ) -> Portfolio:
        """Create a portfolio, enforcing code uniqueness and owner validity."""
        if self.portfolios.get_by_code(self._org_id, code):
            raise ConflictError(
                f"A portfolio with code '{code}' already exists.",
                details={"code": code},
            )
        self._require_owner_in_org(owner_user_id)
        self._validate_date_range(start_date, end_date)

        portfolio = Portfolio(
            organization_id=self._org_id,
            name=name,
            code=code,
            description=description,
            owner_user_id=owner_user_id,
            status=PortfolioStatus.PROPOSED,
            priority=priority,
            planned_budget=planned_budget,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
            created_by=self._actor_id,
        )
        self.portfolios.add(portfolio)
        self._uow.record_audit(
            "Portfolio",
            portfolio.id,
            "create",
            f"Created portfolio '{name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return portfolio

    def get_portfolio(self, portfolio_id: uuid.UUID) -> Portfolio:
        """Return a single portfolio by id."""
        return self._get_or_404(portfolio_id)

    def search_portfolios(
        self,
        *,
        query: str | None,
        status: PortfolioStatus | None,
        owner_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Portfolio], int]:
        """Return a filtered page of portfolios and the total matching count."""
        items = list(
            self.portfolios.search(
                self._org_id,
                query=query,
                status=status,
                owner_user_id=owner_user_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.portfolios.count(
            self._org_id, query=query, status=status, owner_user_id=owner_user_id
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_portfolio(
        self,
        portfolio_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
        owner_user_id: uuid.UUID | None,
        status: PortfolioStatus | None,
        priority: PortfolioPriority | None,
        health: PortfolioHealth | None,
        planned_budget: Decimal | None,
        currency: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> Portfolio:
        """Apply a partial update, validating status transitions and dates."""
        portfolio = self._get_or_404(portfolio_id)

        if status is not None:
            self._validate_transition(portfolio.status, status)
            portfolio.status = status
        if owner_user_id is not None:
            self._require_owner_in_org(owner_user_id)
            portfolio.owner_user_id = owner_user_id
        if name is not None:
            portfolio.name = name
        if description is not None:
            portfolio.description = description
        if priority is not None:
            portfolio.priority = priority
        if health is not None:
            portfolio.health = health
        if planned_budget is not None:
            portfolio.planned_budget = planned_budget
        if currency is not None:
            portfolio.currency = currency
        if start_date is not None:
            portfolio.start_date = start_date
        if end_date is not None:
            portfolio.end_date = end_date

        # Validate the effective date range after applying the partial update.
        self._validate_date_range(portfolio.start_date, portfolio.end_date)

        portfolio.modified_by = self._actor_id
        self.portfolios.update(portfolio)
        self._uow.record_audit(
            "Portfolio",
            portfolio.id,
            "update",
            f"Updated portfolio '{portfolio.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return portfolio

    def delete_portfolio(self, portfolio_id: uuid.UUID) -> None:
        """Soft-delete a portfolio, blocking if it still contains programs or projects."""
        portfolio = self._get_or_404(portfolio_id)
        if self.programs.has_for_portfolio(self._org_id, portfolio_id):
            raise ConflictError(
                "Cannot delete a portfolio that still contains programs.",
                code="portfolio_in_use",
            )
        if self.projects.has_for_portfolio(self._org_id, portfolio_id):
            raise ConflictError(
                "Cannot delete a portfolio that still contains projects.",
                code="portfolio_in_use",
            )
        self.portfolios.soft_delete(portfolio, actor_id=self._actor_id)
        self._uow.record_audit(
            "Portfolio",
            portfolio.id,
            "delete",
            f"Deleted portfolio '{portfolio.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Objectives
    # ------------------------------------------------------------------
    def add_objective(
        self,
        portfolio_id: uuid.UUID,
        *,
        title: str,
        description: str,
        weight: int,
    ) -> PortfolioObjective:
        """Add a strategic objective to a portfolio."""
        self._get_or_404(portfolio_id)
        objective = PortfolioObjective(
            organization_id=self._org_id,
            portfolio_id=portfolio_id,
            title=title,
            description=description,
            weight=weight,
            created_by=self._actor_id,
        )
        self.objectives.add(objective)
        self._uow.record_audit(
            "PortfolioObjective",
            objective.id,
            "create",
            f"Added objective '{title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return objective

    def list_objectives(self, portfolio_id: uuid.UUID) -> Sequence[PortfolioObjective]:
        """Return the objectives of a portfolio."""
        self._get_or_404(portfolio_id)
        return self.objectives.list_for_portfolio(self._org_id, portfolio_id)

    def remove_objective(self, portfolio_id: uuid.UUID, objective_id: uuid.UUID) -> None:
        """Remove a strategic objective from a portfolio."""
        objective = self.objectives.get_in_portfolio(self._org_id, portfolio_id, objective_id)
        if objective is None:
            raise NotFoundError("Objective not found.")
        self.objectives.soft_delete(objective, actor_id=self._actor_id)
        self._uow.record_audit(
            "PortfolioObjective",
            objective.id,
            "delete",
            "Removed objective",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
