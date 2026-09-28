"""Pydantic v2 schemas for the Jira connector."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class JiraConfigUpsert(BaseModel):
    """Create or update the tenant's Jira connection."""

    base_url: str = Field(min_length=1, max_length=500)
    project_key: str = Field(min_length=1, max_length=50)
    user_email: str = Field(min_length=1, max_length=320)
    api_token: str = Field(default="", max_length=1000)
    webhook_secret: str = Field(default="", max_length=200)
    default_project_id: uuid.UUID | None = None
    is_enabled: bool = False


class JiraConfigResponse(BaseModel):
    """The tenant's Jira connection (the API token is never returned)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    base_url: str
    project_key: str
    user_email: str
    default_project_id: uuid.UUID | None
    is_enabled: bool
    api_token: str = Field(exclude=True, default="")
    webhook_secret: str = Field(exclude=True, default="")
    created_date: datetime
    version: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def token_set(self) -> bool:
        """Whether an API token is stored (its value stays hidden)."""
        return bool(self.api_token)


class ExternalLinkResponse(BaseModel):
    """A link between an ETIP entity and an external record."""

    model_config = ConfigDict(from_attributes=True)

    entity_type: str
    entity_id: uuid.UUID
    system: str
    external_key: str
    external_url: str


class WebhookResult(BaseModel):
    """Outcome of processing an inbound Jira webhook."""

    action: str  # created | updated | skipped
    task_id: uuid.UUID | None = None
    external_key: str = ""


class TestConnectionResult(BaseModel):
    """Result of verifying the stored Jira credentials."""

    ok: bool
    account_id: str = ""
    display_name: str = ""
    email: str = ""
    message: str = ""


class ImportRequest(BaseModel):
    """Request to bulk-import issues from Jira into ETIP tasks."""

    jql: str | None = Field(default=None, max_length=1000)
    max_results: int = Field(default=100, ge=1, le=1000)


class SyncResult(BaseModel):
    """Counts from a bulk import (or push) run."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    message: str = ""


class SyncLogResponse(BaseModel):
    """One Jira sync audit record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: str
    status: str
    summary: str
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    external_ref: str
    created_date: datetime
