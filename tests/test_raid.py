"""Integration tests for the RAID Log module.

Covers action and decision CRUD, their status lifecycles (with date stamping),
owner/decider validation, search/filter, the project cascade, the consolidated
RAID summary that aggregates across risks/actions/issues/decisions, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

ACTIONS = "/api/v1/actions"
DECISIONS = "/api/v1/decisions"
RISKS = "/api/v1/risks"
ISSUES = "/api/v1/issues"
PROJECTS = "/api/v1/projects"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str = "PR") -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _action(
    client: TestClient,
    h: dict[str, str],
    project_id: str,
    title: str = "Do a thing",
    **o: object,
) -> dict:
    body: dict[str, object] = {"project_id": project_id, "title": title}
    body.update(o)
    r = client.post(ACTIONS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _decision(
    client: TestClient,
    h: dict[str, str],
    project_id: str,
    title: str = "Pick a stack",
    **o: object,
) -> dict:
    body: dict[str, object] = {"project_id": project_id, "title": title}
    body.update(o)
    r = client.post(DECISIONS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --- Actions ---------------------------------------------------------------
def test_create_action_defaults(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a1 = _action(client, admin_headers, proj["id"])
    a2 = _action(client, admin_headers, proj["id"], title="Second thing")
    assert a1["status"] == "open"
    assert a2["number"] == a1["number"] + 1


def test_action_requires_project_and_owner(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    assert (
        client.post(
            ACTIONS,
            headers=admin_headers,
            json={"project_id": str(uuid.uuid4()), "title": "Orphan action"},
        ).status_code
        == 404
    )
    proj = _project(client, admin_headers)
    bad = client.post(
        ACTIONS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "Owned",
            "owner_user_id": str(uuid.uuid4()),
        },
    )
    assert bad.status_code == 422


def test_action_workflow_and_completed_date(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    action = _action(client, admin_headers, proj["id"])
    aid = action["id"]

    client.patch(f"{ACTIONS}/{aid}", headers=admin_headers, json={"status": "in_progress"})
    done = client.patch(f"{ACTIONS}/{aid}", headers=admin_headers, json={"status": "done"})
    assert done.status_code == 200
    assert done.json()["completed_date"] is not None

    # done can only reopen to in_progress (which clears the completed date).
    reopened = client.patch(
        f"{ACTIONS}/{aid}", headers=admin_headers, json={"status": "in_progress"}
    )
    assert reopened.status_code == 200 and reopened.json()["completed_date"] is None

    cancelled = _action(client, admin_headers, proj["id"], title="To cancel")
    client.patch(
        f"{ACTIONS}/{cancelled['id']}",
        headers=admin_headers,
        json={"status": "cancelled"},
    )
    assert (
        client.patch(
            f"{ACTIONS}/{cancelled['id']}",
            headers=admin_headers,
            json={"status": "open"},
        ).status_code
        == 422
    )


def test_action_search_and_delete(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a = _action(client, admin_headers, proj["id"], title="Alpha")
    _action(client, admin_headers, proj["id"], title="Beta")
    client.patch(f"{ACTIONS}/{a['id']}", headers=admin_headers, json={"status": "done"})

    done = client.get(
        ACTIONS,
        headers=admin_headers,
        params={"project_id": proj["id"], "status": "done"},
    ).json()
    assert done["total"] == 1 and done["items"][0]["title"] == "Alpha"
    assert client.delete(f"{ACTIONS}/{a['id']}", headers=admin_headers).status_code == 200


# --- Decisions -------------------------------------------------------------
def test_decision_lifecycle_and_date(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    decision = _decision(client, admin_headers, proj["id"], rationale="Because")
    did = decision["id"]
    assert decision["status"] == "proposed"

    decided = client.patch(f"{DECISIONS}/{did}", headers=admin_headers, json={"status": "decided"})
    assert decided.status_code == 200 and decided.json()["decision_date"] is not None

    # decided cannot go back to proposed; can be superseded.
    assert (
        client.patch(
            f"{DECISIONS}/{did}", headers=admin_headers, json={"status": "proposed"}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{DECISIONS}/{did}", headers=admin_headers, json={"status": "superseded"}
        ).status_code
        == 200
    )


def test_decision_reject_and_search(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    d = _decision(client, admin_headers, proj["id"], title="Maybe not")
    client.patch(f"{DECISIONS}/{d['id']}", headers=admin_headers, json={"status": "rejected"})

    rejected = client.get(
        DECISIONS,
        headers=admin_headers,
        params={"project_id": proj["id"], "status": "rejected"},
    ).json()
    assert rejected["total"] == 1
    assert client.delete(f"{DECISIONS}/{d['id']}", headers=admin_headers).status_code == 200


# --- Consolidated summary --------------------------------------------------
def test_raid_summary_aggregates_all_quadrants(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    # One open risk.
    client.post(
        RISKS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "A risk",
            "probability": 3,
            "impact": 3,
        },
    )
    # One open issue.
    client.post(
        ISSUES,
        headers=admin_headers,
        json={"project_id": proj["id"], "title": "An issue"},
    )
    # Two actions, one done (so one open).
    a = _action(client, admin_headers, proj["id"], title="Action one")
    _action(client, admin_headers, proj["id"], title="Action two")
    client.patch(f"{ACTIONS}/{a['id']}", headers=admin_headers, json={"status": "done"})
    # One proposed decision.
    _decision(client, admin_headers, proj["id"], title="A decision")

    raid = client.get(f"{PROJECTS}/{proj['id']}/raid", headers=admin_headers).json()
    assert raid["risks"] == {"open_count": 1, "total_count": 1}
    assert raid["actions"] == {"open_count": 1, "total_count": 2}
    assert raid["issues"] == {"open_count": 1, "total_count": 1}
    assert raid["decisions"] == {"open_count": 1, "total_count": 1}


def test_project_delete_cascades_raid(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    action = _action(client, admin_headers, proj["id"])
    decision = _decision(client, admin_headers, proj["id"])
    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{ACTIONS}/{action['id']}", headers=admin_headers).status_code == 404
    assert client.get(f"{DECISIONS}/{decision['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_read_update_not_create(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    """Member has raid:read + raid:update but not raid:create/delete."""
    proj = _project(client, admin_headers)
    action = _action(client, admin_headers, proj["id"])
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

    assert (
        client.get(ACTIONS, headers=headers, params={"project_id": proj["id"]}).status_code == 200
    )
    # Member can progress an existing action.
    assert (
        client.patch(
            f"{ACTIONS}/{action['id']}", headers=headers, json={"status": "in_progress"}
        ).status_code
        == 200
    )
    # But cannot create.
    assert (
        client.post(
            ACTIONS,
            headers=headers,
            json={"project_id": proj["id"], "title": "Nope action"},
        ).status_code
        == 403
    )
