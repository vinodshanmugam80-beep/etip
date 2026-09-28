"""Pydantic v2 schemas for the Integration Hub (outbound webhooks)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.modules.integration.models import EVENT_TYPES, DeliveryStatus


def _validate_events(value: list[str]) -> list[str]:
    unknown = sorted(set(value) - set(EVENT_TYPES))
    if unknown:
        raise ValueError(f"Unknown event type(s): {', '.join(unknown)}")
    return value


def _validate_url(value: str) -> str:
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("target_url must start with http:// or https://")
    return value


class WebhookEndpointCreateRequest(BaseModel):
    """Payload to register a webhook endpoint."""

    name: str = Field(min_length=2, max_length=200)
    target_url: str = Field(min_length=8, max_length=1000)
    secret: str = Field(default="", max_length=200)
    event_types: list[str] = Field(default_factory=list)
    is_active: bool = True
    description: str = Field(default="", max_length=2000)

    @field_validator("target_url")
    @classmethod
    def _url(cls, v: str) -> str:
        return _validate_url(v)

    @field_validator("event_types")
    @classmethod
    def _events(cls, v: list[str]) -> list[str]:
        return _validate_events(v)


class WebhookEndpointUpdateRequest(BaseModel):
    """Payload to update a webhook endpoint (all optional)."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    target_url: str | None = Field(default=None, min_length=8, max_length=1000)
    secret: str | None = Field(default=None, max_length=200)
    event_types: list[str] | None = None
    is_active: bool | None = None
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("target_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return _validate_url(v) if v is not None else v

    @field_validator("event_types")
    @classmethod
    def _events(cls, v: list[str] | None) -> list[str] | None:
        return _validate_events(v) if v is not None else v


class WebhookEndpointResponse(BaseModel):
    """A registered webhook endpoint (the secret is never returned)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    target_url: str
    event_types: list[str]
    is_active: bool
    description: str
    secret: str = Field(exclude=True, default="")
    created_date: datetime
    version: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def secret_set(self) -> bool:
        """Whether a signing secret is configured (the value itself is hidden)."""
        return bool(self.secret)


class PaginatedWebhookEndpoints(BaseModel):
    """A page of webhook endpoints."""

    items: list[WebhookEndpointResponse]
    total: int
    limit: int
    offset: int


class WebhookDeliveryResponse(BaseModel):
    """A recorded delivery attempt."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint_id: uuid.UUID
    event_type: str
    status: DeliveryStatus
    status_code: int | None
    attempts: int
    error: str
    payload: str
    delivered_date: datetime | None
    next_retry_at: datetime | None
    created_date: datetime


class PaginatedWebhookDeliveries(BaseModel):
    """A page of delivery records."""

    items: list[WebhookDeliveryResponse]
    total: int
    limit: int
    offset: int


class PublishRequest(BaseModel):
    """Payload to publish an event to subscribed endpoints."""

    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(f"Unknown event type: {v}")
        return v


class PublishResult(BaseModel):
    """The outcome of publishing an event."""

    event_type: str
    endpoints_matched: int
    delivered: int
    failed: int
    deliveries: list[WebhookDeliveryResponse]


class EventCatalogue(BaseModel):
    """The set of event types an endpoint may subscribe to."""

    event_types: list[str]


class OutboxEventResponse(BaseModel):
    """A transactional-outbox event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    status: str
    attempts: int
    created_date: datetime
    dispatched_date: datetime | None


class PaginatedOutboxEvents(BaseModel):
    """A page of outbox events."""

    items: list[OutboxEventResponse]
    total: int
    limit: int
    offset: int


class OutboxDispatchResult(BaseModel):
    """Outcome of dispatching pending outbox events."""

    dispatched: int
    deliveries_created: int
