"""Data access for the Integration Hub."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.base import OutboxEvent
from app.modules.integration.models import (
    DeliveryStatus,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.repositories.base import BaseRepository


class WebhookEndpointRepository(BaseRepository[WebhookEndpoint]):
    """Repository for :class:`WebhookEndpoint`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WebhookEndpoint)

    def _filtered(
        self, organization_id: uuid.UUID, *, is_active: bool | None
    ) -> Select[tuple[WebhookEndpoint]]:
        stmt = self._base_query(organization_id)
        if is_active is not None:
            stmt = stmt.where(WebhookEndpoint.is_active.is_(is_active))
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[WebhookEndpoint]:
        """Return a filtered, paginated page of endpoints (by name)."""
        stmt = self._filtered(organization_id, is_active=is_active)
        stmt = stmt.order_by(WebhookEndpoint.name).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(self, organization_id: uuid.UUID, *, is_active: bool | None = None) -> int:
        """Return the number of endpoints matching the filter."""
        inner = self._filtered(organization_id, is_active=is_active).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def list_active(self, organization_id: uuid.UUID) -> Sequence[WebhookEndpoint]:
        """Return all active endpoints for the tenant."""
        stmt = self._base_query(organization_id).where(WebhookEndpoint.is_active.is_(True))
        return self.session.execute(stmt).scalars().all()


class WebhookDeliveryRepository(BaseRepository[WebhookDelivery]):
    """Repository for :class:`WebhookDelivery`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WebhookDelivery)

    def _filtered(
        self,
        organization_id: uuid.UUID,
        *,
        endpoint_id: uuid.UUID | None,
        status: DeliveryStatus | None,
    ) -> Select[tuple[WebhookDelivery]]:
        stmt = self._base_query(organization_id)
        if endpoint_id is not None:
            stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
        if status is not None:
            stmt = stmt.where(WebhookDelivery.status == status)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        endpoint_id: uuid.UUID | None = None,
        status: DeliveryStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[WebhookDelivery]:
        """Return a filtered, paginated page of deliveries (newest first)."""
        stmt = self._filtered(organization_id, endpoint_id=endpoint_id, status=status)
        stmt = stmt.order_by(WebhookDelivery.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        endpoint_id: uuid.UUID | None = None,
        status: DeliveryStatus | None = None,
    ) -> int:
        """Return the number of deliveries matching the filters."""
        inner = self._filtered(organization_id, endpoint_id=endpoint_id, status=status).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def list_due_for_retry(
        self,
        organization_id: uuid.UUID,
        *,
        now: datetime,
        max_attempts: int,
        limit: int,
    ) -> Sequence[WebhookDelivery]:
        """Return failed deliveries whose backoff window has elapsed."""
        stmt = (
            self._base_query(organization_id)
            .where(
                WebhookDelivery.status == DeliveryStatus.FAILED,
                WebhookDelivery.next_retry_at.is_not(None),
                WebhookDelivery.next_retry_at <= now,
                WebhookDelivery.attempts < max_attempts,
            )
            .order_by(WebhookDelivery.next_retry_at)
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()


class OutboxRepository:
    """Access to the transactional outbox (``OutboxEvent`` is a plain infra table)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_pending(self, organization_id: uuid.UUID, limit: int) -> list[OutboxEvent]:
        """Return the oldest pending events for the tenant."""
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.organization_id == organization_id, OutboxEvent.status == "pending")
            .order_by(OutboxEvent.created_date)
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_recent(
        self, organization_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[OutboxEvent]:
        """Return the tenant's events, newest first."""
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.organization_id == organization_id)
            .order_by(OutboxEvent.created_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    def count(self, organization_id: uuid.UUID, *, status: str | None = None) -> int:
        """Return the number of events (optionally filtered by status)."""
        stmt = (
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.organization_id == organization_id)
        )
        if status is not None:
            stmt = stmt.where(OutboxEvent.status == status)
        return int(self.session.execute(stmt).scalar_one())
