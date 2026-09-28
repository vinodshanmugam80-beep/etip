"""Integration tests for the authentication module.

Each test drives the running application through the HTTP layer, covering the
happy paths and the security-critical edge cases (token rotation, refresh
reuse detection, RBAC enforcement, MFA and account lockout).
"""

from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient

from tests.conftest import _login

BASE = "/api/v1/auth"


def test_register_creates_admin_with_system_role(
    client: TestClient, registered_org: dict[str, str]
) -> None:
    tokens = _login(client, registered_org)
    me = client.get(
        f"{BASE}/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    ).json()
    assert me["email"] == "admin@contoso.com"
    role_names = {role["name"] for role in me["roles"]}
    assert "Organization Admin" in role_names


def test_duplicate_organization_rejected(
    client: TestClient, registered_org: dict[str, str]
) -> None:
    response = client.post(
        f"{BASE}/register",
        json={
            "organization_name": "Contoso Ltd",
            "admin_email": "other@contoso.com",
            "admin_full_name": "Other",
            "password": "An0ther-Passphrase!",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_login_rejects_wrong_password(client: TestClient, registered_org: dict[str, str]) -> None:
    response = client.post(
        f"{BASE}/login",
        json={
            "organization_slug": registered_org["organization_slug"],
            "email": registered_org["email"],
            "password": "wrong-password",
        },
    )
    assert response.status_code == 401


def test_weak_password_rejected_at_schema(client: TestClient) -> None:
    response = client.post(
        f"{BASE}/register",
        json={
            "organization_name": "Weakpass Inc",
            "admin_email": "a@weak.com",
            "admin_full_name": "A",
            "password": "short",
        },
    )
    assert response.status_code == 422


def test_protected_route_requires_token(client: TestClient) -> None:
    response = client.get(f"{BASE}/me")
    assert response.status_code == 401


def test_refresh_rotates_and_detects_reuse(
    client: TestClient, registered_org: dict[str, str]
) -> None:
    tokens = _login(client, registered_org)
    original_refresh = tokens["refresh_token"]

    # First rotation succeeds and returns a new refresh token.
    rotated = client.post(f"{BASE}/refresh", json={"refresh_token": original_refresh})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh_token"]
    assert new_refresh != original_refresh

    # Replaying the original (now revoked) token is detected as reuse.
    replay = client.post(f"{BASE}/refresh", json={"refresh_token": original_refresh})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "authentication_error"

    # The reuse triggered family revocation: the rotated token is dead too.
    after_family_revoke = client.post(f"{BASE}/refresh", json={"refresh_token": new_refresh})
    assert after_family_revoke.status_code == 401


def test_logout_revokes_refresh_token(client: TestClient, registered_org: dict[str, str]) -> None:
    tokens = _login(client, registered_org)
    logout = client.post(f"{BASE}/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout.status_code == 200
    reuse = client.post(f"{BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reuse.status_code == 401


def test_account_locks_after_repeated_failures(
    client: TestClient, registered_org: dict[str, str]
) -> None:
    for _ in range(5):
        client.post(
            f"{BASE}/login",
            json={
                "organization_slug": registered_org["organization_slug"],
                "email": registered_org["email"],
                "password": "definitely-wrong",
            },
        )
    # Even the correct password is now refused while locked.
    locked = client.post(
        f"{BASE}/login",
        json={
            "organization_slug": registered_org["organization_slug"],
            "email": registered_org["email"],
            "password": registered_org["password"],
        },
    )
    assert locked.status_code == 401
    assert locked.json()["error"]["code"] == "account_locked"


def test_mfa_enrollment_and_enforcement(client: TestClient, registered_org: dict[str, str]) -> None:
    tokens = _login(client, registered_org)
    auth_header = {"Authorization": f"Bearer {tokens['access_token']}"}

    enroll = client.post(f"{BASE}/mfa/enroll", headers=auth_header)
    assert enroll.status_code == 200
    secret = enroll.json()["secret"]

    code = pyotp.TOTP(secret).now()
    verify = client.post(f"{BASE}/mfa/verify", headers=auth_header, json={"code": code})
    assert verify.status_code == 200

    # Login without an MFA code is now rejected.
    without_code = client.post(
        f"{BASE}/login",
        json={
            "organization_slug": registered_org["organization_slug"],
            "email": registered_org["email"],
            "password": registered_org["password"],
        },
    )
    assert without_code.status_code == 401
    assert without_code.json()["error"]["code"] == "mfa_required"

    # Login with a valid MFA code succeeds.
    with_code = client.post(
        f"{BASE}/login",
        json={
            "organization_slug": registered_org["organization_slug"],
            "email": registered_org["email"],
            "password": registered_org["password"],
            "mfa_code": pyotp.TOTP(secret).now(),
        },
    )
    assert with_code.status_code == 200


def test_security_headers_present(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "X-Request-ID" in response.headers


def test_me_permissions(client: TestClient, admin_headers: dict[str, str]) -> None:
    r = client.get("/api/v1/auth/me/permissions", headers=admin_headers)
    assert r.status_code == 200
    perms = r.json()
    assert isinstance(perms, list) and perms == sorted(perms)  # sorted list of codes
    # Org Admin holds the capabilities the dashboard gates on.
    assert {"intelligence:read", "copilot:use", "vendor:read"} <= set(perms)


def test_me_permissions_unauthenticated(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me/permissions").status_code == 401
