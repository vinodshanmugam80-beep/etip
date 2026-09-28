"""Pydantic v2 schemas for the Meeting Management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.meeting.models import (
    AttendeeResponse,
    AttendeeRole,
    MeetingStatus,
    MeetingType,
)
from app.modules.raid.models import ActionPriority


class MeetingCreateRequest(BaseModel):
    """Payload to schedule a meeting."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "00000000-0000-0000-0000-000000000000",
                "title": "Sprint 12 review",
                "meeting_type": "review",
                "location": "https://meet.example.com/abc",
                "agenda": "Demo, metrics, next-sprint scope",
                "scheduled_start": "2026-03-10T15:00:00Z",
                "scheduled_end": "2026-03-10T16:00:00Z",
                "organizer_user_id": None,
            }
        }
    )

    project_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    meeting_type: MeetingType = MeetingType.STATUS
    location: str = Field(default="", max_length=500)
    agenda: str = Field(default="", max_length=8000)
    scheduled_start: datetime
    scheduled_end: datetime
    organizer_user_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Title must be at least 2 characters.")
        return cleaned

    @model_validator(mode="after")
    def _end_after_start(self) -> MeetingCreateRequest:
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end must be after scheduled_start.")
        return self


class MeetingUpdateRequest(BaseModel):
    """Partial update for a meeting; unset fields are left unchanged."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    meeting_type: MeetingType | None = None
    status: MeetingStatus | None = None
    location: str | None = Field(default=None, max_length=500)
    agenda: str | None = Field(default=None, max_length=8000)
    minutes: str | None = Field(default=None, max_length=16000)
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    organizer_user_id: uuid.UUID | None = None


class MeetingResponse(BaseModel):
    """Meeting representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    organizer_user_id: uuid.UUID | None
    number: int
    title: str
    meeting_type: MeetingType
    status: MeetingStatus
    location: str
    agenda: str
    minutes: str
    scheduled_start: datetime
    scheduled_end: datetime
    actual_start: datetime | None
    actual_end: datetime | None
    created_date: datetime
    version: int


class PaginatedMeetings(BaseModel):
    """A page of meetings with total-count metadata."""

    items: list[MeetingResponse]
    total: int
    limit: int
    offset: int


class AttendeeAddRequest(BaseModel):
    """Payload to invite an attendee."""

    user_id: uuid.UUID
    role: AttendeeRole = AttendeeRole.REQUIRED


class AttendeeUpdateRequest(BaseModel):
    """Partial update for an attendee (RSVP, attendance, role)."""

    role: AttendeeRole | None = None
    response: AttendeeResponse | None = None
    attended: bool | None = None


class AttendeeResponseModel(BaseModel):
    """Attendee representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meeting_id: uuid.UUID
    user_id: uuid.UUID
    role: AttendeeRole
    response: AttendeeResponse
    attended: bool


class ActionItemCreateRequest(BaseModel):
    """Payload to raise an action item from a meeting."""

    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=4000)
    priority: ActionPriority = ActionPriority.MEDIUM
    owner_user_id: uuid.UUID | None = None
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Title must be at least 2 characters.")
        return cleaned


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
