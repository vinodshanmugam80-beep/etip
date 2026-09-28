"""Scheduled Integration-Hub tasks.

Celery beat drives these periodically so the webhook system runs hands-free:
pending outbox events are dispatched and due failed deliveries are retried, across
all tenants. The orchestration is factored into plain functions
(:func:`dispatch_all_pending`, :func:`retry_all_due`) so it can be unit-tested
without a broker.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import OutboxEvent, utcnow
from app.db.session import SessionFactory
from app.db.unit_of_work import UnitOfWork
from app.modules.integration.models import MAX_ATTEMPTS, DeliveryStatus, WebhookDelivery
from app.modules.integration.service import IntegrationService
from app.worker import celery_app

# A well-known "system" identity for automated (non-user) actions.
SYSTEM_ACTOR = uuid.UUID(int=0)
_BATCH = 500


def _pending_event_orgs(session: Session) -> list[uuid.UUID]:
    stmt = select(OutboxEvent.organization_id).where(OutboxEvent.status == "pending").distinct()
    return list(session.execute(stmt).scalars().all())


def _due_delivery_orgs(session: Session) -> list[uuid.UUID]:
    stmt = (
        select(WebhookDelivery.organization_id)
        .where(
            WebhookDelivery.status == DeliveryStatus.FAILED,
            WebhookDelivery.next_retry_at.is_not(None),
            WebhookDelivery.next_retry_at <= utcnow(),
            WebhookDelivery.attempts < MAX_ATTEMPTS,
            WebhookDelivery.is_deleted.is_(False),
        )
        .distinct()
    )
    return list(session.execute(stmt).scalars().all())


def dispatch_all_pending(uow: UnitOfWork) -> dict[str, int]:
    """Dispatch pending outbox events for every tenant that has any."""
    orgs = _pending_event_orgs(uow.session)
    events = deliveries = 0
    for org in orgs:
        service = IntegrationService(uow, organization_id=org, actor_id=SYSTEM_ACTOR)
        ev, dl = service.dispatch_outbox(limit=_BATCH)
        events += ev
        deliveries += dl
    uow.commit()
    return {"organizations": len(orgs), "events": events, "deliveries": deliveries}


def retry_all_due(uow: UnitOfWork) -> dict[str, int]:
    """Retry due failed deliveries for every tenant that has any."""
    orgs = _due_delivery_orgs(uow.session)
    retried = 0
    for org in orgs:
        service = IntegrationService(uow, organization_id=org, actor_id=SYSTEM_ACTOR)
        retried += len(service.retry_due(limit=_BATCH))
    uow.commit()
    return {"organizations": len(orgs), "retried": retried}


@celery_app.task(name="etip.integration.dispatch_outbox")  # type: ignore[untyped-decorator]
def dispatch_outbox_task() -> dict[str, int]:
    """Beat-scheduled: deliver all pending outbox events."""
    with UnitOfWork(SessionFactory) as uow:
        return dispatch_all_pending(uow)


@celery_app.task(name="etip.integration.retry_due")  # type: ignore[untyped-decorator]
def retry_due_task() -> dict[str, int]:
    """Beat-scheduled: retry all due failed deliveries."""
    with UnitOfWork(SessionFactory) as uow:
        return retry_all_due(uow)
