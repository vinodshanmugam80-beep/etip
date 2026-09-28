"""Integration tests for the Timesheet Management module.

Covers time-entry CRUD, the user/project stamps, task-link validation, the
submit→approve/reject workflow, edit-locking of non-draft entries, the
separation-of-duties rule for approvals, the task ``logged_hours`` rollup from
approved time, the hours summary, the project cascade, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

TS = "/api/v1/timesheets"
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


def _entry(
    client: TestClient,
    h: dict[str, str],
    project_id: str,
    hours: str = "6.50",
    date_str: str = "2026-03-02",
    **o: object,
) -> dict:
    body: dict[str, object] = {"project_id": project_id, "work_date": date_str, "hours": hours}
    body.update(o)
    r = client.post(TS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _submit(client: TestClient, h: dict[str, str], entry_id: str) -> None:
    r = client.patch(f"{TS}/{entry_id}", headers=h, json={"status": "submitted"})
    assert r.status_code == 200, r.text


def test_create_defaults(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    e = _entry(client, admin_headers, proj["id"])
    assert e["status"] == "draft"
    assert e["billable"] is True
    assert e["user_id"] is not None  # logged for the caller


def test_create_validations(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert (
        client.post(
            TS,
            headers=admin_headers,
            json={"project_id": str(uuid.uuid4()), "work_date": "2026-03-02", "hours": "1.00"},
        ).status_code
        == 404
    )
    proj_a = _project(client, admin_headers, code="PRA")
    proj_b = _project(client, admin_headers, code="PRB")
    task_b = _task(client, admin_headers, proj_b["id"])
    mismatch = client.post(
        TS,
        headers=admin_headers,
        json={
            "project_id": proj_a["id"],
            "work_date": "2026-03-02",
            "hours": "1.00",
            "task_id": task_b["id"],
        },
    )
    assert (
        mismatch.status_code == 422 and mismatch.json()["error"]["code"] == "task_project_mismatch"
    )
    # Hours out of range.
    assert (
        client.post(
            TS,
            headers=admin_headers,
            json={"project_id": proj_a["id"], "work_date": "2026-03-02", "hours": "25.00"},
        ).status_code
        == 422
    )


def test_edit_locking_and_recall(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    e = _entry(client, admin_headers, proj["id"])
    eid = e["id"]

    # Draft is editable.
    assert (
        client.patch(f"{TS}/{eid}", headers=admin_headers, json={"hours": "7.00"}).status_code
        == 200
    )
    _submit(client, admin_headers, eid)
    # Submitted is locked against field edits.
    locked = client.patch(f"{TS}/{eid}", headers=admin_headers, json={"hours": "8.00"})
    assert locked.status_code == 422 and locked.json()["error"]["code"] == "entry_locked"
    # But can be recalled to draft, then edited.
    assert (
        client.patch(f"{TS}/{eid}", headers=admin_headers, json={"status": "draft"}).status_code
        == 200
    )
    assert (
        client.patch(f"{TS}/{eid}", headers=admin_headers, json={"hours": "8.00"}).status_code
        == 200
    )


def test_update_cannot_decide(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    e = _entry(client, admin_headers, proj["id"])
    _submit(client, admin_headers, e["id"])
    blocked = client.patch(f"{TS}/{e['id']}", headers=admin_headers, json={"status": "approved"})
    assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "use_decision_endpoint"


def test_approve_reject_workflow(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    e = _entry(client, admin_headers, proj["id"])
    eid = e["id"]

    # Cannot approve a draft.
    assert client.post(f"{TS}/{eid}/approve", headers=admin_headers, json={}).status_code == 422

    _submit(client, admin_headers, eid)
    approved = client.post(
        f"{TS}/{eid}/approve", headers=admin_headers, json={"decision_notes": "ok"}
    )
    assert approved.status_code == 200
    body = approved.json()
    assert (
        body["status"] == "approved"
        and body["decided_date"] is not None
        and body["approver_user_id"] is not None
    )
    # Approved is terminal: it cannot be moved on to rejected.
    assert client.post(f"{TS}/{eid}/reject", headers=admin_headers, json={}).status_code == 422

    # Reject flow: submit another, reject, then resubmit from rejected.
    e2 = _entry(client, admin_headers, proj["id"], hours="2.00")
    _submit(client, admin_headers, e2["id"])
    rejected = client.post(
        f"{TS}/{e2['id']}/reject", headers=admin_headers, json={"decision_notes": "wrong project"}
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert (
        client.patch(
            f"{TS}/{e2['id']}", headers=admin_headers, json={"status": "draft"}
        ).status_code
        == 200
    )


def test_task_logged_hours_rollup(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    task = _task(client, admin_headers, proj["id"])

    e1 = _entry(client, admin_headers, proj["id"], hours="5.00", task_id=task["id"])
    e2 = _entry(client, admin_headers, proj["id"], hours="3.00", task_id=task["id"])
    # Drafts do not count yet.
    got = client.get(f"{TASKS}/{task['id']}", headers=admin_headers).json()
    assert got["logged_hours"] == "0.00"

    for e in (e1, e2):
        _submit(client, admin_headers, e["id"])
        client.post(f"{TS}/{e['id']}/approve", headers=admin_headers, json={})
    got = client.get(f"{TASKS}/{task['id']}", headers=admin_headers).json()
    assert got["logged_hours"] == "8.00"  # sum of approved

    # Deleting an approved entry lowers the rollup.
    client.delete(f"{TS}/{e1['id']}", headers=admin_headers)
    got = client.get(f"{TASKS}/{task['id']}", headers=admin_headers).json()
    assert got["logged_hours"] == "3.00"


def test_summary(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    billable = _entry(client, admin_headers, proj["id"], hours="6.00", billable=True)
    _entry(client, admin_headers, proj["id"], hours="2.00", billable=False)
    _submit(client, admin_headers, billable["id"])
    client.post(f"{TS}/{billable['id']}/approve", headers=admin_headers, json={})

    summary = client.get(
        TS + "/summary", headers=admin_headers, params={"project_id": proj["id"]}
    ).json()
    assert summary["total_hours"] == "8.00"
    assert summary["billable_hours"] == "6.00"
    assert summary["approved_hours"] == "6.00"
    assert summary["entry_count"] == 2

    # The list endpoint filters by billable and status.
    only_billable = client.get(
        TS, headers=admin_headers, params={"project_id": proj["id"], "billable": True}
    ).json()
    assert only_billable["total"] == 1 and only_billable["items"][0]["hours"] == "6.00"
    approved_only = client.get(
        TS, headers=admin_headers, params={"project_id": proj["id"], "status": "approved"}
    ).json()
    assert approved_only["total"] == 1


def test_project_delete_cascades_entries(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    e = _entry(client, admin_headers, proj["id"])
    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{TS}/{e['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_logs_not_approves(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    """Member has create/read/update but not approve or delete."""
    proj = _project(client, admin_headers)
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role_id = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "logger@contoso.com",
            "full_name": "Lo",
            "password": PW,
            "role_ids": [member_role_id],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "logger@contoso.com",
            "password": PW,
        },
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    logged = client.post(
        TS,
        headers=headers,
        json={"project_id": proj["id"], "work_date": "2026-03-02", "hours": "4.00"},
    )
    assert logged.status_code == 201
    eid = logged.json()["id"]
    # Member can submit their own entry.
    assert (
        client.patch(f"{TS}/{eid}", headers=headers, json={"status": "submitted"}).status_code
        == 200
    )
    # But cannot approve or delete.
    assert client.post(f"{TS}/{eid}/approve", headers=headers, json={}).status_code == 403
    assert client.delete(f"{TS}/{eid}", headers=headers).status_code == 403
