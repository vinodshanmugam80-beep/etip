"""Shared Earned Value Management primitives for the Intelligence Layer.

Pure, dependency-light functions so every intelligence engine (Performance,
Variance, Forecast, …) derives EVM the same way without duplicating formulas or
coupling to one another.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.modules.project.models import Project

HUNDRED = Decimal("100")
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class RawEVM:
    """Core EVM figures for a scope, in Decimal (pre-formatting)."""

    bac: Decimal  # Budget at Completion
    pv: Decimal | None  # Planned Value
    ev: Decimal  # Earned Value
    ac: Decimal  # Actual Cost
    planned_percent: float | None
    actual_percent: float


def planned_percent(
    baseline_start: date | None, baseline_end: date | None, as_of: date
) -> float | None:
    """Return the fraction of the baseline schedule elapsed at ``as_of``."""
    if baseline_start is None or baseline_end is None or baseline_end <= baseline_start:
        return None
    if as_of <= baseline_start:
        return 0.0
    if as_of >= baseline_end:
        return 1.0
    return (as_of - baseline_start).days / (baseline_end - baseline_start).days


def raw_for_project(project: Project, as_of: date) -> RawEVM:
    """Compute the core EVM figures for a project as of a date."""
    bac = project.budget
    ev = (Decimal(project.progress_percent) / HUNDRED) * bac
    ac = project.actual_cost
    pp = planned_percent(project.baseline_start_date, project.baseline_end_date, as_of)
    pv = Decimal(str(pp)) * bac if pp is not None else None
    return RawEVM(
        bac=bac,
        pv=pv,
        ev=ev,
        ac=ac,
        planned_percent=pp,
        actual_percent=project.progress_percent / 100,
    )


def indices(raw: RawEVM) -> tuple[float | None, float | None]:
    """Return ``(SPI, CPI)`` — ``None`` where the divisor is unavailable."""
    spi = round(float(raw.ev / raw.pv), 3) if raw.pv is not None and raw.pv > 0 else None
    cpi = round(float(raw.ev / raw.ac), 3) if raw.ac > 0 else None
    return spi, cpi


def eac(raw: RawEVM) -> Decimal:
    """Estimate at Completion (BAC / CPI), falling back to BAC."""
    if raw.ev > 0 and raw.ac > 0:
        return raw.bac * raw.ac / raw.ev
    return raw.bac


def started(raw: RawEVM) -> bool:
    """Whether the scope has any earned value or actual cost yet."""
    return raw.ev > 0 or raw.ac > 0


# RAG thresholds on the worst available performance index.
GREEN_THRESHOLD = 0.95
AMBER_THRESHOLD = 0.85


def rag(spi: float | None, cpi: float | None, *, has_started: bool) -> str:
    """Return the RAG band from the worst available performance index."""
    if not has_started:
        return "not_started"
    indices = [idx for idx in (spi, cpi) if idx is not None]
    if not indices:
        return "unknown"
    worst = min(indices)
    if worst >= GREEN_THRESHOLD:
        return "green"
    if worst >= AMBER_THRESHOLD:
        return "amber"
    return "red"


def money(value: Decimal) -> str:
    """Format a Decimal as a fixed-2-decimal string."""
    return f"{value:.2f}"
