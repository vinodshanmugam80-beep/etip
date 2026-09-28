"""Tests for the liveness and readiness health probes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readiness_up(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Session:
        def __enter__(self) -> _Session:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def execute(self, *args: object, **kwargs: object) -> None:
            return None

    import app.db.session as dbs

    monkeypatch.setattr(dbs, "SessionFactory", lambda: _Session())
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "database": "up"}


def test_readiness_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.db.session as dbs

    def _boom() -> None:
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(dbs, "SessionFactory", _boom)
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "unavailable"
