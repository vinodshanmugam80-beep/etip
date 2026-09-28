"""Integration tests for the per-project KPI register.

Covers CRUD on a project's KPIs, the derived attainment / on-target maths for
both directions (higher-is-better and lower-is-better), the equal-baseline-target
edge case, the project KPI summary roll-up, RBAC, and not-found handling.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

PROJECTS = "/api/v1/projects"
PKPI = "/api/v1/project-kpis"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str) -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": f"Project {code}", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _kpi(client: TestClient, h: dict[str, str], pid: str, **body: object) -> dict:
    payload: dict[str, object] = {"name": "KPI", "direction": "increase"}
    payload.update(body)
    r = client.post(f"{PROJECTS}/{pid}/kpis", headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_attainment_increase_and_on_target(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    p = _project(client, admin_headers, "PK1")
    # baseline 40 → target 90, current 65 → halfway = 50%.
    k = _kpi(
        client,
        admin_headers,
        p["id"],
        name="Coverage",
        unit="%",
        direction="increase",
        baseline_value="40",
        current_value="65",
        target_value="90",
    )
    assert k["attainment_percent"] == 50.0
    assert k["on_target"] is False

    # Reaching the target flips on_target and attainment to 100.
    updated = client.patch(
        f"{PKPI}/{k['id']}", headers=admin_headers, json={"current_value": "90"}
    ).json()
    assert updated["attainment_percent"] == 100.0
    assert updated["on_target"] is True


def test_attainment_decrease_direction(client: TestClient, admin_headers: dict[str, str]) -> None:
    p = _project(client, admin_headers, "PK2")
    # Lower is better: baseline 120 → target 30, current 75 → (120-75)/(120-30)=50%.
    k = _kpi(
        client,
        admin_headers,
        p["id"],
        name="MTTR",
        unit="min",
        direction="decrease",
        baseline_value="120",
        current_value="75",
        target_value="30",
    )
    assert k["attainment_percent"] == 50.0
    assert k["on_target"] is False
    # At/below target is on_target.
    below = client.patch(
        f"{PKPI}/{k['id']}", headers=admin_headers, json={"current_value": "25"}
    ).json()
    assert below["on_target"] is True


def test_equal_baseline_target_reports_none(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    p = _project(client, admin_headers, "PK3")
    k = _kpi(
        client,
        admin_headers,
        p["id"],
        name="Flat",
        direction="increase",
        baseline_value="50",
        current_value="50",
        target_value="50",
    )
    assert k["attainment_percent"] is None
    assert k["on_target"] is True  # current >= target


def test_list_and_summary(client: TestClient, admin_headers: dict[str, str]) -> None:
    p = _project(client, admin_headers, "PK4")
    _kpi(
        client,
        admin_headers,
        p["id"],
        name="On track",
        direction="increase",
        baseline_value="0",
        current_value="100",
        target_value="100",
    )  # 100%, on target
    _kpi(
        client,
        admin_headers,
        p["id"],
        name="Behind",
        direction="increase",
        baseline_value="0",
        current_value="20",
        target_value="100",
    )  # 20%, off target

    listing = client.get(f"{PROJECTS}/{p['id']}/kpis", headers=admin_headers).json()
    assert listing["total"] == 2

    summary = client.get(f"{PROJECTS}/{p['id']}/kpi-summary", headers=admin_headers).json()
    assert summary["total"] == 2
    assert summary["on_target"] == 1
    assert summary["off_target"] == 1
    assert summary["average_attainment"] == 60.0  # (100 + 20) / 2


def test_delete(client: TestClient, admin_headers: dict[str, str]) -> None:
    p = _project(client, admin_headers, "PK5")
    k = _kpi(client, admin_headers, p["id"], name="Temp")
    assert client.delete(f"{PKPI}/{k['id']}", headers=admin_headers).status_code == 200
    listing = client.get(f"{PROJECTS}/{p['id']}/kpis", headers=admin_headers).json()
    assert listing["total"] == 0


def test_not_found(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{PROJECTS}/{uuid.uuid4()}/kpis", headers=admin_headers).status_code == 404
    assert (
        client.patch(
            f"{PKPI}/{uuid.uuid4()}", headers=admin_headers, json={"current_value": "1"}
        ).status_code
        == 404
    )


def test_rbac(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    p = _project(client, admin_headers, "PK6")
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "pk-member@contoso.com",
            "full_name": "Pk Member",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "pk-member@contoso.com",
            "password": PW,
        },
    )
    member = {"Authorization": f"Bearer {tokens['access_token']}"}
    # Member can read KPIs but not create them.
    assert client.get(f"{PROJECTS}/{p['id']}/kpis", headers=member).status_code == 200
    assert (
        client.post(f"{PROJECTS}/{p['id']}/kpis", headers=member, json={"name": "Nope"}).status_code
        == 403
    )
