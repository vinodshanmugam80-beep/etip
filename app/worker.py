"""Celery application.

Configures the Celery app used for asynchronous, out-of-process work
(notifications, report generation, scheduled rollups, AI Copilot inference).
The broker is RabbitMQ and the result backend is Redis, both sourced from
environment configuration. Task modules from feature modules are autodiscovered
as they are added.
"""

from __future__ import annotations

import os

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "etip",
    broker=os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"),
    backend=os.getenv("CELERY_RESULT_BACKEND", _settings.redis_url),
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # Deliver queued webhook events every minute.
        "dispatch-outbox-events": {
            "task": "etip.integration.dispatch_outbox",
            "schedule": 60.0,
        },
        # Retry failed deliveries whose backoff window has elapsed, every 5 minutes.
        "retry-due-deliveries": {
            "task": "etip.integration.retry_due",
            "schedule": 300.0,
        },
    },
)

# Feature modules register their tasks under ``app.modules.<name>.tasks``.
celery_app.autodiscover_tasks(["app.modules"])


@celery_app.task(name="etip.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    """Trivial liveness task used to verify the worker/broker wiring."""
    return "pong"
