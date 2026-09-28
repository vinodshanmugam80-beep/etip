"""Jira connector models.

``JiraConnection`` holds a tenant's Jira credentials and defaults (the API token is
never returned by the API). ``ExternalLink`` maps an ETIP record to its counterpart
in an external system (Jira issue key), so inbound webhooks and outbound pushes stay
idempotent instead of creating duplicates.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class JiraConnection(BaseEntity, TenantMixin):
    """A tenant's Jira Cloud connection (one per organization)."""

    __tablename__ = "jira_connections"

    base_url: Mapped[str] = mapped_column(String(500), default="")
    project_key: Mapped[str] = mapped_column(String(50), default="")
    user_email: Mapped[str] = mapped_column(String(320), default="")
    api_token: Mapped[str] = mapped_column(String(1000), default="")
    webhook_secret: Mapped[str] = mapped_column(String(200), default="")
    default_project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class ExternalLink(BaseEntity, TenantMixin):
    """Maps an ETIP entity to a record in an external system (e.g. a Jira issue)."""

    __tablename__ = "external_links"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "system",
            "entity_type",
            "entity_id",
            name="uq_external_link_entity",
        ),
    )

    system: Mapped[str] = mapped_column(String(50), default="jira", index=True)
    entity_type: Mapped[str] = mapped_column(String(50), default="task")
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    external_key: Mapped[str] = mapped_column(String(100), default="", index=True)
    external_id: Mapped[str] = mapped_column(String(100), default="")
    external_url: Mapped[str] = mapped_column(String(500), default="")


class SyncDirection(enum.StrEnum):
    """Direction of a Jira sync operation."""

    INBOUND = "inbound"  # Jira → ETIP (webhook)
    IMPORT = "import"  # Jira → ETIP (bulk pull)
    OUTBOUND = "outbound"  # ETIP → Jira (push)
    TEST = "test"  # connection test


class SyncStatus(enum.StrEnum):
    """Outcome of a Jira sync operation."""

    SUCCESS = "success"
    ERROR = "error"


class JiraSyncLog(BaseEntity, TenantMixin):
    """An audit record of one Jira sync operation (import / push / webhook / test)."""

    __tablename__ = "jira_sync_logs"

    direction: Mapped[SyncDirection] = mapped_column(enum_column(SyncDirection), index=True)
    status: Mapped[SyncStatus] = mapped_column(enum_column(SyncStatus), index=True)
    summary: Mapped[str] = mapped_column(String(1000), default="")
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    external_ref: Mapped[str] = mapped_column(String(200), default="")
