"""Integration tests for API keys (service-account auth)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.conftest import _login

AK = "/api/v1/api-keys"
PROJECTS = "/api/v1/projects"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _issue(client: TestClient, h: dict[str, str], **body: object) -> dict:
    payload: dict[str, object] = {"name": "Integration key"}
    payload.update(body)
    r = client.post(AK, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_issue_returns_secret_once_and_hides_hash(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    key = _issue(client, admin_headers, name="Jira")
    assert key["api_key"].startswith("etip_")
    assert key["prefix"] == key["api_key"][:12]
    assert "key_hash" not in key
    # Listing never exposes the secret.
    listed = client.get(AK, headers=admin_headers).json()
    assert listed["total"] == 1
    assert "api_key" not in listed["items"][0] and "key_hash" not in listed["items"][0]


def test_api_key_authenticates_rest_calls(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    key = _issue(client, admin_headers)["api_key"]
    # A protected endpoint works with X-API-Key and no JWT.
    assert client.get(PROJECTS, headers={"X-API-Key": key}).status_code == 200
    # Bad key and no auth are rejected.
    assert client.get(PROJECTS, headers={"X-API-Key": "etip_not-a-real-key"}).status_code == 401
    assert client.get(PROJECTS, headers={"X-API-Key": "short"}).status_code == 401
    assert client.get(PROJECTS).status_code == 401


def test_revoke_and_delete(client: TestClient, admin_headers: dict[str, str]) -> None:
    resp = _issue(client, admin_headers)
    key, kid = resp["api_key"], resp["id"]
    assert client.get(PROJECTS, headers={"X-API-Key": key}).status_code == 200
    client.post(f"{AK}/{kid}/revoke", headers=admin_headers)
    assert client.get(PROJECTS, headers={"X-API-Key": key}).status_code == 401  # revoked
    assert client.delete(f"{AK}/{kid}", headers=admin_headers).status_code == 204
    assert client.get(f"{AK}/{kid}", headers=admin_headers).status_code == 404


def test_expired_key_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    key = _issue(client, admin_headers, expires_date=str(date.today() - timedelta(days=1)))[
        "api_key"
    ]
    assert client.get(PROJECTS, headers={"X-API-Key": key}).status_code == 401


def test_unknown_user_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    r = client.post(AK, headers=admin_headers, json={"name": "Bad", "user_id": str(uuid.uuid4())})
    assert r.status_code == 422


def test_rbac_only_admin_manages(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "ak@contoso.com",
            "full_name": "Ak Member",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "ak@contoso.com",
            "password": PW,
        },
    )
    member = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.post(AK, headers=member, json={"name": "Nope"}).status_code == 403
