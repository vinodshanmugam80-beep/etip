"""Pydantic v2 schemas for the Notifications module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.notification.models import (
    NotificationEntityType,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)


class NotificationCreateRequest(BaseModel):
    """Payload to send a notification to a user (privileged)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "00000000-0000-0000-0000-000000000000",
                "notification_type": "assignment",
                "priority": "normal",
                "title": "You were assigned a task",
                "body": "Task ETIP-42 'Wire up billing' is now yours.",
                "entity_type": "task",
                "entity_id": "11111111-1111-1111-1111-111111111111",
                "link": "/projects/etip/tasks/42",
            }
        }
    )

    user_id: uuid.UUID
    notification_type: NotificationType
    priority: NotificationPriority = NotificationPriority.NORMAL
    title: str = Field(min_length=2, max_length=300)
    body: str = Field(default="", max_length=4000)
    entity_type: NotificationEntityType | None = None
    entity_id: uuid.UUID | None = None
    link: str = Field(default="", max_length=1024)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Title must be at least 2 characters.")
        return cleaned


class NotificationUpdateRequest(BaseModel):
    """Change the state of one of the caller's own notifications."""

    status: NotificationStatus


class NotificationResponse(BaseModel):
    """Notification representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    notification_type: NotificationType
    priority: NotificationPriority
    status: NotificationStatus
    title: str
    body: str
    link: str
    entity_type: NotificationEntityType | None
    entity_id: uuid.UUID | None
    read_date: datetime | None
    created_date: datetime
    version: int


class PaginatedNotifications(BaseModel):
    """A page of notifications with total-count metadata."""

    items: list[NotificationResponse]
    total: int
    limit: int
    offset: int


class NotificationSendResult(BaseModel):
    """Outcome of a send: created unless muted by the recipient."""

    created: bool
    notification: NotificationResponse | None = None
    detail: str


class UnreadCountResponse(BaseModel):
    """The caller's unread notification count."""

    unread: int


class PreferenceResponse(BaseModel):
    """A user's preference for one notification type."""

    notification_type: NotificationType
    muted: bool


class PreferenceSetRequest(BaseModel):
    """Set the muted flag for a notification type."""

    muted: bool


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
