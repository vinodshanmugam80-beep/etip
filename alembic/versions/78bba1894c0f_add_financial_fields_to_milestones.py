"""add financial fields to milestones

Revision ID: 78bba1894c0f
Revises: 252b656da890
Create Date: 2026-09-26 13:35:32.038373
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "78bba1894c0f"
down_revision: str | None = "252b656da890"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Financial (billing) milestone fields. The three NOT NULL columns carry a
    # server_default so the migration is safe on tables that already hold rows;
    # the ORM supplies the value for new rows.
    op.add_column(
        "milestones",
        sa.Column("deliverable", sa.String(length=500), nullable=False, server_default=""),
    )
    op.add_column(
        "milestones",
        sa.Column("payment_amount", sa.Numeric(precision=18, scale=2), nullable=True),
    )
    op.add_column(
        "milestones",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
    )
    op.add_column(
        "milestones",
        sa.Column(
            "payment_status",
            sa.Enum(
                "not_applicable",
                "pending",
                "released",
                name="milestonepaymentstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
            server_default="not_applicable",
        ),
    )
    op.add_column("milestones", sa.Column("acceptance_instance_id", sa.Uuid(), nullable=True))
    op.add_column("milestones", sa.Column("paid_date", sa.Date(), nullable=True))
    op.create_index(
        op.f("ix_milestones_payment_status"),
        "milestones",
        ["payment_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_milestones_payment_status"), table_name="milestones")
    op.drop_column("milestones", "paid_date")
    op.drop_column("milestones", "acceptance_instance_id")
    op.drop_column("milestones", "payment_status")
    op.drop_column("milestones", "currency")
    op.drop_column("milestones", "payment_amount")
    op.drop_column("milestones", "deliverable")
