"""Integration Hub models — outbound webhooks.

A :class:`WebhookEndpoint` is a registered external target subscribed to a set of
event types; a :class:`WebhookDelivery` records each attempt to notify it. This is
the integration primitive that lets ETIP push events to Slack, Teams, Jira and
other systems. Payloads are HMAC-signed with the endpoint's secret.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column

# The catalogue of events an endpoint may subscribe to.
EVENT_TYPES: tuple[str, ...] = (
    "project.created",
    "project.updated",
    "risk.raised",
    "benefit.realized",
    "workflow.approved",
    "milestone.overdue",
    "build.deployed",
    "build.failed",
)


class DeliveryStatus(enum.StrEnum):
    """Lifecycle of a webhook delivery attempt."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


# Retry policy: exponential backoff in minutes, capped at MAX_ATTEMPTS total tries.
MAX_ATTEMPTS = 5
BACKOFF_MINUTES: tuple[int, ...] = (1, 5, 15, 60, 240)


class WebhookEndpoint(BaseEntity, TenantMixin):
    """A registered outbound webhook target."""

    __tablename__ = "webhook_endpoints"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    target_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret: Mapped[str] = mapped_column(String(200), default="")
    event_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    description: Mapped[str] = mapped_column(String(2000), default="")


class WebhookDelivery(BaseEntity, TenantMixin):
    """A single attempt to deliver an event to an endpoint."""

    __tablename__ = "webhook_deliveries"

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(String(8000), default="")
    status: Mapped[DeliveryStatus] = mapped_column(
        enum_column(DeliveryStatus), default=DeliveryStatus.PENDING, index=True
    )
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(2000), default="")
    delivered_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
