"""HTTP routes for the Financial Management module.

Thin adapters over :class:`FinanceService`. Reads require ``finance:read``;
mutations require the corresponding ``finance:*`` permission. The per-project
summary lives under the projects path for discoverability.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import FinanceServiceDep, UowDep, require_permission
from app.modules.finance.models import CostCategory, FinancialEntryType
from app.modules.finance.schemas import (
    FinancialEntryCreateRequest,
    FinancialEntryResponse,
    FinancialEntryUpdateRequest,
    FinancialSummaryResponse,
    MessageResponse,
    PaginatedFinancialEntries,
)

router = APIRouter(tags=["Financial Management"])


@router.post(
    "/financial-entries",
    response_model=FinancialEntryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("finance:create"))],
    summary="Add a financial entry",
)
def create_entry(
    payload: FinancialEntryCreateRequest, service: FinanceServiceDep, uow: UowDep
) -> FinancialEntryResponse:
    """Add a budget, forecast, or actual line to a project's ledger."""
    entry = service.create_entry(
        project_id=payload.project_id,
        entry_type=payload.entry_type,
        category=payload.category,
        amount=payload.amount,
        currency=payload.currency,
        entry_date=payload.entry_date,
        description=payload.description,
        vendor=payload.vendor,
    )
    uow.commit()
    return FinancialEntryResponse.model_validate(entry)


@router.get(
    "/financial-entries",
    response_model=PaginatedFinancialEntries,
    dependencies=[Depends(require_permission("finance:read"))],
    summary="List and filter financial entries",
)
def list_entries(
    service: FinanceServiceDep,
    project_id: uuid.UUID | None = Query(default=None),
    entry_type: FinancialEntryType | None = Query(default=None),
    category: CostCategory | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedFinancialEntries:
    """Return a filtered, paginated page of financial entries."""
    items, total = service.search_entries(
        project_id=project_id,
        entry_type=entry_type,
        category=category,
        limit=limit,
        offset=offset,
    )
    return PaginatedFinancialEntries(
        items=[FinancialEntryResponse.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/financial-entries/{entry_id}",
    response_model=FinancialEntryResponse,
    dependencies=[Depends(require_permission("finance:read"))],
    summary="Get a financial entry",
)
def get_entry(entry_id: uuid.UUID, service: FinanceServiceDep) -> FinancialEntryResponse:
    """Return a single financial entry by id."""
    return FinancialEntryResponse.model_validate(service.get_entry(entry_id))


@router.patch(
    "/financial-entries/{entry_id}",
    response_model=FinancialEntryResponse,
    dependencies=[Depends(require_permission("finance:update"))],
    summary="Update a financial entry",
)
def update_entry(
    entry_id: uuid.UUID,
    payload: FinancialEntryUpdateRequest,
    service: FinanceServiceDep,
    uow: UowDep,
) -> FinancialEntryResponse:
    """Apply a partial update and refresh the project rollups."""
    entry = service.update_entry(
        entry_id,
        entry_type=payload.entry_type,
        category=payload.category,
        amount=payload.amount,
        entry_date=payload.entry_date,
        description=payload.description,
        vendor=payload.vendor,
    )
    uow.commit()
    return FinancialEntryResponse.model_validate(entry)


@router.delete(
    "/financial-entries/{entry_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("finance:delete"))],
    summary="Delete a financial entry",
)
def delete_entry(entry_id: uuid.UUID, service: FinanceServiceDep, uow: UowDep) -> MessageResponse:
    """Soft-delete a financial entry and refresh the project rollups."""
    service.delete_entry(entry_id)
    uow.commit()
    return MessageResponse(detail="Financial entry deleted.")


@router.get(
    "/projects/{project_id}/financial-summary",
    response_model=FinancialSummaryResponse,
    dependencies=[Depends(require_permission("finance:read"))],
    summary="Get a project's financial summary",
)
def get_summary(project_id: uuid.UUID, service: FinanceServiceDep) -> FinancialSummaryResponse:
    """Return the aggregated financial position of a project."""
    return service.get_summary(project_id)
