"""Meeting Management service.

Business rules for project meetings. A meeting belongs to a project and gets a
per-project number; its status lifecycle stamps actual start/end times.
Attendees are managed as child records with an RSVP response and an attended
flag. Action items agreed in a meeting are created as **RAID actions** on the
meeting's project, tagged with ``source_meeting_id`` so meeting outcomes are
tracked in the RAID log and traceable back to their meeting.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.base import ensure_aware, utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.meeting.models import (
    AttendeeResponse,
    AttendeeRole,
    Meeting,
    MeetingAttendee,
    MeetingStatus,
    MeetingType,
)
from app.modules.meeting.repository import (
    MeetingAttendeeRepository,
    MeetingRepository,
)
from app.modules.project.models import Project
from app.modules.project.repository import ProjectRepository
from app.modules.raid.models import Action, ActionPriority, ActionStatus
from app.modules.raid.repository import ActionRepository

logger = get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[MeetingStatus, set[MeetingStatus]] = {
    MeetingStatus.SCHEDULED: {
        MeetingStatus.IN_PROGRESS,
        MeetingStatus.COMPLETED,
        MeetingStatus.CANCELLED,
    },
    MeetingStatus.IN_PROGRESS: {
        MeetingStatus.COMPLETED,
        MeetingStatus.CANCELLED,
    },
    MeetingStatus.COMPLETED: set(),
    MeetingStatus.CANCELLED: set(),
}


class MeetingService:
    """Coordinates meeting, attendee and action-item use cases within a tenant."""

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
        self.meetings = MeetingRepository(session)
        self.attendees = MeetingAttendeeRepository(session)
        self.projects = ProjectRepository(session)
        self.users = UserRepository(session)
        self.actions = ActionRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_meeting_or_404(self, meeting_id: uuid.UUID) -> Meeting:
        meeting = self.meetings.get(meeting_id, organization_id=self._org_id)
        if meeting is None:
            raise NotFoundError("Meeting not found.")
        return meeting

    def _get_project_or_404(self, project_id: uuid.UUID) -> Project:
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    def _require_user(self, user_id: uuid.UUID | None, *, label: str) -> None:
        if user_id is None:
            return
        if self.users.get(user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                f"{label} does not belong to this organization.",
                details={"user_id": str(user_id)},
            )

    # ------------------------------------------------------------------
    # Meetings
    # ------------------------------------------------------------------
    def create_meeting(
        self,
        *,
        project_id: uuid.UUID,
        title: str,
        meeting_type: MeetingType,
        location: str,
        agenda: str,
        scheduled_start: datetime,
        scheduled_end: datetime,
        organizer_user_id: uuid.UUID | None,
    ) -> Meeting:
        """Schedule a meeting; the organizer is invited as an accepted attendee."""
        self._get_project_or_404(project_id)
        organizer_id = organizer_user_id or self._actor_id
        self._require_user(organizer_id, label="Organizer")
        meeting = Meeting(
            organization_id=self._org_id,
            project_id=project_id,
            organizer_user_id=organizer_id,
            number=self.meetings.next_number(project_id),
            title=title,
            meeting_type=meeting_type,
            status=MeetingStatus.SCHEDULED,
            location=location,
            agenda=agenda,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            created_by=self._actor_id,
        )
        self.meetings.add(meeting)
        # Invite the organizer as an accepted attendee.
        self.attendees.add(
            MeetingAttendee(
                organization_id=self._org_id,
                meeting_id=meeting.id,
                user_id=organizer_id,
                role=AttendeeRole.ORGANIZER,
                response=AttendeeResponse.ACCEPTED,
                created_by=self._actor_id,
            )
        )
        self._uow.record_audit(
            "Meeting",
            meeting.id,
            "create",
            f"Scheduled meeting '{title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return meeting

    def get_meeting(self, meeting_id: uuid.UUID) -> Meeting:
        """Return a single meeting by id."""
        return self._get_meeting_or_404(meeting_id)

    def search_meetings(
        self,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: MeetingStatus | None,
        meeting_type: MeetingType | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Meeting], int]:
        """Return a filtered page of meetings and the total matching count."""
        items = list(
            self.meetings.search(
                self._org_id,
                query=query,
                project_id=project_id,
                status=status,
                meeting_type=meeting_type,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
            )
        )
        total = self.meetings.count(
            self._org_id,
            query=query,
            project_id=project_id,
            status=status,
            meeting_type=meeting_type,
            date_from=date_from,
            date_to=date_to,
        )
        return items, total

    def update_meeting(
        self,
        meeting_id: uuid.UUID,
        *,
        title: str | None,
        meeting_type: MeetingType | None,
        status: MeetingStatus | None,
        location: str | None,
        agenda: str | None,
        minutes: str | None,
        scheduled_start: datetime | None,
        scheduled_end: datetime | None,
        organizer_user_id: uuid.UUID | None,
    ) -> Meeting:
        """Apply a partial update, managing status and actual-time stamping."""
        meeting = self._get_meeting_or_404(meeting_id)

        if status is not None and status != meeting.status:
            validate_status_transition(_ALLOWED_TRANSITIONS, meeting.status, status)
            now = utcnow()
            if status == MeetingStatus.IN_PROGRESS and meeting.actual_start is None:
                meeting.actual_start = now
            elif status == MeetingStatus.COMPLETED:
                if meeting.actual_start is None:
                    meeting.actual_start = now
                meeting.actual_end = now
            meeting.status = status
        if organizer_user_id is not None:
            self._require_user(organizer_user_id, label="Organizer")
            meeting.organizer_user_id = organizer_user_id

        new_start = scheduled_start if scheduled_start is not None else meeting.scheduled_start
        new_end = scheduled_end if scheduled_end is not None else meeting.scheduled_end
        if ensure_aware(new_end) <= ensure_aware(new_start):
            raise ValidationError(
                "scheduled_end must be after scheduled_start.",
                code="invalid_schedule",
            )
        for attr, value in (
            ("title", title),
            ("meeting_type", meeting_type),
            ("location", location),
            ("agenda", agenda),
            ("minutes", minutes),
            ("scheduled_start", scheduled_start),
            ("scheduled_end", scheduled_end),
        ):
            if value is not None:
                setattr(meeting, attr, value)

        meeting.modified_by = self._actor_id
        self.meetings.update(meeting)
        self._uow.record_audit(
            "Meeting",
            meeting.id,
            "update",
            f"Updated meeting '{meeting.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return meeting

    def delete_meeting(self, meeting_id: uuid.UUID) -> None:
        """Soft-delete a meeting and its attendees."""
        meeting = self._get_meeting_or_404(meeting_id)
        self.attendees.soft_delete_for_meeting(self._org_id, meeting_id, actor_id=self._actor_id)
        self.meetings.soft_delete(meeting, actor_id=self._actor_id)
        self._uow.record_audit(
            "Meeting",
            meeting.id,
            "delete",
            f"Deleted meeting '{meeting.title}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Attendees
    # ------------------------------------------------------------------
    def _get_attendee_or_404(
        self, meeting_id: uuid.UUID, attendee_id: uuid.UUID
    ) -> MeetingAttendee:
        attendee = self.attendees.get(attendee_id, organization_id=self._org_id)
        if attendee is None or attendee.meeting_id != meeting_id:
            raise NotFoundError("Attendee not found.")
        return attendee

    def add_attendee(
        self, meeting_id: uuid.UUID, *, user_id: uuid.UUID, role: AttendeeRole
    ) -> MeetingAttendee:
        """Invite a user to a meeting."""
        self._get_meeting_or_404(meeting_id)
        self._require_user(user_id, label="Attendee")
        if self.attendees.get_by_meeting_and_user(self._org_id, meeting_id, user_id):
            raise ConflictError(
                "User is already an attendee of this meeting.",
                code="duplicate_attendee",
            )
        attendee = MeetingAttendee(
            organization_id=self._org_id,
            meeting_id=meeting_id,
            user_id=user_id,
            role=role,
            response=AttendeeResponse.NO_RESPONSE,
            created_by=self._actor_id,
        )
        self.attendees.add(attendee)
        self._uow.record_audit(
            "MeetingAttendee",
            attendee.id,
            "create",
            "Added meeting attendee",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return attendee

    def list_attendees(self, meeting_id: uuid.UUID) -> list[MeetingAttendee]:
        """Return every attendee of a meeting."""
        self._get_meeting_or_404(meeting_id)
        return list(self.attendees.list_for_meeting(self._org_id, meeting_id))

    def update_attendee(
        self,
        meeting_id: uuid.UUID,
        attendee_id: uuid.UUID,
        *,
        role: AttendeeRole | None,
        response: AttendeeResponse | None,
        attended: bool | None,
    ) -> MeetingAttendee:
        """Update an attendee's role, RSVP response, or attendance."""
        attendee = self._get_attendee_or_404(meeting_id, attendee_id)
        if role is not None:
            attendee.role = role
        if response is not None:
            attendee.response = response
        if attended is not None:
            attendee.attended = attended
        attendee.modified_by = self._actor_id
        self.attendees.update(attendee)
        return attendee

    def remove_attendee(self, meeting_id: uuid.UUID, attendee_id: uuid.UUID) -> None:
        """Remove an attendee from a meeting."""
        attendee = self._get_attendee_or_404(meeting_id, attendee_id)
        self.attendees.soft_delete(attendee, actor_id=self._actor_id)

    # ------------------------------------------------------------------
    # Action items (RAID actions raised from the meeting)
    # ------------------------------------------------------------------
    def create_action_item(
        self,
        meeting_id: uuid.UUID,
        *,
        title: str,
        description: str,
        priority: ActionPriority,
        owner_user_id: uuid.UUID | None,
        due_date: date | None,
    ) -> Action:
        """Raise a RAID action on the meeting's project, tagged to the meeting."""
        meeting = self._get_meeting_or_404(meeting_id)
        self._require_user(owner_user_id, label="Owner")
        action = Action(
            organization_id=self._org_id,
            project_id=meeting.project_id,
            number=self.actions.next_number(meeting.project_id),
            title=title,
            description=description,
            status=ActionStatus.OPEN,
            priority=priority,
            owner_user_id=owner_user_id,
            due_date=due_date,
            source_meeting_id=meeting_id,
            created_by=self._actor_id,
        )
        self.actions.add(action)
        self._uow.record_audit(
            "Action",
            action.id,
            "create",
            f"Raised action '{title}' from meeting",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return action

    def list_action_items(self, meeting_id: uuid.UUID) -> list[Action]:
        """Return the RAID actions raised from a meeting."""
        self._get_meeting_or_404(meeting_id)
        return list(self.actions.list_by_meeting(self._org_id, meeting_id))
