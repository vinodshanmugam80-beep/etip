"""Integration tests for the Sprint Management module.

Covers sprint CRUD, per-project numbering, the planned→active→completed
lifecycle, the single-active-sprint-per-project rule, task assignment (with the
same-project constraint), the delete-unassigns-tasks behaviour, the
`/tasks?sprint_id=` filter, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

SPRINTS = "/api/v1/sprints"
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


def _sprint(client: TestClient, h: dict[str, str], project_id: str, name: str = "Sprint 1") -> dict:
    r = client.post(SPRINTS, headers=h, json={"project_id": project_id, "name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_sprint_defaults_and_numbering(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    s1 = _sprint(client, admin_headers, proj["id"], name="Sprint 1")
    s2 = _sprint(client, admin_headers, proj["id"], name="Sprint 2")
    assert s1["status"] == "planned"
    assert s2["number"] == s1["number"] + 1


def test_create_requires_project_and_valid_dates(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    assert (
        client.post(
            SPRINTS, headers=admin_headers, json={"project_id": str(uuid.uuid4()), "name": "S"}
        ).status_code
        == 404
    )
    proj = _project(client, admin_headers)
    bad = client.post(
        SPRINTS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "name": "S",
            "start_date": "2026-06-01",
            "end_date": "2026-01-01",
        },
    )
    assert bad.status_code == 422


def test_status_lifecycle(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    sprint = _sprint(client, admin_headers, proj["id"])
    sid = sprint["id"]

    illegal = client.patch(f"{SPRINTS}/{sid}", headers=admin_headers, json={"status": "completed"})
    assert illegal.status_code == 422

    assert (
        client.patch(
            f"{SPRINTS}/{sid}", headers=admin_headers, json={"status": "active"}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"{SPRINTS}/{sid}", headers=admin_headers, json={"status": "completed"}
        ).status_code
        == 200
    )
    # completed is terminal.
    assert (
        client.patch(
            f"{SPRINTS}/{sid}", headers=admin_headers, json={"status": "active"}
        ).status_code
        == 422
    )


def test_single_active_sprint_per_project(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    s1 = _sprint(client, admin_headers, proj["id"], name="Sprint 1")
    s2 = _sprint(client, admin_headers, proj["id"], name="Sprint 2")

    assert (
        client.patch(
            f"{SPRINTS}/{s1['id']}", headers=admin_headers, json={"status": "active"}
        ).status_code
        == 200
    )
    conflict = client.patch(
        f"{SPRINTS}/{s2['id']}", headers=admin_headers, json={"status": "active"}
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "active_sprint_exists"

    # Completing the first frees the slot.
    client.patch(f"{SPRINTS}/{s1['id']}", headers=admin_headers, json={"status": "completed"})
    assert (
        client.patch(
            f"{SPRINTS}/{s2['id']}", headers=admin_headers, json={"status": "active"}
        ).status_code
        == 200
    )


def test_search_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, code="PRS")
    s = _sprint(client, admin_headers, proj["id"], name="Sprint 1")
    _sprint(client, admin_headers, proj["id"], name="Sprint 2")
    client.patch(f"{SPRINTS}/{s['id']}", headers=admin_headers, json={"status": "active"})

    by_project = client.get(
        SPRINTS, headers=admin_headers, params={"project_id": proj["id"]}
    ).json()
    assert by_project["total"] == 2
    by_status = client.get(SPRINTS, headers=admin_headers, params={"status": "active"}).json()
    assert by_status["total"] == 1


def test_task_assignment_and_project_constraint(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers, code="PRA")
    other = _project(client, admin_headers, code="PRB")
    sprint = _sprint(client, admin_headers, proj["id"])
    task = _task(client, admin_headers, proj["id"])
    foreign_task = _task(client, admin_headers, other["id"])

    assigned = client.post(f"{SPRINTS}/{sprint['id']}/tasks/{task['id']}", headers=admin_headers)
    assert assigned.status_code == 200
    assert assigned.json()["sprint_id"] == sprint["id"]

    # A task from a different project cannot be assigned.
    mismatch = client.post(
        f"{SPRINTS}/{sprint['id']}/tasks/{foreign_task['id']}", headers=admin_headers
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "task_project_mismatch"

    # Sprint task listing and the /tasks?sprint_id= filter agree.
    in_sprint = client.get(f"{SPRINTS}/{sprint['id']}/tasks", headers=admin_headers).json()
    assert [t["id"] for t in in_sprint["tasks"]] == [task["id"]]
    filtered = client.get(TASKS, headers=admin_headers, params={"sprint_id": sprint["id"]}).json()
    assert filtered["total"] == 1

    # Remove from sprint.
    removed = client.delete(f"{SPRINTS}/{sprint['id']}/tasks/{task['id']}", headers=admin_headers)
    assert removed.status_code == 200
    assert (
        client.get(f"{SPRINTS}/{sprint['id']}/tasks", headers=admin_headers).json()["tasks"] == []
    )


def test_remove_task_not_in_sprint(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    sprint = _sprint(client, admin_headers, proj["id"])
    task = _task(client, admin_headers, proj["id"])
    # Task exists but is not assigned to the sprint.
    assert (
        client.delete(
            f"{SPRINTS}/{sprint['id']}/tasks/{task['id']}", headers=admin_headers
        ).status_code
        == 404
    )


def test_delete_sprint_unassigns_tasks(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    sprint = _sprint(client, admin_headers, proj["id"])
    task = _task(client, admin_headers, proj["id"])
    client.post(f"{SPRINTS}/{sprint['id']}/tasks/{task['id']}", headers=admin_headers)

    assert client.delete(f"{SPRINTS}/{sprint['id']}", headers=admin_headers).status_code == 200
    # The task survives the sprint and is no longer assigned to it.
    fetched = client.get(f"{TASKS}/{task['id']}", headers=admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["sprint_id"] is None


def test_rbac_member_read_not_create(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role_id = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "reader@contoso.com",
            "full_name": "Reed",
            "password": PW,
            "role_ids": [member_role_id],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "reader@contoso.com",
            "password": PW,
        },
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get(SPRINTS, headers=headers).status_code == 200
    assert (
        client.post(
            SPRINTS, headers=headers, json={"project_id": proj["id"], "name": "Nope"}
        ).status_code
        == 403
    )
