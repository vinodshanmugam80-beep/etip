"""Integration tests for the Project Management module.

Covers project CRUD, auto-assigned numbers, portfolio/program hierarchy
resolution and consistency, reference validation, the status lifecycle,
schedule validation, search/filter/pagination, tags/custom fields, the team-
member and comment child collections, the parent delete guards, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.modules.auth.models import User
from tests.conftest import _login

PROJECTS = "/api/v1/projects"
PORTFOLIOS = "/api/v1/portfolios"
PROGRAMS = "/api/v1/programs"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _portfolio(client: TestClient, h: dict[str, str], code: str = "PF") -> dict:
    r = client.post(PORTFOLIOS, headers=h, json={"name": "PF", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _program(client: TestClient, h: dict[str, str], portfolio_id: str, code: str = "PG") -> dict:
    r = client.post(
        PROGRAMS,
        headers=h,
        json={"portfolio_id": portfolio_id, "name": "PG", "code": code},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _project(client: TestClient, h: dict[str, str], code: str = "P1", **overrides: object) -> dict:
    body: dict[str, object] = {"name": "Billing Rebuild", "code": code}
    body.update(overrides)
    r = client.post(PROJECTS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_project_defaults_and_number(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    p1 = _project(client, admin_headers, code="P1")
    p2 = _project(client, admin_headers, code="P2")
    assert p1["status"] == "proposed"
    assert p1["stage"] == "initiation"
    assert p1["number"] >= 1
    assert p2["number"] == p1["number"] + 1  # running number increments


def test_duplicate_code_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    _project(client, admin_headers, code="dup")
    dup = client.post(PROJECTS, headers=admin_headers, json={"name": "Proj", "code": "DUP"})
    assert dup.status_code == 409


def test_hierarchy_derivation_and_mismatch(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    pf = _portfolio(client, admin_headers, code="PFA")
    pg = _program(client, admin_headers, pf["id"], code="PGA")

    # Supplying only the program derives the portfolio from it.
    proj = _project(client, admin_headers, code="H1", program_id=pg["id"])
    assert proj["program_id"] == pg["id"]
    assert proj["portfolio_id"] == pf["id"]

    # A program with a mismatched explicit portfolio is rejected.
    other_pf = _portfolio(client, admin_headers, code="PFB")
    mismatch = client.post(
        PROJECTS,
        headers=admin_headers,
        json={
            "name": "Mism",
            "code": "H2",
            "program_id": pg["id"],
            "portfolio_id": other_pf["id"],
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "hierarchy_mismatch"


def test_unknown_references_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert (
        client.post(
            PROJECTS,
            headers=admin_headers,
            json={"name": "Proj", "code": "U1", "portfolio_id": str(uuid.uuid4())},
        ).status_code
        == 404
    )
    assert (
        client.post(
            PROJECTS,
            headers=admin_headers,
            json={"name": "Proj", "code": "U2", "program_id": str(uuid.uuid4())},
        ).status_code
        == 404
    )
    assert (
        client.post(
            PROJECTS,
            headers=admin_headers,
            json={"name": "Proj", "code": "U3", "department_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )
    assert (
        client.post(
            PROJECTS,
            headers=admin_headers,
            json={"name": "Proj", "code": "U4", "manager_user_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )


def test_schedule_validation(client: TestClient, admin_headers: dict[str, str]) -> None:
    bad = client.post(
        PROJECTS,
        headers=admin_headers,
        json={"name": "Proj", "code": "S1", "start_date": "2026-06-01", "end_date": "2026-01-01"},
    )
    assert bad.status_code == 422
    bad_base = client.post(
        PROJECTS,
        headers=admin_headers,
        json={
            "name": "Proj",
            "code": "S2",
            "baseline_start_date": "2026-06-01",
            "baseline_end_date": "2026-01-01",
        },
    )
    assert bad_base.status_code == 422


def test_tags_and_custom_fields(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(
        client,
        admin_headers,
        code="T1",
        tags=["finance", "finance", " modernization "],
        custom_fields={"cost_center": "CC-1"},
    )
    assert proj["tags"] == ["finance", "modernization"]  # de-duped and trimmed
    assert proj["custom_fields"]["cost_center"] == "CC-1"


def test_search_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _portfolio(client, admin_headers, code="PFS")
    a = _project(client, admin_headers, code="AAA", name="Alpha", portfolio_id=pf["id"])
    _project(client, admin_headers, code="BBB", name="Beta")
    client.patch(f"{PROJECTS}/{a['id']}", headers=admin_headers, json={"status": "active"})

    page = client.get(PROJECTS, headers=admin_headers, params={"limit": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1

    active = client.get(PROJECTS, headers=admin_headers, params={"status": "active"}).json()
    assert active["total"] == 1 and active["items"][0]["code"] == "AAA"

    in_pf = client.get(PROJECTS, headers=admin_headers, params={"portfolio_id": pf["id"]}).json()
    assert in_pf["total"] == 1


def test_status_lifecycle_and_progress(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, code="L1")
    pid = proj["id"]

    illegal = client.patch(f"{PROJECTS}/{pid}", headers=admin_headers, json={"status": "closed"})
    assert illegal.status_code == 422

    for target in ("active", "on_hold", "active", "closed"):
        assert (
            client.patch(
                f"{PROJECTS}/{pid}", headers=admin_headers, json={"status": target}
            ).status_code
            == 200
        )

    # Progress bounds enforced by schema.
    proj2 = _project(client, admin_headers, code="L2")
    assert (
        client.patch(
            f"{PROJECTS}/{proj2['id']}", headers=admin_headers, json={"progress_percent": 150}
        ).status_code
        == 422
    )


def test_update_fields_and_partial_date_check(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers, code="UP", start_date="2026-06-01")
    updated = client.patch(
        f"{PROJECTS}/{proj['id']}",
        headers=admin_headers,
        json={"actual_cost": "123.45", "progress_percent": 60, "health": "at_risk"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["actual_cost"] == "123.45"
    assert body["progress_percent"] == 60
    assert body["health"] == "at_risk"

    # Setting only end_date earlier than the stored start_date is rejected.
    bad = client.patch(
        f"{PROJECTS}/{proj['id']}", headers=admin_headers, json={"end_date": "2026-01-01"}
    )
    assert bad.status_code == 422


def test_team_members(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, code="TM")
    with session_factory() as session:
        admin_id = str(session.query(User).one().id)

    added = client.post(
        f"{PROJECTS}/{proj['id']}/team",
        headers=admin_headers,
        json={"user_id": admin_id, "role_label": "Lead", "allocation_percent": 50},
    )
    assert added.status_code == 201
    assert added.json()["role_label"] == "Lead"

    # Duplicate membership rejected.
    dup = client.post(
        f"{PROJECTS}/{proj['id']}/team", headers=admin_headers, json={"user_id": admin_id}
    )
    assert dup.status_code == 409

    # Unknown user rejected.
    unknown = client.post(
        f"{PROJECTS}/{proj['id']}/team",
        headers=admin_headers,
        json={"user_id": str(uuid.uuid4())},
    )
    assert unknown.status_code == 422

    members = client.get(f"{PROJECTS}/{proj['id']}/team", headers=admin_headers)
    assert len(members.json()) == 1

    removed = client.delete(f"{PROJECTS}/{proj['id']}/team/{admin_id}", headers=admin_headers)
    assert removed.status_code == 200


def test_comments(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, code="CM")
    posted = client.post(
        f"{PROJECTS}/{proj['id']}/comments",
        headers=admin_headers,
        json={"body": "Kickoff scheduled for Monday."},
    )
    assert posted.status_code == 201
    cid = posted.json()["id"]

    listing = client.get(f"{PROJECTS}/{proj['id']}/comments", headers=admin_headers)
    assert len(listing.json()) == 1

    # Empty body rejected.
    empty = client.post(
        f"{PROJECTS}/{proj['id']}/comments", headers=admin_headers, json={"body": ""}
    )
    assert empty.status_code == 422

    removed = client.delete(f"{PROJECTS}/{proj['id']}/comments/{cid}", headers=admin_headers)
    assert removed.status_code == 200


def test_parent_delete_guards(client: TestClient, admin_headers: dict[str, str]) -> None:
    pf = _portfolio(client, admin_headers, code="PFG")
    pg = _program(client, admin_headers, pf["id"], code="PGG")
    proj = _project(client, admin_headers, code="PG1", program_id=pg["id"])

    # Program with a project cannot be deleted.
    assert client.delete(f"{PROGRAMS}/{pg['id']}", headers=admin_headers).status_code == 409
    # Portfolio with a project (and a program) cannot be deleted.
    assert client.delete(f"{PORTFOLIOS}/{pf['id']}", headers=admin_headers).status_code == 409

    # Remove the project, then the program, then the portfolio.
    client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers)
    assert client.delete(f"{PROGRAMS}/{pg['id']}", headers=admin_headers).status_code == 200
    assert client.delete(f"{PORTFOLIOS}/{pf['id']}", headers=admin_headers).status_code == 200


def test_rbac_member_read_not_create(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
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
    assert client.get(PROJECTS, headers=headers).status_code == 200
    assert (
        client.post(PROJECTS, headers=headers, json={"name": "Nope", "code": "NOPE"}).status_code
        == 403
    )
