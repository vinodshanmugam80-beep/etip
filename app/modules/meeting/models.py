"""ORM models for the Meeting Management module.

A :class:`Meeting` is a scheduled gathering on a project — with an agenda, a
schedule, minutes, and a status lifecycle. :class:`MeetingAttendee` records who
was invited, their RSVP response, and whether they attended. Action items agreed
in a meeting are created as RAID actions (see the service) tagged with the
meeting they came from, so meeting outcomes are tracked in the RAID log.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class MeetingType(enum.StrEnum):
    """Kind of meeting."""

    STANDUP = "standup"
    PLANNING = "planning"
    REVIEW = "review"
    RETROSPECTIVE = "retrospective"
    STATUS = "status"
    STAKEHOLDER = "stakeholder"
    KICKOFF = "kickoff"
    OTHER = "other"


class MeetingStatus(enum.StrEnum):
    """Lifecycle state of a meeting."""

    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AttendeeRole(enum.StrEnum):
    """An attendee's role in a meeting."""

    ORGANIZER = "organizer"
    REQUIRED = "required"
    OPTIONAL = "optional"
    PRESENTER = "presenter"


class AttendeeResponse(enum.StrEnum):
    """An attendee's RSVP response."""

    NO_RESPONSE = "no_response"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TENTATIVE = "tentative"


class Meeting(BaseEntity, TenantMixin):
    """A scheduled meeting on a project."""

    __tablename__ = "meetings"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_meeting_number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organizer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    meeting_type: Mapped[MeetingType] = mapped_column(
        enum_column(MeetingType), default=MeetingType.STATUS, index=True
    )
    status: Mapped[MeetingStatus] = mapped_column(
        enum_column(MeetingStatus), default=MeetingStatus.SCHEDULED, index=True
    )

    location: Mapped[str] = mapped_column(String(500), default="")
    agenda: Mapped[str] = mapped_column(String(8000), default="")
    minutes: Mapped[str] = mapped_column(String(16000), default="")

    scheduled_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MeetingAttendee(BaseEntity, TenantMixin):
    """A participant invited to a meeting."""

    __tablename__ = "meeting_attendees"
    __table_args__ = (UniqueConstraint("meeting_id", "user_id", name="uq_meeting_attendee"),)

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    role: Mapped[AttendeeRole] = mapped_column(
        enum_column(AttendeeRole), default=AttendeeRole.REQUIRED
    )
    response: Mapped[AttendeeResponse] = mapped_column(
        enum_column(AttendeeResponse), default=AttendeeResponse.NO_RESPONSE
    )
    attended: Mapped[bool] = mapped_column(Boolean, default=False)
