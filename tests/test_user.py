"""Integration tests for the User Management module.

Drives the running application through HTTP with a real authenticated admin,
covering user creation and search, profile updates, activation/deactivation
(and its session-revocation and self-lockout guards), role assignment,
admin password reset, self-service password change, deletion guards, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.modules.auth.models import Organization, Role, User
from tests.conftest import _login

BASE = "/api/v1/users"
PW = "Initial-Passphrase!1"


def _create_user(
    client: TestClient,
    headers: dict[str, str],
    email: str = "member@contoso.com",
    **overrides: object,
) -> dict:
    body: dict[str, object] = {
        "email": email,
        "full_name": "Mel Member",
        "password": PW,
    }
    body.update(overrides)
    response = client.post(BASE, headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_user_and_duplicate_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    user = _create_user(client, admin_headers)
    assert user["email"] == "member@contoso.com"
    assert user["is_active"] is True

    duplicate = client.post(
        BASE,
        headers=admin_headers,
        json={"email": "MEMBER@contoso.com", "full_name": "Dup", "password": PW},
    )
    assert duplicate.status_code == 409


def test_create_user_weak_password_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post(
        BASE,
        headers=admin_headers,
        json={"email": "x@contoso.com", "full_name": "X", "password": "weak"},
    )
    assert response.status_code == 422


def test_create_user_with_unknown_role_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post(
        BASE,
        headers=admin_headers,
        json={
            "email": "y@contoso.com",
            "full_name": "Y",
            "password": PW,
            "role_ids": [str(uuid.uuid4())],
        },
    )
    assert response.status_code == 422


def test_search_and_pagination(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_user(client, admin_headers, email="alice@contoso.com")
    _create_user(client, admin_headers, email="bob@contoso.com")

    # Admin + 2 created = 3 users total.
    page = client.get(BASE, headers=admin_headers, params={"limit": 2}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["limit"] == 2

    # Substring search on email.
    found = client.get(BASE, headers=admin_headers, params={"q": "alice"}).json()
    assert found["total"] == 1
    assert found["items"][0]["email"] == "alice@contoso.com"


def test_get_unknown_user_404(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get(f"{BASE}/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


def test_update_profile_and_email_conflict(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    a = _create_user(client, admin_headers, email="a@contoso.com")
    _create_user(client, admin_headers, email="b@contoso.com")

    renamed = client.patch(
        f"{BASE}/{a['id']}", headers=admin_headers, json={"full_name": "Renamed"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["full_name"] == "Renamed"

    # Changing a's email to b's is rejected.
    conflict = client.patch(
        f"{BASE}/{a['id']}", headers=admin_headers, json={"email": "b@contoso.com"}
    )
    assert conflict.status_code == 409


def test_deactivate_revokes_sessions_and_blocks_login(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    user = _create_user(client, admin_headers, email="temp@contoso.com")

    # The new user can log in and obtains a refresh token.
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "temp@contoso.com",
            "password": PW,
        },
    )

    deactivated = client.post(f"{BASE}/{user['id']}/deactivate", headers=admin_headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    # Existing refresh token is revoked.
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 401

    # Fresh login is refused while inactive.
    login_again = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registered_org["organization_slug"],
            "email": "temp@contoso.com",
            "password": PW,
        },
    )
    assert login_again.status_code == 401

    # Reactivation restores login.
    client.post(f"{BASE}/{user['id']}/activate", headers=admin_headers)
    ok = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registered_org["organization_slug"],
            "email": "temp@contoso.com",
            "password": PW,
        },
    )
    assert ok.status_code == 200


def test_cannot_deactivate_or_delete_self(
    client: TestClient, admin_headers: dict[str, str], session_factory
) -> None:
    with session_factory() as session:
        admin_id = str(session.query(User).one().id)

    deactivate = client.post(f"{BASE}/{admin_id}/deactivate", headers=admin_headers)
    assert deactivate.status_code == 422

    delete = client.delete(f"{BASE}/{admin_id}", headers=admin_headers)
    assert delete.status_code == 422


def test_set_roles(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    user = _create_user(client, admin_headers, email="roleless@contoso.com")
    assert user["roles"] == []

    with session_factory() as session:
        pm_role = session.query(Role).filter(Role.name == "Project Manager").one()
        pm_role_id = str(pm_role.id)

    updated = client.put(
        f"{BASE}/{user['id']}/roles",
        headers=admin_headers,
        json={"role_ids": [pm_role_id]},
    )
    assert updated.status_code == 200
    assert [r["name"] for r in updated.json()["roles"]] == ["Project Manager"]

    # Unknown role id is rejected.
    bad = client.put(
        f"{BASE}/{user['id']}/roles",
        headers=admin_headers,
        json={"role_ids": [str(uuid.uuid4())]},
    )
    assert bad.status_code == 422


def test_admin_reset_password(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    user = _create_user(client, admin_headers, email="reset@contoso.com")
    new_pw = "Reset-Passphrase!2"

    reset = client.post(
        f"{BASE}/{user['id']}/reset-password",
        headers=admin_headers,
        json={"new_password": new_pw},
    )
    assert reset.status_code == 200

    # Old password no longer works; new one does.
    old = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registered_org["organization_slug"],
            "email": "reset@contoso.com",
            "password": PW,
        },
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registered_org["organization_slug"],
            "email": "reset@contoso.com",
            "password": new_pw,
        },
    )
    assert new.status_code == 200


def test_self_service_change_password(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    _create_user(client, admin_headers, email="selfchg@contoso.com")
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "selfchg@contoso.com",
            "password": PW,
        },
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    new_pw = "Self-Passphrase!3"

    # Wrong current password is rejected.
    wrong = client.post(
        f"{BASE}/me/change-password",
        headers=headers,
        json={"current_password": "not-it", "new_password": new_pw},
    )
    assert wrong.status_code == 401

    ok = client.post(
        f"{BASE}/me/change-password",
        headers=headers,
        json={"current_password": PW, "new_password": new_pw},
    )
    assert ok.status_code == 200

    # New password logs in.
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": registered_org["organization_slug"],
            "email": "selfchg@contoso.com",
            "password": new_pw,
        },
    )
    assert login.status_code == 200


def test_delete_user(client: TestClient, admin_headers: dict[str, str]) -> None:
    user = _create_user(client, admin_headers, email="gone@contoso.com")
    deleted = client.delete(f"{BASE}/{user['id']}", headers=admin_headers)
    assert deleted.status_code == 200
    # Soft-deleted users are not returned.
    assert client.get(f"{BASE}/{user['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_cannot_manage_users(
    client: TestClient,
    registered_org: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    from app.core.security import hash_password

    with session_factory() as session:
        org = session.query(Organization).one()
        member_role = (
            session.query(Role).filter(Role.organization_id == org.id, Role.name == "Member").one()
        )
        member = User(
            organization_id=org.id,
            email="member2@contoso.com",
            full_name="Mel",
            hashed_password=hash_password("Member-Passphrase!1"),
        )
        member.roles.append(member_role)
        session.add(member)
        session.commit()

    tokens = _login(
        client,
        {
            "organization_slug": "contoso-ltd",
            "email": "member2@contoso.com",
            "password": "Member-Passphrase!1",
        },
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Member has user:read but not user:create.
    assert client.get(BASE, headers=headers).status_code == 200
    forbidden = client.post(
        BASE,
        headers=headers,
        json={"email": "nope@contoso.com", "full_name": "No", "password": PW},
    )
    assert forbidden.status_code == 403
