"""Shared KPI attainment logic, used by schemas and the service."""

from __future__ import annotations

from decimal import Decimal

from app.modules.initiative.models import KPIDirection


def attainment_percent(
    baseline: Decimal,
    current: Decimal,
    target: Decimal,
    direction: KPIDirection,
) -> float | None:
    """Progress from baseline toward target, as a percentage.

    Returns ``None`` when baseline equals target (no measurable gap).
    """
    if direction == KPIDirection.INCREASE:
        denom = target - baseline
    else:
        denom = baseline - target
    if denom == 0:
        return None
    if direction == KPIDirection.INCREASE:
        progress = current - baseline
    else:
        progress = baseline - current
    return round(float(progress / denom) * 100, 2)


def target_met(current: Decimal, target: Decimal, direction: KPIDirection) -> bool:
    """Whether the KPI has reached or beaten its target."""
    if direction == KPIDirection.INCREASE:
        return current >= target
    return current <= target
