"""Integration tests for the Program Management module.

Covers program CRUD, the required portfolio reference, code uniqueness and
manager validation, the status lifecycle, search/filter/pagination, the
portfolio-deletion guard (a portfolio containing programs cannot be deleted),
and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

PROGRAMS = "/api/v1/programs"
PORTFOLIOS = "/api/v1/portfolios"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _create_portfolio(client: TestClient, headers: dict[str, str], code: str = "PF1") -> dict:
    response = client.post(
        PORTFOLIOS,
        headers=headers,
        json={"name": "Container", "code": code},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_program(
    client: TestClient,
    headers: dict[str, str],
    portfolio_id: str,
    code: str = "CLOUD",
    **overrides: object,
) -> dict:
    body: dict[str, object] = {
        "portfolio_id": portfolio_id,
        "name": "Cloud Migration",
        "code": code,
        "priority": "high",
        "planned_budget": "1200000.00",
    }
    body.update(overrides)
    response = client.post(PROGRAMS, headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_program(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _create_portfolio(client, admin_headers)
    prog = _create_program(client, admin_headers, pf["id"])
    assert prog["portfolio_id"] == pf["id"]
    assert prog["status"] == "proposed"
    assert prog["code"] == "CLOUD"


def test_create_program_requires_existing_portfolio(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post(
        PROGRAMS,
        headers=admin_headers,
        json={"portfolio_id": str(uuid.uuid4()), "name": "Orphan", "code": "ORPH"},
    )
    assert response.status_code == 404


def test_duplicate_program_code_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _create_portfolio(client, admin_headers)
    _create_program(client, admin_headers, pf["id"], code="dup")
    dup = client.post(
        PROGRAMS,
        headers=admin_headers,
        json={"portfolio_id": pf["id"], "name": "Other", "code": "DUP"},
    )
    assert dup.status_code == 409


def test_unknown_manager_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _create_portfolio(client, admin_headers)
    response = client.post(
        PROGRAMS,
        headers=admin_headers,
        json={
            "portfolio_id": pf["id"],
            "name": "X",
            "code": "X1",
            "manager_user_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 422


def test_bad_date_range_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _create_portfolio(client, admin_headers)
    response = client.post(
        PROGRAMS,
        headers=admin_headers,
        json={
            "portfolio_id": pf["id"],
            "name": "X",
            "code": "X2",
            "start_date": "2026-06-01",
            "end_date": "2026-01-01",
        },
    )
    assert response.status_code == 422


def test_search_by_portfolio_and_status(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf_a = _create_portfolio(client, admin_headers, code="PFA")
    pf_b = _create_portfolio(client, admin_headers, code="PFB")
    _create_program(client, admin_headers, pf_a["id"], code="PA1")
    prog_b = _create_program(client, admin_headers, pf_b["id"], code="PB1")
    client.patch(f"{PROGRAMS}/{prog_b['id']}", headers=admin_headers, json={"status": "active"})

    in_a = client.get(PROGRAMS, headers=admin_headers, params={"portfolio_id": pf_a["id"]}).json()
    assert in_a["total"] == 1
    assert in_a["items"][0]["code"] == "PA1"

    active = client.get(PROGRAMS, headers=admin_headers, params={"status": "active"}).json()
    assert active["total"] == 1
    assert active["items"][0]["code"] == "PB1"


def test_status_lifecycle(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _create_portfolio(client, admin_headers)
    prog = _create_program(client, admin_headers, pf["id"])
    pid = prog["id"]

    illegal = client.patch(f"{PROGRAMS}/{pid}", headers=admin_headers, json={"status": "closed"})
    assert illegal.status_code == 422
    assert illegal.json()["error"]["code"] == "illegal_status_transition"

    for target in ("active", "on_hold", "active", "closed"):
        assert (
            client.patch(
                f"{PROGRAMS}/{pid}", headers=admin_headers, json={"status": target}
            ).status_code
            == 200
        )
    # closed is terminal.
    assert (
        client.patch(
            f"{PROGRAMS}/{pid}", headers=admin_headers, json={"status": "active"}
        ).status_code
        == 422
    )


def test_update_and_delete_program(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _create_portfolio(client, admin_headers)
    prog = _create_program(client, admin_headers, pf["id"])

    updated = client.patch(
        f"{PROGRAMS}/{prog['id']}",
        headers=admin_headers,
        json={"name": "Cloud Migration 2", "planned_budget": "5.50"},
    )
    assert updated.status_code == 200
    assert updated.json()["planned_budget"] == "5.50"

    deleted = client.delete(f"{PROGRAMS}/{prog['id']}", headers=admin_headers)
    assert deleted.status_code == 200
    assert client.get(f"{PROGRAMS}/{prog['id']}", headers=admin_headers).status_code == 404


def test_portfolio_delete_blocked_while_it_has_programs(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    pf = _create_portfolio(client, admin_headers)
    prog = _create_program(client, admin_headers, pf["id"])

    blocked = client.delete(f"{PORTFOLIOS}/{pf['id']}", headers=admin_headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "portfolio_in_use"

    # Removing the program frees the portfolio for deletion.
    client.delete(f"{PROGRAMS}/{prog['id']}", headers=admin_headers)
    ok = client.delete(f"{PORTFOLIOS}/{pf['id']}", headers=admin_headers)
    assert ok.status_code == 200


def test_rbac_member_can_read_not_create(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    """The Member system role grants program:read but not program:create."""
    pf = _create_portfolio(client, admin_headers)
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

    assert client.get(PROGRAMS, headers=headers).status_code == 200
    forbidden = client.post(
        PROGRAMS,
        headers=headers,
        json={"portfolio_id": pf["id"], "name": "Nope", "code": "NOPE"},
    )
    assert forbidden.status_code == 403
