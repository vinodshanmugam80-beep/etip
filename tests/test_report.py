"""Integration tests for the Reports module.

Covers report-definition CRUD, owner + shared visibility scoping, owner-only
edit/delete (distinct from RBAC), the report engine for each report type
(assembled from live cross-module data), parameter validation, last-run
stamping, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

REPORTS = "/api/v1/reports"
PROJECTS = "/api/v1/projects"
RISKS = "/api/v1/risks"
ISSUES = "/api/v1/issues"
ACTIONS = "/api/v1/actions"
MILESTONES = "/api/v1/milestones"
TS = "/api/v1/timesheets"
PORTFOLIOS = "/api/v1/portfolios"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str = "PR", **o: object) -> dict:
    body: dict[str, object] = {"name": "Project", "code": code}
    body.update(o)
    r = client.post(PROJECTS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _user_with_role(
    client: TestClient, admin_headers: dict[str, str], email: str, role_name: str
) -> str:
    roles = client.get(ROLES, headers=admin_headers).json()
    role_id = next(r["id"] for r in roles if r["name"] == role_name)
    r = client.post(
        USERS,
        headers=admin_headers,
        json={"email": email, "full_name": "Person", "password": PW, "role_ids": [role_id]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _headers(client: TestClient, registered_org: dict[str, str], email: str) -> dict[str, str]:
    tokens = _login(
        client,
        {"organization_slug": registered_org["organization_slug"], "email": email, "password": PW},
    )
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _report(
    client: TestClient,
    h: dict[str, str],
    report_type: str,
    params: dict,
    name: str = "My report",
    shared: bool = False,
) -> dict:
    r = client.post(
        REPORTS,
        headers=h,
        json={"name": name, "report_type": report_type, "parameters": params, "is_shared": shared},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_visibility_own_and_shared(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    _report(
        client,
        admin_headers,
        "project_status",
        {"project_id": proj["id"]},
        name="Shared one",
        shared=True,
    )
    _report(
        client,
        admin_headers,
        "project_status",
        {"project_id": proj["id"]},
        name="Private one",
        shared=False,
    )

    _user_with_role(client, admin_headers, "pm@contoso.com", "Project Manager")
    pm = _headers(client, registered_org, "pm@contoso.com")
    own = _report(client, pm, "raid_summary", {"project_id": proj["id"]}, name="PM own")

    listing = client.get(REPORTS, headers=pm).json()
    names = {r["name"] for r in listing["items"]}
    assert "Shared one" in names  # shared by admin
    assert "PM own" in names  # own
    assert "Private one" not in names  # admin's private, not visible
    assert own["created_by"] is not None


def test_owner_only_edit(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    shared = _report(
        client,
        admin_headers,
        "project_status",
        {"project_id": proj["id"]},
        name="Admin shared",
        shared=True,
    )

    _user_with_role(client, admin_headers, "pm2@contoso.com", "Project Manager")
    pm = _headers(client, registered_org, "pm2@contoso.com")
    # PM can see and run it, but is not the owner, so cannot edit (403 despite
    # holding report:update).
    assert client.get(f"{REPORTS}/{shared['id']}", headers=pm).status_code == 200
    assert (
        client.patch(f"{REPORTS}/{shared['id']}", headers=pm, json={"name": "Hijack"}).status_code
        == 403
    )
    assert client.delete(f"{REPORTS}/{shared['id']}", headers=pm).status_code == 403
    # The owner can.
    assert (
        client.patch(
            f"{REPORTS}/{shared['id']}", headers=admin_headers, json={"name": "Renamed"}
        ).status_code
        == 200
    )


def test_run_project_status_and_param_validation(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers, code="ATLAS", budget="100000.00")
    run = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={"report_type": "project_status", "parameters": {"project_id": proj["id"]}},
    )
    assert run.status_code == 200
    data = run.json()["data"]
    assert data["code"] == "ATLAS" and data["budget"] == "100000.00"
    assert data["status"] == proj["status"]

    # Missing parameter.
    missing = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={"report_type": "project_status", "parameters": {}},
    )
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "missing_parameter"
    # Unknown project.
    unknown = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={"report_type": "project_status", "parameters": {"project_id": str(uuid.uuid4())}},
    )
    assert unknown.status_code == 404


def test_run_raid_milestone_timesheet(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    pid = proj["id"]
    client.post(
        RISKS,
        headers=admin_headers,
        json={"project_id": pid, "title": "A risk", "probability": 4, "impact": 4},
    )
    client.post(ISSUES, headers=admin_headers, json={"project_id": pid, "title": "An issue"})
    client.post(ACTIONS, headers=admin_headers, json={"project_id": pid, "title": "An action"})
    client.post(
        MILESTONES,
        headers=admin_headers,
        json={
            "project_id": pid,
            "name": "A milestone",
            "target_date": "2030-01-01",
            "is_key": True,
        },
    )
    entry = client.post(
        TS,
        headers=admin_headers,
        json={"project_id": pid, "work_date": "2026-03-02", "hours": "5.00"},
    ).json()
    client.patch(f"{TS}/{entry['id']}", headers=admin_headers, json={"status": "submitted"})
    client.post(f"{TS}/{entry['id']}/approve", headers=admin_headers, json={})

    raid = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={"report_type": "raid_summary", "parameters": {"project_id": pid}},
    ).json()["data"]
    assert (
        raid["risks"]["open"] == 1 and raid["issues"]["open"] == 1 and raid["actions"]["open"] == 1
    )

    ms = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={"report_type": "milestone_status", "parameters": {"project_id": pid}},
    ).json()["data"]
    assert ms["total"] == 1 and ms["key"] == 1

    hours = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={"report_type": "timesheet_hours", "parameters": {"project_id": pid}},
    ).json()["data"]
    assert hours["total_hours"] == "5.00" and hours["by_status"].get("approved") == "5.00"


def test_run_financial_and_portfolio(client: TestClient, admin_headers: dict[str, str]) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Growth", "code": "GROW"}
    ).json()
    p1 = _project(client, admin_headers, code="P1", budget="50000.00", portfolio_id=port["id"])
    _project(client, admin_headers, code="P2", budget="30000.00", portfolio_id=port["id"])

    fin = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={"report_type": "financial_summary", "parameters": {"project_id": p1["id"]}},
    ).json()["data"]
    assert fin["budget"] == "50000.00" and fin["cost_variance"] == "50000.00"

    over = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={"report_type": "portfolio_overview", "parameters": {"portfolio_id": port["id"]}},
    ).json()["data"]
    assert over["project_count"] == 2
    assert over["total_budget"] == "80000.00"


def test_run_saved_stamps_last_run(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    saved = _report(
        client, admin_headers, "project_status", {"project_id": proj["id"]}, name="Saved"
    )
    assert saved["last_run_date"] is None
    run = client.post(f"{REPORTS}/{saved['id']}/run", headers=admin_headers)
    assert run.status_code == 200 and run.json()["report_type"] == "project_status"
    got = client.get(f"{REPORTS}/{saved['id']}", headers=admin_headers).json()
    assert got["last_run_date"] is not None


def test_update_and_invalid_params(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    rpt = _report(
        client, admin_headers, "project_status", {"project_id": proj["id"]}, name="Editable"
    )
    updated = client.patch(
        f"{REPORTS}/{rpt['id']}",
        headers=admin_headers,
        json={
            "description": "now described",
            "parameters": {"project_id": proj["id"]},
            "is_shared": True,
        },
    ).json()
    assert updated["description"] == "now described" and updated["is_shared"] is True

    bad_id = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={"report_type": "project_status", "parameters": {"project_id": "not-a-uuid"}},
    )
    assert bad_id.status_code == 422 and bad_id.json()["error"]["code"] == "invalid_parameter"

    bad_date = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={
            "report_type": "timesheet_hours",
            "parameters": {"project_id": proj["id"], "date_from": "03/02/2026"},
        },
    )
    assert bad_date.status_code == 422 and bad_date.json()["error"]["code"] == "invalid_parameter"

    neither = client.post(
        f"{REPORTS}/run",
        headers=admin_headers,
        json={"report_type": "timesheet_hours", "parameters": {}},
    )
    assert neither.status_code == 422

    filtered = client.get(
        REPORTS, headers=admin_headers, params={"report_type": "project_status"}
    ).json()
    assert filtered["total"] >= 1


def test_rbac_member_creates_runs_not_updates(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    _user_with_role(client, admin_headers, "rep@contoso.com", "Member")
    h = _headers(client, registered_org, "rep@contoso.com")

    created = _report(client, h, "project_status", {"project_id": proj["id"]}, name="Member report")
    # Member can run (report:read).
    assert client.post(f"{REPORTS}/{created['id']}/run", headers=h).status_code == 200
    # But lacks report:update / report:delete.
    assert (
        client.patch(f"{REPORTS}/{created['id']}", headers=h, json={"name": "x2"}).status_code
        == 403
    )
    assert client.delete(f"{REPORTS}/{created['id']}", headers=h).status_code == 403
