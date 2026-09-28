"""HTTP routes for the Meeting Management module.

Thin adapters over :class:`MeetingService`. Reads require ``meeting:read``;
create/edit and attendee/action-item management require ``meeting:create`` /
``meeting:update``; delete requires ``meeting:delete``. Action items are RAID
actions and are returned using the RAID action schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import MeetingServiceDep, UowDep, require_permission
from app.modules.meeting.models import MeetingStatus, MeetingType
from app.modules.meeting.schemas import (
    ActionItemCreateRequest,
    AttendeeAddRequest,
    AttendeeResponseModel,
    AttendeeUpdateRequest,
    MeetingCreateRequest,
    MeetingResponse,
    MeetingUpdateRequest,
    MessageResponse,
    PaginatedMeetings,
)
from app.modules.raid.schemas import ActionResponse

router = APIRouter(tags=["Meeting Management"])


# --- Meetings --------------------------------------------------------------
@router.post(
    "/meetings",
    response_model=MeetingResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("meeting:create"))],
    summary="Schedule a meeting",
)
def create_meeting(
    payload: MeetingCreateRequest, service: MeetingServiceDep, uow: UowDep
) -> MeetingResponse:
    """Schedule a meeting on a project."""
    meeting = service.create_meeting(
        project_id=payload.project_id,
        title=payload.title,
        meeting_type=payload.meeting_type,
        location=payload.location,
        agenda=payload.agenda,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        organizer_user_id=payload.organizer_user_id,
    )
    uow.commit()
    return MeetingResponse.model_validate(meeting)


@router.get(
    "/meetings",
    response_model=PaginatedMeetings,
    dependencies=[Depends(require_permission("meeting:read"))],
    summary="List and search meetings",
)
def list_meetings(
    service: MeetingServiceDep,
    q: str | None = Query(default=None, description="Search title"),
    project_id: uuid.UUID | None = Query(default=None),
    status_filter: MeetingStatus | None = Query(default=None, alias="status"),
    meeting_type: MeetingType | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedMeetings:
    """Return a filtered, paginated page of meetings (soonest first)."""
    items, total = service.search_meetings(
        query=q,
        project_id=project_id,
        status=status_filter,
        meeting_type=meeting_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return PaginatedMeetings(
        items=[MeetingResponse.model_validate(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/meetings/{meeting_id}",
    response_model=MeetingResponse,
    dependencies=[Depends(require_permission("meeting:read"))],
    summary="Get a meeting",
)
def get_meeting(meeting_id: uuid.UUID, service: MeetingServiceDep) -> MeetingResponse:
    """Return a single meeting by id."""
    return MeetingResponse.model_validate(service.get_meeting(meeting_id))


@router.patch(
    "/meetings/{meeting_id}",
    response_model=MeetingResponse,
    dependencies=[Depends(require_permission("meeting:update"))],
    summary="Update a meeting",
)
def update_meeting(
    meeting_id: uuid.UUID,
    payload: MeetingUpdateRequest,
    service: MeetingServiceDep,
    uow: UowDep,
) -> MeetingResponse:
    """Apply a partial update, including a validated status transition."""
    meeting = service.update_meeting(
        meeting_id,
        title=payload.title,
        meeting_type=payload.meeting_type,
        status=payload.status,
        location=payload.location,
        agenda=payload.agenda,
        minutes=payload.minutes,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        organizer_user_id=payload.organizer_user_id,
    )
    uow.commit()
    return MeetingResponse.model_validate(meeting)


@router.delete(
    "/meetings/{meeting_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("meeting:delete"))],
    summary="Delete a meeting",
)
def delete_meeting(
    meeting_id: uuid.UUID, service: MeetingServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a meeting and its attendees."""
    service.delete_meeting(meeting_id)
    uow.commit()
    return MessageResponse(detail="Meeting deleted.")


# --- Attendees -------------------------------------------------------------
@router.post(
    "/meetings/{meeting_id}/attendees",
    response_model=AttendeeResponseModel,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("meeting:update"))],
    summary="Invite an attendee",
)
def add_attendee(
    meeting_id: uuid.UUID,
    payload: AttendeeAddRequest,
    service: MeetingServiceDep,
    uow: UowDep,
) -> AttendeeResponseModel:
    """Invite a user to a meeting."""
    attendee = service.add_attendee(meeting_id, user_id=payload.user_id, role=payload.role)
    uow.commit()
    return AttendeeResponseModel.model_validate(attendee)


@router.get(
    "/meetings/{meeting_id}/attendees",
    response_model=list[AttendeeResponseModel],
    dependencies=[Depends(require_permission("meeting:read"))],
    summary="List a meeting's attendees",
)
def list_attendees(
    meeting_id: uuid.UUID, service: MeetingServiceDep
) -> list[AttendeeResponseModel]:
    """Return every attendee of a meeting."""
    return [AttendeeResponseModel.model_validate(a) for a in service.list_attendees(meeting_id)]


@router.patch(
    "/meetings/{meeting_id}/attendees/{attendee_id}",
    response_model=AttendeeResponseModel,
    dependencies=[Depends(require_permission("meeting:update"))],
    summary="Update an attendee",
)
def update_attendee(
    meeting_id: uuid.UUID,
    attendee_id: uuid.UUID,
    payload: AttendeeUpdateRequest,
    service: MeetingServiceDep,
    uow: UowDep,
) -> AttendeeResponseModel:
    """Update an attendee's role, RSVP response, or attendance."""
    attendee = service.update_attendee(
        meeting_id,
        attendee_id,
        role=payload.role,
        response=payload.response,
        attended=payload.attended,
    )
    uow.commit()
    return AttendeeResponseModel.model_validate(attendee)


@router.delete(
    "/meetings/{meeting_id}/attendees/{attendee_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("meeting:update"))],
    summary="Remove an attendee",
)
def remove_attendee(
    meeting_id: uuid.UUID,
    attendee_id: uuid.UUID,
    service: MeetingServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Remove an attendee from a meeting."""
    service.remove_attendee(meeting_id, attendee_id)
    uow.commit()
    return MessageResponse(detail="Attendee removed.")


# --- Action items (RAID actions) -------------------------------------------
@router.post(
    "/meetings/{meeting_id}/action-items",
    response_model=ActionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("meeting:update"))],
    summary="Raise an action item from a meeting",
)
def create_action_item(
    meeting_id: uuid.UUID,
    payload: ActionItemCreateRequest,
    service: MeetingServiceDep,
    uow: UowDep,
) -> ActionResponse:
    """Raise a RAID action on the meeting's project, tagged to the meeting."""
    action = service.create_action_item(
        meeting_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        owner_user_id=payload.owner_user_id,
        due_date=payload.due_date,
    )
    uow.commit()
    return ActionResponse.model_validate(action)


@router.get(
    "/meetings/{meeting_id}/action-items",
    response_model=list[ActionResponse],
    dependencies=[Depends(require_permission("meeting:read"))],
    summary="List a meeting's action items",
)
def list_action_items(meeting_id: uuid.UUID, service: MeetingServiceDep) -> list[ActionResponse]:
    """Return the RAID actions raised from a meeting."""
    return [ActionResponse.model_validate(a) for a in service.list_action_items(meeting_id)]
