"""Integration tests for the Roles & Permissions module.

Covers the permission catalogue, custom-role CRUD, permission grant/revoke
(including idempotency), the protection of seeded system roles, the
in-use-role deletion guard, and RBAC enforcement.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

ROLES = "/api/v1/roles"
PERMISSIONS = "/api/v1/permissions"
USERS = "/api/v1/users"
PW = "Initial-Passphrase!1"


def _create_role(
    client: TestClient,
    headers: dict[str, str],
    name: str = "Portfolio Analyst",
    permissions: list[str] | None = None,
) -> dict:
    response = client.post(
        ROLES,
        headers=headers,
        json={
            "name": name,
            "description": "Custom role",
            "permissions": ["project:read"] if permissions is None else permissions,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _system_role(client: TestClient, headers: dict[str, str], name: str) -> dict:
    roles = client.get(ROLES, headers=headers).json()
    return next(r for r in roles if r["name"] == name)


# --- Catalogue -------------------------------------------------------------
def test_permission_catalogue_is_listed(client: TestClient, admin_headers: dict[str, str]) -> None:
    perms = client.get(PERMISSIONS, headers=admin_headers)
    assert perms.status_code == 200
    codes = [p["code"] for p in perms.json()]
    assert "project:create" in codes
    assert codes == sorted(codes)  # returned in stable order


# --- Create / read ---------------------------------------------------------
def test_create_role_with_permissions(client: TestClient, admin_headers: dict[str, str]) -> None:
    role = _create_role(client, admin_headers, permissions=["project:read", "organization:read"])
    assert role["is_system"] is False
    assert {p["code"] for p in role["permissions"]} == {
        "project:read",
        "organization:read",
    }


def test_duplicate_role_name_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_role(client, admin_headers, name="Analyst")
    dup = client.post(
        ROLES,
        headers=admin_headers,
        json={"name": "Analyst", "permissions": []},
    )
    assert dup.status_code == 409


def test_create_role_unknown_permission_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post(
        ROLES,
        headers=admin_headers,
        json={"name": "Bad", "permissions": ["does:not-exist"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_get_unknown_role_404(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{ROLES}/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_list_includes_system_roles(client: TestClient, admin_headers: dict[str, str]) -> None:
    roles = client.get(ROLES, headers=admin_headers).json()
    system = {r["name"] for r in roles if r["is_system"]}
    assert {"Organization Admin", "Project Manager", "Member"} <= system


# --- Update / permissions --------------------------------------------------
def test_update_custom_role_and_replace_permissions(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    role = _create_role(client, admin_headers)
    renamed = client.patch(
        f"{ROLES}/{role['id']}",
        headers=admin_headers,
        json={"name": "Analyst II", "description": "Updated"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Analyst II"

    replaced = client.put(
        f"{ROLES}/{role['id']}/permissions",
        headers=admin_headers,
        json={"permissions": ["user:read"]},
    )
    assert replaced.status_code == 200
    assert {p["code"] for p in replaced.json()["permissions"]} == {"user:read"}


def test_grant_and_revoke_single_permission_idempotent(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    role = _create_role(client, admin_headers, permissions=[])

    granted = client.post(f"{ROLES}/{role['id']}/permissions/project:update", headers=admin_headers)
    assert granted.status_code == 200
    assert {p["code"] for p in granted.json()["permissions"]} == {"project:update"}

    # Granting again is a no-op (no duplicate).
    again = client.post(f"{ROLES}/{role['id']}/permissions/project:update", headers=admin_headers)
    assert len(again.json()["permissions"]) == 1

    revoked = client.delete(
        f"{ROLES}/{role['id']}/permissions/project:update", headers=admin_headers
    )
    assert revoked.status_code == 200
    assert revoked.json()["permissions"] == []


def test_grant_unknown_permission_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    role = _create_role(client, admin_headers)
    response = client.post(f"{ROLES}/{role['id']}/permissions/nope:nope", headers=admin_headers)
    assert response.status_code == 422


# --- System-role protection ------------------------------------------------
def test_system_roles_are_protected(client: TestClient, admin_headers: dict[str, str]) -> None:
    admin_role = _system_role(client, admin_headers, "Organization Admin")

    update = client.patch(
        f"{ROLES}/{admin_role['id']}",
        headers=admin_headers,
        json={"description": "hijack"},
    )
    assert update.status_code == 409
    assert update.json()["error"]["code"] == "protected_role"

    set_perms = client.put(
        f"{ROLES}/{admin_role['id']}/permissions",
        headers=admin_headers,
        json={"permissions": []},
    )
    assert set_perms.status_code == 409

    delete = client.delete(f"{ROLES}/{admin_role['id']}", headers=admin_headers)
    assert delete.status_code == 409


# --- Deletion --------------------------------------------------------------
def test_delete_role_blocked_while_assigned(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    role = _create_role(client, admin_headers, name="Temp Role")

    # Create a user and assign the custom role.
    user = client.post(
        USERS,
        headers=admin_headers,
        json={"email": "holder@contoso.com", "full_name": "H", "password": PW},
    ).json()
    client.put(
        f"{USERS}/{user['id']}/roles",
        headers=admin_headers,
        json={"role_ids": [role["id"]]},
    )

    blocked = client.delete(f"{ROLES}/{role['id']}", headers=admin_headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "role_in_use"

    # Unassign, then deletion succeeds.
    client.put(
        f"{USERS}/{user['id']}/roles",
        headers=admin_headers,
        json={"role_ids": []},
    )
    ok = client.delete(f"{ROLES}/{role['id']}", headers=admin_headers)
    assert ok.status_code == 200


# --- RBAC ------------------------------------------------------------------
def test_rbac_reader_cannot_create_role(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    """A Project Manager holds role:read but not role:create."""
    pm_role = _system_role(client, admin_headers, "Project Manager")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "pm@contoso.com",
            "full_name": "Pat Manager",
            "password": PW,
            "role_ids": [pm_role["id"]],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "pm@contoso.com",
            "password": PW,
        },
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.get(ROLES, headers=headers).status_code == 200
    forbidden = client.post(ROLES, headers=headers, json={"name": "Nope", "permissions": []})
    assert forbidden.status_code == 403
