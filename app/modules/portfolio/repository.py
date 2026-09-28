"""Repositories for the Portfolio Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.portfolio.models import (
    Portfolio,
    PortfolioObjective,
    PortfolioStatus,
)
from app.repositories.base import BaseRepository


class PortfolioRepository(BaseRepository[Portfolio]):
    """Data access for :class:`Portfolio`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Portfolio)

    def get_by_code(self, organization_id: uuid.UUID, code: str) -> Portfolio | None:
        """Return a portfolio by its per-organization code."""
        stmt = self._base_query(organization_id).where(Portfolio.code == code)
        return self.session.execute(stmt).scalar_one_or_none()

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        query: str | None,
        status: PortfolioStatus | None,
        owner_user_id: uuid.UUID | None,
    ) -> Select[tuple[Portfolio]]:
        """Build the filtered (unpaginated) portfolio query."""
        stmt = self._base_query(organization_id)
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(
                func.lower(Portfolio.name).like(like) | func.lower(Portfolio.code).like(like)
            )
        if status is not None:
            stmt = stmt.where(Portfolio.status == status)
        if owner_user_id is not None:
            stmt = stmt.where(Portfolio.owner_user_id == owner_user_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        status: PortfolioStatus | None = None,
        owner_user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Portfolio]:
        """Return a filtered, paginated page of portfolios."""
        stmt = self._search_stmt(organization_id, query, status, owner_user_id)
        stmt = stmt.order_by(Portfolio.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        status: PortfolioStatus | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> int:
        """Return the total number of portfolios matching the filters."""
        inner = self._search_stmt(organization_id, query, status, owner_user_id).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())


class PortfolioObjectiveRepository(BaseRepository[PortfolioObjective]):
    """Data access for :class:`PortfolioObjective`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, PortfolioObjective)

    def list_for_portfolio(
        self, organization_id: uuid.UUID, portfolio_id: uuid.UUID
    ) -> Sequence[PortfolioObjective]:
        """Return the objectives of a portfolio."""
        stmt = self._base_query(organization_id).where(
            PortfolioObjective.portfolio_id == portfolio_id
        )
        return self.session.execute(stmt).scalars().all()

    def get_in_portfolio(
        self,
        organization_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        objective_id: uuid.UUID,
    ) -> PortfolioObjective | None:
        """Return a specific objective scoped to its portfolio."""
        stmt = self._base_query(organization_id).where(
            PortfolioObjective.portfolio_id == portfolio_id,
            PortfolioObjective.id == objective_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()
