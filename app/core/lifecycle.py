"""Shared lifecycle helpers.

A small, enum-agnostic status-transition validator reused by every aggregate
with a status lifecycle (portfolios, programs, and later projects). Each module
supplies its own transition table over its own status enum; the validation
logic lives here so it is written and tested once.
"""

from __future__ import annotations

import enum
from typing import TypeVar

from app.core.exceptions import ValidationError

StatusT = TypeVar("StatusT", bound=enum.Enum)


def validate_status_transition(
    transitions: dict[StatusT, set[StatusT]],
    current: StatusT,
    target: StatusT,
) -> None:
    """Reject an illegal status transition.

    :param transitions: Mapping of each status to the set of statuses it may
        move to. Statuses mapped to an empty set are terminal.
    :param current: The entity's current status.
    :param target: The requested new status.
    :raises ValidationError: If ``target`` is neither equal to ``current`` nor
        an allowed successor. Moving to the same status is always a no-op.
    """
    if target == current:
        return
    if target not in transitions.get(current, set()):
        raise ValidationError(
            f"Cannot change status from '{current.value}' to '{target.value}'.",
            code="illegal_status_transition",
            details={"from": current.value, "to": target.value},
        )
