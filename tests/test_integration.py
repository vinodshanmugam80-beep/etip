"""Integration tests for the Integration Hub (outbound webhooks).

The HTTP sender is monkeypatched, so delivery is exercised without real network
calls — covering delivered, failed, publish routing, signing, RBAC and 404s.
"""

from __future__ import annotations

import uuid
from datetime import UTC

import pytest
from fastapi.testclient import TestClient

import app.modules.integration.service as svc
from tests.conftest import _login

WH = "/api/v1/integrations/webhooks"
EVENTS = "/api/v1/integrations/events"
PUBLISH = "/api/v1/integrations/events/publish"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


@pytest.fixture
def ok_sender(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Patch the sender to succeed and capture the headers of each call."""
    calls: list[dict[str, str]] = []

    def _fake(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        calls.append(headers)
        return 200, ""

    monkeypatch.setattr(svc, "send_request", _fake)
    return calls


def _endpoint(client: TestClient, h: dict[str, str], **body: object) -> dict:
    payload: dict[str, object] = {
        "name": "Slack alerts",
        "target_url": "https://example.com/hook",
        "secret": "s3cr3t",
        "event_types": ["risk.raised"],
    }
    payload.update(body)
    r = client.post(WH, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_event_catalogue(client: TestClient, admin_headers: dict[str, str]) -> None:
    body = client.get(EVENTS, headers=admin_headers).json()
    assert "risk.raised" in body["event_types"] and "benefit.realized" in body["event_types"]


def test_endpoint_crud_and_secret_hidden(client: TestClient, admin_headers: dict[str, str]) -> None:
    ep = _endpoint(client, admin_headers)
    assert "secret" not in ep and ep["secret_set"] is True  # secret value never returned
    # Bad URL and unknown event are rejected.
    assert (
        client.post(
            WH,
            headers=admin_headers,
            json={"name": "Bad", "target_url": "ftp://x", "event_types": []},
        ).status_code
        == 422
    )
    assert (
        client.post(
            WH,
            headers=admin_headers,
            json={
                "name": "Bad",
                "target_url": "https://x.co",
                "event_types": ["nope.event"],
            },
        ).status_code
        == 422
    )

    got = client.get(f"{WH}/{ep['id']}", headers=admin_headers).json()
    assert got["name"] == "Slack alerts"
    upd = client.patch(f"{WH}/{ep['id']}", headers=admin_headers, json={"is_active": False}).json()
    assert upd["is_active"] is False
    assert client.get(WH, headers=admin_headers, params={"is_active": False}).json()["total"] == 1
    assert client.delete(f"{WH}/{ep['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"{WH}/{ep['id']}", headers=admin_headers).status_code == 404


def test_test_delivery_signed(
    client: TestClient, admin_headers: dict[str, str], ok_sender: list
) -> None:
    ep = _endpoint(client, admin_headers)
    d = client.post(f"{WH}/{ep['id']}/test", headers=admin_headers).json()
    assert (
        d["status"] == "delivered" and d["status_code"] == 200 and d["event_type"] == "webhook.test"
    )
    # The payload was HMAC-signed.
    assert ok_sender and ok_sender[-1]["X-ETIP-Signature"].startswith("sha256=")


def test_delivery_failure_recorded(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(svc, "send_request", _boom)
    ep = _endpoint(client, admin_headers)
    d = client.post(f"{WH}/{ep['id']}/test", headers=admin_headers).json()
    assert d["status"] == "failed" and "connection refused" in d["error"]


def test_publish_routes_to_subscribers(
    client: TestClient, admin_headers: dict[str, str], ok_sender: list
) -> None:
    _endpoint(client, admin_headers, name="Risk hook", event_types=["risk.raised"])
    _endpoint(client, admin_headers, name="Benefit hook", event_types=["benefit.realized"])

    res = client.post(
        PUBLISH,
        headers=admin_headers,
        json={"event_type": "risk.raised", "payload": {"project": "ATLAS"}},
    ).json()
    assert res["endpoints_matched"] == 1 and res["delivered"] == 1 and res["failed"] == 0

    # An event nobody subscribes to matches nothing.
    none = client.post(
        PUBLISH,
        headers=admin_headers,
        json={"event_type": "milestone.overdue", "payload": {}},
    ).json()
    assert none["endpoints_matched"] == 0

    # Unknown event type is rejected.
    assert (
        client.post(
            PUBLISH,
            headers=admin_headers,
            json={"event_type": "made.up", "payload": {}},
        ).status_code
        == 422
    )

    # Deliveries are logged.
    deliveries = client.get(f"{WH}/deliveries", headers=admin_headers).json()
    assert deliveries["total"] >= 1


def test_not_found(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{WH}/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.post(f"{WH}/{uuid.uuid4()}/test", headers=admin_headers).status_code == 404


def test_rbac(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    _endpoint(client, admin_headers)
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "int@contoso.com",
            "full_name": "Int Reader",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "int@contoso.com",
            "password": PW,
        },
    )
    member = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get(WH, headers=member).status_code == 200  # read allowed
    assert (
        client.post(
            WH,
            headers=member,
            json={"name": "Nope", "target_url": "https://x.co", "event_types": []},
        ).status_code
        == 403
    )


def test_retry_failed_then_succeeds(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        raise RuntimeError("down")

    monkeypatch.setattr(svc, "send_request", _boom)
    ep = _endpoint(client, admin_headers)
    d = client.post(f"{WH}/{ep['id']}/test", headers=admin_headers).json()
    assert d["status"] == "failed" and d["attempts"] == 1 and d["next_retry_at"] is not None

    # Retry now succeeds: attempts increments, status flips, retry schedule clears.
    monkeypatch.setattr(svc, "send_request", lambda u, b, h: (200, ""))
    r = client.post(f"{WH}/deliveries/{d['id']}/retry", headers=admin_headers).json()
    assert r["status"] == "delivered" and r["attempts"] == 2 and r["next_retry_at"] is None


def test_retry_conflicts_and_not_found(
    client: TestClient, admin_headers: dict[str, str], ok_sender: list
) -> None:
    ep = _endpoint(client, admin_headers)
    d = client.post(f"{WH}/{ep['id']}/test", headers=admin_headers).json()  # delivered
    # Delivered deliveries can't be retried.
    assert client.post(f"{WH}/deliveries/{d['id']}/retry", headers=admin_headers).status_code == 409
    assert (
        client.post(f"{WH}/deliveries/{uuid.uuid4()}/retry", headers=admin_headers).status_code
        == 404
    )


def test_retry_due(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime, timedelta

    from app.modules.integration.models import WebhookDelivery

    def _boom(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        raise RuntimeError("down")

    monkeypatch.setattr(svc, "send_request", _boom)
    ep = _endpoint(client, admin_headers)
    d = client.post(f"{WH}/{ep['id']}/test", headers=admin_headers).json()

    # Backdate the retry window so the delivery is due.
    with session_factory() as s:
        row = s.get(WebhookDelivery, uuid.UUID(d["id"]))
        row.next_retry_at = datetime.now(UTC) - timedelta(minutes=1)
        s.commit()

    monkeypatch.setattr(svc, "send_request", lambda u, b, h: (200, ""))
    res = client.post(f"{WH}/deliveries/retry-due", headers=admin_headers).json()
    assert res["total"] == 1 and res["items"][0]["status"] == "delivered"


def test_outbox_emits_and_dispatches(
    client: TestClient, admin_headers: dict[str, str], ok_sender: list
) -> None:
    # Subscribe a webhook to project.created.
    _endpoint(client, admin_headers, name="Proj hook", event_types=["project.created"])
    # Creating a project auto-emits an event into the transactional outbox.
    client.post(
        "/api/v1/projects",
        headers=admin_headers,
        json={"name": "Outbox Proj", "code": "OBX"},
    )
    ob = client.get("/api/v1/integrations/outbox", headers=admin_headers).json()
    assert any(
        e["event_type"] == "project.created" and e["status"] == "pending" for e in ob["items"]
    )

    # Dispatch delivers pending events to subscribers, out-of-band.
    res = client.post("/api/v1/integrations/outbox/dispatch", headers=admin_headers).json()
    assert res["dispatched"] >= 1 and res["deliveries_created"] >= 1

    ob2 = client.get("/api/v1/integrations/outbox", headers=admin_headers).json()
    assert all(e["status"] == "dispatched" for e in ob2["items"])
    dl = client.get("/api/v1/integrations/webhooks/deliveries", headers=admin_headers).json()
    assert any(d["event_type"] == "project.created" for d in dl["items"])


def test_outbox_dispatch_no_subscribers(client: TestClient, admin_headers: dict[str, str]) -> None:
    # No webhook subscribes; the event still dispatches (0 deliveries).
    client.post(
        "/api/v1/projects",
        headers=admin_headers,
        json={"name": "NoSub Proj", "code": "NOS"},
    )
    res = client.post("/api/v1/integrations/outbox/dispatch", headers=admin_headers).json()
    assert res["dispatched"] >= 1 and res["deliveries_created"] == 0


def test_scheduled_dispatch_across_tenant(
    client: TestClient, admin_headers: dict[str, str], session_factory, ok_sender: list
) -> None:
    from app.db.unit_of_work import UnitOfWork
    from app.modules.integration.tasks import dispatch_all_pending

    _endpoint(client, admin_headers, name="Beat hook", event_types=["project.created"])
    client.post(
        "/api/v1/projects",
        headers=admin_headers,
        json={"name": "Beat Proj", "code": "BEAT"},
    )

    # Run the beat-scheduled orchestration directly (no broker needed).
    with UnitOfWork(session_factory) as uow:
        res = dispatch_all_pending(uow)
    assert res["organizations"] >= 1 and res["events"] >= 1 and res["deliveries"] >= 1

    ob = client.get("/api/v1/integrations/outbox", headers=admin_headers).json()
    assert ob["items"] and all(e["status"] == "dispatched" for e in ob["items"])
