"""Integration tests for the Jira connector.

The Jira REST calls are mocked, so inbound webhook mapping and outbound push are
exercised without a live Jira instance.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.modules.jira.client as jira_client
from tests.conftest import _login

CFG = "/api/v1/integrations/jira/config"
PROJECTS = "/api/v1/projects"
TASKS = "/api/v1/tasks"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
SLUG = "contoso-ltd"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str]) -> str:
    return client.post(PROJECTS, headers=h, json={"name": "Sync Project", "code": "SYNC"}).json()[
        "id"
    ]


def _config(client: TestClient, h: dict[str, str], project_id: str, **over: object) -> dict:
    body = {
        "base_url": "https://acme.atlassian.net",
        "project_key": "ETIP",
        "user_email": "bot@acme.com",
        "api_token": "tok",
        "webhook_secret": "whsec",
        "default_project_id": project_id,
        "is_enabled": True,
    }
    body.update(over)
    return client.put(CFG, headers=h, json=body).json()


def _issue(key: str, summary: str, status: str) -> dict:
    return {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "id": "10001",
            "key": key,
            "fields": {"summary": summary, "description": "d", "status": {"name": status}},
        },
    }


def test_config_hides_token(client: TestClient, admin_headers: dict[str, str]) -> None:
    pid = _project(client, admin_headers)
    body = _config(client, admin_headers, pid)
    assert body["token_set"] is True and "api_token" not in body and body["project_key"] == "ETIP"


def test_inbound_webhook_creates_then_updates(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    pid = _project(client, admin_headers)
    cfg = _config(client, admin_headers, pid)
    org = cfg["organization_id"]
    r = client.post(
        f"/api/v1/integrations/jira/webhook/{org}",
        params={"secret": "whsec"},
        json=_issue("ETIP-1", "Fix login", "To Do"),
    )
    assert r.status_code == 200 and r.json()["action"] == "created"
    tid = r.json()["task_id"]
    assert client.get(f"{TASKS}/{tid}", headers=admin_headers).json()["title"] == "Fix login"
    # Same key → updates the same task, no duplicate.
    r2 = client.post(
        f"/api/v1/integrations/jira/webhook/{org}",
        params={"secret": "whsec"},
        json=_issue("ETIP-1", "Fix login page", "In Progress"),
    )
    assert r2.json()["action"] == "updated" and r2.json()["task_id"] == tid
    task = client.get(f"{TASKS}/{tid}", headers=admin_headers).json()
    assert task["title"] == "Fix login page" and task["status"] == "in_progress"
    assert client.get(TASKS, headers=admin_headers, params={"project_id": pid}).json()["total"] == 1


def test_webhook_rejects_bad_secret(client: TestClient, admin_headers: dict[str, str]) -> None:
    pid = _project(client, admin_headers)
    org = _config(client, admin_headers, pid)["organization_id"]
    r = client.post(
        f"/api/v1/integrations/jira/webhook/{org}",
        params={"secret": "wrong"},
        json=_issue("ETIP-9", "x", "To Do"),
    )
    assert r.status_code == 401


def test_outbound_push_creates_then_updates(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _project(client, admin_headers)
    _config(client, admin_headers, pid)
    task_id = client.post(
        TASKS, headers=admin_headers, json={"project_id": pid, "title": "Ship feature"}
    ).json()["id"]

    calls: list[tuple[str, str]] = []

    def fake(conn: object, method: str, path: str, payload: object = None) -> dict:
        calls.append((method, path))
        return {"id": "20001", "key": "ETIP-42"}

    monkeypatch.setattr(jira_client, "jira_request", fake)
    r = client.post(f"/api/v1/integrations/jira/tasks/{task_id}/push", headers=admin_headers)
    assert (
        r.status_code == 200
        and r.json()["action"] == "created"
        and r.json()["external_key"] == "ETIP-42"
    )
    assert calls[-1][0] == "POST"
    # Push again → updates the existing issue (PUT), no new link.
    r2 = client.post(f"/api/v1/integrations/jira/tasks/{task_id}/push", headers=admin_headers)
    assert r2.json()["action"] == "updated" and r2.json()["external_key"] == "ETIP-42"
    assert any(m == "PUT" and "ETIP-42" in p for m, p in calls)


def test_config_requires_permission(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    pid = _project(client, admin_headers)
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "jira@contoso.com",
            "full_name": "J M",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(
        client, {"organization_slug": SLUG, "email": "jira@contoso.com", "password": PW}
    )
    member = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.put(CFG, headers=member, json=_config_body(pid)).status_code == 403


def _config_body(pid: str) -> dict:
    return {
        "base_url": "https://acme.atlassian.net",
        "project_key": "ETIP",
        "user_email": "bot@acme.com",
        "api_token": "tok",
        "webhook_secret": "s",
        "default_project_id": pid,
        "is_enabled": True,
    }


def _issue_prio(key: str, priority: str) -> dict:
    return {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "id": "10007",
            "key": key,
            "fields": {
                "summary": "P",
                "description": "d",
                "status": {"name": "To Do"},
                "priority": {"name": priority},
            },
        },
    }


def test_priority_mapping_inbound_and_outbound(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _project(client, admin_headers)
    org = _config(client, admin_headers, pid)["organization_id"]
    # Inbound: Jira "Highest" -> ETIP "critical".
    r = client.post(
        f"/api/v1/integrations/jira/webhook/{org}",
        params={"secret": "whsec"},
        json=_issue_prio("ETIP-7", "Highest"),
    )
    tid = r.json()["task_id"]
    assert client.get(f"{TASKS}/{tid}", headers=admin_headers).json()["priority"] == "critical"

    # Outbound: task priority is included in the pushed Jira fields.
    payloads: list[dict] = []

    def fake(conn: object, method: str, path: str, payload: dict | None = None) -> dict:
        payloads.append(payload or {})
        return {"id": "1", "key": "ETIP-70"}

    monkeypatch.setattr(jira_client, "jira_request", fake)
    client.post(f"/api/v1/integrations/jira/tasks/{tid}/push", headers=admin_headers)
    field_payloads = [p for p in payloads if p and "fields" in p]
    assert field_payloads[-1]["fields"]["priority"]["name"] == "Highest"


def test_outbound_push_applies_status_transition(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _project(client, admin_headers)
    _config(client, admin_headers, pid)
    tid = client.post(
        TASKS, headers=admin_headers, json={"project_id": pid, "title": "Transition me"}
    ).json()["id"]
    calls: list[tuple[str, str, object]] = []

    def fake(conn: object, method: str, path: str, payload: object = None) -> dict:
        calls.append((method, path, payload))
        if method == "GET" and path.endswith("/transitions"):
            return {"transitions": [{"id": "21", "name": "Start", "to": {"name": "In Progress"}}]}
        if method == "POST" and path == "/rest/api/2/issue":
            return {"id": "1", "key": "ETIP-50"}
        return {}

    monkeypatch.setattr(jira_client, "jira_request", fake)
    client.post(f"/api/v1/integrations/jira/tasks/{tid}/push", headers=admin_headers)  # create link
    client.patch(f"{TASKS}/{tid}", headers=admin_headers, json={"status": "in_progress"})
    calls.clear()
    client.post(
        f"/api/v1/integrations/jira/tasks/{tid}/push", headers=admin_headers
    )  # update + transition
    assert any(m == "GET" and p.endswith("/transitions") for m, p, _ in calls)
    posted = [(p, pl) for m, p, pl in calls if m == "POST" and p.endswith("/transitions")]
    assert posted and posted[-1][1] == {"transition": {"id": "21"}}


def test_inbound_assignee_mapping(client: TestClient, admin_headers: dict[str, str]) -> None:
    pid = _project(client, admin_headers)
    org = _config(client, admin_headers, pid)["organization_id"]
    admin_id = next(
        u["id"]
        for u in client.get(USERS, headers=admin_headers).json()["items"]
        if u["email"] == "admin@contoso.com"
    )
    payload = {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "id": "10020",
            "key": "ETIP-20",
            "fields": {
                "summary": "Assigned",
                "description": "d",
                "status": {"name": "To Do"},
                "assignee": {"emailAddress": "admin@contoso.com"},
            },
        },
    }
    r = client.post(
        f"/api/v1/integrations/jira/webhook/{org}", params={"secret": "whsec"}, json=payload
    )
    tid = r.json()["task_id"]
    assert (
        client.get(f"{TASKS}/{tid}", headers=admin_headers).json()["assignee_user_id"] == admin_id
    )


def _issue_row(key: str, summary: str, status: str = "To Do") -> dict:
    return {
        "id": key.split("-")[-1],
        "key": key,
        "fields": {"summary": summary, "description": "d", "status": {"name": status}},
    }


def test_connection_verifies_credentials(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _project(client, admin_headers)
    _config(client, admin_headers, pid)

    def fake(conn: object, method: str, path: str, payload: object = None) -> dict:
        assert path.endswith("/myself")
        return {"accountId": "5b10", "displayName": "ETIP Bot", "emailAddress": "bot@acme.com"}

    monkeypatch.setattr(jira_client, "jira_request", fake)
    r = client.post("/api/v1/integrations/jira/test", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["display_name"] == "ETIP Bot"

    # The test is recorded in the sync log.
    logs = client.get("/api/v1/integrations/jira/sync-log", headers=admin_headers).json()
    assert any(x["direction"] == "test" and x["status"] == "success" for x in logs)


def test_import_creates_then_updates(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _project(client, admin_headers)
    _config(client, admin_headers, pid)
    rows = [_issue_row("ETIP-101", "Import one"), _issue_row("ETIP-102", "Import two")]

    def fake(conn: object, method: str, path: str, payload: object = None) -> dict:
        if "/search" in path:
            return {"issues": rows, "total": len(rows), "startAt": 0, "maxResults": 50}
        return {}

    monkeypatch.setattr(jira_client, "jira_request", fake)
    r = client.post(
        "/api/v1/integrations/jira/import", headers=admin_headers, json={"max_results": 50}
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2 and r.json()["updated"] == 0
    assert client.get(TASKS, headers=admin_headers, params={"project_id": pid}).json()["total"] == 2

    # Links are listed, and a re-import updates rather than duplicates.
    links = client.get("/api/v1/integrations/jira/links", headers=admin_headers).json()
    assert {x["external_key"] for x in links} == {"ETIP-101", "ETIP-102"}
    rows[0]["fields"]["summary"] = "Import one (edited)"
    r2 = client.post(
        "/api/v1/integrations/jira/import", headers=admin_headers, json={"max_results": 50}
    )
    assert r2.json()["updated"] == 2 and r2.json()["created"] == 0
    assert client.get(TASKS, headers=admin_headers, params={"project_id": pid}).json()["total"] == 2


def test_import_requires_enabled_connection(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    # No connection configured yet → 422.
    r = client.post("/api/v1/integrations/jira/import", headers=admin_headers, json={})
    assert r.status_code == 422
