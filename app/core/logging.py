"""Structured JSON logging configuration.

The platform emits one JSON object per log line so logs can be shipped to a
central store (Loki / ELK) and correlated by ``request_id`` and ``tenant_id``.
A :class:`contextvars.ContextVar` carries request-scoped context set by the
request-context middleware.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Request-scoped context populated by middleware. Kept intentionally small.
request_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "request_context", default=None
)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON documents."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        ctx = request_context.get()
        if ctx:
            payload.update(ctx)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Merge structured extras passed via ``logger.info(..., extra={...})``.
        for key, value in record.__dict__.items():
            if key.startswith("ctx_"):
                payload[key[4:]] = value

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger.

    :param level: Minimum log level name (e.g. ``"INFO"``, ``"DEBUG"``).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Silence noisy third-party loggers.
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger."""
    return logging.getLogger(name)
