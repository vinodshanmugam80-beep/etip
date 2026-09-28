"""Integration tests for the Financial Management module.

Covers ledger entry CRUD, the project reference and currency-match rules, the
project forecast/actual rollup sync, the financial summary (planned vs forecast
vs actual, variances, category breakdown), the project→entry cascade, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

ENTRIES = "/api/v1/financial-entries"
PROJECTS = "/api/v1/projects"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str = "PR", **overrides: object) -> dict:
    body: dict[str, object] = {"name": "Project", "code": code}
    body.update(overrides)
    r = client.post(PROJECTS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _entry(
    client: TestClient,
    h: dict[str, str],
    project_id: str,
    entry_type: str,
    amount: str,
    category: str = "labor",
    currency: str = "USD",
) -> object:
    return client.post(
        ENTRIES,
        headers=h,
        json={
            "project_id": project_id,
            "entry_type": entry_type,
            "category": category,
            "amount": amount,
            "currency": currency,
            "entry_date": "2026-03-31",
        },
    )


def test_create_entry_requires_project(client: TestClient, admin_headers: dict[str, str]) -> None:
    r = _entry(client, admin_headers, str(uuid.uuid4()), "actual", "100.00")
    assert r.status_code == 404


def test_currency_must_match_project(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, currency="USD")
    mismatch = _entry(client, admin_headers, proj["id"], "actual", "100.00", currency="EUR")
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "currency_mismatch"


def test_entries_sync_project_rollups(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, budget="100000.00")
    _entry(client, admin_headers, proj["id"], "forecast", "80000.00")
    _entry(client, admin_headers, proj["id"], "actual", "30000.00")
    _entry(client, admin_headers, proj["id"], "actual", "12000.00", category="travel")

    refreshed = client.get(f"{PROJECTS}/{proj['id']}", headers=admin_headers).json()
    assert refreshed["forecast"] == "80000.00"
    assert refreshed["actual_cost"] == "42000.00"  # 30000 + 12000


def test_financial_summary(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, budget="100000.00")
    _entry(client, admin_headers, proj["id"], "budget", "95000.00")
    _entry(client, admin_headers, proj["id"], "forecast", "90000.00")
    _entry(client, admin_headers, proj["id"], "actual", "40000.00", category="labor")
    _entry(client, admin_headers, proj["id"], "actual", "10000.00", category="software")

    summary = client.get(f"{PROJECTS}/{proj['id']}/financial-summary", headers=admin_headers).json()
    assert summary["approved_budget"] == "100000.00"
    assert summary["planned_total"] == "95000.00"
    assert summary["forecast_total"] == "90000.00"
    assert summary["actual_total"] == "50000.00"
    assert summary["budget_variance"] == "50000.00"  # 100000 - 50000
    assert summary["forecast_variance"] == "10000.00"  # 100000 - 90000
    cats = {c["category"]: c["amount"] for c in summary["actual_by_category"]}
    assert cats == {"labor": "40000.00", "software": "10000.00"}


def test_negative_amount_allowed_as_credit(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers, budget="100000.00")
    _entry(client, admin_headers, proj["id"], "actual", "50000.00")
    _entry(client, admin_headers, proj["id"], "actual", "-5000.00")  # refund/credit
    refreshed = client.get(f"{PROJECTS}/{proj['id']}", headers=admin_headers).json()
    assert refreshed["actual_cost"] == "45000.00"


def test_update_and_delete_resync(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    created = _entry(client, admin_headers, proj["id"], "actual", "20000.00").json()

    updated = client.patch(
        f"{ENTRIES}/{created['id']}", headers=admin_headers, json={"amount": "25000.00"}
    )
    assert updated.status_code == 200
    after_update = client.get(f"{PROJECTS}/{proj['id']}", headers=admin_headers).json()
    assert after_update["actual_cost"] == "25000.00"

    assert client.delete(f"{ENTRIES}/{created['id']}", headers=admin_headers).status_code == 200
    after_delete = client.get(f"{PROJECTS}/{proj['id']}", headers=admin_headers).json()
    assert after_delete["actual_cost"] == "0.00"  # rollup back to zero


def test_list_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    _entry(client, admin_headers, proj["id"], "actual", "100.00", category="labor")
    _entry(client, admin_headers, proj["id"], "forecast", "200.00", category="travel")

    by_type = client.get(
        ENTRIES,
        headers=admin_headers,
        params={"project_id": proj["id"], "entry_type": "actual"},
    ).json()
    assert by_type["total"] == 1
    by_cat = client.get(
        ENTRIES,
        headers=admin_headers,
        params={"project_id": proj["id"], "category": "travel"},
    ).json()
    assert by_cat["total"] == 1


def test_project_delete_cascades_entries(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    entry = _entry(client, admin_headers, proj["id"], "actual", "5000.00").json()

    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{ENTRIES}/{entry['id']}", headers=admin_headers).status_code == 404


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
        client.get(ENTRIES, headers=headers, params={"project_id": proj["id"]}).status_code == 200
    )
    assert _entry(client, headers, proj["id"], "actual", "1.00").status_code == 403
