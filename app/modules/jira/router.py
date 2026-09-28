"""Jira connector routes.

Config and push require ``integration:manage``. The inbound webhook is public
(pre-authentication) and guarded by the connection's shared secret; the tenant is
identified by the ``organization_id`` in the URL.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query

from app.core.dependencies import JiraServiceDep, UowDep, require_permission
from app.core.exceptions import NotFoundError
from app.modules.jira.schemas import (
    ExternalLinkResponse,
    ImportRequest,
    JiraConfigResponse,
    JiraConfigUpsert,
    SyncLogResponse,
    SyncResult,
    TestConnectionResult,
    WebhookResult,
)
from app.modules.jira.service import JiraService

router = APIRouter(prefix="/integrations/jira", tags=["Jira Connector"])


@router.put(
    "/config",
    response_model=JiraConfigResponse,
    dependencies=[Depends(require_permission("integration:manage"))],
    summary="Create or update the tenant's Jira connection",
)
def upsert_jira_config(
    payload: JiraConfigUpsert, service: JiraServiceDep, uow: UowDep
) -> JiraConfigResponse:
    """Configure the organization's Jira connection."""
    conn = service.upsert_config(payload)
    uow.commit()
    return JiraConfigResponse.model_validate(conn)


@router.get(
    "/config",
    response_model=JiraConfigResponse,
    dependencies=[Depends(require_permission("integration:manage"))],
    summary="Get the tenant's Jira connection",
)
def get_jira_config(service: JiraServiceDep) -> JiraConfigResponse:
    """Return the Jira connection (token hidden)."""
    conn = service.get_config()
    if conn is None:
        raise NotFoundError("No Jira connection for this organization.")
    return JiraConfigResponse.model_validate(conn)


@router.post(
    "/tasks/{task_id}/push",
    response_model=WebhookResult,
    dependencies=[Depends(require_permission("integration:manage"))],
    summary="Push an ETIP task to Jira (create or update the issue)",
)
def push_task(task_id: uuid.UUID, service: JiraServiceDep, uow: UowDep) -> WebhookResult:
    """Create or update the Jira issue linked to this task."""
    result = service.push_task(task_id)
    uow.commit()
    return WebhookResult.model_validate(result)


@router.post(
    "/test",
    response_model=TestConnectionResult,
    dependencies=[Depends(require_permission("integration:manage"))],
    summary="Verify the stored Jira credentials",
)
def test_connection(service: JiraServiceDep, uow: UowDep) -> TestConnectionResult:
    """Call Jira's /myself to confirm the connection works."""
    result = service.test_connection()
    uow.commit()
    return result


@router.post(
    "/import",
    response_model=SyncResult,
    dependencies=[Depends(require_permission("integration:manage"))],
    summary="Bulk-import Jira issues into ETIP tasks",
)
def import_issues(service: JiraServiceDep, uow: UowDep, payload: ImportRequest) -> SyncResult:
    """Pull issues from Jira (JQL, default: the configured project) and upsert tasks."""
    result = service.import_issues(jql=payload.jql, max_results=payload.max_results)
    uow.commit()
    return result


@router.get(
    "/links",
    response_model=list[ExternalLinkResponse],
    dependencies=[Depends(require_permission("integration:read"))],
    summary="List ETIP↔Jira links",
)
def list_links(service: JiraServiceDep) -> list[ExternalLinkResponse]:
    """Return the tenant's synced task↔issue links."""
    return [ExternalLinkResponse.model_validate(x) for x in service.list_links()]


@router.get(
    "/sync-log",
    response_model=list[SyncLogResponse],
    dependencies=[Depends(require_permission("integration:read"))],
    summary="Recent Jira sync activity",
)
def sync_log(service: JiraServiceDep) -> list[SyncLogResponse]:
    """Return the most recent Jira sync audit records."""
    return [SyncLogResponse.model_validate(x) for x in service.list_sync_logs()]


@router.post(
    "/webhook/{organization_id}",
    response_model=WebhookResult,
    summary="Inbound Jira webhook — upserts the matching ETIP task",
)
def jira_webhook(
    organization_id: uuid.UUID,
    uow: UowDep,
    secret: str = Query(...),
    payload: dict[str, Any] = Body(...),
) -> WebhookResult:
    """Receive a Jira issue event and upsert the corresponding ETIP task."""
    service = JiraService(uow)
    result = service.handle_webhook(organization_id, secret, payload)
    uow.commit()
    return WebhookResult.model_validate(result)
