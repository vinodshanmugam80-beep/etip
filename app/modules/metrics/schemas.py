"""Pydantic v2 schemas for metric snapshots and sparklines."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel


class SnapshotPoint(BaseModel):
    """One point on a metric's time series."""

    captured_date: date
    value: float


class SeriesResponse(BaseModel):
    """An ordered time series for one metric/scope."""

    scope: str
    scope_id: uuid.UUID | None
    metric: str
    points: list[SnapshotPoint]


class CaptureResult(BaseModel):
    """Outcome of a capture run."""

    captured: int
    as_of: date


class Sparklines(BaseModel):
    """Compact trend bundle for the dashboard (headline + per-project SPI)."""

    headline: dict[str, list[float]]
    projects: dict[str, list[float]]
