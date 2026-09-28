"""Integration tests for the Change Request Management module.

Covers change-request CRUD, the requested-by stamp, approver validation, the
approval workflow, the separation-of-duties rule (approve/reject need
``change:approve`` and cannot be reached via a plain update), signed impact
fields, search/filter, the change summary, the project cascade, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

CHANGES = "/api/v1/change-requests"
PROJECTS = "/api/v1/projects"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str = "PR") -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _change(
    client: TestClient,
    h: dict[str, str],
    project_id: str,
    title: str = "Scope change",
    **o: object,
) -> dict:
    body: dict[str, object] = {"project_id": project_id, "title": title}
    body.update(o)
    r = client.post(CHANGES, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _submit(client: TestClient, h: dict[str, str], change_id: str) -> None:
    r = client.patch(f"{CHANGES}/{change_id}", headers=h, json={"status": "submitted"})
    assert r.status_code == 200, r.text


def test_create_defaults_and_requester(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    cr = _change(
        client,
        admin_headers,
        proj["id"],
        schedule_impact_days=15,
        cost_impact="40000.00",
    )
    assert cr["status"] == "draft"
    assert cr["requested_by_user_id"] is not None
    assert cr["schedule_impact_days"] == 15
    assert cr["cost_impact"] == "40000.00"


def test_create_requires_project_and_approver(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    assert (
        client.post(
            CHANGES,
            headers=admin_headers,
            json={"project_id": str(uuid.uuid4()), "title": "Orphan CR"},
        ).status_code
        == 404
    )
    proj = _project(client, admin_headers)
    bad = client.post(
        CHANGES,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "CR",
            "approver_user_id": str(uuid.uuid4()),
        },
    )
    assert bad.status_code == 422


def test_negative_impacts_allowed(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    cr = _change(
        client,
        admin_headers,
        proj["id"],
        schedule_impact_days=-5,
        cost_impact="-12000.00",
    )
    assert cr["schedule_impact_days"] == -5  # acceleration
    assert cr["cost_impact"] == "-12000.00"  # saving


def test_update_cannot_decide(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    cr = _change(client, admin_headers, proj["id"])
    _submit(client, admin_headers, cr["id"])
    # Reaching a decision status through a plain update is refused.
    blocked = client.patch(
        f"{CHANGES}/{cr['id']}", headers=admin_headers, json={"status": "approved"}
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "use_decision_endpoint"


def test_approval_workflow(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    cr = _change(client, admin_headers, proj["id"])
    cid = cr["id"]

    # Cannot approve a draft (must be submitted / under review).
    assert (
        client.post(f"{CHANGES}/{cid}/approve", headers=admin_headers, json={}).status_code == 422
    )

    _submit(client, admin_headers, cid)
    approved = client.post(
        f"{CHANGES}/{cid}/approve",
        headers=admin_headers,
        json={"decision_notes": "Looks good"},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "approved"
    assert body["decided_date"] is not None
    assert body["approver_user_id"] is not None
    assert body["decision_notes"] == "Looks good"

    # Approved can be implemented; rejected/implemented are terminal.
    impl = client.patch(f"{CHANGES}/{cid}", headers=admin_headers, json={"status": "implemented"})
    assert impl.status_code == 200
    assert (
        client.patch(
            f"{CHANGES}/{cid}", headers=admin_headers, json={"status": "cancelled"}
        ).status_code
        == 422
    )


def test_reject_flow(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    cr = _change(client, admin_headers, proj["id"])
    _submit(client, admin_headers, cr["id"])
    rejected = client.post(
        f"{CHANGES}/{cr['id']}/reject",
        headers=admin_headers,
        json={"decision_notes": "Out of budget"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    # Rejected is terminal.
    assert (
        client.post(f"{CHANGES}/{cr['id']}/approve", headers=admin_headers, json={}).status_code
        == 422
    )


def test_search_and_summary(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    a = _change(client, admin_headers, proj["id"], title="Scope creep", change_type="scope")
    _change(client, admin_headers, proj["id"], title="Budget bump", change_type="budget")
    _submit(client, admin_headers, a["id"])
    client.post(f"{CHANGES}/{a['id']}/approve", headers=admin_headers, json={})

    scope = client.get(
        CHANGES,
        headers=admin_headers,
        params={"project_id": proj["id"], "change_type": "scope"},
    ).json()
    assert scope["total"] == 1 and scope["items"][0]["title"] == "Scope creep"

    summary = client.get(f"{PROJECTS}/{proj['id']}/change-summary", headers=admin_headers).json()
    assert summary["total_count"] == 2
    assert (
        summary["pending_count"] == 1
    )  # the budget one is still draft; approved one is not pending
    counts = {c["status"]: c["count"] for c in summary["by_status"]}
    assert counts.get("approved") == 1 and counts.get("draft") == 1


def test_project_delete_cascades_changes(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    cr = _change(client, admin_headers, proj["id"])
    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{CHANGES}/{cr['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_can_raise_not_approve_or_edit(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    """Member has change:read + change:create but not update/approve/delete."""
    proj = _project(client, admin_headers)
    admin_cr = _change(client, admin_headers, proj["id"])
    _submit(client, admin_headers, admin_cr["id"])

    roles = client.get(ROLES, headers=admin_headers).json()
    member_role_id = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "raiser@contoso.com",
            "full_name": "Ray",
            "password": PW,
            "role_ids": [member_role_id],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "raiser@contoso.com",
            "password": PW,
        },
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Member can raise a change request and read it.
    raised = client.post(
        CHANGES, headers=headers, json={"project_id": proj["id"], "title": "Member CR"}
    )
    assert raised.status_code == 201
    assert (
        client.get(CHANGES, headers=headers, params={"project_id": proj["id"]}).status_code == 200
    )
    # But cannot edit or approve.
    assert (
        client.patch(
            f"{CHANGES}/{raised.json()['id']}",
            headers=headers,
            json={"status": "submitted"},
        ).status_code
        == 403
    )
    assert (
        client.post(f"{CHANGES}/{admin_cr['id']}/approve", headers=headers, json={}).status_code
        == 403
    )
