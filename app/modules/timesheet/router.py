"""HTTP routes for the Timesheet Management module.

Thin adapters over :class:`TimesheetService`. Reads require ``timesheet:read``;
logging/editing require ``timesheet:create`` / ``timesheet:update``; **approving
and rejecting require ``timesheet:approve``**; delete requires
``timesheet:delete``.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import TimesheetServiceDep, UowDep, require_permission
from app.modules.timesheet.models import ActivityType, TimeEntryStatus
from app.modules.timesheet.schemas import (
    MessageResponse,
    PaginatedTimeEntries,
    TimeEntryCreateRequest,
    TimeEntryDecisionRequest,
    TimeEntryResponse,
    TimeEntryUpdateRequest,
    TimesheetSummaryResponse,
)

router = APIRouter(tags=["Timesheet Management"])


@router.post(
    "/timesheets",
    response_model=TimeEntryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("timesheet:create"))],
    summary="Log a time entry",
)
def create_entry(
    payload: TimeEntryCreateRequest, service: TimesheetServiceDep, uow: UowDep
) -> TimeEntryResponse:
    """Log a draft time entry for the calling user."""
    entry = service.create_entry(
        project_id=payload.project_id,
        task_id=payload.task_id,
        work_date=payload.work_date,
        hours=payload.hours,
        billable=payload.billable,
        activity_type=payload.activity_type,
        description=payload.description,
    )
    uow.commit()
    return TimeEntryResponse.model_validate(entry)


@router.get(
    "/timesheets/summary",
    response_model=TimesheetSummaryResponse,
    dependencies=[Depends(require_permission("timesheet:read"))],
    summary="Summarize logged hours",
)
def summary(
    service: TimesheetServiceDep,
    project_id: uuid.UUID | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> TimesheetSummaryResponse:
    """Return aggregated hours over a filtered set of time entries."""
    return service.get_summary(
        project_id=project_id,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/timesheets",
    response_model=PaginatedTimeEntries,
    dependencies=[Depends(require_permission("timesheet:read"))],
    summary="List and search time entries",
)
def list_entries(
    service: TimesheetServiceDep,
    project_id: uuid.UUID | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    status_filter: TimeEntryStatus | None = Query(default=None, alias="status"),
    billable: bool | None = Query(default=None),
    activity_type: ActivityType | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedTimeEntries:
    """Return a filtered, paginated page of time entries (newest first)."""
    items, total = service.search_entries(
        project_id=project_id,
        task_id=task_id,
        user_id=user_id,
        status=status_filter,
        billable=billable,
        activity_type=activity_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return PaginatedTimeEntries(
        items=[TimeEntryResponse.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/timesheets/{entry_id}",
    response_model=TimeEntryResponse,
    dependencies=[Depends(require_permission("timesheet:read"))],
    summary="Get a time entry",
)
def get_entry(entry_id: uuid.UUID, service: TimesheetServiceDep) -> TimeEntryResponse:
    """Return a single time entry by id."""
    return TimeEntryResponse.model_validate(service.get_entry(entry_id))


@router.patch(
    "/timesheets/{entry_id}",
    response_model=TimeEntryResponse,
    dependencies=[Depends(require_permission("timesheet:update"))],
    summary="Update a time entry",
)
def update_entry(
    entry_id: uuid.UUID,
    payload: TimeEntryUpdateRequest,
    service: TimesheetServiceDep,
    uow: UowDep,
) -> TimeEntryResponse:
    """Edit a draft/rejected entry and move between draft and submitted."""
    entry = service.update_entry(
        entry_id,
        task_id=payload.task_id,
        work_date=payload.work_date,
        hours=payload.hours,
        billable=payload.billable,
        activity_type=payload.activity_type,
        description=payload.description,
        status=payload.status,
    )
    uow.commit()
    return TimeEntryResponse.model_validate(entry)


@router.post(
    "/timesheets/{entry_id}/approve",
    response_model=TimeEntryResponse,
    dependencies=[Depends(require_permission("timesheet:approve"))],
    summary="Approve a time entry",
)
def approve_entry(
    entry_id: uuid.UUID,
    payload: TimeEntryDecisionRequest,
    service: TimesheetServiceDep,
    uow: UowDep,
) -> TimeEntryResponse:
    """Approve a submitted time entry (requires timesheet:approve)."""
    entry = service.approve(entry_id, decision_notes=payload.decision_notes)
    uow.commit()
    return TimeEntryResponse.model_validate(entry)


@router.post(
    "/timesheets/{entry_id}/reject",
    response_model=TimeEntryResponse,
    dependencies=[Depends(require_permission("timesheet:approve"))],
    summary="Reject a time entry",
)
def reject_entry(
    entry_id: uuid.UUID,
    payload: TimeEntryDecisionRequest,
    service: TimesheetServiceDep,
    uow: UowDep,
) -> TimeEntryResponse:
    """Reject a submitted time entry (requires timesheet:approve)."""
    entry = service.reject(entry_id, decision_notes=payload.decision_notes)
    uow.commit()
    return TimeEntryResponse.model_validate(entry)


@router.delete(
    "/timesheets/{entry_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("timesheet:delete"))],
    summary="Delete a time entry",
)
def delete_entry(entry_id: uuid.UUID, service: TimesheetServiceDep, uow: UowDep) -> MessageResponse:
    """Soft-delete a time entry."""
    service.delete_entry(entry_id)
    uow.commit()
    return MessageResponse(detail="Time entry deleted.")
