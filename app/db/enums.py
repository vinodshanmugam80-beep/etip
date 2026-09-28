"""Shared column helpers.

``enum_column`` builds a portable, string-backed :class:`~sqlalchemy.Enum`
column so enum values persist identically on PostgreSQL and on the SQLite
database used in tests (avoiding native ENUM types and their migrations).
"""

from __future__ import annotations

import enum

from sqlalchemy import Enum


def enum_column(enum_type: type[enum.Enum]) -> Enum:
    """Return a portable string-backed ``Enum`` column type for ``enum_type``.

    Values are stored using each member's ``value`` (e.g. ``"active"``) rather
    than its name, keeping the API contract and the database representation the
    same.
    """
    return Enum(
        enum_type,
        native_enum=False,
        length=20,
        values_callable=lambda e: [member.value for member in e],
    )
