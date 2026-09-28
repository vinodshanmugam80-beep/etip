"""HTTP routes for the Integration Hub (outbound webhooks).

Reads require ``integration:read``; managing endpoints and publishing/testing
require ``integration:manage``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import IntegrationServiceDep, UowDep, require_permission
from app.modules.integration.models import EVENT_TYPES, DeliveryStatus
from app.modules.integration.schemas import (
    EventCatalogue,
    OutboxDispatchResult,
    OutboxEventResponse,
    PaginatedOutboxEvents,
    PaginatedWebhookDeliveries,
    PaginatedWebhookEndpoints,
    PublishRequest,
    PublishResult,
    WebhookDeliveryResponse,
    WebhookEndpointCreateRequest,
    WebhookEndpointResponse,
    WebhookEndpointUpdateRequest,
)

router = APIRouter(prefix="/integrations", tags=["Integration Hub"])
_READ = Depends(require_permission("integration:read"))
_MANAGE = Depends(require_permission("integration:manage"))


@router.get(
    "/events",
    response_model=EventCatalogue,
    dependencies=[_READ],
    summary="List subscribable event types",
)
def event_catalogue() -> EventCatalogue:
    """Return the catalogue of event types an endpoint may subscribe to."""
    return EventCatalogue(event_types=list(EVENT_TYPES))


@router.get(
    "/outbox",
    response_model=PaginatedOutboxEvents,
    dependencies=[_READ],
    summary="List transactional-outbox events",
)
def list_outbox(
    service: IntegrationServiceDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedOutboxEvents:
    """Return domain events queued/dispatched via the transactional outbox."""
    items, total = service.list_outbox(limit=limit, offset=offset)
    return PaginatedOutboxEvents(
        items=[OutboxEventResponse.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/outbox/dispatch",
    response_model=OutboxDispatchResult,
    dependencies=[_MANAGE],
    summary="Dispatch pending outbox events",
)
def dispatch_outbox(
    service: IntegrationServiceDep,
    uow: UowDep,
    limit: int = Query(200, ge=1, le=1000),
) -> OutboxDispatchResult:
    """Deliver pending domain events to subscribers (driven by a worker/cron)."""
    dispatched, deliveries = service.dispatch_outbox(limit=limit)
    uow.commit()
    return OutboxDispatchResult(dispatched=dispatched, deliveries_created=deliveries)


# --- Endpoints -------------------------------------------------------------
@router.post(
    "/webhooks",
    response_model=WebhookEndpointResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Register a webhook",
)
def create_webhook(
    payload: WebhookEndpointCreateRequest, service: IntegrationServiceDep, uow: UowDep
) -> WebhookEndpointResponse:
    """Register an outbound webhook endpoint."""
    endpoint = service.create_endpoint(payload)
    uow.commit()
    return WebhookEndpointResponse.model_validate(endpoint)


@router.get(
    "/webhooks",
    response_model=PaginatedWebhookEndpoints,
    dependencies=[_READ],
    summary="List webhooks",
)
def list_webhooks(
    service: IntegrationServiceDep,
    is_active: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedWebhookEndpoints:
    """Return a filtered, paginated page of webhook endpoints."""
    items, total = service.search_endpoints(is_active=is_active, limit=limit, offset=offset)
    return PaginatedWebhookEndpoints(
        items=[WebhookEndpointResponse.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# --- Deliveries (literal route before /{endpoint_id}) ----------------------
@router.get(
    "/webhooks/deliveries",
    response_model=PaginatedWebhookDeliveries,
    dependencies=[_READ],
    summary="List delivery records",
)
def list_deliveries(
    service: IntegrationServiceDep,
    endpoint_id: uuid.UUID | None = Query(default=None),
    delivery_status: DeliveryStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedWebhookDeliveries:
    """Return a filtered, paginated page of delivery records."""
    items, total = service.list_deliveries(
        endpoint_id=endpoint_id, status=delivery_status, limit=limit, offset=offset
    )
    return PaginatedWebhookDeliveries(
        items=[WebhookDeliveryResponse.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/events/publish",
    response_model=PublishResult,
    dependencies=[_MANAGE],
    summary="Publish an event to subscribers",
)
def publish_event(
    payload: PublishRequest, service: IntegrationServiceDep, uow: UowDep
) -> PublishResult:
    """Deliver an event to every active endpoint subscribed to it."""
    matched, deliveries = service.publish(payload.event_type, payload.payload)
    uow.commit()
    delivered = sum(1 for d in deliveries if d.status == DeliveryStatus.DELIVERED)
    return PublishResult(
        event_type=payload.event_type,
        endpoints_matched=matched,
        delivered=delivered,
        failed=len(deliveries) - delivered,
        deliveries=[WebhookDeliveryResponse.model_validate(d) for d in deliveries],
    )


@router.post(
    "/webhooks/deliveries/retry-due",
    response_model=PaginatedWebhookDeliveries,
    dependencies=[_MANAGE],
    summary="Retry all deliveries whose backoff has elapsed",
)
def retry_due(
    service: IntegrationServiceDep,
    uow: UowDep,
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedWebhookDeliveries:
    """Re-attempt failed deliveries whose exponential-backoff window has elapsed."""
    retried = service.retry_due(limit=limit)
    uow.commit()
    return PaginatedWebhookDeliveries(
        items=[WebhookDeliveryResponse.model_validate(d) for d in retried],
        total=len(retried),
        limit=limit,
        offset=0,
    )


@router.post(
    "/webhooks/deliveries/{delivery_id}/retry",
    response_model=WebhookDeliveryResponse,
    dependencies=[_MANAGE],
    summary="Retry a failed delivery",
)
def retry_delivery(
    delivery_id: uuid.UUID, service: IntegrationServiceDep, uow: UowDep
) -> WebhookDeliveryResponse:
    """Re-attempt a single failed delivery (up to the attempt cap)."""
    delivery = service.retry_delivery(delivery_id)
    uow.commit()
    return WebhookDeliveryResponse.model_validate(delivery)


@router.get(
    "/webhooks/{endpoint_id}",
    response_model=WebhookEndpointResponse,
    dependencies=[_READ],
    summary="Get a webhook",
)
def get_webhook(endpoint_id: uuid.UUID, service: IntegrationServiceDep) -> WebhookEndpointResponse:
    """Return a single webhook endpoint."""
    return WebhookEndpointResponse.model_validate(service.get_endpoint(endpoint_id))


@router.patch(
    "/webhooks/{endpoint_id}",
    response_model=WebhookEndpointResponse,
    dependencies=[_MANAGE],
    summary="Update a webhook",
)
def update_webhook(
    endpoint_id: uuid.UUID,
    payload: WebhookEndpointUpdateRequest,
    service: IntegrationServiceDep,
    uow: UowDep,
) -> WebhookEndpointResponse:
    """Update a webhook endpoint."""
    endpoint = service.update_endpoint(endpoint_id, payload)
    uow.commit()
    return WebhookEndpointResponse.model_validate(endpoint)


@router.delete(
    "/webhooks/{endpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_MANAGE],
    summary="Delete a webhook",
)
def delete_webhook(endpoint_id: uuid.UUID, service: IntegrationServiceDep, uow: UowDep) -> None:
    """Soft-delete a webhook endpoint and its deliveries."""
    service.delete_endpoint(endpoint_id)
    uow.commit()


@router.post(
    "/webhooks/{endpoint_id}/test",
    response_model=WebhookDeliveryResponse,
    dependencies=[_MANAGE],
    summary="Send a test delivery",
)
def test_webhook(
    endpoint_id: uuid.UUID, service: IntegrationServiceDep, uow: UowDep
) -> WebhookDeliveryResponse:
    """Send a synthetic ping to the endpoint and record the result."""
    delivery = service.test_endpoint(endpoint_id)
    uow.commit()
    return WebhookDeliveryResponse.model_validate(delivery)
