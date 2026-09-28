"""Integration tests for the Skills Matrix.

Covers skill-catalogue CRUD with name uniqueness, resource-skill assignments,
the matrix / coverage / capacity views, cascade on skill delete, RBAC and
not-found handling.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

SK = "/api/v1/skills"
RESOURCES = "/api/v1/resources"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _skill(client: TestClient, h: dict[str, str], name: str, **body: object) -> dict:
    payload: dict[str, object] = {"name": name}
    payload.update(body)
    r = client.post(SK, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _resource(client: TestClient, h: dict[str, str], name: str, hours: str = "40.00") -> str:
    r = client.post(
        RESOURCES,
        headers=h,
        json={
            "name": name,
            "resource_type": "employee",
            "capacity_hours_per_week": hours,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _assign(
    client: TestClient, h: dict[str, str], resource_id: str, skill_id: str, prof: int
) -> dict:
    r = client.post(
        f"{SK}/assignments",
        headers=h,
        json={"resource_id": resource_id, "skill_id": skill_id, "proficiency": prof},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_skill_catalogue_crud(client: TestClient, admin_headers: dict[str, str]) -> None:
    skill = _skill(client, admin_headers, "Python", category="technical", description="Backend")
    assert skill["category"] == "technical"
    # Duplicate name (case-insensitive) → 409.
    dup = client.post(SK, headers=admin_headers, json={"name": "python"})
    assert dup.status_code == 409

    got = client.get(f"{SK}/{skill['id']}", headers=admin_headers).json()
    assert got["name"] == "Python"
    updated = client.patch(
        f"{SK}/{skill['id']}", headers=admin_headers, json={"category": "functional"}
    ).json()
    assert updated["category"] == "functional"

    # Search by category + query.
    _skill(client, admin_headers, "Leadership", category="leadership")
    tech = client.get(SK, headers=admin_headers, params={"category": "functional"}).json()
    assert tech["total"] == 1
    q = client.get(SK, headers=admin_headers, params={"query": "lead"}).json()
    assert q["total"] == 1

    assert client.delete(f"{SK}/{skill['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"{SK}/{skill['id']}", headers=admin_headers).status_code == 404


def test_assignments(client: TestClient, admin_headers: dict[str, str]) -> None:
    res = _resource(client, admin_headers, "Ada Lovelace")
    skill = _skill(client, admin_headers, "Rust")
    a = _assign(client, admin_headers, res, skill["id"], 4)
    assert a["proficiency"] == 4

    # Duplicate assignment → 409.
    dup = client.post(
        f"{SK}/assignments",
        headers=admin_headers,
        json={"resource_id": res, "skill_id": skill["id"], "proficiency": 2},
    )
    assert dup.status_code == 409

    # A resource's skills.
    listing = client.get(f"{SK}/resources/{res}", headers=admin_headers).json()
    assert len(listing) == 1 and listing[0]["skill_id"] == skill["id"]

    # Update + remove.
    upd = client.patch(
        f"{SK}/assignments/{a['id']}",
        headers=admin_headers,
        json={"proficiency": 5, "years_experience": "3.5"},
    ).json()
    assert upd["proficiency"] == 5 and upd["years_experience"] == "3.5"
    assert client.delete(f"{SK}/assignments/{a['id']}", headers=admin_headers).status_code == 204

    # Unknown resource / skill on assign → 404.
    assert (
        client.post(
            f"{SK}/assignments",
            headers=admin_headers,
            json={
                "resource_id": str(uuid.uuid4()),
                "skill_id": skill["id"],
                "proficiency": 3,
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{SK}/assignments",
            headers=admin_headers,
            json={"resource_id": res, "skill_id": str(uuid.uuid4()), "proficiency": 3},
        ).status_code
        == 404
    )


def test_matrix_coverage_capacity(client: TestClient, admin_headers: dict[str, str]) -> None:
    r1 = _resource(client, admin_headers, "Engineer One", "40.00")
    r2 = _resource(client, admin_headers, "Engineer Two", "20.00")
    py = _skill(client, admin_headers, "Python")
    sql = _skill(client, admin_headers, "SQL")
    _assign(client, admin_headers, r1, py["id"], 5)
    _assign(client, admin_headers, r1, sql["id"], 3)
    _assign(client, admin_headers, r2, py["id"], 2)

    # Matrix.
    matrix = client.get(f"{SK}/matrix", headers=admin_headers).json()
    assert len(matrix["skills"]) == 2
    rows = {row["resource_name"]: row for row in matrix["rows"]}
    assert len(rows["Engineer One"]["skills"]) == 2
    assert len(rows["Engineer Two"]["skills"]) == 1

    # Coverage: Python at proficiency >= 3 → only Engineer One.
    cov = client.get(
        f"{SK}/{py['id']}/resources",
        headers=admin_headers,
        params={"min_proficiency": 3},
    ).json()
    assert cov["resource_count"] == 1 and cov["resources"][0]["resource_name"] == "Engineer One"

    # Capacity: Python has 2 resources, 60 hours; SQL has 1, 40 hours.
    cap = client.get(f"{SK}/capacity", headers=admin_headers).json()
    by_skill = {i["skill_name"]: i for i in cap["items"]}
    assert by_skill["Python"]["resource_count"] == 2
    assert float(by_skill["Python"]["total_capacity_hours"]) == 60.0
    assert by_skill["Python"]["average_proficiency"] == 3.5  # (5 + 2) / 2
    assert float(by_skill["SQL"]["total_capacity_hours"]) == 40.0


def test_delete_skill_cascades_assignments(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    res = _resource(client, admin_headers, "Grace Hopper")
    skill = _skill(client, admin_headers, "COBOL")
    _assign(client, admin_headers, res, skill["id"], 5)
    assert client.delete(f"{SK}/{skill['id']}", headers=admin_headers).status_code == 204
    # The resource no longer shows the skill.
    listing = client.get(f"{SK}/resources/{res}", headers=admin_headers).json()
    assert listing == []


def test_rbac_member_read_only(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    _skill(client, admin_headers, "Kubernetes")
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "sk@contoso.com",
            "full_name": "Sk Reader",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "sk@contoso.com",
            "password": PW,
        },
    )
    member = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get(SK, headers=member).status_code == 200
    assert client.post(SK, headers=member, json={"name": "Terraform"}).status_code == 403


def test_not_found(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{SK}/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{SK}/{uuid.uuid4()}/resources", headers=admin_headers).status_code == 404
    assert client.get(f"{SK}/resources/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_update_skill_name(client: TestClient, admin_headers: dict[str, str]) -> None:
    a = _skill(client, admin_headers, "Golang")
    _skill(client, admin_headers, "Scala")
    # Rename to a fresh name.
    renamed = client.patch(
        f"{SK}/{a['id']}",
        headers=admin_headers,
        json={"name": "Go", "description": "Backend"},
    ).json()
    assert renamed["name"] == "Go" and renamed["description"] == "Backend"
    # Rename onto an existing name → 409.
    clash = client.patch(f"{SK}/{a['id']}", headers=admin_headers, json={"name": "Scala"})
    assert clash.status_code == 409
