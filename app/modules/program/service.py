"""Program Management service.

Business rules for programs: each program belongs to exactly one **portfolio**
(validated against the tenant), code is unique per organization, the manager
must be a user in the tenant, the status follows the shared lifecycle state
machine, and date ranges are validated. Framework-agnostic.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.program.models import (
    Program,
    ProgramHealth,
    ProgramPriority,
    ProgramStatus,
)
from app.modules.program.repository import ProgramRepository
from app.modules.project.repository import ProjectRepository

logger = get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[ProgramStatus, set[ProgramStatus]] = {
    ProgramStatus.PROPOSED: {ProgramStatus.ACTIVE, ProgramStatus.CANCELLED},
    ProgramStatus.ACTIVE: {
        ProgramStatus.ON_HOLD,
        ProgramStatus.CLOSED,
        ProgramStatus.CANCELLED,
    },
    ProgramStatus.ON_HOLD: {ProgramStatus.ACTIVE, ProgramStatus.CANCELLED},
    ProgramStatus.CLOSED: set(),
    ProgramStatus.CANCELLED: set(),
}


class ProgramService:
    """Coordinates program use cases within a tenant.

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
        self.programs = ProgramRepository(session)
        self.portfolios = PortfolioRepository(session)
        self.projects = ProjectRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, program_id: uuid.UUID) -> Program:
        """Return a program in the caller's tenant or raise NotFoundError."""
        program = self.programs.get(program_id, organization_id=self._org_id)
        if program is None:
            raise NotFoundError("Program not found.")
        return program

    def _require_portfolio(self, portfolio_id: uuid.UUID) -> None:
        """Validate that the referenced portfolio exists in the tenant."""
        if self.portfolios.get(portfolio_id, organization_id=self._org_id) is None:
            raise NotFoundError("Portfolio not found.")

    def _require_manager_in_org(self, manager_user_id: uuid.UUID | None) -> None:
        """Validate that a manager id, if given, belongs to the tenant."""
        if manager_user_id is None:
            return
        if self.users.get(manager_user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Manager does not belong to this organization.",
                details={"manager_user_id": str(manager_user_id)},
            )

    @staticmethod
    def _validate_date_range(start: date | None, end: date | None) -> None:
        """Reject an end date earlier than the start date."""
        if start and end and end < start:
            raise ValidationError("end_date must not be before start_date.")

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_program(
        self,
        *,
        portfolio_id: uuid.UUID,
        name: str,
        code: str,
        description: str,
        manager_user_id: uuid.UUID | None,
        priority: ProgramPriority,
        planned_budget: Decimal,
        currency: str,
        start_date: date | None,
        end_date: date | None,
    ) -> Program:
        """Create a program under a portfolio, enforcing all invariants."""
        self._require_portfolio(portfolio_id)
        if self.programs.get_by_code(self._org_id, code):
            raise ConflictError(
                f"A program with code '{code}' already exists.",
                details={"code": code},
            )
        self._require_manager_in_org(manager_user_id)
        self._validate_date_range(start_date, end_date)

        program = Program(
            organization_id=self._org_id,
            portfolio_id=portfolio_id,
            name=name,
            code=code,
            description=description,
            manager_user_id=manager_user_id,
            status=ProgramStatus.PROPOSED,
            priority=priority,
            planned_budget=planned_budget,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
            created_by=self._actor_id,
        )
        self.programs.add(program)
        self._uow.record_audit(
            "Program",
            program.id,
            "create",
            f"Created program '{name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return program

    def get_program(self, program_id: uuid.UUID) -> Program:
        """Return a single program by id."""
        return self._get_or_404(program_id)

    def search_programs(
        self,
        *,
        query: str | None,
        status: ProgramStatus | None,
        portfolio_id: uuid.UUID | None,
        manager_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Program], int]:
        """Return a filtered page of programs and the total matching count."""
        items = list(
            self.programs.search(
                self._org_id,
                query=query,
                status=status,
                portfolio_id=portfolio_id,
                manager_user_id=manager_user_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.programs.count(
            self._org_id,
            query=query,
            status=status,
            portfolio_id=portfolio_id,
            manager_user_id=manager_user_id,
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_program(
        self,
        program_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
        manager_user_id: uuid.UUID | None,
        status: ProgramStatus | None,
        priority: ProgramPriority | None,
        health: ProgramHealth | None,
        planned_budget: Decimal | None,
        currency: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> Program:
        """Apply a partial update, validating status transitions and dates."""
        program = self._get_or_404(program_id)

        if status is not None:
            validate_status_transition(_ALLOWED_TRANSITIONS, program.status, status)
            program.status = status
        if manager_user_id is not None:
            self._require_manager_in_org(manager_user_id)
            program.manager_user_id = manager_user_id
        if name is not None:
            program.name = name
        if description is not None:
            program.description = description
        if priority is not None:
            program.priority = priority
        if health is not None:
            program.health = health
        if planned_budget is not None:
            program.planned_budget = planned_budget
        if currency is not None:
            program.currency = currency
        if start_date is not None:
            program.start_date = start_date
        if end_date is not None:
            program.end_date = end_date

        self._validate_date_range(program.start_date, program.end_date)

        program.modified_by = self._actor_id
        self.programs.update(program)
        self._uow.record_audit(
            "Program",
            program.id,
            "update",
            f"Updated program '{program.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return program

    def delete_program(self, program_id: uuid.UUID) -> None:
        """Soft-delete a program, blocking if it still contains projects."""
        program = self._get_or_404(program_id)
        if self.projects.has_for_program(self._org_id, program_id):
            raise ConflictError(
                "Cannot delete a program that still contains projects.",
                code="program_in_use",
            )
        self.programs.soft_delete(program, actor_id=self._actor_id)
        self._uow.record_audit(
            "Program",
            program.id,
            "delete",
            f"Deleted program '{program.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
