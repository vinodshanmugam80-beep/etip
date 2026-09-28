"""Integration tests for the Dashboards module.

Covers dashboard CRUD, owner + shared visibility, owner-only edit/widget
management (distinct from RBAC), single-default-per-owner, widget CRUD with the
report-widget validation, the render path (REPORT widgets run through the engine,
TEXT widgets return content, a broken widget captures its error without breaking
the whole dashboard), and RBAC.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import _login

DASH = "/api/v1/dashboards"
PROJECTS = "/api/v1/projects"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str = "PR") -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _user_with_role(
    client: TestClient, admin_headers: dict[str, str], email: str, role_name: str
) -> str:
    roles = client.get(ROLES, headers=admin_headers).json()
    role_id = next(r["id"] for r in roles if r["name"] == role_name)
    r = client.post(
        USERS,
        headers=admin_headers,
        json={"email": email, "full_name": "Person", "password": PW, "role_ids": [role_id]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _headers(client: TestClient, registered_org: dict[str, str], email: str) -> dict[str, str]:
    tokens = _login(
        client,
        {"organization_slug": registered_org["organization_slug"], "email": email, "password": PW},
    )
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _dashboard(
    client: TestClient, h: dict[str, str], name: str = "My board", shared: bool = False
) -> dict:
    r = client.post(DASH, headers=h, json={"name": name, "is_shared": shared})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_defaults(client: TestClient, admin_headers: dict[str, str]) -> None:
    d = _dashboard(client, admin_headers, name="Overview")
    assert d["is_shared"] is False and d["is_default"] is False


def test_visibility_own_and_shared(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    _dashboard(client, admin_headers, name="Shared board", shared=True)
    _dashboard(client, admin_headers, name="Private board", shared=False)
    _user_with_role(client, admin_headers, "pm@contoso.com", "Project Manager")
    pm = _headers(client, registered_org, "pm@contoso.com")
    _dashboard(client, pm, name="PM board")

    names = {d["name"] for d in client.get(DASH, headers=pm).json()["items"]}
    assert "Shared board" in names and "PM board" in names
    assert "Private board" not in names


def test_owner_only_widget_management(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    shared = _dashboard(client, admin_headers, name="Admin shared", shared=True)
    _user_with_role(client, admin_headers, "pm2@contoso.com", "Project Manager")
    pm = _headers(client, registered_org, "pm2@contoso.com")

    # PM can see it, but not add widgets or edit it (not owner) despite holding
    # dashboard:update.
    assert client.get(f"{DASH}/{shared['id']}", headers=pm).status_code == 200
    add = client.post(
        f"{DASH}/{shared['id']}/widgets",
        headers=pm,
        json={"title": "Sneaky", "widget_type": "text", "content": "hi"},
    )
    assert add.status_code == 403
    assert (
        client.patch(f"{DASH}/{shared['id']}", headers=pm, json={"name": "Nope"}).status_code == 403
    )


def test_single_default_per_owner(client: TestClient, admin_headers: dict[str, str]) -> None:
    a = _dashboard(client, admin_headers, name="Board A")
    b = _dashboard(client, admin_headers, name="Board B")
    assert (
        client.post(f"{DASH}/{a['id']}/set-default", headers=admin_headers).json()["is_default"]
        is True
    )
    # Setting B as default clears A.
    assert (
        client.post(f"{DASH}/{b['id']}/set-default", headers=admin_headers).json()["is_default"]
        is True
    )
    assert client.get(f"{DASH}/{a['id']}", headers=admin_headers).json()["is_default"] is False


def test_widget_crud_and_validation(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    d = _dashboard(client, admin_headers)

    # A report widget requires a report_type.
    bad = client.post(
        f"{DASH}/{d['id']}/widgets",
        headers=admin_headers,
        json={"title": "No type", "widget_type": "report"},
    )
    assert bad.status_code == 422

    rep = client.post(
        f"{DASH}/{d['id']}/widgets",
        headers=admin_headers,
        json={
            "title": "Status",
            "widget_type": "report",
            "report_type": "project_status",
            "parameters": {"project_id": proj["id"]},
            "position": 2,
        },
    )
    assert rep.status_code == 201
    txt = client.post(
        f"{DASH}/{d['id']}/widgets",
        headers=admin_headers,
        json={"title": "Note", "widget_type": "text", "content": "Hello", "position": 1},
    )
    assert txt.status_code == 201

    # Ordered by position.
    widgets = client.get(f"{DASH}/{d['id']}/widgets", headers=admin_headers).json()
    assert [w["title"] for w in widgets] == ["Note", "Status"]

    # Update and remove.
    upd = client.patch(
        f"{DASH}/{d['id']}/widgets/{txt.json()['id']}",
        headers=admin_headers,
        json={"content": "Updated"},
    )
    assert upd.status_code == 200 and upd.json()["content"] == "Updated"
    assert (
        client.delete(
            f"{DASH}/{d['id']}/widgets/{txt.json()['id']}", headers=admin_headers
        ).status_code
        == 200
    )
    assert len(client.get(f"{DASH}/{d['id']}/widgets", headers=admin_headers).json()) == 1


def test_render_mixed_widgets_and_error_isolation(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers, code="RND")
    d = _dashboard(client, admin_headers, name="Render me")
    # Good report widget.
    client.post(
        f"{DASH}/{d['id']}/widgets",
        headers=admin_headers,
        json={
            "title": "Status",
            "widget_type": "report",
            "report_type": "project_status",
            "parameters": {"project_id": proj["id"]},
            "position": 1,
        },
    )
    # Text widget.
    client.post(
        f"{DASH}/{d['id']}/widgets",
        headers=admin_headers,
        json={"title": "Note", "widget_type": "text", "content": "Standup at 9", "position": 2},
    )
    # Broken report widget: missing required project_id parameter.
    client.post(
        f"{DASH}/{d['id']}/widgets",
        headers=admin_headers,
        json={
            "title": "Broken",
            "widget_type": "report",
            "report_type": "project_status",
            "parameters": {},
            "position": 3,
        },
    )

    render = client.get(f"{DASH}/{d['id']}/render", headers=admin_headers)
    assert render.status_code == 200
    widgets = {w["title"]: w for w in render.json()["widgets"]}

    assert widgets["Status"]["data"]["code"] == "RND" and widgets["Status"]["error"] is None
    assert widgets["Note"]["content"] == "Standup at 9"
    # The broken widget carries an error but did not break the whole render.
    assert widgets["Broken"]["data"] is None and widgets["Broken"]["error"] is not None


def test_full_updates_delete_and_missing(client: TestClient, admin_headers: dict[str, str]) -> None:
    import uuid

    proj = _project(client, admin_headers, code="UPD")
    d = _dashboard(client, admin_headers, name="Editable")

    upd = client.patch(
        f"{DASH}/{d['id']}",
        headers=admin_headers,
        json={"description": "desc", "is_shared": True, "layout": {"columns": 8}},
    ).json()
    assert upd["description"] == "desc" and upd["is_shared"] is True
    assert upd["layout"] == {"columns": 8}

    w = client.post(
        f"{DASH}/{d['id']}/widgets",
        headers=admin_headers,
        json={
            "title": "Wid",
            "widget_type": "report",
            "report_type": "raid_summary",
            "parameters": {"project_id": proj["id"]},
        },
    ).json()
    upd_w = client.patch(
        f"{DASH}/{d['id']}/widgets/{w['id']}",
        headers=admin_headers,
        json={
            "title": "Renamed",
            "report_type": "project_status",
            "parameters": {"project_id": proj["id"]},
            "position": 5,
            "width": 12,
        },
    ).json()
    assert upd_w["title"] == "Renamed" and upd_w["width"] == 12
    assert upd_w["report_type"] == "project_status"

    # Delete the dashboard (owner) — cascades the widget.
    assert client.delete(f"{DASH}/{d['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{DASH}/{d['id']}", headers=admin_headers).status_code == 404
    assert client.get(f"{DASH}/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_rbac_member_creates_renders_not_updates(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    _user_with_role(client, admin_headers, "dash@contoso.com", "Member")
    h = _headers(client, registered_org, "dash@contoso.com")
    created = _dashboard(client, h, name="Member board")
    # Member can render (dashboard:read).
    assert client.get(f"{DASH}/{created['id']}/render", headers=h).status_code == 200
    # But lacks dashboard:update / dashboard:delete.
    assert (
        client.patch(f"{DASH}/{created['id']}", headers=h, json={"name": "Renamed"}).status_code
        == 403
    )
    assert client.delete(f"{DASH}/{created['id']}", headers=h).status_code == 403
