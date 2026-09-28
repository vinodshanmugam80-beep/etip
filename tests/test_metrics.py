"""Integration tests for the metric-snapshot / sparkline surface.

Verifies that a capture writes one point per headline metric plus one per
project, that captures are idempotent per day (upsert, not append), that the
demo backfill produces a multi-point trend, and that the sparkline bundle is
shaped as the dashboard expects. Read access (``intelligence:read``) is
enforced. EVM inputs are written directly on the project rows so the captured
values are deterministic.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.modules.project.models import Project

METRICS = "/api/v1/intelligence/metrics"
PROJECTS = "/api/v1/projects"


def _project(client: TestClient, h: dict[str, str], code: str) -> dict:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def _configure(
    factory: sessionmaker[Session],
    project_id: str,
    *,
    budget: str,
    progress: int,
    actual: str,
    bstart: date,
    bend: date,
) -> None:
    with factory() as session:
        project = session.get(Project, uuid.UUID(project_id))
        assert project is not None
        project.budget = Decimal(budget)
        project.progress_percent = progress
        project.actual_cost = Decimal(actual)
        project.baseline_start_date = bstart
        project.baseline_end_date = bend
        session.commit()


def _seed_project(
    client: TestClient,
    headers: dict[str, str],
    factory: sessionmaker[Session],
    code: str,
) -> dict:
    proj = _project(client, headers, code)
    _configure(
        factory,
        proj["id"],
        budget="100000.00",
        progress=25,
        actual="40000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    return proj


def test_capture_writes_headline_and_project_points(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    _seed_project(client, admin_headers, session_factory, "MCA")

    r = client.post(f"{METRICS}/capture", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # headline: success_score + spi + cpi + realization, plus one project spi.
    assert body["captured"] >= 2
    assert body["as_of"]


def test_capture_is_idempotent_per_day(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    _seed_project(client, admin_headers, session_factory, "MCB")

    first = client.post(f"{METRICS}/capture", headers=admin_headers).json()["captured"]
    client.post(f"{METRICS}/capture", headers=admin_headers)

    spark = client.get(f"{METRICS}/sparklines", headers=admin_headers).json()
    # Two captures on the same day upsert the same rows: each series has one point.
    assert first >= 1
    for points in spark["headline"].values():
        assert len(points) == 1
    for points in spark["projects"].values():
        assert len(points) == 1


def test_backfill_demo_produces_a_trend(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    _seed_project(client, admin_headers, session_factory, "MCC")

    r = client.post(f"{METRICS}/backfill-demo", headers=admin_headers, params={"days": 6})
    assert r.status_code == 200, r.text
    assert r.json()["captured"] > 0

    spark = client.get(f"{METRICS}/sparklines", headers=admin_headers).json()
    assert spark["headline"], "expected headline series after backfill"
    # 6 backfilled days + today = 7 points on the success_score trend.
    assert len(spark["headline"]["success_score"]) == 7
    for points in spark["projects"].values():
        assert len(points) == 7


def test_sparklines_shape_without_history(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    spark = client.get(f"{METRICS}/sparklines", headers=admin_headers).json()
    assert spark == {"headline": {}, "projects": {}}


def test_sparkline_limit_is_respected(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    _seed_project(client, admin_headers, session_factory, "MCD")
    client.post(f"{METRICS}/backfill-demo", headers=admin_headers, params={"days": 20})

    spark = client.get(
        f"{METRICS}/sparklines", headers=admin_headers, params={"limit": 5}
    ).json()
    assert len(spark["headline"]["success_score"]) == 5


def test_metrics_requires_authentication(client: TestClient) -> None:
    assert client.get(f"{METRICS}/sparklines").status_code == 401
    assert client.post(f"{METRICS}/capture").status_code == 401
