"""HTTP routes for the Notifications module.

Sending (``POST /notifications``) requires ``notification:create`` and targets
any user. All other routes act on the **caller's own** notifications and
preferences: reads require ``notification:read``, state changes require
``notification:update``, and deletion requires ``notification:delete``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import NotificationServiceDep, UowDep, require_permission
from app.modules.notification.models import (
    NotificationStatus,
    NotificationType,
)
from app.modules.notification.schemas import (
    MessageResponse,
    NotificationCreateRequest,
    NotificationResponse,
    NotificationSendResult,
    NotificationUpdateRequest,
    PaginatedNotifications,
    PreferenceResponse,
    PreferenceSetRequest,
    UnreadCountResponse,
)

router = APIRouter(tags=["Notifications"])


@router.post(
    "/notifications",
    response_model=NotificationSendResult,
    dependencies=[Depends(require_permission("notification:create"))],
    summary="Send a notification to a user",
)
def send_notification(
    payload: NotificationCreateRequest, service: NotificationServiceDep, uow: UowDep
) -> NotificationSendResult:
    """Send a notification, unless the recipient has muted its type."""
    notification = service.create_notification(
        user_id=payload.user_id,
        notification_type=payload.notification_type,
        priority=payload.priority,
        title=payload.title,
        body=payload.body,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        link=payload.link,
    )
    uow.commit()
    if notification is None:
        return NotificationSendResult(
            created=False,
            notification=None,
            detail="Suppressed by the recipient's preferences.",
        )
    return NotificationSendResult(
        created=True,
        notification=NotificationResponse.model_validate(notification),
        detail="Notification sent.",
    )


@router.get(
    "/notifications",
    response_model=PaginatedNotifications,
    dependencies=[Depends(require_permission("notification:read"))],
    summary="List my notifications",
)
def list_notifications(
    service: NotificationServiceDep,
    status_filter: NotificationStatus | None = Query(default=None, alias="status"),
    notification_type: NotificationType | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedNotifications:
    """Return a filtered page of the caller's own notifications (newest first)."""
    items, total = service.list_notifications(
        status=status_filter,
        notification_type=notification_type,
        limit=limit,
        offset=offset,
    )
    return PaginatedNotifications(
        items=[NotificationResponse.model_validate(n) for n in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/notifications/unread-count",
    response_model=UnreadCountResponse,
    dependencies=[Depends(require_permission("notification:read"))],
    summary="Count my unread notifications",
)
def unread_count(service: NotificationServiceDep) -> UnreadCountResponse:
    """Return the caller's unread notification count."""
    return UnreadCountResponse(unread=service.unread_count())


@router.get(
    "/notifications/preferences",
    response_model=list[PreferenceResponse],
    dependencies=[Depends(require_permission("notification:read"))],
    summary="List my notification preferences",
)
def list_preferences(
    service: NotificationServiceDep,
) -> list[PreferenceResponse]:
    """Return every notification preference the caller has set."""
    return [
        PreferenceResponse(notification_type=p.notification_type, muted=p.muted)
        for p in service.list_preferences()
    ]


@router.put(
    "/notifications/preferences/{notification_type}",
    response_model=PreferenceResponse,
    dependencies=[Depends(require_permission("notification:update"))],
    summary="Set a notification-type preference",
)
def set_preference(
    notification_type: NotificationType,
    payload: PreferenceSetRequest,
    service: NotificationServiceDep,
    uow: UowDep,
) -> PreferenceResponse:
    """Mute or unmute a notification type for the caller."""
    pref = service.set_preference(notification_type, muted=payload.muted)
    uow.commit()
    return PreferenceResponse(notification_type=pref.notification_type, muted=pref.muted)


@router.post(
    "/notifications/read-all",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("notification:update"))],
    summary="Mark all my notifications read",
)
def read_all(service: NotificationServiceDep, uow: UowDep) -> MessageResponse:
    """Mark all of the caller's unread notifications as read."""
    count = service.mark_all_read()
    uow.commit()
    return MessageResponse(detail=f"Marked {count} notification(s) as read.")


@router.get(
    "/notifications/{notification_id}",
    response_model=NotificationResponse,
    dependencies=[Depends(require_permission("notification:read"))],
    summary="Get one of my notifications",
)
def get_notification(
    notification_id: uuid.UUID, service: NotificationServiceDep
) -> NotificationResponse:
    """Return one of the caller's own notifications."""
    return NotificationResponse.model_validate(service.get_notification(notification_id))


@router.patch(
    "/notifications/{notification_id}",
    response_model=NotificationResponse,
    dependencies=[Depends(require_permission("notification:update"))],
    summary="Change a notification's state",
)
def update_notification(
    notification_id: uuid.UUID,
    payload: NotificationUpdateRequest,
    service: NotificationServiceDep,
    uow: UowDep,
) -> NotificationResponse:
    """Move one of the caller's notifications to read/unread/archived."""
    notification = service.set_status(notification_id, payload.status)
    uow.commit()
    return NotificationResponse.model_validate(notification)


@router.delete(
    "/notifications/{notification_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("notification:delete"))],
    summary="Delete one of my notifications",
)
def delete_notification(
    notification_id: uuid.UUID, service: NotificationServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete one of the caller's notifications."""
    service.delete_notification(notification_id)
    uow.commit()
    return MessageResponse(detail="Notification deleted.")
