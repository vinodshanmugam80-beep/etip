"""Repositories for the Notifications module.

Every query is scoped to a single recipient (``user_id``); notifications are
never returned across users.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.notification.models import (
    Notification,
    NotificationPreference,
    NotificationStatus,
    NotificationType,
)
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Data access for :class:`Notification` (recipient-scoped)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Notification)

    def get_for_user(
        self, notification_id: uuid.UUID, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification | None:
        """Return a notification only if it belongs to the given user."""
        stmt = self._base_query(organization_id).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        status: NotificationStatus | None,
        notification_type: NotificationType | None,
    ) -> Select[tuple[Notification]]:
        stmt = self._base_query(organization_id).where(Notification.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Notification.status == status)
        if notification_type is not None:
            stmt = stmt.where(Notification.notification_type == notification_type)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        status: NotificationStatus | None = None,
        notification_type: NotificationType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Notification]:
        """Return a filtered page of the user's notifications (newest first)."""
        stmt = self._search_stmt(
            organization_id, user_id, status=status, notification_type=notification_type
        )
        stmt = stmt.order_by(Notification.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        status: NotificationStatus | None = None,
        notification_type: NotificationType | None = None,
    ) -> int:
        """Return the number of the user's notifications matching the filters."""
        inner = self._search_stmt(
            organization_id, user_id, status=status, notification_type=notification_type
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def unread_count(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Return the number of unread notifications for a user."""
        stmt = select(func.count()).where(
            Notification.organization_id == organization_id,
            Notification.user_id == user_id,
            Notification.is_deleted.is_(False),
            Notification.status == NotificationStatus.UNREAD,
        )
        return int(self.session.execute(stmt).scalar_one())

    def mark_all_read(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        read_at: datetime,
        actor_id: uuid.UUID,
    ) -> int:
        """Mark all of the user's unread notifications as read."""
        stmt = self._base_query(organization_id).where(
            Notification.user_id == user_id,
            Notification.status == NotificationStatus.UNREAD,
        )
        rows = list(self.session.execute(stmt).scalars().all())
        for notification in rows:
            notification.status = NotificationStatus.READ
            notification.read_date = read_at
            notification.modified_by = actor_id
        self.session.flush()
        return len(rows)


class NotificationPreferenceRepository(BaseRepository[NotificationPreference]):
    """Data access for :class:`NotificationPreference` (user-scoped)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, NotificationPreference)

    def get_for_type(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_type: NotificationType,
    ) -> NotificationPreference | None:
        """Return the user's preference for a type, if set."""
        stmt = self._base_query(organization_id).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notification_type,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_for_user(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> Sequence[NotificationPreference]:
        """Return every preference row a user has set."""
        stmt = self._base_query(organization_id).where(NotificationPreference.user_id == user_id)
        return self.session.execute(stmt).scalars().all()
