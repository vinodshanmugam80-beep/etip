"""HTTP routes for the Program Management module.

Thin adapters over :class:`ProgramService`. Reads require ``program:read``;
mutations require the corresponding ``program:*`` permission.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import ProgramServiceDep, UowDep, require_permission
from app.modules.program.models import ProgramStatus
from app.modules.program.schemas import (
    MessageResponse,
    PaginatedPrograms,
    ProgramCreateRequest,
    ProgramResponse,
    ProgramUpdateRequest,
)

router = APIRouter(prefix="/programs", tags=["Program Management"])


@router.post(
    "",
    response_model=ProgramResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("program:create"))],
    summary="Create a program",
)
def create_program(
    payload: ProgramCreateRequest, service: ProgramServiceDep, uow: UowDep
) -> ProgramResponse:
    """Create a program within a portfolio."""
    program = service.create_program(
        portfolio_id=payload.portfolio_id,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        manager_user_id=payload.manager_user_id,
        priority=payload.priority,
        planned_budget=payload.planned_budget,
        currency=payload.currency,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    uow.commit()
    return ProgramResponse.model_validate(program)


@router.get(
    "",
    response_model=PaginatedPrograms,
    dependencies=[Depends(require_permission("program:read"))],
    summary="List and search programs",
)
def list_programs(
    service: ProgramServiceDep,
    q: str | None = Query(default=None, description="Search name or code"),
    status_filter: ProgramStatus | None = Query(default=None, alias="status"),
    portfolio_id: uuid.UUID | None = Query(default=None),
    manager_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedPrograms:
    """Return a filtered, paginated page of programs."""
    items, total = service.search_programs(
        query=q,
        status=status_filter,
        portfolio_id=portfolio_id,
        manager_user_id=manager_user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedPrograms(
        items=[ProgramResponse.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{program_id}",
    response_model=ProgramResponse,
    dependencies=[Depends(require_permission("program:read"))],
    summary="Get a program",
)
def get_program(program_id: uuid.UUID, service: ProgramServiceDep) -> ProgramResponse:
    """Return a single program by id."""
    return ProgramResponse.model_validate(service.get_program(program_id))


@router.patch(
    "/{program_id}",
    response_model=ProgramResponse,
    dependencies=[Depends(require_permission("program:update"))],
    summary="Update a program",
)
def update_program(
    program_id: uuid.UUID,
    payload: ProgramUpdateRequest,
    service: ProgramServiceDep,
    uow: UowDep,
) -> ProgramResponse:
    """Apply a partial update, including a validated status transition."""
    program = service.update_program(
        program_id,
        name=payload.name,
        description=payload.description,
        manager_user_id=payload.manager_user_id,
        status=payload.status,
        priority=payload.priority,
        health=payload.health,
        planned_budget=payload.planned_budget,
        currency=payload.currency,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    uow.commit()
    return ProgramResponse.model_validate(program)


@router.delete(
    "/{program_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("program:delete"))],
    summary="Delete a program",
)
def delete_program(
    program_id: uuid.UUID, service: ProgramServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a program."""
    service.delete_program(program_id)
    uow.commit()
    return MessageResponse(detail="Program deleted.")
