"""Integration tests for the Dependency Management module.

Covers task→task and project→project dependencies, endpoint validation, the
same-project rule for tasks, duplicate and self-link guards, and — centrally —
**cycle detection** across the dependency graph. Also covers update, the
per-entity listing, cleanup on task and project deletion, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

DEPS = "/api/v1/dependencies"
TASKS = "/api/v1/tasks"
PROJECTS = "/api/v1/projects"
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


def _dep(
    client: TestClient, h: dict[str, str], entity_type: str, pred: str, succ: str, **o: object
) -> object:
    body: dict[str, object] = {
        "entity_type": entity_type,
        "predecessor_id": pred,
        "successor_id": succ,
    }
    body.update(o)
    return client.post(DEPS, headers=h, json=body)


def test_create_task_dependency(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a = _task(client, admin_headers, proj["id"], "Task A")
    b = _task(client, admin_headers, proj["id"], "Task B")
    r = _dep(
        client,
        admin_headers,
        "task",
        a["id"],
        b["id"],
        dependency_type="finish_to_start",
        lag_days=2,
    )
    assert r.status_code == 201, r.text
    assert r.json()["lag_days"] == 2


def test_self_and_duplicate_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a = _task(client, admin_headers, proj["id"], "Task A")
    b = _task(client, admin_headers, proj["id"], "Task B")

    # Self-link.
    assert _dep(client, admin_headers, "task", a["id"], a["id"]).status_code == 422

    # Duplicate edge.
    assert _dep(client, admin_headers, "task", a["id"], b["id"]).status_code == 201
    dup = _dep(client, admin_headers, "task", a["id"], b["id"])
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "duplicate_dependency"


def test_task_endpoints_must_exist_and_share_project(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj_a = _project(client, admin_headers, code="PRA")
    proj_b = _project(client, admin_headers, code="PRB")
    a = _task(client, admin_headers, proj_a["id"], "Task A")
    b = _task(client, admin_headers, proj_b["id"], "Task B")

    # Unknown successor.
    assert _dep(client, admin_headers, "task", a["id"], str(uuid.uuid4())).status_code == 404
    # Cross-project task dependency.
    cross = _dep(client, admin_headers, "task", a["id"], b["id"])
    assert cross.status_code == 422
    assert cross.json()["error"]["code"] == "cross_project_dependency"


def test_cycle_detection_tasks(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a = _task(client, admin_headers, proj["id"], "Task A")
    b = _task(client, admin_headers, proj["id"], "Task B")
    c = _task(client, admin_headers, proj["id"], "Task C")

    assert _dep(client, admin_headers, "task", a["id"], b["id"]).status_code == 201
    assert _dep(client, admin_headers, "task", b["id"], c["id"]).status_code == 201

    # C -> A would close the loop A -> B -> C -> A.
    cycle = _dep(client, admin_headers, "task", c["id"], a["id"])
    assert cycle.status_code == 409
    assert cycle.json()["error"]["code"] == "cycle_detected"

    # The direct 2-node loop B -> A is also rejected.
    two = _dep(client, admin_headers, "task", b["id"], a["id"])
    assert two.status_code == 409


def test_project_dependencies_and_cycle(client: TestClient, admin_headers: dict[str, str]) -> None:
    p1 = _project(client, admin_headers, code="P1")
    p2 = _project(client, admin_headers, code="P2")
    p3 = _project(client, admin_headers, code="P3")

    assert _dep(client, admin_headers, "project", p1["id"], p2["id"]).status_code == 201
    assert _dep(client, admin_headers, "project", p2["id"], p3["id"]).status_code == 201
    assert _dep(client, admin_headers, "project", p3["id"], p1["id"]).status_code == 409


def test_update_and_list_for_entity(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a = _task(client, admin_headers, proj["id"], "Task A")
    b = _task(client, admin_headers, proj["id"], "Task B")
    dep = _dep(client, admin_headers, "task", a["id"], b["id"]).json()

    updated = client.patch(
        f"{DEPS}/{dep['id']}",
        headers=admin_headers,
        json={"lag_days": 5, "dependency_type": "start_to_start"},
    )
    assert updated.status_code == 200
    assert updated.json()["lag_days"] == 5 and updated.json()["dependency_type"] == "start_to_start"

    # B has A as a predecessor; A has B as a successor.
    b_deps = client.get(f"{TASKS}/{b['id']}/dependencies", headers=admin_headers).json()
    assert len(b_deps["predecessors"]) == 1 and len(b_deps["successors"]) == 0
    a_deps = client.get(f"{TASKS}/{a['id']}/dependencies", headers=admin_headers).json()
    assert len(a_deps["successors"]) == 1


def test_task_delete_cleans_dependencies(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a = _task(client, admin_headers, proj["id"], "Task A")
    b = _task(client, admin_headers, proj["id"], "Task B")
    dep = _dep(client, admin_headers, "task", a["id"], b["id"]).json()

    assert client.delete(f"{TASKS}/{a['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{DEPS}/{dep['id']}", headers=admin_headers).status_code == 404


def test_project_delete_cleans_dependencies(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    p1 = _project(client, admin_headers, code="P1")
    p2 = _project(client, admin_headers, code="P2")
    a = _task(client, admin_headers, p1["id"], "Task A")
    b = _task(client, admin_headers, p1["id"], "Task B")
    task_dep = _dep(client, admin_headers, "task", a["id"], b["id"]).json()
    proj_dep = _dep(client, admin_headers, "project", p1["id"], p2["id"]).json()

    assert client.delete(f"{PROJECTS}/{p1['id']}", headers=admin_headers).status_code == 200
    # Both the internal task dependency and the project-level edge are gone.
    assert client.get(f"{DEPS}/{task_dep['id']}", headers=admin_headers).status_code == 404
    assert client.get(f"{DEPS}/{proj_dep['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_read_not_create(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    a = _task(client, admin_headers, proj["id"], "Task A")
    b = _task(client, admin_headers, proj["id"], "Task B")
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
    assert client.get(DEPS, headers=headers).status_code == 200
    assert _dep(client, headers, "task", a["id"], b["id"]).status_code == 403
