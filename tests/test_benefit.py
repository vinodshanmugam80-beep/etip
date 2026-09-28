"""Integration tests for Benefits Realization.

Covers CRUD, the computed realisation %/ROI/variance, realisation recording with
auto status inference, status-transition validation, program/portfolio rollups,
RBAC, and not-found handling.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

BEN = "/api/v1/benefits"
PROJECTS = "/api/v1/projects"
PORTFOLIOS = "/api/v1/portfolios"
PROGRAMS = "/api/v1/programs"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str, **body: object) -> str:
    payload: dict[str, object] = {"name": "Project", "code": code}
    payload.update(body)
    r = client.post(PROJECTS, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _benefit(client: TestClient, h: dict[str, str], project_id: str, **body: object) -> dict:
    payload: dict[str, object] = {"project_id": project_id, "title": "Cost saving"}
    payload.update(body)
    r = client.post(BEN, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_computed_fields(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, "BEN")
    body = _benefit(
        client,
        admin_headers,
        proj,
        target_value="100000.00",
        realized_value="40000.00",
        investment_cost="20000.00",
    )
    assert body["realization_percent"] == 40.0
    assert body["roi_percent"] == 100.0  # (40000 - 20000) / 20000
    assert body["variance"] == "-60000.00"  # realized - target
    # Round-trips on GET.
    got = client.get(f"{BEN}/{body['id']}", headers=admin_headers).json()
    assert got["realization_percent"] == 40.0


def test_record_realization_auto_status(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, "REA")
    ben = _benefit(client, admin_headers, proj, target_value="1000.00")
    # Partial realisation.
    partial = client.post(
        f"{BEN}/{ben['id']}/realization", headers=admin_headers, json={"realized_value": "300.00"}
    ).json()
    assert partial["status"] == "partially_realized" and partial["realization_percent"] == 30.0
    # Full realisation.
    full = client.post(
        f"{BEN}/{ben['id']}/realization", headers=admin_headers, json={"realized_value": "1000.00"}
    ).json()
    assert full["status"] == "realized" and full["realization_percent"] == 100.0
    assert full["realized_date"] is not None


def test_status_transition_validation(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, "TRN")
    ben = _benefit(client, admin_headers, proj, target_value="1000.00")
    # Drive it to realized.
    client.post(
        f"{BEN}/{ben['id']}/realization", headers=admin_headers, json={"realized_value": "1000.00"}
    )
    # realized → planned is not allowed.
    r = client.patch(f"{BEN}/{ben['id']}", headers=admin_headers, json={"status": "planned"})
    assert r.status_code == 422


def test_search_and_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, "SCH")
    _benefit(client, admin_headers, proj, title="Financial one", category="financial")
    _benefit(client, admin_headers, proj, title="Strategic one", category="strategic")
    all_for_proj = client.get(BEN, headers=admin_headers, params={"project_id": proj}).json()
    assert all_for_proj["total"] == 2
    fin = client.get(
        BEN, headers=admin_headers, params={"project_id": proj, "category": "financial"}
    ).json()
    assert fin["total"] == 1 and fin["items"][0]["category"] == "financial"


def test_delete(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, "DEL")
    ben = _benefit(client, admin_headers, proj)
    assert client.delete(f"{BEN}/{ben['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"{BEN}/{ben['id']}", headers=admin_headers).status_code == 404


def test_summaries(client: TestClient, admin_headers: dict[str, str]) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Bens", "code": "BSM"}
    ).json()
    prog = client.post(
        PROGRAMS,
        headers=admin_headers,
        json={"name": "Prog", "code": "BPM", "portfolio_id": port["id"]},
    ).json()
    p1 = _project(client, admin_headers, "SM1", portfolio_id=port["id"], program_id=prog["id"])
    p2 = _project(client, admin_headers, "SM2", portfolio_id=port["id"])
    _benefit(
        client,
        admin_headers,
        p1,
        target_value="100000.00",
        realized_value="60000.00",
        investment_cost="40000.00",
    )
    _benefit(
        client,
        admin_headers,
        p2,
        target_value="100000.00",
        realized_value="40000.00",
        investment_cost="10000.00",
    )

    port_sum = client.get(f"{BEN}/summary/portfolios/{port['id']}", headers=admin_headers).json()
    assert port_sum["benefit_count"] == 2
    assert port_sum["total_target"] == "200000.00"
    assert port_sum["total_realized"] == "100000.00"
    assert port_sum["realization_percent"] == 50.0
    # ROI = (100000 - 50000) / 50000 = 100%
    assert port_sum["roi_percent"] == 100.0
    assert port_sum["variance"] == "-100000.00"

    prog_sum = client.get(f"{BEN}/summary/programs/{prog['id']}", headers=admin_headers).json()
    assert prog_sum["benefit_count"] == 1  # only p1 is in the program

    # Unknown scopes → 404.
    assert (
        client.get(f"{BEN}/summary/portfolios/{uuid.uuid4()}", headers=admin_headers).status_code
        == 404
    )
    assert (
        client.get(f"{BEN}/summary/programs/{uuid.uuid4()}", headers=admin_headers).status_code
        == 404
    )


def test_not_found(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{BEN}/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    # Create under an unknown project.
    r = client.post(
        BEN, headers=admin_headers, json={"project_id": str(uuid.uuid4()), "title": "Orphan"}
    )
    assert r.status_code == 404


def test_rbac_member_read_only(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    proj = _project(client, admin_headers, "RBC")
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "ben@contoso.com",
            "full_name": "Ben Reader",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "ben@contoso.com",
            "password": PW,
        },
    )
    member = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Member can read, but cannot create.
    assert client.get(BEN, headers=member, params={"project_id": proj}).status_code == 200
    r = client.post(BEN, headers=member, json={"project_id": proj, "title": "No can do"})
    assert r.status_code == 403


def test_update_fields_and_owner_validation(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers, "UPD")
    ben = _benefit(client, admin_headers, proj, target_value="1000.00")
    # Create a user to own the benefit.
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    owner = client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "owner@contoso.com",
            "full_name": "Owner P",
            "password": PW,
            "role_ids": [member_role],
        },
    ).json()

    updated = client.patch(
        f"{BEN}/{ben['id']}",
        headers=admin_headers,
        json={
            "title": "Renamed benefit",
            "description": "Now described",
            "category": "financial",
            "target_value": "2000.00",
            "investment_cost": "500.00",
            "target_date": "2026-12-31",
            "status": "in_progress",
            "owner_user_id": owner["id"],
        },
    ).json()
    assert updated["title"] == "Renamed benefit"
    assert updated["category"] == "financial"
    assert updated["target_value"] == "2000.00"
    assert updated["status"] == "in_progress"
    assert updated["owner_user_id"] == owner["id"]

    # Unknown owner is rejected.
    bad = client.patch(
        f"{BEN}/{ben['id']}", headers=admin_headers, json={"owner_user_id": str(uuid.uuid4())}
    )
    assert bad.status_code == 422


def test_zero_target_computed_none(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, "ZRO")
    ben = _benefit(client, admin_headers, proj, target_value="0.00", investment_cost="0.00")
    assert ben["realization_percent"] is None and ben["roi_percent"] is None
    # Recording realisation with a zero target leaves status unchanged (no inference).
    rec = client.post(
        f"{BEN}/{ben['id']}/realization", headers=admin_headers, json={"realized_value": "500.00"}
    ).json()
    assert rec["status"] == "planned"


def test_search_by_status_and_owner(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, "SBO")
    ben = _benefit(client, admin_headers, proj, target_value="1000.00")
    client.post(
        f"{BEN}/{ben['id']}/realization", headers=admin_headers, json={"realized_value": "1000.00"}
    )
    realized = client.get(
        BEN, headers=admin_headers, params={"project_id": proj, "status": "realized"}
    ).json()
    assert realized["total"] == 1
    none_owner = client.get(
        BEN, headers=admin_headers, params={"owner_user_id": str(uuid.uuid4())}
    ).json()
    assert none_owner["total"] == 0
