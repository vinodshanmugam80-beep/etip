"""Jira Cloud REST client — isolated so it can be mocked in tests.

Uses HTTP basic auth (email + API token), the standard Jira Cloud scheme.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any

from app.core.exceptions import ValidationError
from app.modules.jira.models import JiraConnection


def jira_request(
    conn: JiraConnection, method: str, path: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Call the Jira REST API and return the parsed JSON body (``{}`` if empty)."""
    url = conn.base_url.rstrip("/") + path
    token = base64.b64encode(f"{conn.user_email}:{conn.api_token}".encode()).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:300]
        raise ValidationError(f"Jira API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValidationError(f"Could not reach Jira: {exc.reason}") from exc


def get_myself(conn: JiraConnection) -> dict[str, Any]:
    """Return the authenticated Jira account (used to verify credentials)."""
    return jira_request(conn, "GET", "/rest/api/2/myself")


def search_issues(
    conn: JiraConnection, jql: str, *, start_at: int = 0, max_results: int = 50
) -> dict[str, Any]:
    """Return a page of issues matching a JQL query (Jira Cloud search API)."""
    from urllib.parse import quote

    path = (
        f"/rest/api/2/search?jql={quote(jql)}"
        f"&startAt={start_at}&maxResults={max_results}"
        f"&fields=summary,description,status,priority,assignee"
    )
    return jira_request(conn, "GET", path)
