"""user management: must_change_password

Revision ID: 466e8c2bd60d
Revises: 7d9a1c13815f
Create Date: 2026-07-28 11:41:55.177322
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '466e8c2bd60d'
down_revision: str | None = '7d9a1c13815f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add with a server default so existing rows backfill safely on populated
    # tables, then drop the server default so the application-side default
    # (False) governs subsequent inserts.
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # SQLite cannot ALTER a column to drop its default; the backfill default is
    # harmless there. On PostgreSQL we drop it so the ORM default governs.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("users", "must_change_password", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
