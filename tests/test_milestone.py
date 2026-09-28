"""Integration tests for the Milestone Management module.

Covers milestone CRUD, the project reference, task-link and owner validation,
the status lifecycle with actual-date stamping, the derived ``is_overdue`` flag,
search/filter, the milestone summary, the project cascade, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

MILESTONES = "/api/v1/milestones"
PROJECTS = "/api/v1/projects"
TASKS = "/api/v1/tasks"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"
FUTURE = "2030-01-01"
PAST = "2020-01-01"


def _project(client: TestClient, h: dict[str, str], code: str = "PR") -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _task(client: TestClient, h: dict[str, str], project_id: str, title: str = "Task item") -> dict:
    r = client.post(TASKS, headers=h, json={"project_id": project_id, "title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _milestone(
    client: TestClient,
    h: dict[str, str],
    project_id: str,
    name: str = "Beta launch",
    target: str = FUTURE,
    **o: object,
) -> dict:
    body: dict[str, object] = {"project_id": project_id, "name": name, "target_date": target}
    body.update(o)
    r = client.post(MILESTONES, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_defaults(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    m = _milestone(client, admin_headers, proj["id"], milestone_type="go_live", is_key=True)
    assert m["status"] == "planned"
    assert m["number"] >= 1
    assert m["is_key"] is True
    assert m["is_overdue"] is False  # target is in the future


def test_create_requires_project_and_owner(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    assert (
        client.post(
            MILESTONES,
            headers=admin_headers,
            json={"project_id": str(uuid.uuid4()), "name": "Orphan", "target_date": FUTURE},
        ).status_code
        == 404
    )
    proj = _project(client, admin_headers)
    bad = client.post(
        MILESTONES,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "name": "Owned",
            "target_date": FUTURE,
            "owner_user_id": str(uuid.uuid4()),
        },
    )
    assert bad.status_code == 422


def test_task_link_validation(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj_a = _project(client, admin_headers, code="PRA")
    proj_b = _project(client, admin_headers, code="PRB")
    task_b = _task(client, admin_headers, proj_b["id"])
    mismatch = client.post(
        MILESTONES,
        headers=admin_headers,
        json={
            "project_id": proj_a["id"],
            "name": "Linked",
            "target_date": FUTURE,
            "task_id": task_b["id"],
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "task_project_mismatch"


def test_status_lifecycle_and_actual_date(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    m = _milestone(client, admin_headers, proj["id"])
    mid = m["id"]

    client.patch(f"{MILESTONES}/{mid}", headers=admin_headers, json={"status": "in_progress"})
    achieved = client.patch(
        f"{MILESTONES}/{mid}", headers=admin_headers, json={"status": "achieved"}
    )
    assert achieved.status_code == 200
    assert achieved.json()["actual_date"] is not None

    # Achieved can only reopen to in_progress; jumping to planned is illegal.
    assert (
        client.patch(
            f"{MILESTONES}/{mid}", headers=admin_headers, json={"status": "planned"}
        ).status_code
        == 422
    )

    # Reopening to in_progress clears the actual date.
    reopened = client.patch(
        f"{MILESTONES}/{mid}", headers=admin_headers, json={"status": "in_progress"}
    )
    assert reopened.status_code == 200 and reopened.json()["actual_date"] is None

    # A missed milestone carries no actual date.
    m2 = _milestone(client, admin_headers, proj["id"], name="Missed one")
    missed = client.patch(
        f"{MILESTONES}/{m2['id']}", headers=admin_headers, json={"status": "missed"}
    )
    assert missed.status_code == 200 and missed.json()["actual_date"] is None


def test_is_overdue_flag(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    # Open milestone with a past target date is overdue.
    m = _milestone(client, admin_headers, proj["id"], name="Late one", target=PAST)
    assert m["is_overdue"] is True
    # Achieving it makes it no longer overdue (no longer open).
    client.patch(f"{MILESTONES}/{m['id']}", headers=admin_headers, json={"status": "achieved"})
    got = client.get(f"{MILESTONES}/{m['id']}", headers=admin_headers).json()
    assert got["is_overdue"] is False


def test_search_orders_by_target_date(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    _milestone(client, admin_headers, proj["id"], name="Later", target="2031-01-01")
    _milestone(client, admin_headers, proj["id"], name="Sooner", target="2029-01-01")
    keyed = _milestone(
        client, admin_headers, proj["id"], name="Keyed", target="2030-06-01", is_key=True
    )

    listing = client.get(
        MILESTONES, headers=admin_headers, params={"project_id": proj["id"]}
    ).json()
    names = [m["name"] for m in listing["items"]]
    assert names == ["Sooner", "Keyed", "Later"]  # ascending target date

    only_key = client.get(
        MILESTONES, headers=admin_headers, params={"project_id": proj["id"], "is_key": True}
    ).json()
    assert only_key["total"] == 1 and only_key["items"][0]["id"] == keyed["id"]


def test_milestone_summary(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    _milestone(client, admin_headers, proj["id"], name="Overdue one", target=PAST)  # open + overdue
    _milestone(client, admin_headers, proj["id"], name="Key one", target=FUTURE, is_key=True)
    achieved = _milestone(client, admin_headers, proj["id"], name="Done one", target=FUTURE)
    client.patch(
        f"{MILESTONES}/{achieved['id']}", headers=admin_headers, json={"status": "achieved"}
    )

    summary = client.get(f"{PROJECTS}/{proj['id']}/milestone-summary", headers=admin_headers).json()
    assert summary["total_count"] == 3
    assert summary["key_count"] == 1
    assert summary["overdue_count"] == 1
    counts = {c["status"]: c["count"] for c in summary["by_status"]}
    assert counts.get("planned") == 2 and counts.get("achieved") == 1


def test_project_delete_cascades_milestones(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    m = _milestone(client, admin_headers, proj["id"])
    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{MILESTONES}/{m['id']}", headers=admin_headers).status_code == 404


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
    assert (
        client.get(MILESTONES, headers=headers, params={"project_id": proj["id"]}).status_code
        == 200
    )
    assert (
        client.post(
            MILESTONES,
            headers=headers,
            json={"project_id": proj["id"], "name": "Nope", "target_date": FUTURE},
        ).status_code
        == 403
    )
