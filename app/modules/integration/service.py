"""Integration Hub service — outbound webhook delivery.

Manages webhook endpoints and delivers HMAC-signed event payloads to them. The
HTTP call is isolated in the module-level :func:`send_request` so it can be
swapped in tests; live delivery to arbitrary external URLs is best-effort and
subject to the deployment's network egress.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.request
import uuid
from datetime import timedelta
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.db.base import OutboxEvent, utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.integration.models import (
    BACKOFF_MINUTES,
    MAX_ATTEMPTS,
    DeliveryStatus,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.modules.integration.repository import (
    OutboxRepository,
    WebhookDeliveryRepository,
    WebhookEndpointRepository,
)
from app.modules.integration.schemas import (
    WebhookEndpointCreateRequest,
    WebhookEndpointUpdateRequest,
)

logger = get_logger(__name__)

_TIMEOUT = 5


def send_request(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
    """POST ``body`` to ``url``; return ``(status_code, error)``.

    Isolated at module level so tests can monkeypatch it without real network I/O.
    """
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
        return int(resp.status), ""


class IntegrationService:
    """Manage webhook endpoints and deliver events, scoped to the tenant."""

    def __init__(self, uow: UnitOfWork, *, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.endpoints = WebhookEndpointRepository(session)
        self.deliveries = WebhookDeliveryRepository(session)
        self.outbox = OutboxRepository(session)
        self._session = session

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------
    def create_endpoint(self, payload: WebhookEndpointCreateRequest) -> WebhookEndpoint:
        """Register a webhook endpoint."""
        endpoint = WebhookEndpoint(
            organization_id=self._org_id,
            name=payload.name,
            target_url=payload.target_url,
            secret=payload.secret,
            event_types=payload.event_types,
            is_active=payload.is_active,
            description=payload.description,
            created_by=self._actor_id,
        )
        endpoint = self.endpoints.add(endpoint)
        self._audit(endpoint.id, "create", f"Registered webhook '{endpoint.name}'")
        return endpoint

    def update_endpoint(
        self, endpoint_id: uuid.UUID, payload: WebhookEndpointUpdateRequest
    ) -> WebhookEndpoint:
        """Update a webhook endpoint."""
        endpoint = self._get_or_404(endpoint_id)
        for field in ("name", "target_url", "secret", "event_types", "is_active", "description"):
            value = getattr(payload, field)
            if value is not None:
                setattr(endpoint, field, value)
        endpoint.modified_by = self._actor_id
        endpoint = self.endpoints.update(endpoint)
        self._audit(endpoint.id, "update", f"Updated webhook '{endpoint.name}'")
        return endpoint

    def delete_endpoint(self, endpoint_id: uuid.UUID) -> None:
        """Soft-delete a webhook endpoint and its delivery records."""
        endpoint = self._get_or_404(endpoint_id)
        for delivery in self.deliveries.search(self._org_id, endpoint_id=endpoint_id, limit=1000):
            self.deliveries.soft_delete(delivery, actor_id=self._actor_id)
        self.endpoints.soft_delete(endpoint, actor_id=self._actor_id)
        self._audit(endpoint.id, "delete", f"Deleted webhook '{endpoint.name}'")

    def get_endpoint(self, endpoint_id: uuid.UUID) -> WebhookEndpoint:
        """Return an endpoint or raise ``NotFoundError``."""
        return self._get_or_404(endpoint_id)

    def search_endpoints(
        self, *, is_active: bool | None, limit: int, offset: int
    ) -> tuple[list[WebhookEndpoint], int]:
        """Return a filtered page of endpoints and the total count."""
        items = list(
            self.endpoints.search(self._org_id, is_active=is_active, limit=limit, offset=offset)
        )
        total = self.endpoints.count(self._org_id, is_active=is_active)
        return items, total

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------
    def publish(
        self, event_type: str, payload: dict[str, Any]
    ) -> tuple[int, list[WebhookDelivery]]:
        """Deliver an event to every active endpoint subscribed to it."""
        matched = [
            e
            for e in self.endpoints.list_active(self._org_id)
            if event_type in (e.event_types or [])
        ]
        body = self._envelope(event_type, payload)
        deliveries = [self._deliver(e, event_type, body) for e in matched]
        self._audit(
            self._org_id, "publish", f"Published '{event_type}' to {len(matched)} endpoint(s)"
        )
        return len(matched), deliveries

    def test_endpoint(self, endpoint_id: uuid.UUID) -> WebhookDelivery:
        """Send a synthetic ping to a single endpoint."""
        endpoint = self._get_or_404(endpoint_id)
        body = self._envelope("webhook.test", {"message": "ETIP webhook test"})
        delivery = self._deliver(endpoint, "webhook.test", body)
        self._audit(endpoint.id, "test", f"Sent test delivery to '{endpoint.name}'")
        return delivery

    def list_deliveries(
        self,
        *,
        endpoint_id: uuid.UUID | None,
        status: DeliveryStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[WebhookDelivery], int]:
        """Return a filtered page of delivery records and the total count."""
        items = list(
            self.deliveries.search(
                self._org_id, endpoint_id=endpoint_id, status=status, limit=limit, offset=offset
            )
        )
        total = self.deliveries.count(self._org_id, endpoint_id=endpoint_id, status=status)
        return items, total

    def retry_delivery(self, delivery_id: uuid.UUID) -> WebhookDelivery:
        """Re-attempt a single failed delivery (respecting the attempt cap)."""
        delivery = self.deliveries.get(delivery_id, organization_id=self._org_id)
        if delivery is None:
            raise NotFoundError("Delivery not found.")
        if delivery.status != DeliveryStatus.FAILED:
            raise ConflictError("Only failed deliveries can be retried.")
        if delivery.attempts >= MAX_ATTEMPTS:
            raise ConflictError("This delivery has exhausted its retry attempts.")
        endpoint = self.endpoints.get(delivery.endpoint_id, organization_id=self._org_id)
        if endpoint is None:
            raise NotFoundError("The delivery's endpoint no longer exists.")
        self._attempt(delivery, endpoint, delivery.payload.encode())
        delivery.modified_by = self._actor_id
        delivery = self.deliveries.update(delivery)
        self._audit(endpoint.id, "retry", f"Retried delivery (attempt {delivery.attempts})")
        return delivery

    def retry_due(self, *, limit: int) -> list[WebhookDelivery]:
        """Re-attempt all failed deliveries whose backoff window has elapsed.

        Intended to be driven by a scheduler / worker (or a cron hitting the
        ``/retry-due`` endpoint).
        """
        due = self.deliveries.list_due_for_retry(
            self._org_id, now=utcnow(), max_attempts=MAX_ATTEMPTS, limit=limit
        )
        retried: list[WebhookDelivery] = []
        for delivery in due:
            endpoint = self.endpoints.get(delivery.endpoint_id, organization_id=self._org_id)
            if endpoint is None:
                delivery.next_retry_at = None  # endpoint gone — stop retrying
                self.deliveries.update(delivery)
                continue
            self._attempt(delivery, endpoint, delivery.payload.encode())
            delivery.modified_by = self._actor_id
            self.deliveries.update(delivery)
            retried.append(delivery)
        if retried:
            self._audit(self._org_id, "retry_due", f"Retried {len(retried)} due delivery(ies)")
        return retried

    # ------------------------------------------------------------------
    # Transactional outbox
    # ------------------------------------------------------------------
    def dispatch_outbox(self, *, limit: int) -> tuple[int, int]:
        """Deliver pending outbox events to subscribers; return (events, deliveries)."""
        events = self.outbox.list_pending(self._org_id, limit)
        deliveries = 0
        for event in events:
            _matched, made = self.publish(event.event_type, event.payload)
            deliveries += len(made)
            event.status = "dispatched"
            event.attempts += 1
            event.dispatched_date = utcnow()
            self._session.add(event)
        if events:
            self._audit(self._org_id, "dispatch", f"Dispatched {len(events)} outbox event(s)")
        return len(events), deliveries

    def list_outbox(self, *, limit: int, offset: int) -> tuple[list[OutboxEvent], int]:
        """Return a page of outbox events and the total count."""
        items = self.outbox.list_recent(self._org_id, limit=limit, offset=offset)
        return items, self.outbox.count(self._org_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _envelope(self, event_type: str, payload: dict[str, Any]) -> bytes:
        return json.dumps(
            {
                "event": event_type,
                "organization_id": str(self._org_id),
                "timestamp": utcnow().isoformat(),
                "data": payload,
            }
        ).encode()

    def _deliver(self, endpoint: WebhookEndpoint, event_type: str, body: bytes) -> WebhookDelivery:
        delivery = WebhookDelivery(
            organization_id=self._org_id,
            endpoint_id=endpoint.id,
            event_type=event_type,
            payload=body.decode()[:8000],
            status=DeliveryStatus.PENDING,
            attempts=0,
            created_by=self._actor_id,
        )
        self._attempt(delivery, endpoint, body)
        return self.deliveries.add(delivery)

    def _attempt(self, delivery: WebhookDelivery, endpoint: WebhookEndpoint, body: bytes) -> None:
        """Perform one delivery attempt, updating status and retry schedule."""
        delivery.attempts += 1
        signature = hmac.new((endpoint.secret or "").encode(), body, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-ETIP-Event": delivery.event_type,
            "X-ETIP-Signature": f"sha256={signature}",
        }
        try:
            code, err = send_request(endpoint.target_url, body, headers)
            delivery.status_code = code
            if 200 <= code < 300:
                delivery.status = DeliveryStatus.DELIVERED
                delivery.delivered_date = utcnow()
                delivery.error = ""
                delivery.next_retry_at = None
                return
            delivery.error = err or f"HTTP {code}"
        except Exception as exc:  # noqa: BLE001 - any failure is a failed delivery
            delivery.error = str(exc)[:2000]
        delivery.status = DeliveryStatus.FAILED
        self._schedule_retry(delivery)

    @staticmethod
    def _schedule_retry(delivery: WebhookDelivery) -> None:
        if delivery.attempts < MAX_ATTEMPTS:
            minutes = BACKOFF_MINUTES[min(delivery.attempts - 1, len(BACKOFF_MINUTES) - 1)]
            delivery.next_retry_at = utcnow() + timedelta(minutes=minutes)
        else:
            delivery.next_retry_at = None  # retries exhausted

    def _get_or_404(self, endpoint_id: uuid.UUID) -> WebhookEndpoint:
        endpoint = self.endpoints.get(endpoint_id, organization_id=self._org_id)
        if endpoint is None:
            raise NotFoundError("Webhook endpoint not found.")
        return endpoint

    def _audit(self, entity_id: uuid.UUID, action: str, summary: str) -> None:
        self._uow.record_audit(
            "WebhookEndpoint",
            entity_id,
            action,
            summary,
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
