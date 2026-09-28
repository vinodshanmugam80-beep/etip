"""Integration tests for the Portfolio Management module.

Covers portfolio CRUD, code uniqueness and owner validation, the status
lifecycle state machine (legal and illegal transitions), search/filter/
pagination, cross-field date validation on partial updates, the strategic-
objectives child collection, cascade delete, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

BASE = "/api/v1/portfolios"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _create(
    client: TestClient,
    headers: dict[str, str],
    code: str = "DX",
    **overrides: object,
) -> dict:
    body: dict[str, object] = {
        "name": "Digital Transformation",
        "code": code,
        "description": "Enterprise digital initiatives",
        "priority": "high",
        "planned_budget": "2500000.00",
    }
    body.update(overrides)
    response = client.post(BASE, headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_portfolio_defaults(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _create(client, admin_headers)
    assert pf["code"] == "DX"
    assert pf["status"] == "proposed"  # lifecycle starts here
    assert pf["priority"] == "high"
    assert pf["planned_budget"] == "2500000.00"
    assert pf["objectives"] == []


def test_duplicate_code_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create(client, admin_headers, code="dx")  # normalised to DX
    dup = client.post(BASE, headers=admin_headers, json={"name": "Other", "code": "DX"})
    assert dup.status_code == 409


def test_unknown_owner_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        BASE,
        headers=admin_headers,
        json={"name": "X", "code": "X1", "owner_user_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422


def test_create_bad_date_range_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        BASE,
        headers=admin_headers,
        json={
            "name": "X",
            "code": "X2",
            "start_date": "2026-06-01",
            "end_date": "2026-01-01",
        },
    )
    assert response.status_code == 422


def test_search_filter_and_pagination(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create(client, admin_headers, code="AAA", name="Alpha")
    beta = _create(client, admin_headers, code="BBB", name="Beta")
    # Activate beta so we can filter by status.
    client.patch(f"{BASE}/{beta['id']}", headers=admin_headers, json={"status": "active"})

    page = client.get(BASE, headers=admin_headers, params={"limit": 1}).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1

    active = client.get(BASE, headers=admin_headers, params={"status": "active"}).json()
    assert active["total"] == 1
    assert active["items"][0]["code"] == "BBB"

    found = client.get(BASE, headers=admin_headers, params={"q": "alpha"}).json()
    assert found["total"] == 1


def test_status_lifecycle_valid_and_invalid(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    pf = _create(client, admin_headers)
    pid = pf["id"]

    def patch_status(value: str) -> int:
        return client.patch(
            f"{BASE}/{pid}", headers=admin_headers, json={"status": value}
        ).status_code

    # proposed -> closed is illegal.
    illegal = client.patch(f"{BASE}/{pid}", headers=admin_headers, json={"status": "closed"})
    assert illegal.status_code == 422
    assert illegal.json()["error"]["code"] == "illegal_status_transition"

    # Legal progression: proposed -> active -> on_hold -> active -> closed.
    assert patch_status("active") == 200
    assert patch_status("on_hold") == 200
    assert patch_status("active") == 200
    assert patch_status("closed") == 200

    # closed is terminal: closed -> active is illegal.
    assert patch_status("active") == 422


def test_update_owner_and_budget(
    client: TestClient, admin_headers: dict[str, str], session_factory
) -> None:
    from app.modules.auth.models import User

    pf = _create(client, admin_headers)
    with session_factory() as session:
        admin_id = str(session.query(User).one().id)

    updated = client.patch(
        f"{BASE}/{pf['id']}",
        headers=admin_headers,
        json={
            "owner_user_id": admin_id,
            "planned_budget": "999.99",
            "health": "at_risk",
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["owner_user_id"] == admin_id
    assert body["planned_budget"] == "999.99"
    assert body["health"] == "at_risk"
    assert body["version"] == pf["version"] + 1


def test_partial_update_date_cross_validation(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    pf = _create(client, admin_headers, start_date="2026-06-01")
    # Setting only end_date, earlier than the stored start_date, is rejected.
    bad = client.patch(f"{BASE}/{pf['id']}", headers=admin_headers, json={"end_date": "2026-01-01"})
    assert bad.status_code == 422


def test_objectives_lifecycle(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _create(client, admin_headers)
    added = client.post(
        f"{BASE}/{pf['id']}/objectives",
        headers=admin_headers,
        json={"title": "Reduce cycle time", "weight": 40},
    )
    assert added.status_code == 201
    obj_id = added.json()["id"]

    listing = client.get(f"{BASE}/{pf['id']}/objectives", headers=admin_headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    removed = client.delete(f"{BASE}/{pf['id']}/objectives/{obj_id}", headers=admin_headers)
    assert removed.status_code == 200
    assert client.get(f"{BASE}/{pf['id']}/objectives", headers=admin_headers).json() == []


def test_objective_weight_bounds(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _create(client, admin_headers)
    response = client.post(
        f"{BASE}/{pf['id']}/objectives",
        headers=admin_headers,
        json={"title": "Too heavy", "weight": 150},
    )
    assert response.status_code == 422


def test_delete_portfolio(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _create(client, admin_headers)
    client.post(
        f"{BASE}/{pf['id']}/objectives",
        headers=admin_headers,
        json={"title": "Obj"},
    )
    deleted = client.delete(f"{BASE}/{pf['id']}", headers=admin_headers)
    assert deleted.status_code == 200
    assert client.get(f"{BASE}/{pf['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_can_read_not_create(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    """The Member system role grants portfolio:read but not portfolio:create."""
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role_id = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "reader@contoso.com",
            "full_name": "Reed Reader",
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

    assert client.get(BASE, headers=headers).status_code == 200
    forbidden = client.post(BASE, headers=headers, json={"name": "Nope", "code": "NOPE"})
    assert forbidden.status_code == 403
