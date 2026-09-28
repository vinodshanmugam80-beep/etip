"""Integration tests for the Issue Management module.

Covers issue CRUD, the project reference, task-link and assignee validation, the
reporter stamp, the status workflow with reopen and resolved-date handling, the
project ``issue_count`` rollup (open issues), search/filter, the issue summary,
the project→issue cascade, and RBAC (members may raise and work issues).
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

ISSUES = "/api/v1/issues"
PROJECTS = "/api/v1/projects"
TASKS = "/api/v1/tasks"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str = "PR") -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _task(client: TestClient, h: dict[str, str], project_id: str, title: str = "Task item") -> dict:
    r = client.post(TASKS, headers=h, json={"project_id": project_id, "title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _issue(
    client: TestClient,
    h: dict[str, str],
    project_id: str,
    title: str = "Something broke",
    **overrides: object,
) -> dict:
    body: dict[str, object] = {"project_id": project_id, "title": title}
    body.update(overrides)
    r = client.post(ISSUES, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_defaults_and_reporter(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    issue = _issue(client, admin_headers, proj["id"])
    assert issue["status"] == "open"
    assert issue["number"] >= 1
    assert issue["reporter_user_id"] is not None  # stamped with the actor


def test_create_requires_project(client: TestClient, admin_headers: dict[str, str]) -> None:
    r = client.post(
        ISSUES,
        headers=admin_headers,
        json={"project_id": str(uuid.uuid4()), "title": "Orphan issue"},
    )
    assert r.status_code == 404


def test_task_link_validation(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj_a = _project(client, admin_headers, code="PRA")
    proj_b = _project(client, admin_headers, code="PRB")
    task_b = _task(client, admin_headers, proj_b["id"])

    # Unknown task.
    unknown = client.post(
        ISSUES,
        headers=admin_headers,
        json={"project_id": proj_a["id"], "title": "Xx", "task_id": str(uuid.uuid4())},
    )
    assert unknown.status_code == 404

    # Task belongs to a different project.
    mismatch = client.post(
        ISSUES,
        headers=admin_headers,
        json={"project_id": proj_a["id"], "title": "Xx", "task_id": task_b["id"]},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "task_project_mismatch"


def test_issue_count_rollup(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a = _issue(client, admin_headers, proj["id"], title="Aa")
    _issue(client, admin_headers, proj["id"], title="Bb")

    refreshed = client.get(f"{PROJECTS}/{proj['id']}", headers=admin_headers).json()
    assert refreshed["issue_count"] == 2  # both open

    # Closing one drops the open count.
    client.patch(f"{ISSUES}/{a['id']}", headers=admin_headers, json={"status": "closed"})
    after_close = client.get(f"{PROJECTS}/{proj['id']}", headers=admin_headers).json()
    assert after_close["issue_count"] == 1

    # A resolved (but not closed) issue still counts as open.
    b_list = client.get(
        ISSUES,
        headers=admin_headers,
        params={"project_id": proj["id"], "status": "open"},
    ).json()
    other_id = b_list["items"][0]["id"]
    client.patch(f"{ISSUES}/{other_id}", headers=admin_headers, json={"status": "resolved"})
    after_resolve = client.get(f"{PROJECTS}/{proj['id']}", headers=admin_headers).json()
    assert after_resolve["issue_count"] == 1


def test_status_workflow_and_resolved_date(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    issue = _issue(client, admin_headers, proj["id"])
    iid = issue["id"]

    prog = client.patch(f"{ISSUES}/{iid}", headers=admin_headers, json={"status": "in_progress"})
    assert prog.status_code == 200

    resolved = client.patch(
        f"{ISSUES}/{iid}",
        headers=admin_headers,
        json={"status": "resolved", "resolution": "Patched"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved_date"] is not None

    # Resolved cannot jump straight back to open.
    assert (
        client.patch(f"{ISSUES}/{iid}", headers=admin_headers, json={"status": "open"}).status_code
        == 422
    )

    # Reopening to in_progress clears the resolved date.
    reopened = client.patch(
        f"{ISSUES}/{iid}", headers=admin_headers, json={"status": "in_progress"}
    )
    assert reopened.status_code == 200
    assert reopened.json()["resolved_date"] is None

    # Close, then reopen from closed.
    client.patch(f"{ISSUES}/{iid}", headers=admin_headers, json={"status": "closed"})
    assert (
        client.patch(
            f"{ISSUES}/{iid}", headers=admin_headers, json={"status": "in_progress"}
        ).status_code
        == 200
    )


def test_search_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    task = _task(client, admin_headers, proj["id"])
    _issue(
        client,
        admin_headers,
        proj["id"],
        title="Crash",
        severity="critical",
        issue_type="bug",
        task_id=task["id"],
    )
    _issue(
        client,
        admin_headers,
        proj["id"],
        title="Typo",
        severity="low",
        issue_type="improvement",
    )

    crit = client.get(
        ISSUES,
        headers=admin_headers,
        params={"project_id": proj["id"], "severity": "critical"},
    ).json()
    assert crit["total"] == 1 and crit["items"][0]["title"] == "Crash"
    by_task = client.get(ISSUES, headers=admin_headers, params={"task_id": task["id"]}).json()
    assert by_task["total"] == 1
    bugs = client.get(ISSUES, headers=admin_headers, params={"issue_type": "improvement"}).json()
    assert bugs["total"] == 1


def test_issue_summary(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a = _issue(client, admin_headers, proj["id"], title="Aa")
    _issue(client, admin_headers, proj["id"], title="Bb")
    _issue(client, admin_headers, proj["id"], title="Cc")
    client.patch(f"{ISSUES}/{a['id']}", headers=admin_headers, json={"status": "closed"})

    summary = client.get(f"{PROJECTS}/{proj['id']}/issue-summary", headers=admin_headers).json()
    assert summary["total_count"] == 3
    assert summary["open_count"] == 2
    counts = {c["status"]: c["count"] for c in summary["by_status"]}
    assert counts.get("open") == 2 and counts.get("closed") == 1


def test_project_delete_cascades_issues(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    issue = _issue(client, admin_headers, proj["id"])
    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{ISSUES}/{issue['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_can_report_and_work_not_delete(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role_id = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "worker@contoso.com",
            "full_name": "Wanda",
            "password": PW,
            "role_ids": [member_role_id],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "worker@contoso.com",
            "password": PW,
        },
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Member can raise and work an issue.
    raised = client.post(
        ISSUES,
        headers=headers,
        json={"project_id": proj["id"], "title": "Member found this"},
    )
    assert raised.status_code == 201
    iid = raised.json()["id"]
    assert (
        client.patch(f"{ISSUES}/{iid}", headers=headers, json={"status": "in_progress"}).status_code
        == 200
    )
    # But cannot delete.
    assert client.delete(f"{ISSUES}/{iid}", headers=headers).status_code == 403
