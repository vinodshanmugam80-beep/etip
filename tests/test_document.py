"""Integration tests for the Document Management module.

Covers document CRUD, polymorphic owner validation, duplicate storage-key
guarding, version lineages (supersession + current tracking), promote-on-delete,
the current-only filter, the project cascade (project- and task-owned docs), and
RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

DOCS = "/api/v1/documents"
PROJECTS = "/api/v1/projects"
TASKS = "/api/v1/tasks"
RISKS = "/api/v1/risks"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str = "PR") -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _task(client: TestClient, h: dict[str, str], project_id: str) -> dict:
    r = client.post(TASKS, headers=h, json={"project_id": project_id, "title": "Task item"})
    assert r.status_code == 201, r.text
    return r.json()


def _doc(
    client: TestClient,
    h: dict[str, str],
    owner_type: str,
    owner_id: str,
    key: str,
    name: str = "SOW.pdf",
    **o: object,
) -> dict:
    body: dict[str, object] = {
        "owner_type": owner_type,
        "owner_id": owner_id,
        "name": name,
        "storage_key": key,
        "content_type": "application/pdf",
        "size_bytes": 1024,
    }
    body.update(o)
    r = client.post(DOCS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_defaults(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    d = _doc(client, admin_headers, "project", proj["id"], "k/sow-v1.pdf")
    assert d["revision"] == 1
    assert d["is_current"] is True
    assert d["supersedes_id"] is None
    assert d["lineage_id"] is not None
    assert d["uploaded_by_user_id"] is not None


def test_owner_must_exist_across_types(client: TestClient, admin_headers: dict[str, str]) -> None:
    # Unknown project owner.
    missing = client.post(
        DOCS,
        headers=admin_headers,
        json={
            "owner_type": "project",
            "owner_id": str(uuid.uuid4()),
            "name": "x",
            "storage_key": "k/x",
        },
    )
    assert missing.status_code == 404

    # Valid task and risk owners of different types.
    proj = _project(client, admin_headers)
    task = _task(client, admin_headers, proj["id"])
    risk = client.post(
        RISKS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "A risk",
            "probability": 2,
            "impact": 2,
        },
    ).json()
    assert _doc(client, admin_headers, "task", task["id"], "k/task.pdf")["owner_type"] == "task"
    assert _doc(client, admin_headers, "risk", risk["id"], "k/risk.pdf")["owner_type"] == "risk"


def test_duplicate_storage_key(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    _doc(client, admin_headers, "project", proj["id"], "k/dup.pdf")
    dup = client.post(
        DOCS,
        headers=admin_headers,
        json={
            "owner_type": "project",
            "owner_id": proj["id"],
            "name": "again",
            "storage_key": "k/dup.pdf",
        },
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_storage_key"


def test_versioning(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    v1 = _doc(client, admin_headers, "project", proj["id"], "k/v1.pdf", name="Spec.pdf")

    v2 = client.post(
        f"{DOCS}/{v1['id']}/versions",
        headers=admin_headers,
        json={
            "storage_key": "k/v2.pdf",
            "content_type": "application/pdf",
            "size_bytes": 2048,
        },
    )
    assert v2.status_code == 201
    v2_body = v2.json()
    assert v2_body["revision"] == 2
    assert v2_body["is_current"] is True
    assert v2_body["supersedes_id"] == v1["id"]
    assert v2_body["lineage_id"] == v1["lineage_id"]
    assert v2_body["name"] == "Spec.pdf"  # inherited

    # v1 is no longer current.
    assert client.get(f"{DOCS}/{v1['id']}", headers=admin_headers).json()["is_current"] is False

    # The lineage lists both, newest first.
    versions = client.get(f"{DOCS}/{v1['id']}/versions", headers=admin_headers).json()
    assert [v["revision"] for v in versions] == [2, 1]

    # A duplicate key on a new version is rejected.
    dup = client.post(
        f"{DOCS}/{v1['id']}/versions",
        headers=admin_headers,
        json={"storage_key": "k/v2.pdf"},
    )
    assert dup.status_code == 409


def test_current_filter(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    v1 = _doc(client, admin_headers, "project", proj["id"], "k/c1.pdf")
    client.post(
        f"{DOCS}/{v1['id']}/versions",
        headers=admin_headers,
        json={"storage_key": "k/c2.pdf"},
    )

    current = client.get(
        DOCS, headers=admin_headers, params={"owner_id": proj["id"], "is_current": True}
    ).json()
    assert current["total"] == 1 and current["items"][0]["revision"] == 2


def test_promote_on_delete(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    v1 = _doc(client, admin_headers, "project", proj["id"], "k/p1.pdf")
    v2 = client.post(
        f"{DOCS}/{v1['id']}/versions",
        headers=admin_headers,
        json={"storage_key": "k/p2.pdf"},
    ).json()

    # Deleting the current revision promotes the predecessor.
    assert client.delete(f"{DOCS}/{v2['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{DOCS}/{v1['id']}", headers=admin_headers).json()["is_current"] is True


def test_update_metadata(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    d = _doc(client, admin_headers, "project", proj["id"], "k/u.pdf")
    updated = client.patch(
        f"{DOCS}/{d['id']}",
        headers=admin_headers,
        json={"name": "Renamed.pdf", "description": "final"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed.pdf" and updated.json()["description"] == "final"


def test_project_delete_cascades_documents(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    task = _task(client, admin_headers, proj["id"])
    proj_doc = _doc(client, admin_headers, "project", proj["id"], "k/pd.pdf")
    task_doc = _doc(client, admin_headers, "task", task["id"], "k/td.pdf")

    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{DOCS}/{proj_doc['id']}", headers=admin_headers).status_code == 404
    assert client.get(f"{DOCS}/{task_doc['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_attaches_not_deletes(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    """Member has document:create + document:read but not update/delete."""
    proj = _project(client, admin_headers)
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role_id = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "attach@contoso.com",
            "full_name": "Amy",
            "password": PW,
            "role_ids": [member_role_id],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "attach@contoso.com",
            "password": PW,
        },
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    d = _doc(client, headers, "project", proj["id"], "k/member.pdf")
    assert client.get(DOCS, headers=headers, params={"owner_id": proj["id"]}).status_code == 200
    assert (
        client.patch(f"{DOCS}/{d['id']}", headers=headers, json={"name": "Nope.pdf"}).status_code
        == 403
    )
    assert client.delete(f"{DOCS}/{d['id']}", headers=headers).status_code == 403
