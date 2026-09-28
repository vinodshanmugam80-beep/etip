"""Repository for the Program Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.program.models import Program, ProgramStatus
from app.repositories.base import BaseRepository


class ProgramRepository(BaseRepository[Program]):
    """Data access for :class:`Program`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Program)

    def get_by_code(self, organization_id: uuid.UUID, code: str) -> Program | None:
        """Return a program by its per-organization code."""
        stmt = self._base_query(organization_id).where(Program.code == code)
        return self.session.execute(stmt).scalar_one_or_none()

    def has_for_portfolio(self, organization_id: uuid.UUID, portfolio_id: uuid.UUID) -> bool:
        """Return ``True`` if any live program belongs to the portfolio.

        Used by the portfolio-deletion guard to prevent orphaning programs.
        """
        stmt = self._base_query(organization_id).where(Program.portfolio_id == portfolio_id)
        return self.session.execute(stmt.limit(1)).first() is not None

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        query: str | None,
        status: ProgramStatus | None,
        portfolio_id: uuid.UUID | None,
        manager_user_id: uuid.UUID | None,
    ) -> Select[tuple[Program]]:
        """Build the filtered (unpaginated) program query."""
        stmt = self._base_query(organization_id)
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(
                func.lower(Program.name).like(like) | func.lower(Program.code).like(like)
            )
        if status is not None:
            stmt = stmt.where(Program.status == status)
        if portfolio_id is not None:
            stmt = stmt.where(Program.portfolio_id == portfolio_id)
        if manager_user_id is not None:
            stmt = stmt.where(Program.manager_user_id == manager_user_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        status: ProgramStatus | None = None,
        portfolio_id: uuid.UUID | None = None,
        manager_user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Program]:
        """Return a filtered, paginated page of programs."""
        stmt = self._search_stmt(organization_id, query, status, portfolio_id, manager_user_id)
        stmt = stmt.order_by(Program.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        status: ProgramStatus | None = None,
        portfolio_id: uuid.UUID | None = None,
        manager_user_id: uuid.UUID | None = None,
    ) -> int:
        """Return the total number of programs matching the filters."""
        inner = self._search_stmt(
            organization_id, query, status, portfolio_id, manager_user_id
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())
