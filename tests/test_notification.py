"""Integration tests for the Notifications module.

Covers sending, recipient validation, the crucial per-user scoping (a user only
ever sees and manages their own notifications), the read/unread/archived state
changes with read-date stamping, unread count, bulk mark-all-read, delete,
mute preferences (which suppress sends), and RBAC.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

NOTES = "/api/v1/notifications"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _member(client: TestClient, admin_headers: dict[str, str], email: str) -> str:
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role_id = next(r["id"] for r in roles if r["name"] == "Member")
    r = client.post(
        USERS,
        headers=admin_headers,
        json={"email": email, "full_name": "Person", "password": PW, "role_ids": [member_role_id]},
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


def _send(
    client: TestClient,
    admin_headers: dict[str, str],
    user_id: str,
    ntype: str = "assignment",
    title: str = "Heads up",
    **o: object,
) -> dict:
    body: dict[str, object] = {"user_id": user_id, "notification_type": ntype, "title": title}
    body.update(o)
    r = client.post(NOTES, headers=admin_headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_send_and_recipient_validation(client: TestClient, admin_headers: dict[str, str]) -> None:
    member_id = _member(client, admin_headers, "recv@contoso.com")
    result = _send(client, admin_headers, member_id, title="You have a task")
    assert result["created"] is True
    assert result["notification"]["status"] == "unread"
    assert result["notification"]["user_id"] == member_id

    # Unknown recipient.
    bad = client.post(
        NOTES,
        headers=admin_headers,
        json={"user_id": str(uuid.uuid4()), "notification_type": "system", "title": "Nope"},
    )
    assert bad.status_code == 422


def test_per_user_scoping_is_private(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    member_id = _member(client, admin_headers, "private@contoso.com")
    sent = _send(client, admin_headers, member_id, title="For the member")
    note_id = sent["notification"]["id"]
    member_headers = _member_headers(client, registered_org, "private@contoso.com")

    # The member sees their notification.
    member_list = client.get(NOTES, headers=member_headers).json()
    assert member_list["total"] == 1 and member_list["items"][0]["id"] == note_id

    # The admin (a different user) does NOT see the member's notification in
    # their own list, and cannot fetch it by id.
    admin_list = client.get(NOTES, headers=admin_headers).json()
    assert all(n["id"] != note_id for n in admin_list["items"])
    assert client.get(f"{NOTES}/{note_id}", headers=admin_headers).status_code == 404
    # The member can fetch their own.
    assert client.get(f"{NOTES}/{note_id}", headers=member_headers).status_code == 200


def test_state_changes_and_read_date(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    member_id = _member(client, admin_headers, "state@contoso.com")
    sent = _send(client, admin_headers, member_id)
    note_id = sent["notification"]["id"]
    h = _member_headers(client, registered_org, "state@contoso.com")

    read = client.patch(f"{NOTES}/{note_id}", headers=h, json={"status": "read"})
    assert read.status_code == 200 and read.json()["read_date"] is not None
    # Back to unread clears the read date.
    unread = client.patch(f"{NOTES}/{note_id}", headers=h, json={"status": "unread"})
    assert unread.status_code == 200 and unread.json()["read_date"] is None
    # Archive.
    assert (
        client.patch(f"{NOTES}/{note_id}", headers=h, json={"status": "archived"}).status_code
        == 200
    )


def test_unread_count_and_read_all(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    member_id = _member(client, admin_headers, "count@contoso.com")
    for i in range(3):
        _send(client, admin_headers, member_id, title=f"Note {i}")
    h = _member_headers(client, registered_org, "count@contoso.com")

    assert client.get(f"{NOTES}/unread-count", headers=h).json()["unread"] == 3
    done = client.post(f"{NOTES}/read-all", headers=h, json={})
    assert done.status_code == 200
    assert client.get(f"{NOTES}/unread-count", headers=h).json()["unread"] == 0


def test_filters_and_delete(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    member_id = _member(client, admin_headers, "filter@contoso.com")
    a = _send(client, admin_headers, member_id, ntype="assignment", title="Assigned")
    _send(client, admin_headers, member_id, ntype="mention", title="Mentioned")
    h = _member_headers(client, registered_org, "filter@contoso.com")

    mentions = client.get(NOTES, headers=h, params={"notification_type": "mention"}).json()
    assert mentions["total"] == 1 and mentions["items"][0]["title"] == "Mentioned"

    assert client.delete(f"{NOTES}/{a['notification']['id']}", headers=h).status_code == 200
    assert client.get(NOTES, headers=h).json()["total"] == 1


def test_mute_preference_suppresses_send(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    member_id = _member(client, admin_headers, "mute@contoso.com")
    h = _member_headers(client, registered_org, "mute@contoso.com")

    # Member mutes the 'system' type.
    pref = client.put(f"{NOTES}/preferences/system", headers=h, json={"muted": True})
    assert pref.status_code == 200 and pref.json()["muted"] is True

    # A system notification is suppressed; an assignment still gets through.
    suppressed = client.post(
        NOTES,
        headers=admin_headers,
        json={"user_id": member_id, "notification_type": "system", "title": "Downtime"},
    )
    assert suppressed.status_code == 200 and suppressed.json()["created"] is False
    delivered = _send(client, admin_headers, member_id, ntype="assignment", title="Task")
    assert delivered["created"] is True

    assert client.get(NOTES, headers=h).json()["total"] == 1  # only the assignment
    prefs = client.get(f"{NOTES}/preferences", headers=h).json()
    assert any(p["notification_type"] == "system" and p["muted"] for p in prefs)

    # Unmuting updates the existing preference row; sends get through again.
    reset = client.put(f"{NOTES}/preferences/system", headers=h, json={"muted": False})
    assert reset.status_code == 200 and reset.json()["muted"] is False
    again = client.post(
        NOTES,
        headers=admin_headers,
        json={"user_id": member_id, "notification_type": "system", "title": "Back on"},
    )
    assert again.json()["created"] is True


def test_rbac_member_cannot_send(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    other_id = _member(client, admin_headers, "target@contoso.com")
    _member(client, admin_headers, "nosend@contoso.com")
    h = _member_headers(client, registered_org, "nosend@contoso.com")
    # Members lack notification:create.
    assert (
        client.post(
            NOTES,
            headers=h,
            json={"user_id": other_id, "notification_type": "system", "title": "Hi there"},
        ).status_code
        == 403
    )
    # But they can read their own inbox.
    assert client.get(NOTES, headers=h).status_code == 200
