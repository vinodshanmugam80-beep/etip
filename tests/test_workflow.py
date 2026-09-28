"""Integration tests for the Stage-Gate / Workflow / Approval engine.

Covers definition + stage CRUD, instance lifecycle (start → advance → complete),
approval gates with separation of duties, rejection, cancellation, the 409
conflict paths, RBAC and not-found handling.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

WF = "/api/v1/workflows"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _def(client: TestClient, h: dict[str, str], name: str = "Project gate", **body: object) -> dict:
    payload: dict[str, object] = {"name": name}
    payload.update(body)
    r = client.post(WF, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _stage(
    client: TestClient, h: dict[str, str], def_id: str, name: str, seq: int, approval: bool
) -> dict:
    r = client.post(
        f"{WF}/{def_id}/stages",
        headers=h,
        json={"name": name, "sequence": seq, "requires_approval": approval},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _start(client: TestClient, h: dict[str, str], def_id: str) -> dict:
    r = client.post(
        f"{WF}/instances",
        headers=h,
        json={"definition_id": def_id, "entity_type": "Project", "entity_id": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _approver(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str], email: str
) -> dict[str, str]:
    """Create a second user with the Project Manager role and log them in."""
    roles = client.get(ROLES, headers=admin_headers).json()
    pm_role = next(r["id"] for r in roles if r["name"] == "Project Manager")
    client.post(
        USERS,
        headers=admin_headers,
        json={"email": email, "full_name": "Approver P", "password": PW, "role_ids": [pm_role]},
    )
    tokens = _login(
        client,
        {"organization_slug": registered_org["organization_slug"], "email": email, "password": PW},
    )
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_definition_and_stages_crud(client: TestClient, admin_headers: dict[str, str]) -> None:
    d = _def(client, admin_headers, entity_type="Project")
    got = client.get(f"{WF}/{d['id']}", headers=admin_headers).json()
    assert got["name"] == "Project gate" and got["is_active"] is True

    _stage(client, admin_headers, d["id"], "Planning", 2, False)
    _stage(client, admin_headers, d["id"], "Initiation", 1, False)
    s3 = _stage(client, admin_headers, d["id"], "Approval", 3, True)
    stages = client.get(f"{WF}/{d['id']}/stages", headers=admin_headers).json()
    assert [s["sequence"] for s in stages] == [1, 2, 3]  # ordered
    assert stages[0]["name"] == "Initiation"

    upd = client.patch(
        f"{WF}/stages/{s3['id']}", headers=admin_headers, json={"name": "Gate review"}
    ).json()
    assert upd["name"] == "Gate review"
    assert client.delete(f"{WF}/stages/{s3['id']}", headers=admin_headers).status_code == 204

    du = client.patch(f"{WF}/{d['id']}", headers=admin_headers, json={"is_active": False}).json()
    assert du["is_active"] is False
    assert client.delete(f"{WF}/{d['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"{WF}/{d['id']}", headers=admin_headers).status_code == 404


def test_start_instance(client: TestClient, admin_headers: dict[str, str]) -> None:
    d = _def(client, admin_headers)
    first = _stage(client, admin_headers, d["id"], "Submit", 1, False)
    _stage(client, admin_headers, d["id"], "Review", 2, True)
    inst = _start(client, admin_headers, d["id"])
    assert inst["status"] == "in_progress" and inst["current_stage_id"] == first["id"]

    # Filter search by entity + definition.
    listing = client.get(
        f"{WF}/instances", headers=admin_headers, params={"definition_id": d["id"]}
    ).json()
    assert listing["total"] == 1

    # No-stage definition → 422.
    empty = _def(client, admin_headers, name="Empty def")
    r = client.post(
        f"{WF}/instances",
        headers=admin_headers,
        json={"definition_id": empty["id"], "entity_type": "X", "entity_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422

    # Inactive definition → 422.
    inactive = _def(client, admin_headers, name="Inactive def", is_active=False)
    _stage(client, admin_headers, inactive["id"], "S1", 1, False)
    r = client.post(
        f"{WF}/instances",
        headers=admin_headers,
        json={"definition_id": inactive["id"], "entity_type": "X", "entity_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422

    # Unknown definition → 404.
    r = client.post(
        f"{WF}/instances",
        headers=admin_headers,
        json={
            "definition_id": str(uuid.uuid4()),
            "entity_type": "X",
            "entity_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 404


def test_advance_non_approval_to_completion(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    d = _def(client, admin_headers)
    _stage(client, admin_headers, d["id"], "Stage one", 1, False)
    s2 = _stage(client, admin_headers, d["id"], "Stage two", 2, False)
    inst = _start(client, admin_headers, d["id"])
    a = client.post(f"{WF}/instances/{inst['id']}/advance", headers=admin_headers).json()
    assert a["current_stage_id"] == s2["id"] and a["status"] == "in_progress"
    b = client.post(f"{WF}/instances/{inst['id']}/advance", headers=admin_headers).json()
    assert b["status"] == "completed" and b["current_stage_id"] is None
    # Acting on a finished instance → 409.
    assert (
        client.post(f"{WF}/instances/{inst['id']}/advance", headers=admin_headers).status_code
        == 409
    )


def test_approval_gate_with_separation_of_duties(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    d = _def(client, admin_headers)
    _stage(client, admin_headers, d["id"], "Submit", 1, False)
    _stage(client, admin_headers, d["id"], "Review", 2, True)
    inst = _start(client, admin_headers, d["id"])  # started_by = admin
    client.post(
        f"{WF}/instances/{inst['id']}/advance", headers=admin_headers
    )  # now at approval gate

    # The initiator cannot approve their own instance → 409 (separation of duties).
    sod = client.post(
        f"{WF}/instances/{inst['id']}/decision",
        headers=admin_headers,
        json={"decision": "approved"},
    )
    assert sod.status_code == 409

    # A different approver can → advances past the last stage → completed.
    approver = _approver(client, admin_headers, registered_org, "wf-approver@contoso.com")
    ok = client.post(
        f"{WF}/instances/{inst['id']}/decision",
        headers=approver,
        json={"decision": "approved", "comment": "Looks good"},
    ).json()
    assert ok["status"] == "completed"

    hist = client.get(f"{WF}/instances/{inst['id']}/approvals", headers=admin_headers).json()
    assert (
        len(hist) == 1 and hist[0]["decision"] == "approved" and hist[0]["comment"] == "Looks good"
    )


def test_rejection(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    d = _def(client, admin_headers)
    _stage(client, admin_headers, d["id"], "Submit", 1, False)
    _stage(client, admin_headers, d["id"], "Review", 2, True)
    inst = _start(client, admin_headers, d["id"])
    client.post(f"{WF}/instances/{inst['id']}/advance", headers=admin_headers)
    approver = _approver(client, admin_headers, registered_org, "wf-rejector@contoso.com")
    rej = client.post(
        f"{WF}/instances/{inst['id']}/decision", headers=approver, json={"decision": "rejected"}
    ).json()
    assert rej["status"] == "rejected"
    # No further action on a rejected instance.
    assert (
        client.post(f"{WF}/instances/{inst['id']}/advance", headers=admin_headers).status_code
        == 409
    )


def test_conflict_paths(client: TestClient, admin_headers: dict[str, str]) -> None:
    # Advance on an approval stage → 409.
    d1 = _def(client, admin_headers, name="Approval first")
    _stage(client, admin_headers, d1["id"], "Gate", 1, True)
    i1 = _start(client, admin_headers, d1["id"])
    assert (
        client.post(f"{WF}/instances/{i1['id']}/advance", headers=admin_headers).status_code == 409
    )

    # Decision on a non-approval stage → 409.
    d2 = _def(client, admin_headers, name="No approval")
    _stage(client, admin_headers, d2["id"], "Plain", 1, False)
    i2 = _start(client, admin_headers, d2["id"])
    r = client.post(
        f"{WF}/instances/{i2['id']}/decision", headers=admin_headers, json={"decision": "approved"}
    )
    assert r.status_code == 409


def test_cancel(client: TestClient, admin_headers: dict[str, str]) -> None:
    d = _def(client, admin_headers)
    _stage(client, admin_headers, d["id"], "Stage one", 1, False)
    inst = _start(client, admin_headers, d["id"])
    c = client.post(f"{WF}/instances/{inst['id']}/cancel", headers=admin_headers).json()
    assert c["status"] == "cancelled"
    # Cannot cancel a finished instance again.
    assert (
        client.post(f"{WF}/instances/{inst['id']}/cancel", headers=admin_headers).status_code == 409
    )


def test_not_found(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{WF}/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{WF}/instances/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{WF}/{uuid.uuid4()}/stages", headers=admin_headers).status_code == 404
    assert (
        client.post(
            f"{WF}/{uuid.uuid4()}/stages",
            headers=admin_headers,
            json={"name": "Stage", "sequence": 1},
        ).status_code
        == 404
    )


def test_rbac(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    _def(client, admin_headers)
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "wf-member@contoso.com",
            "full_name": "Wf Member",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "wf-member@contoso.com",
            "password": PW,
        },
    )
    member = {"Authorization": f"Bearer {tokens['access_token']}"}
    # Member can read.
    assert client.get(WF, headers=member).status_code == 200
    # Member cannot create a definition (needs workflow:manage).
    assert client.post(WF, headers=member, json={"name": "Nope"}).status_code == 403


def test_search_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    _def(client, admin_headers, name="Change gate", entity_type="Change")
    _def(client, admin_headers, name="Retired gate", entity_type="Change", is_active=False)
    # Definition filters: entity_type + is_active.
    by_type = client.get(WF, headers=admin_headers, params={"entity_type": "Change"}).json()
    assert by_type["total"] == 2
    active = client.get(
        WF, headers=admin_headers, params={"entity_type": "Change", "is_active": True}
    ).json()
    assert active["total"] == 1

    # Instance filters: entity_type + status.
    d = _def(client, admin_headers, name="Flow", entity_type="Project")
    _stage(client, admin_headers, d["id"], "Only", 1, False)
    ent = str(uuid.uuid4())
    client.post(
        f"{WF}/instances",
        headers=admin_headers,
        json={"definition_id": d["id"], "entity_type": "Invoice", "entity_id": ent},
    )
    by_ent = client.get(
        f"{WF}/instances",
        headers=admin_headers,
        params={"entity_type": "Invoice", "entity_id": ent},
    ).json()
    assert by_ent["total"] == 1
    in_prog = client.get(
        f"{WF}/instances",
        headers=admin_headers,
        params={"entity_type": "Invoice", "status": "in_progress"},
    ).json()
    assert in_prog["total"] == 1
