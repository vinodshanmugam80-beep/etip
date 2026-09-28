"""Repositories for the Meeting Management aggregates."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.meeting.models import (
    Meeting,
    MeetingAttendee,
    MeetingStatus,
    MeetingType,
)
from app.repositories.base import BaseRepository


class MeetingRepository(BaseRepository[Meeting]):
    """Data access for :class:`Meeting`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Meeting)

    def next_number(self, project_id: uuid.UUID) -> int:
        """Return the next running meeting number within a project."""
        stmt = select(func.coalesce(func.max(Meeting.number), 0)).where(
            Meeting.project_id == project_id
        )
        return int(self.session.execute(stmt).scalar_one()) + 1

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        status: MeetingStatus | None,
        meeting_type: MeetingType | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> Select[tuple[Meeting]]:
        """Build the filtered (unpaginated) meeting query."""
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(func.lower(Meeting.title).like(f"%{query.lower()}%"))
        if project_id is not None:
            stmt = stmt.where(Meeting.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Meeting.status == status)
        if meeting_type is not None:
            stmt = stmt.where(Meeting.meeting_type == meeting_type)
        if date_from is not None:
            stmt = stmt.where(Meeting.scheduled_start >= date_from)
        if date_to is not None:
            stmt = stmt.where(Meeting.scheduled_start <= date_to)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: MeetingStatus | None = None,
        meeting_type: MeetingType | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Meeting]:
        """Return a filtered, paginated page of meetings (soonest first)."""
        stmt = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            meeting_type=meeting_type,
            date_from=date_from,
            date_to=date_to,
        )
        stmt = stmt.order_by(Meeting.scheduled_start.asc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        status: MeetingStatus | None = None,
        meeting_type: MeetingType | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        """Return the number of meetings matching the filters."""
        inner = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            status=status,
            meeting_type=meeting_type,
            date_from=date_from,
            date_to=date_to,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live meeting of a project."""
        stmt = self._base_query(organization_id).where(Meeting.project_id == project_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for meeting in rows:
            meeting.soft_delete(actor_id)
        self.session.flush()
        return len(rows)


class MeetingAttendeeRepository(BaseRepository[MeetingAttendee]):
    """Data access for :class:`MeetingAttendee`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, MeetingAttendee)

    def list_for_meeting(
        self, organization_id: uuid.UUID, meeting_id: uuid.UUID
    ) -> Sequence[MeetingAttendee]:
        """Return every live attendee of a meeting."""
        stmt = self._base_query(organization_id).where(MeetingAttendee.meeting_id == meeting_id)
        return self.session.execute(stmt).scalars().all()

    def get_by_meeting_and_user(
        self, organization_id: uuid.UUID, meeting_id: uuid.UUID, user_id: uuid.UUID
    ) -> MeetingAttendee | None:
        """Return a specific attendee row, if present."""
        stmt = self._base_query(organization_id).where(
            MeetingAttendee.meeting_id == meeting_id,
            MeetingAttendee.user_id == user_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def soft_delete_for_meeting(
        self, organization_id: uuid.UUID, meeting_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every attendee of a meeting."""
        stmt = self._base_query(organization_id).where(MeetingAttendee.meeting_id == meeting_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for attendee in rows:
            attendee.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
