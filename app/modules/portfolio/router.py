"""HTTP routes for the Portfolio Management module.

Thin adapters over :class:`PortfolioService`. Reads require ``portfolio:read``;
mutations require the corresponding ``portfolio:*`` permission.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import PortfolioServiceDep, UowDep, require_permission
from app.modules.portfolio.models import PortfolioStatus
from app.modules.portfolio.schemas import (
    MessageResponse,
    PaginatedPortfolios,
    PortfolioCreateRequest,
    PortfolioObjectiveCreateRequest,
    PortfolioObjectiveResponse,
    PortfolioResponse,
    PortfolioUpdateRequest,
)

router = APIRouter(prefix="/portfolios", tags=["Portfolio Management"])


@router.post(
    "",
    response_model=PortfolioResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("portfolio:create"))],
    summary="Create a portfolio",
)
def create_portfolio(
    payload: PortfolioCreateRequest, service: PortfolioServiceDep, uow: UowDep
) -> PortfolioResponse:
    """Create a portfolio within the caller's organization."""
    portfolio = service.create_portfolio(
        name=payload.name,
        code=payload.code,
        description=payload.description,
        owner_user_id=payload.owner_user_id,
        priority=payload.priority,
        planned_budget=payload.planned_budget,
        currency=payload.currency,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    uow.commit()
    return PortfolioResponse.model_validate(portfolio)


@router.get(
    "",
    response_model=PaginatedPortfolios,
    dependencies=[Depends(require_permission("portfolio:read"))],
    summary="List and search portfolios",
)
def list_portfolios(
    service: PortfolioServiceDep,
    q: str | None = Query(default=None, description="Search name or code"),
    status_filter: PortfolioStatus | None = Query(default=None, alias="status"),
    owner_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedPortfolios:
    """Return a filtered, paginated page of portfolios."""
    items, total = service.search_portfolios(
        query=q,
        status=status_filter,
        owner_user_id=owner_user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedPortfolios(
        items=[PortfolioResponse.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{portfolio_id}",
    response_model=PortfolioResponse,
    dependencies=[Depends(require_permission("portfolio:read"))],
    summary="Get a portfolio",
)
def get_portfolio(portfolio_id: uuid.UUID, service: PortfolioServiceDep) -> PortfolioResponse:
    """Return a single portfolio by id."""
    return PortfolioResponse.model_validate(service.get_portfolio(portfolio_id))


@router.patch(
    "/{portfolio_id}",
    response_model=PortfolioResponse,
    dependencies=[Depends(require_permission("portfolio:update"))],
    summary="Update a portfolio",
)
def update_portfolio(
    portfolio_id: uuid.UUID,
    payload: PortfolioUpdateRequest,
    service: PortfolioServiceDep,
    uow: UowDep,
) -> PortfolioResponse:
    """Apply a partial update, including a validated status transition."""
    portfolio = service.update_portfolio(
        portfolio_id,
        name=payload.name,
        description=payload.description,
        owner_user_id=payload.owner_user_id,
        status=payload.status,
        priority=payload.priority,
        health=payload.health,
        planned_budget=payload.planned_budget,
        currency=payload.currency,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    uow.commit()
    return PortfolioResponse.model_validate(portfolio)


@router.delete(
    "/{portfolio_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("portfolio:delete"))],
    summary="Delete a portfolio",
)
def delete_portfolio(
    portfolio_id: uuid.UUID, service: PortfolioServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a portfolio and its objectives."""
    service.delete_portfolio(portfolio_id)
    uow.commit()
    return MessageResponse(detail="Portfolio deleted.")


# --- Objectives ------------------------------------------------------------
@router.post(
    "/{portfolio_id}/objectives",
    response_model=PortfolioObjectiveResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("portfolio:update"))],
    summary="Add a strategic objective",
)
def add_objective(
    portfolio_id: uuid.UUID,
    payload: PortfolioObjectiveCreateRequest,
    service: PortfolioServiceDep,
    uow: UowDep,
) -> PortfolioObjectiveResponse:
    """Add a strategic objective to a portfolio."""
    objective = service.add_objective(
        portfolio_id,
        title=payload.title,
        description=payload.description,
        weight=payload.weight,
    )
    uow.commit()
    return PortfolioObjectiveResponse.model_validate(objective)


@router.get(
    "/{portfolio_id}/objectives",
    response_model=list[PortfolioObjectiveResponse],
    dependencies=[Depends(require_permission("portfolio:read"))],
    summary="List strategic objectives",
)
def list_objectives(
    portfolio_id: uuid.UUID, service: PortfolioServiceDep
) -> list[PortfolioObjectiveResponse]:
    """Return the strategic objectives of a portfolio."""
    objectives = service.list_objectives(portfolio_id)
    return [PortfolioObjectiveResponse.model_validate(o) for o in objectives]


@router.delete(
    "/{portfolio_id}/objectives/{objective_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("portfolio:update"))],
    summary="Remove a strategic objective",
)
def remove_objective(
    portfolio_id: uuid.UUID,
    objective_id: uuid.UUID,
    service: PortfolioServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Remove a strategic objective from a portfolio."""
    service.remove_objective(portfolio_id, objective_id)
    uow.commit()
    return MessageResponse(detail="Objective removed.")
