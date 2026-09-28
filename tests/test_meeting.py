"""Integration tests for the Meeting Management module.

Covers meeting CRUD, the organizer auto-invite, the status lifecycle with
actual-time stamping, schedule validation, attendee management (add/list/update/
remove, duplicate guard), the action-item → RAID-log integration, the project
cascade, and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

MEETINGS = "/api/v1/meetings"
ACTIONS = "/api/v1/actions"
PROJECTS = "/api/v1/projects"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"
START = "2026-03-10T15:00:00Z"
END = "2026-03-10T16:00:00Z"


def _project(client: TestClient, h: dict[str, str], code: str = "PR") -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _meeting(
    client: TestClient,
    h: dict[str, str],
    project_id: str,
    title: str = "Sprint review",
    **o: object,
) -> dict:
    body: dict[str, object] = {
        "project_id": project_id,
        "title": title,
        "scheduled_start": START,
        "scheduled_end": END,
    }
    body.update(o)
    r = client.post(MEETINGS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _member(client: TestClient, admin_headers: dict[str, str], email: str) -> str:
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role_id = next(r["id"] for r in roles if r["name"] == "Member")
    r = client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": email,
            "full_name": "Person",
            "password": PW,
            "role_ids": [member_role_id],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_defaults_and_organizer_attendee(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    m = _meeting(client, admin_headers, proj["id"], meeting_type="review")
    assert m["status"] == "scheduled"
    assert m["organizer_user_id"] is not None  # defaults to the caller
    # The organizer is auto-invited as an accepted attendee.
    attendees = client.get(f"{MEETINGS}/{m['id']}/attendees", headers=admin_headers).json()
    assert len(attendees) == 1
    assert attendees[0]["role"] == "organizer" and attendees[0]["response"] == "accepted"


def test_create_validations(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert (
        client.post(
            MEETINGS,
            headers=admin_headers,
            json={
                "project_id": str(uuid.uuid4()),
                "title": "Orphan",
                "scheduled_start": START,
                "scheduled_end": END,
            },
        ).status_code
        == 404
    )
    proj = _project(client, admin_headers)
    # End before start.
    bad = client.post(
        MEETINGS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "Backwards",
            "scheduled_start": END,
            "scheduled_end": START,
        },
    )
    assert bad.status_code == 422
    # Unknown organizer.
    bad_org = client.post(
        MEETINGS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "Owned",
            "scheduled_start": START,
            "scheduled_end": END,
            "organizer_user_id": str(uuid.uuid4()),
        },
    )
    assert bad_org.status_code == 422


def test_lifecycle_and_actual_times(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    m = _meeting(client, admin_headers, proj["id"])
    mid = m["id"]

    started = client.patch(
        f"{MEETINGS}/{mid}", headers=admin_headers, json={"status": "in_progress"}
    )
    assert started.status_code == 200 and started.json()["actual_start"] is not None
    completed = client.patch(
        f"{MEETINGS}/{mid}",
        headers=admin_headers,
        json={"status": "completed", "minutes": "Notes"},
    )
    assert completed.status_code == 200
    assert completed.json()["actual_end"] is not None and completed.json()["minutes"] == "Notes"
    # Completed is terminal.
    assert (
        client.patch(
            f"{MEETINGS}/{mid}", headers=admin_headers, json={"status": "cancelled"}
        ).status_code
        == 422
    )


def test_update_schedule_validation(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    m = _meeting(client, admin_headers, proj["id"])
    bad = client.patch(
        f"{MEETINGS}/{m['id']}",
        headers=admin_headers,
        json={"scheduled_end": "2026-03-10T14:00:00Z"},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_schedule"


def test_attendee_management(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    m = _meeting(client, admin_headers, proj["id"])
    mid = m["id"]
    member_id = _member(client, admin_headers, "att@contoso.com")

    added = client.post(
        f"{MEETINGS}/{mid}/attendees",
        headers=admin_headers,
        json={"user_id": member_id, "role": "required"},
    )
    assert added.status_code == 201
    attendee_id = added.json()["id"]
    # Duplicate.
    dup = client.post(
        f"{MEETINGS}/{mid}/attendees",
        headers=admin_headers,
        json={"user_id": member_id},
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_attendee"
    # Unknown user.
    assert (
        client.post(
            f"{MEETINGS}/{mid}/attendees",
            headers=admin_headers,
            json={"user_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )

    # Update RSVP + attendance.
    upd = client.patch(
        f"{MEETINGS}/{mid}/attendees/{attendee_id}",
        headers=admin_headers,
        json={"response": "accepted", "attended": True},
    )
    assert (
        upd.status_code == 200
        and upd.json()["response"] == "accepted"
        and upd.json()["attended"] is True
    )

    listed = client.get(f"{MEETINGS}/{mid}/attendees", headers=admin_headers).json()
    assert len(listed) == 2  # organizer + member
    # Remove.
    assert (
        client.delete(
            f"{MEETINGS}/{mid}/attendees/{attendee_id}", headers=admin_headers
        ).status_code
        == 200
    )
    assert len(client.get(f"{MEETINGS}/{mid}/attendees", headers=admin_headers).json()) == 1


def test_action_items_link_to_raid(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    m = _meeting(client, admin_headers, proj["id"])
    mid = m["id"]

    created = client.post(
        f"{MEETINGS}/{mid}/action-items",
        headers=admin_headers,
        json={"title": "Follow up with vendor", "priority": "high"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["source_meeting_id"] == mid
    assert body["status"] == "open" and body["number"] >= 1

    # It shows in the meeting's action-item list.
    items = client.get(f"{MEETINGS}/{mid}/action-items", headers=admin_headers).json()
    assert len(items) == 1 and items[0]["id"] == body["id"]

    # And it is a first-class RAID action on the project.
    raid = client.get(ACTIONS, headers=admin_headers, params={"project_id": proj["id"]}).json()
    assert raid["total"] == 1 and raid["items"][0]["source_meeting_id"] == mid


def test_search_orders_by_start(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers)
    _meeting(
        client,
        admin_headers,
        proj["id"],
        title="Later",
        meeting_type="planning",
        scheduled_start="2026-05-01T10:00:00Z",
        scheduled_end="2026-05-01T11:00:00Z",
    )
    _meeting(
        client,
        admin_headers,
        proj["id"],
        title="Sooner",
        meeting_type="review",
        scheduled_start="2026-04-01T10:00:00Z",
        scheduled_end="2026-04-01T11:00:00Z",
    )
    listing = client.get(
        MEETINGS, headers=admin_headers, params={"project_id": proj["id"], "q": "er"}
    ).json()
    assert [m["title"] for m in listing["items"]] == ["Sooner", "Later"]

    planning = client.get(
        MEETINGS,
        headers=admin_headers,
        params={"project_id": proj["id"], "meeting_type": "planning"},
    ).json()
    assert planning["total"] == 1 and planning["items"][0]["title"] == "Later"
    windowed = client.get(
        MEETINGS,
        headers=admin_headers,
        params={"project_id": proj["id"], "date_from": "2026-04-15T00:00:00Z"},
    ).json()
    assert windowed["total"] == 1 and windowed["items"][0]["title"] == "Later"


def test_direct_delete_cascades_attendees(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    m = _meeting(client, admin_headers, proj["id"])
    member_id = _member(client, admin_headers, "gone@contoso.com")
    client.post(
        f"{MEETINGS}/{m['id']}/attendees",
        headers=admin_headers,
        json={"user_id": member_id},
    )
    assert client.delete(f"{MEETINGS}/{m['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{MEETINGS}/{m['id']}", headers=admin_headers).status_code == 404
    assert client.get(f"{MEETINGS}/{m['id']}/attendees", headers=admin_headers).status_code == 404


def test_project_delete_cascades_meetings(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers)
    m = _meeting(client, admin_headers, proj["id"])
    assert client.delete(f"{PROJECTS}/{proj['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{MEETINGS}/{m['id']}", headers=admin_headers).status_code == 404


def test_rbac_member_manages_not_deletes(
    client: TestClient,
    admin_headers: dict[str, str],
    registered_org: dict[str, str],
) -> None:
    """Member has create/read/update but not delete."""
    proj = _project(client, admin_headers)
    _member(client, admin_headers, "organizer@contoso.com")
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "organizer@contoso.com",
            "password": PW,
        },
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    created = _meeting(client, headers, proj["id"], title="Member meeting")
    mid = created["id"]
    # Member can update and add attendees.
    assert (
        client.patch(
            f"{MEETINGS}/{mid}", headers=headers, json={"status": "in_progress"}
        ).status_code
        == 200
    )
    other_id = _member(client, admin_headers, "invitee@contoso.com")
    assert (
        client.post(
            f"{MEETINGS}/{mid}/attendees", headers=headers, json={"user_id": other_id}
        ).status_code
        == 201
    )
    # But cannot delete.
    assert client.delete(f"{MEETINGS}/{mid}", headers=headers).status_code == 403
