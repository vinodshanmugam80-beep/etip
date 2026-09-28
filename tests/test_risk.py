"""Integration tests for the Risk Management module.

Covers risk CRUD, the project reference and owner validations, probability ×
impact scoring with derived severity, the project ``risk_score`` rollup (highest
open risk), the status lifecycle, re-scoring on update, search/filter, the risk
summary, the project→risk cascade, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.modules.auth.models import User
from tests.conftest import _login

RISKS = "/api/v1/risks"
PROJECTS = "/api/v1/projects"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str = "PR") -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _risk(
    client: TestClient,
    h: dict[str, str],
    project_id: str,
    probability: int,
    impact: int,
    title: str = "A risk",
    **overrides: object,
) -> dict:
    body: dict[str, object] = {
        "project_id": project_id,
        "title": title,
        "probability": probability,
        "impact": impact,
    }
    body.update(overrides)
    r = client.post(RISKS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_scores_and_severity(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    crit = _risk(client, admin_headers, proj["id"], 4, 5, title="Critical one")
    assert crit["risk_score"] == 20
    assert crit["severity"] == "critical"
    assert crit["status"] == "identified"

    low = _risk(client, admin_headers, proj["id"], 1, 1, title="Low one")
    assert low["risk_score"] == 1 and low["severity"] == "low"
    med = _risk(client, admin_headers, proj["id"], 2, 3, title="Medium one")
    assert med["severity"] == "medium"  # score 6
    high = _risk(client, admin_headers, proj["id"], 3, 4, title="High one")
    assert high["severity"] == "high"  # score 12


def test_create_requires_project_and_owner(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    assert (
        client.post(
            RISKS,
            headers=admin_headers,
            json={
                "project_id": str(uuid.uuid4()),
                "title": "Orphan risk",
                "probability": 2,
                "impact": 2,
            },
        ).status_code
        == 404
    )
    proj = _project(client, admin_headers)
    bad_owner = client.post(
        RISKS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "Owned risk",
            "probability": 2,
            "impact": 2,
            "owner_user_id": str(uuid.uuid4()),
        },
    )
    assert bad_owner.status_code == 422


def test_project_risk_score_rollup(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    top = _risk(client, admin_headers, proj["id"], 5, 5, title="Top")  # score 25
    _risk(client, admin_headers, proj["id"], 2, 3, title="Lesser")  # score 6

    refreshed = client.get(f"{PROJECTS}/{proj['id']}", headers=admin_headers).json()
    assert refreshed["risk_score"] == 25  # highest open risk

    # Closing the top risk drops the rollup to the next open risk.
    client.patch(f"{RISKS}/{top['id']}", headers=admin_headers, json={"status": "closed"})
    after_close = client.get(f"{PROJECTS}/{proj['id']}", headers=admin_headers).json()
    assert after_close["risk_score"] == 6


def test_status_lifecycle(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    risk = _risk(client, admin_headers, proj["id"], 3, 3)
    rid = risk["id"]

    for target in ("analyzing", "mitigating", "monitoring", "closed"):
        assert (
            client.patch(
                f"{RISKS}/{rid}", headers=admin_headers, json={"status": target}
            ).status_code
            == 200
        )
    # closed is terminal.
    assert (
        client.patch(
            f"{RISKS}/{rid}", headers=admin_headers, json={"status": "monitoring"}
        ).status_code
        == 422
    )

    # An illegal jump backwards is rejected.
    risk2 = _risk(client, admin_headers, proj["id"], 2, 2, title="Second")
    client.patch(f"{RISKS}/{risk2['id']}", headers=admin_headers, json={"status": "mitigating"})
    assert (
        client.patch(
            f"{RISKS}/{risk2['id']}",
            headers=admin_headers,
            json={"status": "identified"},
        ).status_code
        == 422
    )


def test_update_rescores_and_updates_rollup(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    risk = _risk(client, admin_headers, proj["id"], 2, 2)  # score 4, low
    updated = client.patch(
        f"{RISKS}/{risk['id']}",
        headers=admin_headers,
        json={"probability": 5, "impact": 4},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["risk_score"] == 20 and body["severity"] == "critical"

    refreshed = client.get(f"{PROJECTS}/{proj['id']}", headers=admin_headers).json()
    assert refreshed["risk_score"] == 20


def test_search_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    _risk(client, admin_headers, proj["id"], 5, 5, title="Sched risk", category="schedule")
    _risk(client, admin_headers, proj["id"], 1, 2, title="Tech risk", category="technical")

    crit = client.get(
        RISKS,
        headers=admin_headers,
        params={"project_id": proj["id"], "severity": "critical"},
    ).json()
    assert crit["total"] == 1 and crit["items"][0]["title"] == "Sched risk"
    sched = client.get(RISKS, headers=admin_headers, params={"category": "schedule"}).json()
    assert sched["total"] == 1


def test_risk_summary(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    _risk(client, admin_headers, proj["id"], 5, 5, title="Crit")  # critical
    _risk(client, admin_headers, proj["id"], 2, 3, title="Med")  # medium
    closed = _risk(client, admin_headers, proj["id"], 4, 4, title="Closed one")  # high
    client.patch(f"{RISKS}/{closed['id']}", headers=admin_headers, json={"status": "closed"})

    summary = client.get(f"{PROJECTS}/{proj['id']}/risk-summary", headers=admin_headers).json()
    assert summary["open_count"] == 2  # closed one excluded
    assert summary["max_score"] == 25
    counts = {c["severity"]: c["count"] for c in summary["by_severity"]}
    assert counts.get("critical") == 1 and counts.get("medium") == 1


def test_owner_assignment(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers)
    with session_factory() as session:
        admin_id = str(session.query(User).one().id)
    risk = _risk(client, admin_headers, proj["id"], 3, 3, owner_user_id=admin_id)
    assert risk["owner_user_id"] == admin_id
    mine = client.get(RISKS, headers=admin_headers, params={"owner_user_id": admin_id}).json()
    assert mine["total"] == 1


def test_project_delete_cascades_risks(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    risk = _risk(client, admin_headers, proj["id"], 3, 3)
    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{RISKS}/{risk['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_read_not_create(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
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
    assert client.get(RISKS, headers=headers, params={"project_id": proj["id"]}).status_code == 200
    assert (
        client.post(
            RISKS,
            headers=headers,
            json={
                "project_id": proj["id"],
                "title": "Nope risk",
                "probability": 2,
                "impact": 2,
            },
        ).status_code
        == 403
    )
