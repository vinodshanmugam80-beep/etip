"""Integration tests for financial (billing) milestones and deliverable acceptance.

Covers: creating a milestone with a payment (payment_status → pending),
submitting the deliverable for acceptance (opens a workflow instance), the
separation-of-duties acceptance at the gate, releasing the payment only after
full acceptance (posting an actual to the project ledger), the guard paths
(release before acceptance, double release, submitting a non-financial
milestone), the rejected path, and the financial-milestone overview roll-up.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import _login

MS = "/api/v1/milestones"
WF = "/api/v1/workflows"
PROJECTS = "/api/v1/projects"
FIN = "/api/v1/milestones/financial"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str) -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": f"Project {code}", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _fin_milestone(
    client: TestClient, h: dict[str, str], project_id: str, *, amount: str = "50000.00", **extra
) -> dict:
    body = {
        "project_id": project_id,
        "name": "Phase payment",
        "milestone_type": "deliverable",
        "deliverable": "Signed-off deliverable pack",
        "payment_amount": amount,
        "currency": "USD",
        "target_date": "2026-12-01",
    }
    body.update(extra)
    r = client.post(MS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _approver(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str], email: str
) -> dict[str, str]:
    roles = client.get(ROLES, headers=admin_headers).json()
    pm_role = next(r["id"] for r in roles if r["name"] == "Project Manager")
    client.post(
        USERS,
        headers=admin_headers,
        json={"email": email, "full_name": "Acer Approver", "password": PW, "role_ids": [pm_role]},
    )
    tokens = _login(
        client,
        {"organization_slug": registered_org["organization_slug"], "email": email, "password": PW},
    )
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _accept_all_gates(client: TestClient, approver: dict[str, str], instance_id: str) -> dict:
    """Approve every acceptance gate (there are two) → instance completes."""
    last: dict = {}
    for _ in range(2):
        r = client.post(
            f"{WF}/instances/{instance_id}/decision",
            headers=approver,
            json={"decision": "approved", "comment": "ok"},
        )
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] != "in_progress":
            break
    return last


def test_create_financial_milestone_starts_pending(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    p = _project(client, admin_headers, "FM1")
    m = _fin_milestone(client, admin_headers, p["id"])
    assert m["payment_amount"] == "50000.00"
    assert m["payment_status"] == "pending"
    assert m["acceptance_instance_id"] is None

    # A schedule-only milestone (no payment) is not_applicable.
    r = client.post(
        MS,
        headers=admin_headers,
        json={
            "project_id": p["id"],
            "name": "Kickoff",
            "milestone_type": "checkpoint",
            "target_date": "2026-07-01",
        },
    )
    assert r.json()["payment_status"] == "not_applicable"


def test_full_acceptance_then_release(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    p = _project(client, admin_headers, "FM2")
    m = _fin_milestone(client, admin_headers, p["id"], amount="60000.00")
    # Admin submits → admin is the initiator, so a different user must accept.
    submitted = client.post(f"{MS}/{m['id']}/submit-for-acceptance", headers=admin_headers)
    assert submitted.status_code == 200, submitted.text
    inst = submitted.json()["acceptance_instance_id"]
    assert inst is not None

    # Cannot release before acceptance completes.
    early = client.post(f"{MS}/{m['id']}/release-payment", headers=admin_headers)
    assert early.status_code == 409

    approver = _approver(client, admin_headers, registered_org, "fm-accept@contoso.com")
    completed = _accept_all_gates(client, approver, inst)
    assert completed["status"] == "completed"

    # Release now succeeds and posts an actual to the project ledger.
    released = client.post(f"{MS}/{m['id']}/release-payment", headers=admin_headers)
    assert released.status_code == 200, released.text
    body = released.json()
    assert body["payment_status"] == "released"
    assert body["status"] == "achieved"
    assert body["paid_date"] is not None

    summary = client.get(
        f"{PROJECTS}/{p['id']}/financial-summary", headers=admin_headers
    ).json()
    assert Decimal(summary["actual_total"]) == Decimal("60000.00")

    # Double release is rejected.
    assert client.post(f"{MS}/{m['id']}/release-payment", headers=admin_headers).status_code == 409


def test_cannot_submit_twice_or_submit_non_financial(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    p = _project(client, admin_headers, "FM3")
    m = _fin_milestone(client, admin_headers, p["id"])
    first = client.post(f"{MS}/{m['id']}/submit-for-acceptance", headers=admin_headers)
    assert first.status_code == 200
    # Second submit while in progress → 409.
    second = client.post(f"{MS}/{m['id']}/submit-for-acceptance", headers=admin_headers)
    assert second.status_code == 409

    # A non-financial milestone cannot be submitted for acceptance.
    r = client.post(
        MS,
        headers=admin_headers,
        json={
            "project_id": p["id"],
            "name": "Plain checkpoint",
            "milestone_type": "checkpoint",
            "target_date": "2026-07-01",
        },
    )
    plain = r.json()
    assert (
        client.post(f"{MS}/{plain['id']}/submit-for-acceptance", headers=admin_headers).status_code
        == 422
    )


def test_rejected_deliverable_blocks_release(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    p = _project(client, admin_headers, "FM4")
    m = _fin_milestone(client, admin_headers, p["id"])
    inst = client.post(
        f"{MS}/{m['id']}/submit-for-acceptance", headers=admin_headers
    ).json()["acceptance_instance_id"]
    approver = _approver(client, admin_headers, registered_org, "fm-reject@contoso.com")
    client.post(
        f"{WF}/instances/{inst}/decision",
        headers=approver,
        json={"decision": "rejected", "comment": "not acceptable"},
    )
    # Rejected → release still blocked.
    assert client.post(f"{MS}/{m['id']}/release-payment", headers=admin_headers).status_code == 409


def test_financial_overview_rollup(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    p = _project(client, admin_headers, "FM5")
    released = _fin_milestone(
        client, admin_headers, p["id"], amount="20000.00", name="Released one"
    )
    pending = _fin_milestone(
        client, admin_headers, p["id"], amount="15000.00", name="Pending one"
    )

    inst = client.post(
        f"{MS}/{released['id']}/submit-for-acceptance", headers=admin_headers
    ).json()["acceptance_instance_id"]
    approver = _approver(client, admin_headers, registered_org, "fm-roll@contoso.com")
    _accept_all_gates(client, approver, inst)
    client.post(f"{MS}/{released['id']}/release-payment", headers=admin_headers)

    # The pending one is submitted and left awaiting the approver.
    client.post(f"{MS}/{pending['id']}/submit-for-acceptance", headers=admin_headers)

    f = client.get(FIN, headers=admin_headers).json()
    s = f["summary"]
    assert s["count"] == 2
    assert Decimal(s["total_value"]) == Decimal("35000.00")
    assert Decimal(s["released_value"]) == Decimal("20000.00")
    assert Decimal(s["pending_value"]) == Decimal("15000.00")
    # The approver sees the pending gate as awaiting their sign-off.
    fa = client.get(FIN, headers=approver).json()
    assert fa["summary"]["awaiting_my_acceptance"] == 1
