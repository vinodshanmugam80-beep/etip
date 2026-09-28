"""Integration tests for the Resource Management module.

Covers resource CRUD, the user-link and department validations, allocation
creation against projects, and — centrally — time-phased **over-allocation
detection** across overlapping windows (including partial overlaps and the
exact-100% boundary). Also covers the resource deletion guard, the project→
allocation cascade, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.modules.auth.models import User
from tests.conftest import _login

RESOURCES = "/api/v1/resources"
ALLOCATIONS = "/api/v1/allocations"
PROJECTS = "/api/v1/projects"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str = "PR") -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _resource(
    client: TestClient,
    h: dict[str, str],
    name: str = "Ada Engineer",
    **overrides: object,
) -> dict:
    body: dict[str, object] = {"name": name}
    body.update(overrides)
    r = client.post(RESOURCES, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _allocate(
    client: TestClient,
    h: dict[str, str],
    resource_id: str,
    project_id: str,
    percent: int,
    start: str,
    end: str,
) -> object:
    return client.post(
        f"{RESOURCES}/{resource_id}/allocations",
        headers=h,
        json={
            "project_id": project_id,
            "start_date": start,
            "end_date": end,
            "allocation_percent": percent,
        },
    )


def test_create_resource_defaults(client: TestClient, admin_headers: dict[str, str]) -> None:
    res = _resource(client, admin_headers, skills=["Python", "python", " SQL "])
    assert res["resource_type"] == "employee"
    assert res["skills"] == ["python", "sql"]  # normalised + de-duped
    assert res["is_active"] is True


def test_user_link_validation(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        admin_id = str(session.query(User).one().id)

    linked = _resource(client, admin_headers, name="Admin Resource", user_id=admin_id)
    assert linked["user_id"] == admin_id

    # Same user twice is rejected.
    dup = client.post(RESOURCES, headers=admin_headers, json={"name": "Again", "user_id": admin_id})
    assert dup.status_code == 409

    # Unknown user is rejected.
    unknown = client.post(
        RESOURCES,
        headers=admin_headers,
        json={"name": "Ghost", "user_id": str(uuid.uuid4())},
    )
    assert unknown.status_code == 422


def test_search_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    _resource(client, admin_headers, name="Emp One", resource_type="employee")
    _resource(client, admin_headers, name="Con One", resource_type="contractor")

    contractors = client.get(
        RESOURCES, headers=admin_headers, params={"resource_type": "contractor"}
    ).json()
    assert contractors["total"] == 1 and contractors["items"][0]["name"] == "Con One"

    found = client.get(RESOURCES, headers=admin_headers, params={"q": "emp"}).json()
    assert found["total"] == 1


def test_allocation_requires_resource_and_project(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    res = _resource(client, admin_headers)
    # Unknown project.
    bad_proj = _allocate(
        client,
        admin_headers,
        res["id"],
        str(uuid.uuid4()),
        50,
        "2026-01-01",
        "2026-03-31",
    )
    assert bad_proj.status_code == 404
    # Unknown resource.
    bad_res = client.post(
        f"{RESOURCES}/{uuid.uuid4()}/allocations",
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "allocation_percent": 50,
        },
    )
    assert bad_res.status_code == 404


def test_over_allocation_full_overlap(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    res = _resource(client, admin_headers)

    a = _allocate(client, admin_headers, res["id"], proj["id"], 60, "2026-01-01", "2026-03-31")
    assert a.status_code == 201

    # Another 60% in the same window would total 120%.
    b = _allocate(client, admin_headers, res["id"], proj["id"], 60, "2026-01-01", "2026-03-31")
    assert b.status_code == 422
    assert b.json()["error"]["code"] == "over_allocation"

    # 40% fits exactly to 100%.
    c = _allocate(client, admin_headers, res["id"], proj["id"], 40, "2026-01-01", "2026-03-31")
    assert c.status_code == 201


def test_over_allocation_partial_overlap(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    res = _resource(client, admin_headers)

    _allocate(client, admin_headers, res["id"], proj["id"], 50, "2026-01-01", "2026-03-31")
    # Overlaps only in March; 50 + 60 = 110% during the overlap → rejected.
    over = _allocate(client, admin_headers, res["id"], proj["id"], 60, "2026-03-01", "2026-05-31")
    assert over.status_code == 422

    # 40% in the overlapping window is fine (50 + 40 = 90%).
    ok = _allocate(client, admin_headers, res["id"], proj["id"], 40, "2026-03-01", "2026-05-31")
    assert ok.status_code == 201


def test_non_overlapping_allocations_allowed(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    res = _resource(client, admin_headers)
    assert (
        _allocate(
            client,
            admin_headers,
            res["id"],
            proj["id"],
            100,
            "2026-01-01",
            "2026-03-31",
        ).status_code
        == 201
    )
    # Adjacent window, no overlap → full capacity again is fine.
    assert (
        _allocate(
            client,
            admin_headers,
            res["id"],
            proj["id"],
            100,
            "2026-04-01",
            "2026-06-30",
        ).status_code
        == 201
    )


def test_update_allocation_rechecks_and_excludes_self(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    res = _resource(client, admin_headers)
    a = _allocate(
        client, admin_headers, res["id"], proj["id"], 50, "2026-01-01", "2026-03-31"
    ).json()
    _allocate(client, admin_headers, res["id"], proj["id"], 50, "2026-01-01", "2026-03-31")

    # Raising the first to 60% would total 110% with the second → rejected.
    over = client.patch(
        f"{ALLOCATIONS}/{a['id']}",
        headers=admin_headers,
        json={"allocation_percent": 60},
    )
    assert over.status_code == 422

    # Editing only its notes must not self-conflict (exclude_id works).
    ok = client.patch(f"{ALLOCATIONS}/{a['id']}", headers=admin_headers, json={"notes": "reworded"})
    assert ok.status_code == 200


def test_delete_resource_blocked_with_allocations(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    res = _resource(client, admin_headers)
    _allocate(client, admin_headers, res["id"], proj["id"], 50, "2026-01-01", "2026-03-31")

    blocked = client.delete(f"{RESOURCES}/{res['id']}", headers=admin_headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "resource_in_use"


def test_project_delete_cascades_allocations(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    res = _resource(client, admin_headers)
    alloc = _allocate(
        client, admin_headers, res["id"], proj["id"], 50, "2026-01-01", "2026-03-31"
    ).json()

    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    # The allocation was soft-deleted with the project; the resource is now free.
    assert client.get(f"{ALLOCATIONS}/{alloc['id']}", headers=admin_headers).status_code == 404
    assert client.delete(f"{RESOURCES}/{res['id']}", headers=admin_headers).status_code == 200


def test_get_update_and_list_paths(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    res = _resource(client, admin_headers)

    # get + update a resource
    got = client.get(f"{RESOURCES}/{res['id']}", headers=admin_headers)
    assert got.status_code == 200
    updated = client.patch(
        f"{RESOURCES}/{res['id']}",
        headers=admin_headers,
        json={
            "name": "Ada Senior",
            "cost_rate": "150.00",
            "is_active": False,
            "skills": ["go"],
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Ada Senior"
    assert body["cost_rate"] == "150.00"
    assert body["is_active"] is False

    # allocation get + update (valid) + list by resource/project
    alloc = _allocate(
        client, admin_headers, res["id"], proj["id"], 30, "2026-01-01", "2026-02-28"
    ).json()
    assert client.get(f"{ALLOCATIONS}/{alloc['id']}", headers=admin_headers).status_code == 200
    edited = client.patch(
        f"{ALLOCATIONS}/{alloc['id']}",
        headers=admin_headers,
        json={"allocation_percent": 80, "role_label": "Lead", "end_date": "2026-03-31"},
    )
    assert edited.status_code == 200
    assert edited.json()["allocation_percent"] == 80

    by_resource = client.get(
        ALLOCATIONS, headers=admin_headers, params={"resource_id": res["id"]}
    ).json()
    assert len(by_resource) == 1
    by_project = client.get(
        ALLOCATIONS, headers=admin_headers, params={"project_id": proj["id"]}
    ).json()
    assert len(by_project) == 1

    # delete the allocation, then the (now free) resource
    assert client.delete(f"{ALLOCATIONS}/{alloc['id']}", headers=admin_headers).status_code == 200
    assert client.delete(f"{RESOURCES}/{res['id']}", headers=admin_headers).status_code == 200


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
    assert client.get(RESOURCES, headers=headers).status_code == 200
    assert client.post(RESOURCES, headers=headers, json={"name": "Nope"}).status_code == 403
