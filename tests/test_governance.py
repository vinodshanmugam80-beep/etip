"""Integration tests for the SDLC stage-gate governance overview.

Covers the canonical SDLC definition setup (idempotent, six gates), the
governance read model (gate-state classification, per-subject progress,
portfolio roll-up), the "awaiting my approval" signal with separation of
duties, and the rejected-gate state. Approvals are recorded by a second user so
the engine's approver-≠-initiator rule is satisfied.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import _login

WF = "/api/v1/workflows"
GOV = "/api/v1/workflows/governance"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PROJECTS = "/api/v1/projects"
PW = "Initial-Passphrase!1"


def _approver(
    client: TestClient,
    admin_headers: dict[str, str],
    registered_org: dict[str, str],
    email: str,
) -> dict[str, str]:
    """Create a second user (Project Manager role) and return their headers."""
    roles = client.get(ROLES, headers=admin_headers).json()
    pm_role = next(r["id"] for r in roles if r["name"] == "Project Manager")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": email,
            "full_name": "Pat Approver",
            "password": PW,
            "role_ids": [pm_role],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": email,
            "password": PW,
        },
    )
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _project(client: TestClient, h: dict[str, str], code: str) -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": f"Project {code}", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _start(client: TestClient, h: dict[str, str], def_id: str, project_id: str) -> dict:
    r = client.post(
        f"{WF}/instances",
        headers=h,
        json={
            "definition_id": def_id,
            "entity_type": "Project",
            "entity_id": project_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_setup_sdlc_is_idempotent_with_six_gates(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    d1 = client.post(f"{WF}/setup-sdlc", headers=admin_headers)
    assert d1.status_code == 200, d1.text
    def_id = d1.json()["id"]
    stages = client.get(f"{WF}/{def_id}/stages", headers=admin_headers).json()
    assert len(stages) == 6
    assert [s["sequence"] for s in stages] == [1, 2, 3, 4, 5, 6]
    assert all(s["requires_approval"] for s in stages)

    # A second call returns the same definition, not a duplicate.
    d2 = client.post(f"{WF}/setup-sdlc", headers=admin_headers)
    assert d2.json()["id"] == def_id
    defs = client.get(WF, headers=admin_headers, params={"entity_type": "Project"}).json()
    assert sum(1 for x in defs["items"] if x["name"] == "SDLC Stage Gates") == 1


def test_overview_empty_before_setup(client: TestClient, admin_headers: dict[str, str]) -> None:
    g = client.get(GOV, headers=admin_headers).json()
    assert g["definition_ready"] is False
    assert g["items"] == []
    assert g["summary"]["approved_gates"] == 0


def test_overview_classifies_gates_and_progress(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    definition = client.post(f"{WF}/setup-sdlc", headers=admin_headers).json()
    project = _project(client, admin_headers, "GOVA")
    # Admin starts the instance so a *different* user must approve (SoD).
    inst = _start(client, admin_headers, definition["id"], project["id"])
    approver = _approver(client, admin_headers, registered_org, "gov-approver@contoso.com")

    # Approve the first two gates.
    for _ in range(2):
        r = client.post(
            f"{WF}/instances/{inst['id']}/decision",
            headers=approver,
            json={"decision": "approved", "comment": "ok"},
        )
        assert r.status_code == 200, r.text

    g = client.get(GOV, headers=admin_headers).json()
    assert g["definition_ready"] is True
    item = next(i for i in g["items"] if i["instance_id"] == inst["id"])
    assert item["entity_label"].startswith("GOVA")
    states = [gate["state"] for gate in item["gates"]]
    # Two approved, then the third pending, the rest upcoming.
    assert states[0] == "approved" and states[1] == "approved"
    assert states[2] == "pending"
    assert states[3:] == ["upcoming", "upcoming", "upcoming"]
    assert item["progress_percent"] == round(2 / 6 * 100)
    assert item["gates"][0]["approver_name"] == "Pat Approver"
    assert g["summary"]["approved_gates"] >= 2
    assert g["summary"]["pending_gates"] >= 1


def test_awaiting_my_approval_respects_separation_of_duties(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    definition = client.post(f"{WF}/setup-sdlc", headers=admin_headers).json()
    project = _project(client, admin_headers, "GOVB")
    inst = _start(client, admin_headers, definition["id"], project["id"])
    approver = _approver(client, admin_headers, registered_org, "gov-await@contoso.com")

    # The initiator (admin) is NOT awaiting their own approval.
    admin_view = client.get(GOV, headers=admin_headers).json()
    admin_item = next(i for i in admin_view["items"] if i["instance_id"] == inst["id"])
    assert admin_item["awaiting_my_approval"] is False
    assert admin_view["summary"]["awaiting_my_approval"] == 0

    # A different approver IS awaiting the current gate.
    approver_view = client.get(GOV, headers=approver).json()
    approver_item = next(i for i in approver_view["items"] if i["instance_id"] == inst["id"])
    assert approver_item["awaiting_my_approval"] is True
    assert approver_view["summary"]["awaiting_my_approval"] == 1


def test_overview_reflects_rejected_gate(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    definition = client.post(f"{WF}/setup-sdlc", headers=admin_headers).json()
    project = _project(client, admin_headers, "GOVC")
    inst = _start(client, admin_headers, definition["id"], project["id"])
    approver = _approver(client, admin_headers, registered_org, "gov-reject@contoso.com")

    client.post(
        f"{WF}/instances/{inst['id']}/decision",
        headers=approver,
        json={"decision": "rejected", "comment": "not acceptable"},
    )
    g = client.get(GOV, headers=admin_headers).json()
    item = next(i for i in g["items"] if i["instance_id"] == inst["id"])
    assert item["status"] == "rejected"
    assert item["gates"][0]["state"] == "rejected"
    assert g["summary"]["instances_rejected"] >= 1
