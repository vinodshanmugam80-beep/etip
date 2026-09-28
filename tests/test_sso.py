"""Integration tests for SSO (OIDC).

The IdP round-trip (code exchange + JWKS verification) is mocked, so provisioning
and token issuance are exercised without a live identity provider.
"""

from __future__ import annotations

import urllib.parse

import pytest
from fastapi.testclient import TestClient

import app.modules.sso.oidc as oidc
from tests.conftest import _login

CFG = "/api/v1/auth/sso/config"
LOGIN = "/api/v1/auth/sso/login"
CALLBACK = "/api/v1/auth/sso/callback"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
SLUG = "contoso-ltd"
PW = "Initial-Passphrase!1"


def _cfg(**over: object) -> dict:
    body = {
        "client_id": "etip-client",
        "client_secret": "shh",
        "issuer": "https://idp.example.com",
        "authorize_url": "https://idp.example.com/authorize",
        "token_url": "https://idp.example.com/token",
        "jwks_url": "https://idp.example.com/jwks",
        "default_role_name": "Member",
        "allowed_domains": [],
        "is_enabled": True,
    }
    body.update(over)
    return body


def _state_from_login(client: TestClient) -> str:
    url = client.get(LOGIN, params={"organization_slug": SLUG}).json()["authorize_url"]
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]


def test_config_upsert_hides_secret(client: TestClient, admin_headers: dict[str, str]) -> None:
    r = client.put(CFG, headers=admin_headers, json=_cfg())
    assert r.status_code == 200
    body = r.json()
    assert body["secret_set"] is True and "client_secret" not in body and body["is_enabled"] is True
    # A PUT without a secret keeps the stored one.
    r2 = client.put(
        CFG, headers=admin_headers, json=_cfg(client_secret="", default_role_name="Project Manager")
    )
    assert r2.status_code == 200 and r2.json()["secret_set"] is True
    assert client.get(CFG, headers=admin_headers).json()["default_role_name"] == "Project Manager"


def test_login_builds_authorize_url(client: TestClient, admin_headers: dict[str, str]) -> None:
    client.put(CFG, headers=admin_headers, json=_cfg())
    url = client.get(LOGIN, params={"organization_slug": SLUG}).json()["authorize_url"]
    assert url.startswith("https://idp.example.com/authorize?")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["client_id"] == ["etip-client"] and "state" in q and "nonce" in q
    assert q["scope"] == ["openid email profile"]


def test_login_disabled_or_unknown(client: TestClient, admin_headers: dict[str, str]) -> None:
    # No config yet → not enabled.
    assert client.get(LOGIN, params={"organization_slug": SLUG}).status_code == 422
    # Unknown org.
    assert client.get(LOGIN, params={"organization_slug": "nope-inc"}).status_code == 404


def test_callback_provisions_user_and_issues_tokens(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client.put(CFG, headers=admin_headers, json=_cfg())
    state = _state_from_login(client)
    monkeypatch.setattr(
        oidc, "fetch_oidc_claims", lambda *a, **k: {"email": "newhire@corp.io", "name": "New Hire"}
    )
    r = client.get(CALLBACK, params={"code": "authcode", "state": state})
    assert r.status_code == 200
    access = r.json()["access_token"]
    # The issued token authenticates a real request as the provisioned user.
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200 and me.json()["email"] == "newhire@corp.io"


def test_callback_enforces_allowed_domain(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client.put(CFG, headers=admin_headers, json=_cfg(allowed_domains=["corp.io"]))
    state = _state_from_login(client)
    monkeypatch.setattr(
        oidc, "fetch_oidc_claims", lambda *a, **k: {"email": "person@other.com", "name": "X"}
    )
    assert client.get(CALLBACK, params={"code": "c", "state": state}).status_code == 401


def test_callback_rejects_bad_state(client: TestClient) -> None:
    assert (
        client.get(CALLBACK, params={"code": "c", "state": "not-a-valid-state"}).status_code == 401
    )


def test_config_requires_permission(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "sso@contoso.com",
            "full_name": "S M",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(client, {"organization_slug": SLUG, "email": "sso@contoso.com", "password": PW})
    member = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.put(CFG, headers=member, json=_cfg()).status_code == 403


def test_discover_populates_endpoints(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Save a config with blank endpoints, then discover them from the issuer.
    client.put(
        CFG,
        headers=admin_headers,
        json=_cfg(authorize_url="", token_url="", jwks_url="", is_enabled=False),
    )
    monkeypatch.setattr(
        oidc,
        "fetch_discovery",
        lambda issuer: {
            "issuer": issuer,
            "authorize_url": "https://idp.example.com/oauth/authorize",
            "token_url": "https://idp.example.com/oauth/token",
            "jwks_url": "https://idp.example.com/oauth/jwks",
        },
    )
    r = client.post(
        "/api/v1/auth/sso/discover",
        headers=admin_headers,
        json={"issuer": "https://idp.example.com"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authorize_url"].endswith("/oauth/authorize")
    assert body["token_url"].endswith("/oauth/token")
    assert body["jwks_url"].endswith("/oauth/jwks")


def test_role_mapping_on_provision(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client.put(
        CFG,
        headers=admin_headers,
        json=_cfg(role_mappings={"etip-admins": "Organization Admin"}),
    )
    state = _state_from_login(client)
    monkeypatch.setattr(
        oidc,
        "fetch_oidc_claims",
        lambda *a, **k: {
            "email": "lead@corp.io",
            "name": "Team Lead",
            "groups": ["etip-admins", "unmapped-group"],
        },
    )
    r = client.get(CALLBACK, params={"code": "authcode", "state": state})
    assert r.status_code == 200
    access = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}).json()
    assert "Organization Admin" in {role["name"] for role in me["roles"]}


def test_discover_requires_existing_config(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    # No config saved yet → 404.
    r = client.post(
        "/api/v1/auth/sso/discover",
        headers=admin_headers,
        json={"issuer": "https://idp.example.com"},
    )
    assert r.status_code == 404
