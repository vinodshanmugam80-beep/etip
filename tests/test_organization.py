"""Integration tests for the Organization Management module.

Drives the running application through HTTP with a real authenticated admin,
covering CRUD, the department hierarchy (including cycle prevention), the
single-primary membership invariant, deletion guards, and RBAC enforcement.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.modules.auth.models import Organization, Role, User
from tests.conftest import _login

BASE = "/api/v1/organization"


def _create_business_unit(client: TestClient, headers: dict[str, str], code: str = "TECH") -> dict:
    response = client.post(
        f"{BASE}/business-units",
        headers=headers,
        json={"name": "Technology", "code": code, "description": "Eng"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_department(
    client: TestClient,
    headers: dict[str, str],
    code: str = "PLAT",
    **overrides: object,
) -> dict:
    body: dict[str, object] = {
        "name": "Platform",
        "code": code,
        "description": "Core platform",
    }
    body.update(overrides)
    response = client.post(f"{BASE}/departments", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --- Business units --------------------------------------------------------
def test_create_and_get_business_unit(client: TestClient, admin_headers: dict[str, str]) -> None:
    unit = _create_business_unit(client, admin_headers)
    assert unit["code"] == "TECH"
    fetched = client.get(f"{BASE}/business-units/{unit['id']}", headers=admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Technology"


def test_business_unit_code_is_normalised_and_unique(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    _create_business_unit(client, admin_headers, code="tech")  # lower-case
    duplicate = client.post(
        f"{BASE}/business-units",
        headers=admin_headers,
        json={"name": "Another", "code": "TECH"},
    )
    assert duplicate.status_code == 409


def test_delete_business_unit_blocked_when_departments_exist(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    unit = _create_business_unit(client, admin_headers)
    _create_department(client, admin_headers, business_unit_id=unit["id"])
    blocked = client.delete(f"{BASE}/business-units/{unit['id']}", headers=admin_headers)
    assert blocked.status_code == 409


# --- Departments -----------------------------------------------------------
def test_department_hierarchy_and_filter(client: TestClient, admin_headers: dict[str, str]) -> None:
    unit = _create_business_unit(client, admin_headers)
    parent = _create_department(client, admin_headers, code="PARENT", business_unit_id=unit["id"])
    child = _create_department(
        client,
        admin_headers,
        code="CHILD",
        business_unit_id=unit["id"],
        parent_department_id=parent["id"],
    )
    assert child["parent_department_id"] == parent["id"]

    filtered = client.get(
        f"{BASE}/departments",
        headers=admin_headers,
        params={"business_unit_id": unit["id"]},
    )
    assert filtered.status_code == 200
    assert {d["code"] for d in filtered.json()} == {"PARENT", "CHILD"}


def test_department_cycle_is_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    a = _create_department(client, admin_headers, code="A")
    b = _create_department(client, admin_headers, code="B", parent_department_id=a["id"])
    # Making A a child of B would create A -> B -> A.
    cycle = client.patch(
        f"{BASE}/departments/{a['id']}",
        headers=admin_headers,
        json={"parent_department_id": b["id"]},
    )
    assert cycle.status_code == 422
    assert cycle.json()["error"]["code"] == "validation_error"


def test_department_cannot_be_its_own_parent(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    dept = _create_department(client, admin_headers, code="SELF")
    response = client.patch(
        f"{BASE}/departments/{dept['id']}",
        headers=admin_headers,
        json={"parent_department_id": dept["id"]},
    )
    assert response.status_code == 422


def test_delete_department_blocked_when_children_exist(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    parent = _create_department(client, admin_headers, code="PARENT")
    _create_department(client, admin_headers, code="CHILD", parent_department_id=parent["id"])
    blocked = client.delete(f"{BASE}/departments/{parent['id']}", headers=admin_headers)
    assert blocked.status_code == 409


def test_reference_to_unknown_business_unit_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post(
        f"{BASE}/departments",
        headers=admin_headers,
        json={
            "name": "Orphan",
            "code": "ORPH",
            "business_unit_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 404


def test_update_business_unit_and_department(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    unit = _create_business_unit(client, admin_headers)
    updated_unit = client.patch(
        f"{BASE}/business-units/{unit['id']}",
        headers=admin_headers,
        json={"name": "Technology & Platform", "is_active": False},
    )
    assert updated_unit.status_code == 200
    body = updated_unit.json()
    assert body["name"] == "Technology & Platform"
    assert body["is_active"] is False
    assert body["version"] == unit["version"] + 1  # optimistic version bumped

    dept = _create_department(client, admin_headers, code="ENG")
    updated_dept = client.patch(
        f"{BASE}/departments/{dept['id']}",
        headers=admin_headers,
        json={"description": "Renamed", "business_unit_id": unit["id"]},
    )
    assert updated_dept.status_code == 200
    assert updated_dept.json()["business_unit_id"] == unit["id"]


# --- Settings --------------------------------------------------------------
def test_settings_defaults_then_update(client: TestClient, admin_headers: dict[str, str]) -> None:
    defaults = client.get(f"{BASE}/settings", headers=admin_headers)
    assert defaults.status_code == 200
    assert defaults.json()["currency"] == "USD"

    updated = client.put(
        f"{BASE}/settings",
        headers=admin_headers,
        json={"currency": "eur", "fiscal_year_start_month": 4},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["currency"] == "EUR"  # normalised to upper-case
    assert body["fiscal_year_start_month"] == 4


def test_invalid_fiscal_month_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.put(
        f"{BASE}/settings",
        headers=admin_headers,
        json={"fiscal_year_start_month": 13},
    )
    assert response.status_code == 422


# --- Memberships -----------------------------------------------------------
def test_membership_single_primary_invariant(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    # The admin is the only user; use them as the member under test.
    with session_factory() as session:
        admin = session.query(User).one()
        admin_id = str(admin.id)

    dept_a = _create_department(client, admin_headers, code="DA")
    dept_b = _create_department(client, admin_headers, code="DB")

    m1 = client.post(
        f"{BASE}/departments/{dept_a['id']}/members",
        headers=admin_headers,
        json={"user_id": admin_id, "is_primary": True},
    )
    assert m1.status_code == 201

    m2 = client.post(
        f"{BASE}/departments/{dept_b['id']}/members",
        headers=admin_headers,
        json={"user_id": admin_id, "is_primary": True},
    )
    assert m2.status_code == 201

    # The first membership's primary flag must have been cleared.
    members_a = client.get(
        f"{BASE}/departments/{dept_a['id']}/members", headers=admin_headers
    ).json()
    assert members_a[0]["is_primary"] is False

    # Duplicate membership is rejected.
    dup = client.post(
        f"{BASE}/departments/{dept_a['id']}/members",
        headers=admin_headers,
        json={"user_id": admin_id},
    )
    assert dup.status_code == 409

    # Removal works.
    removed = client.delete(
        f"{BASE}/departments/{dept_a['id']}/members/{admin_id}",
        headers=admin_headers,
    )
    assert removed.status_code == 200


def test_add_unknown_user_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    dept = _create_department(client, admin_headers, code="DX")
    response = client.post(
        f"{BASE}/departments/{dept['id']}/members",
        headers=admin_headers,
        json={"user_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422


# --- RBAC ------------------------------------------------------------------
def test_member_role_cannot_manage_structure(
    client: TestClient,
    registered_org: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    """A user holding only the 'Member' role lacks organization:update."""
    # Seed a limited user directly (user-management API arrives in Module 3).
    with session_factory() as session:
        org = session.query(Organization).one()
        member_role = (
            session.query(Role).filter(Role.organization_id == org.id, Role.name == "Member").one()
        )
        member = User(
            organization_id=org.id,
            email="member@contoso.com",
            full_name="Mel Member",
            hashed_password=hash_password("Member-Passphrase!1"),
        )
        member.roles.append(member_role)
        session.add(member)
        session.commit()

    tokens = _login(
        client,
        {
            "organization_slug": "contoso-ltd",
            "email": "member@contoso.com",
            "password": "Member-Passphrase!1",
        },
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Reads are allowed; writes are forbidden.
    assert client.get(f"{BASE}/business-units", headers=headers).status_code == 200
    forbidden = client.post(
        f"{BASE}/business-units",
        headers=headers,
        json={"name": "Nope", "code": "NOPE"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "permission_denied"
