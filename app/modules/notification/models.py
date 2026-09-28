"""ORM models for the Notifications module.

A :class:`Notification` is an in-app message addressed to a single user, with an
unread/read/archived state, a type and priority, an optional polymorphic pointer
back to the entity that triggered it, and an optional deep link. Notifications
are strictly personal — the service scopes every read and write to the recipient.

A :class:`NotificationPreference` lets a user mute a notification type; the
service skips creating notifications of a muted type for that user.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class NotificationType(enum.StrEnum):
    """The kind of event a notification represents."""

    ASSIGNMENT = "assignment"
    MENTION = "mention"
    STATUS_CHANGE = "status_change"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_DECISION = "approval_decision"
    DUE_SOON = "due_soon"
    COMMENT = "comment"
    MEETING_INVITE = "meeting_invite"
    SYSTEM = "system"
    OTHER = "other"


class NotificationPriority(enum.StrEnum):
    """Relative importance of a notification."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class NotificationStatus(enum.StrEnum):
    """Delivery/read state of a notification."""

    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"


class NotificationEntityType(enum.StrEnum):
    """The kind of entity a notification points back at."""

    PROJECT = "project"
    TASK = "task"
    MEETING = "meeting"
    RISK = "risk"
    ISSUE = "issue"
    CHANGE_REQUEST = "change_request"
    MILESTONE = "milestone"
    TIMESHEET = "timesheet"
    ACTION = "action"


class Notification(BaseEntity, TenantMixin):
    """An in-app message addressed to a single user."""

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    notification_type: Mapped[NotificationType] = mapped_column(
        enum_column(NotificationType), nullable=False, index=True
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        enum_column(NotificationPriority), default=NotificationPriority.NORMAL
    )
    status: Mapped[NotificationStatus] = mapped_column(
        enum_column(NotificationStatus), default=NotificationStatus.UNREAD, index=True
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(String(4000), default="")
    link: Mapped[str] = mapped_column(String(1024), default="")

    # Optional polymorphic pointer to the triggering entity (metadata only, no FK).
    entity_type: Mapped[NotificationEntityType | None] = mapped_column(
        enum_column(NotificationEntityType), nullable=True, index=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)

    read_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationPreference(BaseEntity, TenantMixin):
    """A user's per-type notification preference."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", name="uq_notification_preference"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        enum_column(NotificationType), nullable=False
    )
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
