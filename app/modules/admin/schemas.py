"""Pydantic v2 schemas for the Administration module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    """A single audit-log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    entity_type: str
    entity_id: uuid.UUID | None
    action: str
    summary: str
    created_date: datetime


class PaginatedAuditLogs(BaseModel):
    """A page of audit-log entries with total-count metadata."""

    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


class AdminOverviewResponse(BaseModel):
    """Governance counts for the tenant."""

    total_users: int
    active_users: int
    roles: int
    projects: int
    portfolios: int
    audit_entries: int
    permission_catalogue_size: int


class DiagnosticsResponse(BaseModel):
    """System diagnostics for operators."""

    status: str
    database: str
    app_name: str
    app_env: str
    server_time: datetime


class RoleReconcileItem(BaseModel):
    """Per-role outcome of a permission reconciliation."""

    role: str
    grants_added: int


class ReconcileResult(BaseModel):
    """Outcome of reconciling the permission catalogue for the tenant."""

    permissions_created: int
    total_grants_added: int
    roles: list[RoleReconcileItem]
    detail: str
