"""Jira connector service.

Two directions on top of ETIP's open hooks:

* **Inbound** — :meth:`handle_webhook` receives a Jira issue event and upserts the
  matching ETIP task (idempotent via :class:`ExternalLink`).
* **Outbound** — :meth:`push_task` creates or updates the Jira issue for an ETIP
  task and records the link.

Config management is tenant-scoped; the webhook runs pre-authentication and is
guarded by a per-connection shared secret.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.exceptions import AuthenticationError, NotFoundError, ValidationError
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.jira import client
from app.modules.jira.models import (
    ExternalLink,
    JiraConnection,
    JiraSyncLog,
    SyncDirection,
    SyncStatus,
)
from app.modules.jira.repository import (
    ExternalLinkRepository,
    JiraConnectionRepository,
    JiraSyncLogRepository,
)
from app.modules.jira.schemas import JiraConfigUpsert, SyncResult, TestConnectionResult
from app.modules.task.models import Task, TaskPriority, TaskStatus
from app.modules.task.repository import TaskRepository

_SYSTEM = "jira"
_CONFIG_FIELDS = (
    "base_url",
    "project_key",
    "user_email",
    "webhook_secret",
    "default_project_id",
    "is_enabled",
)

# Jira status name (lower-cased) -> ETIP task status.
_STATUS_MAP = {
    "to do": TaskStatus.TODO,
    "open": TaskStatus.TODO,
    "backlog": TaskStatus.TODO,
    "in progress": TaskStatus.IN_PROGRESS,
    "in review": TaskStatus.IN_REVIEW,
    "review": TaskStatus.IN_REVIEW,
    "blocked": TaskStatus.BLOCKED,
    "done": TaskStatus.DONE,
    "closed": TaskStatus.DONE,
    "resolved": TaskStatus.DONE,
    "cancelled": TaskStatus.CANCELLED,
    "canceled": TaskStatus.CANCELLED,
}
# Jira priority name (lower-cased) -> ETIP task priority.
_PRIORITY_MAP = {
    "highest": TaskPriority.CRITICAL,
    "critical": TaskPriority.CRITICAL,
    "high": TaskPriority.HIGH,
    "medium": TaskPriority.MEDIUM,
    "low": TaskPriority.LOW,
    "lowest": TaskPriority.LOW,
}
# ETIP task status -> Jira status display name (for outbound transitions).
_TASK_STATUS_TO_JIRA = {
    TaskStatus.TODO: "To Do",
    TaskStatus.IN_PROGRESS: "In Progress",
    TaskStatus.IN_REVIEW: "In Review",
    TaskStatus.BLOCKED: "Blocked",
    TaskStatus.DONE: "Done",
    TaskStatus.CANCELLED: "Cancelled",
}
# ETIP task priority -> Jira priority name (for outbound push).
_TASK_PRIORITY_TO_JIRA = {
    TaskPriority.CRITICAL: "Highest",
    TaskPriority.HIGH: "High",
    TaskPriority.MEDIUM: "Medium",
    TaskPriority.LOW: "Low",
}


class JiraService:
    """Two-way Jira synchronization for the tenant."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        organization_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.connections = JiraConnectionRepository(session)
        self.links = ExternalLinkRepository(session)
        self.logs = JiraSyncLogRepository(session)
        self.tasks = TaskRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------ config
    def upsert_config(self, payload: JiraConfigUpsert) -> JiraConnection:
        assert self._org_id is not None
        conn = self.connections.get_for_org(self._org_id)
        creating = conn is None
        if conn is None:
            conn = JiraConnection(organization_id=self._org_id, created_by=self._actor_id)
        for field in _CONFIG_FIELDS:
            setattr(conn, field, getattr(payload, field))
        if payload.api_token:
            conn.api_token = payload.api_token
        conn.modified_by = self._actor_id
        conn = self.connections.add(conn) if creating else self.connections.update(conn)
        self._uow.record_audit(
            "JiraConnection",
            conn.id,
            "upsert",
            "Updated Jira connection",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return conn

    def get_config(self) -> JiraConnection | None:
        assert self._org_id is not None
        return self.connections.get_for_org(self._org_id)

    # ------------------------------------------------------------------ inbound
    def _resolve_assignee(
        self, organization_id: uuid.UUID, fields: dict[str, Any]
    ) -> uuid.UUID | None:
        email = ((fields.get("assignee") or {}).get("emailAddress") or "").lower().strip()
        if not email:
            return None
        user = self.users.get_by_email(organization_id, email)
        return user.id if user is not None else None

    def _upsert_task_from_issue(
        self, organization_id: uuid.UUID, conn: JiraConnection, issue: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or update the ETIP task mapped from one Jira issue (idempotent)."""
        key = issue.get("key")
        fields = issue.get("fields") or {}
        if not key:
            return {"action": "skipped", "task_id": None, "external_key": ""}

        title = fields.get("summary") or key
        description = fields.get("description") or ""
        if not isinstance(description, str):
            description = ""
        status_name = ((fields.get("status") or {}).get("name") or "").lower()
        status = _STATUS_MAP.get(status_name, TaskStatus.TODO)
        prio_name = ((fields.get("priority") or {}).get("name") or "").lower()
        priority = _PRIORITY_MAP.get(prio_name, TaskPriority.MEDIUM)
        assignee_id = self._resolve_assignee(organization_id, fields)

        link = self.links.by_external_key(organization_id, _SYSTEM, key)
        if link is not None:
            task = self.tasks.get(link.entity_id, organization_id=organization_id)
            if task is not None:
                task.title, task.description, task.status = title[:300], description[:4000], status
                task.priority = priority
                if assignee_id is not None:
                    task.assignee_user_id = assignee_id
                task.modified_by = self._actor_id
                self.tasks.update(task)
            return {"action": "updated", "task_id": link.entity_id, "external_key": key}

        if conn.default_project_id is None:
            raise ValidationError("Set a default project on the Jira connection to import issues.")
        task = Task(
            organization_id=organization_id,
            project_id=conn.default_project_id,
            number=self.tasks.next_number(conn.default_project_id),
            title=title[:300],
            description=description[:4000],
            status=status,
            priority=priority,
            assignee_user_id=assignee_id,
        )
        task = self.tasks.add(task)
        self.links.add(
            ExternalLink(
                organization_id=organization_id,
                system=_SYSTEM,
                entity_type="task",
                entity_id=task.id,
                external_key=key,
                external_id=str(issue.get("id") or ""),
                external_url=f"{conn.base_url.rstrip('/')}/browse/{key}",
            )
        )
        return {"action": "created", "task_id": task.id, "external_key": key}

    def handle_webhook(
        self, organization_id: uuid.UUID, secret: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        conn = self.connections.find_enabled_unscoped(organization_id)
        if conn is None:
            raise NotFoundError("Jira is not enabled for this organization.")
        if not conn.webhook_secret or secret != conn.webhook_secret:
            raise AuthenticationError("Invalid Jira webhook secret.")
        issue = payload.get("issue") or {}
        result = self._upsert_task_from_issue(organization_id, conn, issue)
        counts = {"created": 0, "updated": 0, "skipped": 0}
        if result["action"] in counts:
            counts[result["action"]] = 1
        self._log(
            organization_id, SyncDirection.INBOUND, SyncStatus.SUCCESS,
            f"Webhook {result['action']} {result['external_key']}".strip(),
            counts, external_ref=result["external_key"],
        )
        return result

    # ----------------------------------------------------------------- outbound
    def _apply_transition(self, conn: JiraConnection, key: str, task_status: TaskStatus) -> None:
        """Transition the Jira issue to the status mapped from the ETIP task."""
        want = _TASK_STATUS_TO_JIRA.get(task_status)
        if not want:
            return
        data = client.jira_request(conn, "GET", f"/rest/api/2/issue/{key}/transitions")
        for transition in data.get("transitions", []):
            to_name = ((transition.get("to") or {}).get("name") or "").lower()
            if to_name == want.lower():
                client.jira_request(
                    conn,
                    "POST",
                    f"/rest/api/2/issue/{key}/transitions",
                    {"transition": {"id": transition.get("id")}},
                )
                return

    def push_task(self, task_id: uuid.UUID) -> dict[str, Any]:
        assert self._org_id is not None
        conn = self.connections.find_enabled_unscoped(self._org_id)
        if conn is None:
            raise ValidationError("Jira is not enabled for this organization.")
        task = self.tasks.get(task_id, organization_id=self._org_id)
        if task is None:
            raise NotFoundError("Task not found.")
        fields = {
            "summary": task.title,
            "description": task.description,
            "priority": {"name": _TASK_PRIORITY_TO_JIRA.get(task.priority, "Medium")},
        }
        link = self.links.by_entity(self._org_id, _SYSTEM, "task", task_id)
        if link is not None:
            client.jira_request(
                conn, "PUT", f"/rest/api/2/issue/{link.external_key}", {"fields": fields}
            )
            self._apply_transition(conn, link.external_key, task.status)
            return {"action": "updated", "task_id": task_id, "external_key": link.external_key}
        create_fields = {
            **fields,
            "project": {"key": conn.project_key},
            "issuetype": {"name": "Task"},
        }
        resp = client.jira_request(conn, "POST", "/rest/api/2/issue", {"fields": create_fields})
        key = resp.get("key", "")
        self.links.add(
            ExternalLink(
                organization_id=self._org_id,
                system=_SYSTEM,
                entity_type="task",
                entity_id=task_id,
                external_key=key,
                external_id=str(resp.get("id") or ""),
                external_url=f"{conn.base_url.rstrip('/')}/browse/{key}",
            )
        )
        result = {"action": "created", "task_id": task_id, "external_key": key}
        self._log(
            self._org_id, SyncDirection.OUTBOUND, SyncStatus.SUCCESS,
            f"Pushed task as {key}", {"created": 1}, external_ref=key,
        )
        return result

    # -------------------------------------------------------------- test / pull
    def _require_enabled_conn(self) -> JiraConnection:
        assert self._org_id is not None
        conn = self.connections.find_enabled_unscoped(self._org_id)
        if conn is None:
            raise ValidationError("Jira is not enabled for this organization.")
        return conn

    def test_connection(self) -> TestConnectionResult:
        """Verify the stored credentials by calling Jira's /myself endpoint."""
        conn = self._require_enabled_conn()
        assert self._org_id is not None
        try:
            me = client.get_myself(conn)
        except ValidationError as exc:
            self._log(
                self._org_id, SyncDirection.TEST, SyncStatus.ERROR, str(exc.message), {}
            )
            return TestConnectionResult(ok=False, message=exc.message)
        self._log(
            self._org_id, SyncDirection.TEST, SyncStatus.SUCCESS,
            "Connection verified", {},
            external_ref=str(me.get("accountId") or ""),
        )
        return TestConnectionResult(
            ok=True,
            account_id=str(me.get("accountId") or ""),
            display_name=str(me.get("displayName") or ""),
            email=str(me.get("emailAddress") or ""),
            message="Connection verified.",
        )

    def import_issues(self, *, jql: str | None = None, max_results: int = 100) -> SyncResult:
        """Bulk-import issues from Jira into ETIP tasks (idempotent, paginated)."""
        conn = self._require_enabled_conn()
        assert self._org_id is not None
        if conn.default_project_id is None:
            raise ValidationError("Set a default project on the Jira connection to import issues.")
        query = jql or f"project = {conn.project_key} ORDER BY created DESC"
        created = updated = skipped = failed = 0
        start_at = 0
        page_size = 50
        while created + updated + skipped + failed < max_results:
            want = min(page_size, max_results - (created + updated + skipped + failed))
            data = client.search_issues(conn, query, start_at=start_at, max_results=want)
            issues = data.get("issues") or []
            if not issues:
                break
            for issue in issues:
                try:
                    action = self._upsert_task_from_issue(self._org_id, conn, issue)["action"]
                except ValidationError:
                    failed += 1
                    continue
                if action == "created":
                    created += 1
                elif action == "updated":
                    updated += 1
                else:
                    skipped += 1
            start_at += len(issues)
            if start_at >= int(data.get("total") or 0):
                break
        message = f"Imported {created} new, {updated} updated from Jira."
        self._log(
            self._org_id, SyncDirection.IMPORT, SyncStatus.SUCCESS, message,
            {"created": created, "updated": updated, "skipped": skipped, "failed": failed},
            external_ref=conn.project_key,
        )
        return SyncResult(
            created=created, updated=updated, skipped=skipped, failed=failed, message=message
        )

    def list_links(self, *, limit: int = 100, offset: int = 0) -> list[ExternalLink]:
        assert self._org_id is not None
        return list(self.links.list_for_org(self._org_id, _SYSTEM, limit=limit, offset=offset))

    def list_sync_logs(self, *, limit: int = 50) -> list[JiraSyncLog]:
        assert self._org_id is not None
        return list(self.logs.recent(self._org_id, limit=limit))

    def _log(
        self,
        organization_id: uuid.UUID,
        direction: SyncDirection,
        status: SyncStatus,
        summary: str,
        counts: dict[str, int],
        *,
        external_ref: str = "",
    ) -> None:
        self.logs.add(
            JiraSyncLog(
                organization_id=organization_id,
                direction=direction,
                status=status,
                summary=summary[:1000],
                created_count=counts.get("created", 0),
                updated_count=counts.get("updated", 0),
                skipped_count=counts.get("skipped", 0),
                failed_count=counts.get("failed", 0),
                external_ref=external_ref[:200],
                created_by=self._actor_id,
            )
        )
