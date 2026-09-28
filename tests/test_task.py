"""Integration tests for the Task Management module.

Covers task CRUD, the required project reference, per-project numbering,
assignee validation, the subtask hierarchy (same-project, self-parent and cycle
rules), the task status lifecycle, search/filter/pagination, the subtask
deletion guard, the project→task cascade delete, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

TASKS = "/api/v1/tasks"
PROJECTS = "/api/v1/projects"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str = "PR") -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _task(
    client: TestClient,
    h: dict[str, str],
    project_id: str,
    title: str = "Do the thing",
    **overrides: object,
) -> dict:
    body: dict[str, object] = {"project_id": project_id, "title": title}
    body.update(overrides)
    r = client.post(TASKS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_task_defaults_and_numbering(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    t1 = _task(client, admin_headers, proj["id"])
    t2 = _task(client, admin_headers, proj["id"], title="Second task")
    assert t1["status"] == "todo"
    assert t2["number"] == t1["number"] + 1  # per-project running number


def test_create_requires_project(client: TestClient, admin_headers: dict[str, str]) -> None:
    r = client.post(
        TASKS,
        headers=admin_headers,
        json={"project_id": str(uuid.uuid4()), "title": "X-ray"},
    )
    assert r.status_code == 404


def test_unknown_assignee_and_bad_dates(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    unknown = client.post(
        TASKS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "Task A",
            "assignee_user_id": str(uuid.uuid4()),
        },
    )
    assert unknown.status_code == 422
    bad_dates = client.post(
        TASKS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "Task B",
            "start_date": "2026-06-01",
            "due_date": "2026-01-01",
        },
    )
    assert bad_dates.status_code == 422


def test_subtasks_and_cycle_rules(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a = _task(client, admin_headers, proj["id"], title="Parent task")
    b = _task(client, admin_headers, proj["id"], title="Child task", parent_task_id=a["id"])
    assert b["parent_task_id"] == a["id"]

    subs = client.get(f"{TASKS}/{a['id']}/subtasks", headers=admin_headers)
    assert subs.status_code == 200
    assert [t["id"] for t in subs.json()] == [b["id"]]

    # Making A a child of B creates A -> B -> A: rejected.
    cycle = client.patch(
        f"{TASKS}/{a['id']}", headers=admin_headers, json={"parent_task_id": b["id"]}
    )
    assert cycle.status_code == 422

    # A task cannot be its own parent.
    self_parent = client.patch(
        f"{TASKS}/{a['id']}", headers=admin_headers, json={"parent_task_id": a["id"]}
    )
    assert self_parent.status_code == 422


def test_parent_must_be_same_project(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj_a = _project(client, admin_headers, code="PRA")
    proj_b = _project(client, admin_headers, code="PRB")
    parent = _task(client, admin_headers, proj_a["id"], title="Parent in A")
    cross = client.post(
        TASKS,
        headers=admin_headers,
        json={
            "project_id": proj_b["id"],
            "title": "Child in B",
            "parent_task_id": parent["id"],
        },
    )
    assert cross.status_code == 422


def test_search_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    high = _task(client, admin_headers, proj["id"], title="Urgent fix", priority="high")
    _task(client, admin_headers, proj["id"], title="Routine chore", priority="low")
    client.patch(f"{TASKS}/{high['id']}", headers=admin_headers, json={"status": "in_progress"})

    by_project = client.get(TASKS, headers=admin_headers, params={"project_id": proj["id"]}).json()
    assert by_project["total"] == 2

    by_status = client.get(TASKS, headers=admin_headers, params={"status": "in_progress"}).json()
    assert by_status["total"] == 1 and by_status["items"][0]["title"] == "Urgent fix"

    by_priority = client.get(TASKS, headers=admin_headers, params={"priority": "low"}).json()
    assert by_priority["total"] == 1


def test_status_lifecycle(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    task = _task(client, admin_headers, proj["id"])
    tid = task["id"]

    illegal = client.patch(f"{TASKS}/{tid}", headers=admin_headers, json={"status": "done"})
    assert illegal.status_code == 422

    for target in ("in_progress", "in_review", "done", "in_progress"):
        assert (
            client.patch(
                f"{TASKS}/{tid}", headers=admin_headers, json={"status": target}
            ).status_code
            == 200
        )

    # Cancel is reachable from in_progress; cancelled is terminal.
    assert (
        client.patch(
            f"{TASKS}/{tid}", headers=admin_headers, json={"status": "cancelled"}
        ).status_code
        == 200
    )
    assert (
        client.patch(f"{TASKS}/{tid}", headers=admin_headers, json={"status": "todo"}).status_code
        == 422
    )


def test_update_fields(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    task = _task(client, admin_headers, proj["id"])
    updated = client.patch(
        f"{TASKS}/{task['id']}",
        headers=admin_headers,
        json={"logged_hours": "3.50", "position": 5, "title": "Renamed task"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["logged_hours"] == "3.50"
    assert body["position"] == 5
    assert body["title"] == "Renamed task"


def test_delete_blocked_with_subtasks(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    parent = _task(client, admin_headers, proj["id"], title="Parent task")
    child = _task(
        client,
        admin_headers,
        proj["id"],
        title="Child task",
        parent_task_id=parent["id"],
    )

    blocked = client.delete(f"{TASKS}/{parent['id']}", headers=admin_headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "task_has_subtasks"

    client.delete(f"{TASKS}/{child['id']}", headers=admin_headers)
    assert client.delete(f"{TASKS}/{parent['id']}", headers=admin_headers).status_code == 200


def test_project_delete_cascades_tasks(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    task = _task(client, admin_headers, proj["id"])

    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    # The task was soft-deleted with its project.
    assert client.get(f"{TASKS}/{task['id']}", headers=admin_headers).status_code == 404
    remaining = client.get(TASKS, headers=admin_headers, params={"project_id": proj["id"]}).json()
    assert remaining["total"] == 0


def test_rbac_member_permissions(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    """The Member role has task:read + task:update but not create/delete."""
    proj = _project(client, admin_headers)
    task = _task(client, admin_headers, proj["id"])

    roles = client.get(ROLES, headers=admin_headers).json()
    member_role_id = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "worker@contoso.com",
            "full_name": "Wanda Worker",
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

    assert client.get(TASKS, headers=headers).status_code == 200
    # Member can progress a task (task:update).
    assert (
        client.patch(
            f"{TASKS}/{task['id']}", headers=headers, json={"status": "in_progress"}
        ).status_code
        == 200
    )
    # But cannot create or delete.
    assert (
        client.post(
            TASKS,
            headers=headers,
            json={"project_id": proj["id"], "title": "Nope task"},
        ).status_code
        == 403
    )
    assert client.delete(f"{TASKS}/{task['id']}", headers=headers).status_code == 403
