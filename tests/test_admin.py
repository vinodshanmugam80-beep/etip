"""Integration tests for the Administration module.

Covers audit-log search/filter/get over the entries every service writes, the
governance overview, diagnostics, the permission-reconciliation backfill (the
long-deferred gap), and RBAC (admin endpoints are Organization-Admin only).
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.modules.auth.models import Role
from tests.conftest import _login

ADMIN = "/api/v1/admin"
PROJECTS = "/api/v1/projects"
PORTFOLIOS = "/api/v1/portfolios"
RISKS = "/api/v1/risks"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _member(client: TestClient, admin_headers: dict[str, str], email: str) -> str:
    roles = client.get(ROLES, headers=admin_headers).json()
    role_id = next(r["id"] for r in roles if r["name"] == "Member")
    r = client.post(
        USERS,
        headers=admin_headers,
        json={"email": email, "full_name": "Person", "password": PW, "role_ids": [role_id]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _member_headers(
    client: TestClient, registered_org: dict[str, str], email: str
) -> dict[str, str]:
    tokens = _login(
        client,
        {"organization_slug": registered_org["organization_slug"], "email": email, "password": PW},
    )
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_audit_log_search_and_get(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = client.post(
        PROJECTS, headers=admin_headers, json={"name": "Project", "code": "AUD"}
    ).json()
    client.post(
        RISKS,
        headers=admin_headers,
        json={"project_id": proj["id"], "title": "A risk", "probability": 3, "impact": 3},
    )

    # The audit log has entries written by the create operations.
    logs = client.get(f"{ADMIN}/audit-logs", headers=admin_headers).json()
    assert logs["total"] >= 2

    # Filter by entity type and action.
    projects = client.get(
        f"{ADMIN}/audit-logs",
        headers=admin_headers,
        params={"entity_type": "Project", "action": "create"},
    ).json()
    assert projects["total"] >= 1
    entry = projects["items"][0]
    assert entry["entity_type"] == "Project" and entry["action"] == "create"

    # Get a single entry.
    got = client.get(f"{ADMIN}/audit-logs/{entry['id']}", headers=admin_headers)
    assert got.status_code == 200 and got.json()["id"] == entry["id"]
    # Unknown entry.
    assert (
        client.get(f"{ADMIN}/audit-logs/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    )

    # Filter by entity_id, actor_id, and a date window.
    by_entity = client.get(
        f"{ADMIN}/audit-logs", headers=admin_headers, params={"entity_id": proj["id"]}
    ).json()
    assert by_entity["total"] >= 1
    by_actor = client.get(
        f"{ADMIN}/audit-logs",
        headers=admin_headers,
        params={
            "actor_id": entry["actor_id"],
            "date_from": "2020-01-01T00:00:00Z",
            "date_to": "2100-01-01T00:00:00Z",
        },
    ).json()
    assert by_actor["total"] >= 1


def test_overview_counts(client: TestClient, admin_headers: dict[str, str]) -> None:
    client.post(PROJECTS, headers=admin_headers, json={"name": "Proj", "code": "OV1"})
    client.post(PORTFOLIOS, headers=admin_headers, json={"name": "Port", "code": "OVP"})
    _member(client, admin_headers, "ov@contoso.com")

    ov = client.get(f"{ADMIN}/overview", headers=admin_headers).json()
    assert ov["total_users"] >= 2  # admin + member
    assert ov["active_users"] >= 2
    assert ov["projects"] >= 1 and ov["portfolios"] >= 1
    assert ov["roles"] >= 3  # the three seeded system roles
    assert ov["audit_entries"] >= 1
    assert ov["permission_catalogue_size"] > 50  # the catalogue is large by now


def test_diagnostics(client: TestClient, admin_headers: dict[str, str]) -> None:
    diag = client.get(f"{ADMIN}/diagnostics", headers=admin_headers).json()
    assert diag["status"] == "healthy" and diag["database"] == "ok"
    assert diag["app_env"] == "test"


def test_reconcile_backfills_missing_grants(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    # Simulate an "older" tenant by removing a permission grant from a system
    # role, as if it had been added by a module after the tenant registered.
    with session_factory() as session:
        role = session.query(Role).filter(Role.name == "Member").one()
        removed = role.permissions.pop()
        removed_code = removed.code
        session.commit()

    result = client.post(f"{ADMIN}/reconcile-permissions", headers=admin_headers)
    assert result.status_code == 200
    body = result.json()
    assert body["total_grants_added"] >= 1
    member_item = next(r for r in body["roles"] if r["role"] == "Member")
    assert member_item["grants_added"] >= 1

    # The grant is restored.
    with session_factory() as session:
        role = session.query(Role).filter(Role.name == "Member").one()
        assert removed_code in {p.code for p in role.permissions}

    # Running again is a no-op (idempotent).
    again = client.post(f"{ADMIN}/reconcile-permissions", headers=admin_headers).json()
    assert again["total_grants_added"] == 0


def test_reconcile_all_tenants_self_heals(
    session_factory: sessionmaker[Session],
    registered_org: dict[str, str],
) -> None:
    """The startup job reconciles every tenant in one pass, idempotently."""
    from app.modules.admin.reconcile import (
        reconcile_all_tenants,
        run_startup_reconciliation,
    )

    with session_factory() as session:
        role = session.query(Role).filter(Role.name == "Project Manager").one()
        removed_code = role.permissions.pop().code
        session.commit()

    # The startup entrypoint opens its own session, reconciles, and commits.
    summary = run_startup_reconciliation(session_factory)
    assert summary["organizations"] >= 1 and summary["grants_added"] >= 1

    with session_factory() as session:
        role = session.query(Role).filter(Role.name == "Project Manager").one()
        assert removed_code in {p.code for p in role.permissions}

    # Idempotent second pass via the lower-level function.
    with session_factory() as session:
        again = reconcile_all_tenants(session)
        session.commit()
    assert again["grants_added"] == 0


def test_rbac_admin_only(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    _member(client, admin_headers, "peon@contoso.com")
    member = _member_headers(client, registered_org, "peon@contoso.com")

    # Members lack admin:read and admin:manage.
    assert client.get(f"{ADMIN}/audit-logs", headers=member).status_code == 403
    assert client.get(f"{ADMIN}/overview", headers=member).status_code == 403
    assert client.get(f"{ADMIN}/diagnostics", headers=member).status_code == 403
    assert client.post(f"{ADMIN}/reconcile-permissions", headers=member).status_code == 403
