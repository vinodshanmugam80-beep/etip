"""Metric snapshot / sparkline routes (part of the intelligence surface)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import MetricsServiceDep, UowDep, require_permission
from app.db.base import utcnow
from app.modules.metrics.schemas import CaptureResult, Sparklines

router = APIRouter(prefix="/intelligence/metrics", tags=["Metrics"])
_READ = Depends(require_permission("intelligence:read"))


@router.post(
    "/capture",
    response_model=CaptureResult,
    dependencies=[_READ],
    summary="Capture a daily snapshot of intelligence metrics",
)
def capture(service: MetricsServiceDep, uow: UowDep) -> CaptureResult:
    """Snapshot the current headline + per-project metrics for today."""
    n = service.capture()
    uow.commit()
    return CaptureResult(captured=n, as_of=utcnow().date())


@router.post(
    "/backfill-demo",
    response_model=CaptureResult,
    dependencies=[_READ],
    summary="Seed a short metric history for demos (sparkline trend)",
)
def backfill_demo(
    service: MetricsServiceDep, uow: UowDep, days: int = Query(10, ge=1, le=60)
) -> CaptureResult:
    """Write a short daily history so sparklines show a trend in demos."""
    n = service.backfill_demo(days=days)
    uow.commit()
    return CaptureResult(captured=n, as_of=utcnow().date())


@router.get(
    "/sparklines",
    response_model=Sparklines,
    dependencies=[_READ],
    summary="Compact metric trends for the dashboard",
)
def sparklines(service: MetricsServiceDep, limit: int = Query(12, ge=2, le=60)) -> Sparklines:
    """Return headline + per-project SPI trend series."""
    return service.sparklines(limit=limit)
