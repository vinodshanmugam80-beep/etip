"""Notifications service.

Business rules for in-app notifications. Sending a notification targets a
recipient and is skipped if that recipient has muted the notification's type.
Every other operation — listing, reading, updating state, deleting, and managing
preferences — is scoped to the **calling user**; a user can never see or touch
another user's notifications, which is enforced here rather than by the coarse
role permissions.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid

from app.core.exceptions import NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.notification.models import (
    Notification,
    NotificationEntityType,
    NotificationPreference,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.modules.notification.repository import (
    NotificationPreferenceRepository,
    NotificationRepository,
)

logger = get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[NotificationStatus, set[NotificationStatus]] = {
    NotificationStatus.UNREAD: {NotificationStatus.READ, NotificationStatus.ARCHIVED},
    NotificationStatus.READ: {NotificationStatus.UNREAD, NotificationStatus.ARCHIVED},
    NotificationStatus.ARCHIVED: {NotificationStatus.UNREAD, NotificationStatus.READ},
}


class NotificationService:
    """Coordinates notification use cases within a tenant, scoped to the caller."""

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
        self.notifications = NotificationRepository(session)
        self.preferences = NotificationPreferenceRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _is_muted(self, user_id: uuid.UUID, notification_type: NotificationType) -> bool:
        pref = self.preferences.get_for_type(self._org_id, user_id, notification_type)
        return pref is not None and pref.muted

    def create_notification(
        self,
        *,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        priority: NotificationPriority,
        title: str,
        body: str,
        entity_type: NotificationEntityType | None,
        entity_id: uuid.UUID | None,
        link: str,
    ) -> Notification | None:
        """Send a notification to a user, unless they've muted its type.

        Returns the created notification, or ``None`` if it was suppressed by the
        recipient's preferences.
        """
        if self.users.get(user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Recipient does not belong to this organization.",
                details={"user_id": str(user_id)},
            )
        if self._is_muted(user_id, notification_type):
            return None
        notification = Notification(
            organization_id=self._org_id,
            user_id=user_id,
            actor_user_id=self._actor_id,
            notification_type=notification_type,
            priority=priority,
            status=NotificationStatus.UNREAD,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            link=link,
            created_by=self._actor_id,
        )
        self.notifications.add(notification)
        self._uow.record_audit(
            "Notification",
            notification.id,
            "create",
            f"Sent '{notification_type.value}' notification",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return notification

    # ------------------------------------------------------------------
    # Reading (own only)
    # ------------------------------------------------------------------
    def _get_own_or_404(self, notification_id: uuid.UUID) -> Notification:
        notification = self.notifications.get_for_user(
            notification_id, self._org_id, self._actor_id
        )
        if notification is None:
            raise NotFoundError("Notification not found.")
        return notification

    def get_notification(self, notification_id: uuid.UUID) -> Notification:
        """Return one of the caller's own notifications."""
        return self._get_own_or_404(notification_id)

    def list_notifications(
        self,
        *,
        status: NotificationStatus | None,
        notification_type: NotificationType | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Notification], int]:
        """Return a filtered page of the caller's notifications and the total."""
        items = list(
            self.notifications.search(
                self._org_id,
                self._actor_id,
                status=status,
                notification_type=notification_type,
                limit=limit,
                offset=offset,
            )
        )
        total = self.notifications.count(
            self._org_id,
            self._actor_id,
            status=status,
            notification_type=notification_type,
        )
        return items, total

    def unread_count(self) -> int:
        """Return the caller's unread notification count."""
        return self.notifications.unread_count(self._org_id, self._actor_id)

    # ------------------------------------------------------------------
    # State changes (own only)
    # ------------------------------------------------------------------
    def set_status(self, notification_id: uuid.UUID, status: NotificationStatus) -> Notification:
        """Move one of the caller's notifications to a new state."""
        notification = self._get_own_or_404(notification_id)
        if status != notification.status:
            validate_status_transition(_ALLOWED_TRANSITIONS, notification.status, status)
            notification.status = status
            if status == NotificationStatus.READ:
                notification.read_date = utcnow()
            elif status == NotificationStatus.UNREAD:
                notification.read_date = None
            notification.modified_by = self._actor_id
            self.notifications.update(notification)
        return notification

    def mark_all_read(self) -> int:
        """Mark all of the caller's unread notifications as read."""
        return self.notifications.mark_all_read(
            self._org_id, self._actor_id, read_at=utcnow(), actor_id=self._actor_id
        )

    def delete_notification(self, notification_id: uuid.UUID) -> None:
        """Soft-delete one of the caller's notifications."""
        notification = self._get_own_or_404(notification_id)
        self.notifications.soft_delete(notification, actor_id=self._actor_id)

    # ------------------------------------------------------------------
    # Preferences (own only)
    # ------------------------------------------------------------------
    def list_preferences(self) -> list[NotificationPreference]:
        """Return every preference the caller has set."""
        return list(self.preferences.list_for_user(self._org_id, self._actor_id))

    def set_preference(
        self, notification_type: NotificationType, *, muted: bool
    ) -> NotificationPreference:
        """Set (upsert) the caller's muted flag for a notification type."""
        pref = self.preferences.get_for_type(self._org_id, self._actor_id, notification_type)
        if pref is None:
            pref = NotificationPreference(
                organization_id=self._org_id,
                user_id=self._actor_id,
                notification_type=notification_type,
                muted=muted,
                created_by=self._actor_id,
            )
            self.preferences.add(pref)
        else:
            pref.muted = muted
            pref.modified_by = self._actor_id
            self.preferences.update(pref)
        return pref
