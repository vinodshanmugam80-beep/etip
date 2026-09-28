"""Integration tests for the AI Copilot module.

Covers intent classification, entity resolution (by code and by context),
grounded answers over the report engine, the help/unknown/clarification paths,
conversation persistence (user + assistant turns, auto-title), per-user scoping,
deletion, and that a member can use the assistant.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

COPILOT = "/api/v1/copilot"
PROJECTS = "/api/v1/projects"
PORTFOLIOS = "/api/v1/portfolios"
RISKS = "/api/v1/risks"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _project(client: TestClient, h: dict[str, str], code: str, **o: object) -> dict:
    body: dict[str, object] = {"name": "Project", "code": code}
    body.update(o)
    r = client.post(PROJECTS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _ask(client: TestClient, h: dict[str, str], question: str, context: dict | None = None) -> dict:
    r = client.post(
        f"{COPILOT}/ask", headers=h, json={"question": question, "context": context or {}}
    )
    assert r.status_code == 200, r.text
    return r.json()


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


def _headers(client: TestClient, registered_org: dict[str, str], email: str) -> dict[str, str]:
    tokens = _login(
        client,
        {"organization_slug": registered_org["organization_slug"], "email": email, "password": PW},
    )
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_project_status_grounded(client: TestClient, admin_headers: dict[str, str]) -> None:
    _project(client, admin_headers, "ATLAS", budget="100000.00")
    ans = _ask(client, admin_headers, "How is ATLAS doing?")
    assert ans["intent"] == "project_status"
    assert "ATLAS" in ans["answer"]
    # The answer is grounded in real data.
    assert ans["grounding"]["data"]["code"] == "ATLAS"
    assert ans["grounding"]["data"]["budget"] == "100000.00"
    # Earned-value health is folded in so the copilot matches the dashboard.
    assert "earned-value health" in ans["answer"]
    assert "rag" in ans["grounding"]["data"]
    assert {"spi", "cpi"} <= set(ans["grounding"]["data"])


def test_raid_and_financial_intents(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, "BETA")
    client.post(
        RISKS,
        headers=admin_headers,
        json={"project_id": proj["id"], "title": "A risk", "probability": 4, "impact": 4},
    )

    raid = _ask(client, admin_headers, "What are the open risks and issues for BETA?")
    assert raid["intent"] == "raid_summary"
    assert raid["grounding"]["data"]["risks"]["open"] == 1

    fin = _ask(client, admin_headers, "What's the budget for BETA?")
    assert fin["intent"] == "financial_summary"
    assert "budget" in fin["grounding"]["data"]


def test_portfolio_intent(client: TestClient, admin_headers: dict[str, str]) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Growth", "code": "GROWTH"}
    ).json()
    _project(client, admin_headers, "P1", budget="20000.00", portfolio_id=port["id"])
    ans = _ask(client, admin_headers, "Give me an overview of the GROWTH portfolio")
    assert ans["intent"] == "portfolio_overview"
    assert ans["grounding"]["data"]["project_count"] == 1


def test_context_param_resolution(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, "GAMMA")
    # No code in the text; resolve from context instead.
    ans = _ask(client, admin_headers, "How is it doing?", context={"project_id": proj["id"]})
    assert ans["intent"] == "project_status" and ans["grounding"]["data"]["code"] == "GAMMA"


def test_help_unknown_and_clarification(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert _ask(client, admin_headers, "What can you do?")["intent"] == "help"
    assert _ask(client, admin_headers, "hello there friend")["intent"] == "unknown"
    # Status intent but no resolvable project → asks for clarification.
    needs = _ask(client, admin_headers, "What is the current status?")
    assert needs["intent"] == "needs_project"


def test_conversation_persists_turns_and_titles(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    _project(client, admin_headers, "DELTA")
    conv = client.post(
        f"{COPILOT}/conversations", headers=admin_headers, json={"title": "New conversation"}
    ).json()
    cid = conv["id"]

    asked = client.post(
        f"{COPILOT}/conversations/{cid}/ask",
        headers=admin_headers,
        json={"question": "How is DELTA doing?", "context": {}},
    )
    assert asked.status_code == 200
    body = asked.json()
    assert body["intent"] == "project_status" and body["conversation_id"] == cid

    # Both turns are persisted, in order, and the assistant turn is grounded.
    msgs = client.get(f"{COPILOT}/conversations/{cid}/messages", headers=admin_headers).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["intent"] == "project_status" and msgs[1]["grounding"]["data"]["code"] == "DELTA"

    # The conversation auto-titled from the first question.
    got = client.get(f"{COPILOT}/conversations/{cid}", headers=admin_headers).json()
    assert got["title"].startswith("How is DELTA")


def test_conversations_are_private(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    conv = client.post(
        f"{COPILOT}/conversations", headers=admin_headers, json={"title": "Admin chat"}
    ).json()
    _member(client, admin_headers, "spy@contoso.com")
    member = _headers(client, registered_org, "spy@contoso.com")

    # A different user cannot see, read, ask in, or delete it.
    assert client.get(f"{COPILOT}/conversations/{conv['id']}", headers=member).status_code == 404
    assert (
        client.get(f"{COPILOT}/conversations/{conv['id']}/messages", headers=member).status_code
        == 404
    )
    assert (
        client.post(
            f"{COPILOT}/conversations/{conv['id']}/ask",
            headers=member,
            json={"question": "peek", "context": {}},
        ).status_code
        == 404
    )
    assert client.delete(f"{COPILOT}/conversations/{conv['id']}", headers=member).status_code == 404
    # The member has copilot:use for their own ad-hoc questions.
    assert (
        client.post(
            f"{COPILOT}/ask", headers=member, json={"question": "help", "context": {}}
        ).status_code
        == 200
    )


def test_more_intents_and_resolution(client: TestClient, admin_headers: dict[str, str]) -> None:
    _project(client, admin_headers, "EPS")
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Ops", "code": "OPS"}
    ).json()

    assert (
        _ask(client, admin_headers, "Any overdue milestones for EPS?")["intent"]
        == "milestone_status"
    )
    hours = _ask(client, admin_headers, "How many hours were logged on EPS?")
    assert hours["intent"] == "timesheet_hours"
    assert "total_hours" in hours["grounding"]["data"]

    by_ctx = _ask(
        client, admin_headers, "portfolio overview please", context={"portfolio_id": port["id"]}
    )
    assert by_ctx["intent"] == "portfolio_overview"
    by_code = _ask(client, admin_headers, "status?", context={"project_code": "EPS"})
    assert by_code["intent"] == "project_status"
    assert by_code["grounding"]["data"]["code"] == "EPS"

    assert _ask(client, admin_headers, "show me the portfolio")["intent"] == "needs_portfolio"
    assert (
        _ask(client, admin_headers, "status?", context={"project_id": "not-a-uuid"})["intent"]
        == "needs_project"
    )
    assert _ask(client, admin_headers, "how is NOPE doing")["intent"] == "needs_project"


def test_delete_conversation(client: TestClient, admin_headers: dict[str, str]) -> None:
    _project(client, admin_headers, "OMEGA")
    conv = client.post(
        f"{COPILOT}/conversations", headers=admin_headers, json={"title": "Temp"}
    ).json()
    client.post(
        f"{COPILOT}/conversations/{conv['id']}/ask",
        headers=admin_headers,
        json={"question": "How is OMEGA doing?", "context": {}},
    )
    assert (
        client.delete(f"{COPILOT}/conversations/{conv['id']}", headers=admin_headers).status_code
        == 200
    )
    assert (
        client.get(f"{COPILOT}/conversations/{conv['id']}", headers=admin_headers).status_code
        == 404
    )
    assert client.get(f"{COPILOT}/conversations", headers=admin_headers).json()["total"] == 0
    # Unknown conversation.
    assert (
        client.get(f"{COPILOT}/conversations/{uuid.uuid4()}", headers=admin_headers).status_code
        == 404
    )
