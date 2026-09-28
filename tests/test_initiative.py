"""Integration tests for Strategic Initiatives, Business Goals and KPIs.

Covers CRUD across the three levels, KPI attainment/variance/target-met for both
directions, initiative/goal rollups, cascade on delete, reference validation,
RBAC and not-found handling.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

INIT = "/api/v1/initiatives"
GOALS = "/api/v1/goals"
KPIS = "/api/v1/kpis"
PORTFOLIOS = "/api/v1/portfolios"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _initiative(
    client: TestClient, h: dict[str, str], name: str = "Digital first", **body: object
) -> dict:
    payload: dict[str, object] = {"name": name}
    payload.update(body)
    r = client.post(INIT, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _goal(
    client: TestClient,
    h: dict[str, str],
    initiative_id: str,
    title: str = "Grow revenue",
    **body: object,
) -> dict:
    payload: dict[str, object] = {"initiative_id": initiative_id, "title": title}
    payload.update(body)
    r = client.post(GOALS, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _kpi(client: TestClient, h: dict[str, str], goal_id: str, **body: object) -> dict:
    payload: dict[str, object] = {"goal_id": goal_id, "name": "Revenue"}
    payload.update(body)
    r = client.post(KPIS, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_initiative_crud_and_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Core", "code": "INI"}
    ).json()
    init = _initiative(
        client, admin_headers, portfolio_id=port["id"], status="active", priority="high"
    )
    assert init["status"] == "active" and init["portfolio_id"] == port["id"]

    got = client.get(f"{INIT}/{init['id']}", headers=admin_headers).json()
    assert got["name"] == "Digital first"
    upd = client.patch(
        f"{INIT}/{init['id']}", headers=admin_headers, json={"status": "on_hold"}
    ).json()
    assert upd["status"] == "on_hold"

    _initiative(client, admin_headers, name="Second one", status="active")
    active = client.get(INIT, headers=admin_headers, params={"status": "active"}).json()
    assert active["total"] == 1
    by_port = client.get(INIT, headers=admin_headers, params={"portfolio_id": port["id"]}).json()
    assert by_port["total"] == 1


def test_reference_validation(client: TestClient, admin_headers: dict[str, str]) -> None:
    bad_port = client.post(
        INIT, headers=admin_headers, json={"name": "Bad port", "portfolio_id": str(uuid.uuid4())}
    )
    assert bad_port.status_code == 422
    bad_sponsor = client.post(
        INIT,
        headers=admin_headers,
        json={"name": "Bad sponsor", "sponsor_user_id": str(uuid.uuid4())},
    )
    assert bad_sponsor.status_code == 422


def test_goal_and_kpi_crud(client: TestClient, admin_headers: dict[str, str]) -> None:
    init = _initiative(client, admin_headers)
    goal = _goal(client, admin_headers, init["id"], category="growth")
    assert goal["initiative_id"] == init["id"]
    # Goal under unknown initiative.
    assert (
        client.post(
            GOALS,
            headers=admin_headers,
            json={"initiative_id": str(uuid.uuid4()), "title": "Orphan"},
        ).status_code
        == 404
    )

    kpi = _kpi(client, admin_headers, goal["id"], unit="USD", target_value="1000")
    # KPI under unknown goal.
    assert (
        client.post(
            KPIS, headers=admin_headers, json={"goal_id": str(uuid.uuid4()), "name": "Orphan"}
        ).status_code
        == 404
    )

    # Listings.
    assert len(client.get(f"{INIT}/{init['id']}/goals", headers=admin_headers).json()) == 1
    assert len(client.get(f"{GOALS}/{goal['id']}/kpis", headers=admin_headers).json()) == 1

    # Update + delete KPI.
    client.patch(f"{KPIS}/{kpi['id']}", headers=admin_headers, json={"name": "Net revenue"})
    assert client.get(f"{KPIS}/{kpi['id']}", headers=admin_headers).json()["name"] == "Net revenue"
    assert client.delete(f"{KPIS}/{kpi['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"{KPIS}/{kpi['id']}", headers=admin_headers).status_code == 404


def test_kpi_attainment_increase(client: TestClient, admin_headers: dict[str, str]) -> None:
    init = _initiative(client, admin_headers)
    goal = _goal(client, admin_headers, init["id"])
    kpi = _kpi(
        client,
        admin_headers,
        goal["id"],
        direction="increase",
        baseline_value="0",
        current_value="50",
        target_value="100",
    )
    assert kpi["attainment_percent"] == 50.0
    assert float(kpi["variance"]) == -50.0 and kpi["target_met"] is False
    # Record beyond target.
    beat = client.post(
        f"{KPIS}/{kpi['id']}/measurement", headers=admin_headers, json={"current_value": "120"}
    ).json()
    assert beat["attainment_percent"] == 120.0 and beat["target_met"] is True
    assert float(beat["variance"]) == 20.0


def test_kpi_attainment_decrease(client: TestClient, admin_headers: dict[str, str]) -> None:
    init = _initiative(client, admin_headers)
    goal = _goal(client, admin_headers, init["id"])
    # Lower is better: baseline 100, target 50, current 75 → 50% of the way.
    kpi = _kpi(
        client,
        admin_headers,
        goal["id"],
        name="Defect rate",
        direction="decrease",
        baseline_value="100",
        current_value="75",
        target_value="50",
    )
    assert kpi["attainment_percent"] == 50.0 and kpi["target_met"] is False
    beat = client.post(
        f"{KPIS}/{kpi['id']}/measurement", headers=admin_headers, json={"current_value": "40"}
    ).json()
    assert beat["attainment_percent"] == 120.0 and beat["target_met"] is True


def test_summaries(client: TestClient, admin_headers: dict[str, str]) -> None:
    init = _initiative(client, admin_headers)
    goal = _goal(client, admin_headers, init["id"])
    _kpi(
        client,
        admin_headers,
        goal["id"],
        name="Met",
        baseline_value="0",
        current_value="100",
        target_value="100",
    )
    _kpi(
        client,
        admin_headers,
        goal["id"],
        name="Half",
        baseline_value="0",
        current_value="50",
        target_value="100",
    )

    gs = client.get(f"{GOALS}/{goal['id']}/summary", headers=admin_headers).json()
    assert gs["kpi_count"] == 2 and gs["kpis_met"] == 1
    assert gs["average_attainment"] == 75.0  # (100 + 50) / 2

    isum = client.get(f"{INIT}/{init['id']}/summary", headers=admin_headers).json()
    assert isum["goal_count"] == 1 and isum["kpi_count"] == 2 and isum["kpis_met"] == 1
    assert isum["average_attainment"] == 75.0
    assert len(isum["goals"]) == 1


def test_delete_cascades(client: TestClient, admin_headers: dict[str, str]) -> None:
    init = _initiative(client, admin_headers)
    goal = _goal(client, admin_headers, init["id"])
    kpi = _kpi(client, admin_headers, goal["id"])
    assert client.delete(f"{INIT}/{init['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"{INIT}/{init['id']}", headers=admin_headers).status_code == 404
    assert client.get(f"{GOALS}/{goal['id']}", headers=admin_headers).status_code == 404
    assert client.get(f"{KPIS}/{kpi['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_read_only(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    _initiative(client, admin_headers)
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "init@contoso.com",
            "full_name": "Init Reader",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "init@contoso.com",
            "password": PW,
        },
    )
    member = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get(INIT, headers=member).status_code == 200
    assert client.post(INIT, headers=member, json={"name": "No can do"}).status_code == 403


def test_update_paths_and_goal_delete(client: TestClient, admin_headers: dict[str, str]) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "UpdP", "code": "UPI"}
    ).json()
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    sponsor = client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "sp@contoso.com",
            "full_name": "Sponsor P",
            "password": PW,
            "role_ids": [member_role],
        },
    ).json()

    init = _initiative(client, admin_headers)
    # Update initiative portfolio + sponsor + name.
    upd = client.patch(
        f"{INIT}/{init['id']}",
        headers=admin_headers,
        json={"name": "Renamed init", "portfolio_id": port["id"], "sponsor_user_id": sponsor["id"]},
    ).json()
    assert upd["name"] == "Renamed init" and upd["portfolio_id"] == port["id"]
    assert upd["sponsor_user_id"] == sponsor["id"]

    goal = _goal(client, admin_headers, init["id"])
    kpi = _kpi(
        client,
        admin_headers,
        goal["id"],
        direction="increase",
        baseline_value="0",
        target_value="10",
    )
    # Update goal fields.
    gu = client.patch(
        f"{GOALS}/{goal['id']}",
        headers=admin_headers,
        json={"title": "Bigger goal", "status": "in_progress"},
    ).json()
    assert gu["title"] == "Bigger goal" and gu["status"] == "in_progress"
    # Update KPI definition (direction + target).
    ku = client.patch(
        f"{KPIS}/{kpi['id']}",
        headers=admin_headers,
        json={"direction": "decrease", "target_value": "5"},
    ).json()
    assert ku["direction"] == "decrease"
    # Delete goal alone → its KPI goes too.
    assert client.delete(f"{GOALS}/{goal['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"{KPIS}/{kpi['id']}", headers=admin_headers).status_code == 404
