"""Integration tests for the Intelligence Layer — Performance (EVM) engine.

Verifies the EVM arithmetic against hand-computed scenarios (PV/EV/AC → SV/CV/
SPI/CPI/EAC), RAG health states, the as-of planned-value calculation, program /
portfolio / transformation rollups, not-found handling, and read access.

EVM inputs (budget, progress_percent, actual_cost, baseline dates) are set
directly on the project rows so the expected numbers are exact.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.modules.project.models import Project
from app.modules.resource.models import ResourceAllocation

PERF = "/api/v1/intelligence/performance"
PROJECTS = "/api/v1/projects"
PORTFOLIOS = "/api/v1/portfolios"
PROGRAMS = "/api/v1/programs"


def _project(client: TestClient, h: dict[str, str], code: str, **body: object) -> dict:
    payload: dict[str, object] = {"name": "Project", "code": code}
    payload.update(body)
    r = client.post(PROJECTS, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _configure(
    factory: sessionmaker[Session],
    project_id: str,
    *,
    budget: str,
    progress: int,
    actual: str,
    forecast: str = "0.00",
    bstart: date | None = None,
    bend: date | None = None,
) -> None:
    with factory() as session:
        project = session.get(Project, uuid.UUID(project_id))
        assert project is not None
        project.budget = Decimal(budget)
        project.progress_percent = progress
        project.actual_cost = Decimal(actual)
        project.forecast = Decimal(forecast)
        project.baseline_start_date = bstart
        project.baseline_end_date = bend
        session.commit()


def test_project_evm_math(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, "EVM")
    # Budget 100k, 50% done, spent 60k; baseline 10 days, as_of at day 5 → PV 50%.
    _configure(
        session_factory,
        proj["id"],
        budget="100000.00",
        progress=50,
        actual="60000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    r = client.get(
        f"{PERF}/projects/{proj['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    )
    assert r.status_code == 200
    evm = r.json()["evm"]
    assert evm["bac"] == "100000.00"
    assert evm["ev"] == "50000.00"
    assert evm["ac"] == "60000.00"
    assert evm["pv"] == "50000.00"
    assert evm["sv"] == "0.00" and evm["spi"] == 1.0
    assert evm["cv"] == "-10000.00" and evm["cpi"] == 0.833
    assert evm["eac"] == "120000.00"  # BAC / CPI
    assert evm["vac"] == "-20000.00"
    # Worst index is CPI 0.833 (< 0.85) → red.
    assert r.json()["health"]["rag"] == "red"


def test_health_states(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    green = _project(client, admin_headers, "GRN")
    _configure(
        session_factory,
        green["id"],
        budget="100000.00",
        progress=100,
        actual="90000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    r = client.get(
        f"{PERF}/projects/{green['id']}",
        headers=admin_headers,
        params={"as_of": "2026-02-01"},
    )
    assert r.json()["health"]["rag"] == "green"  # SPI 1.0, CPI 1.11

    fresh = _project(client, admin_headers, "NEW")
    r2 = client.get(f"{PERF}/projects/{fresh['id']}", headers=admin_headers)
    assert r2.json()["health"]["rag"] == "not_started"


def test_planned_value_tracks_as_of(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, "PVT")
    _configure(
        session_factory,
        proj["id"],
        budget="100000.00",
        progress=0,
        actual="0.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    # Before start → PV 0; end → PV = BAC.
    before = client.get(
        f"{PERF}/projects/{proj['id']}",
        headers=admin_headers,
        params={"as_of": "2025-12-01"},
    ).json()
    assert before["evm"]["pv"] == "0.00" and before["evm"]["planned_percent"] == 0.0
    after = client.get(
        f"{PERF}/projects/{proj['id']}",
        headers=admin_headers,
        params={"as_of": "2026-03-01"},
    ).json()
    assert after["evm"]["pv"] == "100000.00" and after["evm"]["planned_percent"] == 1.0


def test_portfolio_rollup(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Growth", "code": "GRW"}
    ).json()
    p1 = _project(client, admin_headers, "PR1", portfolio_id=port["id"])
    p2 = _project(client, admin_headers, "PR2", portfolio_id=port["id"])
    _configure(session_factory, p1["id"], budget="100000.00", progress=50, actual="40000.00")
    _configure(session_factory, p2["id"], budget="200000.00", progress=25, actual="60000.00")

    roll = client.get(f"{PERF}/portfolios/{port['id']}", headers=admin_headers).json()
    assert roll["scope"] == "portfolio" and roll["project_count"] == 2
    # Aggregate BAC 300k, EV = 50k + 50k = 100k, AC = 100k.
    assert roll["evm"]["bac"] == "300000.00"
    assert roll["evm"]["ev"] == "100000.00"
    assert roll["evm"]["ac"] == "100000.00"
    assert roll["evm"]["cpi"] == 1.0
    assert len(roll["breakdown"]) == 2


def test_program_and_transformation(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Port", "code": "PRT"}
    ).json()
    prog = client.post(
        PROGRAMS,
        headers=admin_headers,
        json={"name": "Program", "code": "PGM", "portfolio_id": port["id"]},
    ).json()
    proj = _project(client, admin_headers, "PGP", portfolio_id=port["id"], program_id=prog["id"])
    _configure(session_factory, proj["id"], budget="50000.00", progress=100, actual="50000.00")

    prog_perf = client.get(f"{PERF}/programs/{prog['id']}", headers=admin_headers).json()
    assert prog_perf["scope"] == "program" and prog_perf["project_count"] == 1
    assert prog_perf["evm"]["ev"] == "50000.00"

    trans = client.get(f"{PERF}/transformation", headers=admin_headers).json()
    assert trans["scope"] == "transformation" and trans["scope_id"] is None
    assert trans["project_count"] >= 1


def test_not_found(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{PERF}/projects/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{PERF}/programs/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{PERF}/portfolios/{uuid.uuid4()}", headers=admin_headers).status_code == 404


# --- Variance engine -------------------------------------------------------
VAR = "/api/v1/intelligence/variance"
DEPARTMENTS = "/api/v1/organization/departments"
RESOURCES = "/api/v1/resources"


def test_project_variance_math(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, "VAR")
    _configure(
        session_factory,
        proj["id"],
        budget="100000.00",
        progress=50,
        actual="60000.00",
        forecast="110000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    body = client.get(
        f"{VAR}/projects/{proj['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    ).json()
    # SV = EV - PV = 0
    assert body["schedule"]["amount"] == "0.00" and body["schedule"]["favourable"] is True
    # CV = EV - AC = -10000 (unfavourable), -20% of EV
    assert body["cost"]["amount"] == "-10000.00" and body["cost"]["percent"] == -20.0
    assert body["cost"]["favourable"] is False
    # budget - forecast = 100000 - 110000 = -10000
    assert body["budget"]["amount"] == "-10000.00" and body["budget"]["favourable"] is False
    # forecast - EAC = 110000 - 120000 = -10000
    assert body["forecast"]["amount"] == "-10000.00" and body["forecast"]["favourable"] is False


def test_portfolio_variance_rollup(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Growth", "code": "VGR"}
    ).json()
    p1 = _project(client, admin_headers, "VP1", portfolio_id=port["id"])
    p2 = _project(client, admin_headers, "VP2", portfolio_id=port["id"])
    _configure(
        session_factory,
        p1["id"],
        budget="100000.00",
        progress=50,
        actual="40000.00",
        forecast="90000.00",
    )
    _configure(
        session_factory,
        p2["id"],
        budget="200000.00",
        progress=25,
        actual="60000.00",
        forecast="210000.00",
    )

    roll = client.get(f"{VAR}/portfolios/{port['id']}", headers=admin_headers).json()
    assert roll["scope"] == "portfolio" and roll["project_count"] == 2
    # Aggregate CV = (50000-40000) + (50000-60000) = 0
    assert roll["cost"]["amount"] == "0.00"
    # Aggregate budget - forecast = (300000) - (300000) = 0
    assert roll["budget"]["amount"] == "0.00"
    assert len(roll["breakdown"]) == 2


def test_department_variance(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    dept = client.post(
        DEPARTMENTS, headers=admin_headers, json={"name": "Delivery", "code": "DLV"}
    ).json()
    proj = _project(client, admin_headers, "DVP")
    with session_factory() as session:
        p = session.get(Project, uuid.UUID(proj["id"]))
        assert p is not None
        p.department_id = uuid.UUID(dept["id"])
        p.budget = Decimal("50000.00")
        p.progress_percent = 100
        p.actual_cost = Decimal("50000.00")
        session.commit()

    roll = client.get(f"{VAR}/departments/{dept['id']}", headers=admin_headers).json()
    assert roll["scope"] == "department" and roll["project_count"] == 1
    assert roll["scope_label"] == "Delivery"
    # Unknown department.
    assert client.get(f"{VAR}/departments/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_resource_variance_states(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, "RVP")
    org_id = uuid.UUID(proj["organization_id"])

    # Under-utilised resource via the API (one 50% allocation — valid).
    under = client.post(
        RESOURCES,
        headers=admin_headers,
        json={
            "name": "Ada Engineer",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    ).json()
    r = client.post(
        f"{RESOURCES}/{under['id']}/allocations",
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "allocation_percent": 50,
            "start_date": "2020-01-01",
            "end_date": "2100-01-01",
        },
    )
    assert r.status_code == 201, r.text

    # Over-allocated: V1 blocks this at the API, so insert rows directly to
    # exercise the engine's over-allocation classification.
    over = client.post(
        RESOURCES,
        headers=admin_headers,
        json={
            "name": "Grace Engineer",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    ).json()
    with session_factory() as session:
        for _ in range(2):
            session.add(
                ResourceAllocation(
                    organization_id=org_id,
                    resource_id=uuid.UUID(over["id"]),
                    project_id=uuid.UUID(proj["id"]),
                    allocation_percent=60,
                    start_date=date(2020, 1, 1),
                    end_date=date(2100, 1, 1),
                )
            )
        session.commit()

    summary = client.get(f"{VAR}/resources", headers=admin_headers).json()
    assert summary["over_allocated"] >= 1 and summary["under_utilized"] >= 1
    under_item = next(i for i in summary["items"] if i["resource_id"] == under["id"])
    assert under_item["allocated_percent"] == 50
    assert under_item["status"] == "under_utilized"
    over_item = next(i for i in summary["items"] if i["resource_id"] == over["id"])
    assert over_item["allocated_percent"] == 120
    assert over_item["status"] == "over_allocated"
    assert over_item["variance_percent"] == -20


def test_variance_not_found(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{VAR}/projects/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{VAR}/programs/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{VAR}/portfolios/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_program_transformation_and_balanced_variance(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Port", "code": "VPT"}
    ).json()
    prog = client.post(
        PROGRAMS,
        headers=admin_headers,
        json={"name": "Program", "code": "VPG", "portfolio_id": port["id"]},
    ).json()
    proj = _project(client, admin_headers, "VPP", portfolio_id=port["id"], program_id=prog["id"])
    _configure(
        session_factory,
        proj["id"],
        budget="80000.00",
        progress=50,
        actual="30000.00",
        forecast="80000.00",
    )

    prog_var = client.get(f"{VAR}/programs/{prog['id']}", headers=admin_headers).json()
    assert prog_var["scope"] == "program" and prog_var["project_count"] == 1

    trans_var = client.get(f"{VAR}/transformation", headers=admin_headers).json()
    assert trans_var["scope"] == "transformation" and trans_var["project_count"] >= 1

    # A fully (100%) allocated resource is "balanced".
    res = client.post(
        RESOURCES,
        headers=admin_headers,
        json={
            "name": "Full Engineer",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    ).json()
    client.post(
        f"{RESOURCES}/{res['id']}/allocations",
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "allocation_percent": 100,
            "start_date": "2020-01-01",
            "end_date": "2100-01-01",
        },
    )
    summary = client.get(f"{VAR}/resources", headers=admin_headers).json()
    item = next(i for i in summary["items"] if i["resource_id"] == res["id"])
    assert item["status"] == "balanced" and item["variance_percent"] == 0


# --- Forecast engine -------------------------------------------------------
FC = "/api/v1/intelligence/forecast"


def test_project_forecast_math(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, "FCA")
    # Behind schedule and over cost: at day 5 of a 10-day plan, only 25% done,
    # 40k spent of a 100k budget → SPI 0.5, CPI 0.625.
    _configure(
        session_factory,
        proj["id"],
        budget="100000.00",
        progress=25,
        actual="40000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    body = client.get(
        f"{FC}/projects/{proj['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    ).json()
    sched = body["schedule"]
    assert sched["forecast_completion"] == "2026-01-21"  # 10 / 0.5 = 20 days
    assert sched["slippage_days"] == 10 and sched["will_slip"] is True
    assert sched["basis"] == "SPI 0.50"
    budget = body["budget"]
    assert budget["forecast_cost"] == "160000.00"  # EAC = BAC * AC / EV
    assert budget["overrun_amount"] == "60000.00" and budget["overrun_percent"] == 60.0
    assert budget["will_overrun"] is True


def test_forecast_completed_and_no_baseline(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    done = _project(client, admin_headers, "FCD")
    _configure(
        session_factory,
        done["id"],
        budget="100.00",
        progress=100,
        actual="90.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    s = client.get(f"{FC}/projects/{done['id']}", headers=admin_headers).json()["schedule"]
    assert s["basis"] == "completed" and s["slippage_days"] == 0

    nb = _project(client, admin_headers, "FCN")
    _configure(session_factory, nb["id"], budget="100.00", progress=20, actual="10.00")
    s2 = client.get(f"{FC}/projects/{nb['id']}", headers=admin_headers).json()["schedule"]
    assert s2["basis"] == "no baseline schedule" and s2["forecast_completion"] is None


def test_forecast_rollup_and_transformation(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    port = client.post(PORTFOLIOS, headers=admin_headers, json={"name": "Fc", "code": "FCP"}).json()
    p1 = _project(client, admin_headers, "FR1", portfolio_id=port["id"])
    p2 = _project(client, admin_headers, "FR2", portfolio_id=port["id"])
    _configure(
        session_factory,
        p1["id"],
        budget="100000.00",
        progress=25,
        actual="40000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    _configure(session_factory, p2["id"], budget="100000.00", progress=100, actual="80000.00")

    roll = client.get(
        f"{FC}/portfolios/{port['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    ).json()
    assert roll["project_count"] == 2
    # EAC: p1 = 160000, p2 = 80000 → forecast_cost 240000; BAC 200000; overrun 40000.
    assert roll["forecast_cost"] == "240000.00"
    assert roll["budget_overrun"] == "40000.00"
    assert roll["projects_overrunning"] == 1 and roll["projects_slipping"] == 1
    assert roll["worst_slippage_days"] == 10

    # Insert an over-allocation so the transformation shortage signal fires.
    res = client.post(
        RESOURCES,
        headers=admin_headers,
        json={
            "name": "Over Person",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    ).json()
    with session_factory() as session:
        for _ in range(2):
            session.add(
                ResourceAllocation(
                    organization_id=uuid.UUID(p1["organization_id"]),
                    resource_id=uuid.UUID(res["id"]),
                    project_id=uuid.UUID(p1["id"]),
                    allocation_percent=60,
                    start_date=date(2020, 1, 1),
                    end_date=date(2100, 1, 1),
                )
            )
        session.commit()

    trans = client.get(
        f"{FC}/transformation", headers=admin_headers, params={"as_of": "2026-01-06"}
    ).json()
    assert trans["scope"] == "transformation"
    assert 0 <= trans["success_score"] <= 100
    assert trans["success_label"] in {"likely", "at_risk", "unlikely", "unknown"}
    assert trans["resource_shortage"]["shortage"] is True
    assert trans["resource_shortage"]["over_allocated"] >= 1


def test_forecast_not_found(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{FC}/projects/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{FC}/programs/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{FC}/portfolios/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_forecast_program_and_zero_spi(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    port = client.post(PORTFOLIOS, headers=admin_headers, json={"name": "Fp", "code": "FPP"}).json()
    prog = client.post(
        PROGRAMS,
        headers=admin_headers,
        json={"name": "Program", "code": "FPG", "portfolio_id": port["id"]},
    ).json()
    proj = _project(client, admin_headers, "FPJ", portfolio_id=port["id"], program_id=prog["id"])
    # Baseline exists but 0% earned → SPI 0 → "insufficient data" schedule basis.
    _configure(
        session_factory,
        proj["id"],
        budget="10000.00",
        progress=0,
        actual="500.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    prog_fc = client.get(
        f"{FC}/programs/{prog['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    ).json()
    assert prog_fc["scope"] == "program" and prog_fc["project_count"] == 1
    proj_fc = client.get(
        f"{FC}/projects/{proj['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    ).json()
    assert proj_fc["schedule"]["basis"] == "insufficient data (no SPI)"
    assert proj_fc["schedule"]["forecast_completion"] is None


# --- Heat map engine -------------------------------------------------------
HM = "/api/v1/intelligence/heatmap"
RISKS = "/api/v1/risks"


def test_portfolio_heatmap(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Heat", "code": "HMP"}
    ).json()
    good = _project(client, admin_headers, "HG1", portfolio_id=port["id"])
    bad = _project(client, admin_headers, "HB1", portfolio_id=port["id"])
    # Good: on schedule, under cost. Bad: behind and over cost.
    _configure(
        session_factory,
        good["id"],
        budget="100000.00",
        progress=50,
        actual="40000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    _configure(
        session_factory,
        bad["id"],
        budget="100000.00",
        progress=25,
        actual="60000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    hm = client.get(
        f"{HM}/portfolios/{port['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    ).json()
    assert hm["columns"] == ["Schedule", "Cost", "Budget", "Overall"]
    assert hm["summary"]["green"] == 1 and hm["summary"]["red"] == 1
    cells = {(c["row_label"], c["column"]): c["rag"] for c in hm["cells"]}
    assert cells[("HG1", "Overall")] == "green"
    assert cells[("HB1", "Overall")] == "red"
    assert cells[("HB1", "Cost")] == "red"

    # Unknown portfolio.
    assert client.get(f"{HM}/portfolios/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_risk_heatmap(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = _project(client, admin_headers, "RHM")
    for prob, impact in ((5, 5), (2, 2)):
        r = client.post(
            RISKS,
            headers=admin_headers,
            json={
                "project_id": proj["id"],
                "title": f"Risk {prob}{impact}",
                "probability": prob,
                "impact": impact,
            },
        )
        assert r.status_code == 201, r.text

    hm = client.get(f"{HM}/risk", headers=admin_headers).json()
    assert hm["scope"] == "risk" and hm["total_open"] >= 2
    by_cell = {(c["probability"], c["impact"]): c for c in hm["cells"]}
    assert by_cell[(5, 5)]["count"] == 1 and by_cell[(5, 5)]["severity"] == "critical"
    assert by_cell[(2, 2)]["count"] == 1 and by_cell[(2, 2)]["severity"] == "low"


def test_resource_and_transformation_heatmap(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = _project(client, admin_headers, "THM")
    res = client.post(
        RESOURCES,
        headers=admin_headers,
        json={
            "name": "Half Person",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    ).json()
    client.post(
        f"{RESOURCES}/{res['id']}/allocations",
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "allocation_percent": 50,
            "start_date": "2020-01-01",
            "end_date": "2100-01-01",
        },
    )
    rhm = client.get(f"{HM}/resources", headers=admin_headers).json()
    assert rhm["columns"] == ["Utilization"] and rhm["summary"]["amber"] >= 1
    mine = next(c for c in rhm["cells"] if c["row_key"] == res["id"])
    assert mine["rag"] == "amber"

    thm = client.get(f"{HM}/transformation", headers=admin_headers).json()
    assert thm["scope"] == "transformation" and len(thm["cells"]) >= 1


# --- Executive KPI engine --------------------------------------------------
KPI = "/api/v1/intelligence/kpi"


def test_executive_kpis(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, "KPX")
    _configure(
        session_factory,
        proj["id"],
        budget="100000.00",
        progress=25,
        actual="60000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    client.post(
        RISKS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "Big risk",
            "probability": 5,
            "impact": 5,
        },
    )

    body = client.get(
        f"{KPI}/executive", headers=admin_headers, params={"as_of": "2026-01-06"}
    ).json()
    assert body["scope"] == "transformation"
    groups = {g["name"]: g for g in body["groups"]}
    assert {"Delivery", "Financials", "Schedule", "Risk & Issues", "Resources"} <= set(groups)
    items = {i["key"]: i for g in body["groups"] for i in g["items"]}
    assert int(items["projects_total"]["value"]) >= 1
    assert int(items["high_risks"]["value"]) >= 1 and items["high_risks"]["rag"] == "red"
    assert items["cpi"]["value"] == "0.42"  # 25000 / 60000


def test_portfolio_kpis(client: TestClient, admin_headers: dict[str, str]) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "KpiPort", "code": "KPP"}
    ).json()
    _project(client, admin_headers, "KPO", portfolio_id=port["id"])
    body = client.get(f"{KPI}/portfolios/{port['id']}", headers=admin_headers).json()
    assert body["scope"] == "portfolio" and body["scope_id"] == port["id"]
    names = {g["name"] for g in body["groups"]}
    assert "Resources" not in names  # portfolio scorecard omits org-wide resources
    assert client.get(f"{KPI}/portfolios/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_heatmap_edge_branches(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    from app.modules.risk.models import Risk, RiskStatus

    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "Edge", "code": "EDG"}
    ).json()
    prog = client.post(
        PROGRAMS,
        headers=admin_headers,
        json={"name": "EdgeProg", "code": "EDP", "portfolio_id": port["id"]},
    ).json()
    amber = _project(client, admin_headers, "AMB", portfolio_id=port["id"], program_id=prog["id"])
    unknown = _project(client, admin_headers, "UNK", portfolio_id=port["id"])
    # Amber budget: ~5% overrun. Unknown budget: zero BAC but some cost.
    _configure(
        session_factory,
        amber["id"],
        budget="100000.00",
        progress=50,
        actual="52500.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    _configure(session_factory, unknown["id"], budget="0.00", progress=50, actual="100.00")

    # program_heatmap path
    phm = client.get(
        f"{HM}/programs/{prog['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    ).json()
    assert phm["scope"] == "program" and len(phm["cells"]) == 4

    hm = client.get(
        f"{HM}/portfolios/{port['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    ).json()
    cells = {(c["row_label"], c["column"]): c["rag"] for c in hm["cells"]}
    assert cells[("AMB", "Budget")] == "amber"
    assert cells[("UNK", "Budget")] == "unknown"

    # Resource: balanced (100%) via API + over-allocated (120%) via session.
    proj = _project(client, admin_headers, "REP")
    org_id = uuid.UUID(proj["organization_id"])
    bal = client.post(
        RESOURCES,
        headers=admin_headers,
        json={
            "name": "Bal Person",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    ).json()
    client.post(
        f"{RESOURCES}/{bal['id']}/allocations",
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "allocation_percent": 100,
            "start_date": "2020-01-01",
            "end_date": "2100-01-01",
        },
    )
    ov = client.post(
        RESOURCES,
        headers=admin_headers,
        json={
            "name": "Ov Person",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    ).json()
    with session_factory() as session:
        for _ in range(2):
            session.add(
                ResourceAllocation(
                    organization_id=org_id,
                    resource_id=uuid.UUID(ov["id"]),
                    project_id=uuid.UUID(proj["id"]),
                    allocation_percent=60,
                    start_date=date(2020, 1, 1),
                    end_date=date(2100, 1, 1),
                )
            )
        session.commit()
    rhm = client.get(f"{HM}/resources", headers=admin_headers).json()
    rags = {c["row_key"]: c["rag"] for c in rhm["cells"]}
    assert rags[bal["id"]] == "green" and rags[ov["id"]] == "red"

    # A closed risk is excluded from the risk matrix.
    rk = client.post(
        RISKS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "Closed risk",
            "probability": 3,
            "impact": 3,
        },
    ).json()
    with session_factory() as session:
        risk = session.get(Risk, uuid.UUID(rk["id"]))
        assert risk is not None
        risk.status = RiskStatus.CLOSED
        session.commit()
    matrix = client.get(f"{HM}/risk", headers=admin_headers).json()
    assert (3, 3) not in {(c["probability"], c["impact"]) for c in matrix["cells"]}


# --- Recommendation engine -------------------------------------------------
REC = "/api/v1/intelligence/recommendations"
TI = "/api/v1/intelligence/transformation"


def _set_rollups(
    factory: sessionmaker[Session],
    project_id: str,
    *,
    risk_score: int,
    issue_count: int,
) -> None:
    with factory() as session:
        p = session.get(Project, uuid.UUID(project_id))
        assert p is not None
        p.risk_score = risk_score
        p.issue_count = issue_count
        session.commit()


def test_project_recommendations(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, "REC")
    # Behind schedule, over cost, big overrun.
    _configure(
        session_factory,
        proj["id"],
        budget="100000.00",
        progress=25,
        actual="60000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    _set_rollups(session_factory, proj["id"], risk_score=20, issue_count=25)

    body = client.get(
        f"{REC}/projects/{proj['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    ).json()
    assert body["scope"] == "project" and body["total"] >= 4
    categories = {r["category"] for r in body["recommendations"]}
    assert {"cost", "schedule", "risk", "issue"} <= categories
    # Highest-priority items come first.
    assert body["recommendations"][0]["priority"] == "high"
    # Every recommendation carries a rationale and an action.
    assert all(r["rationale"] and r["recommended_action"] for r in body["recommendations"])

    assert client.get(f"{REC}/projects/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_not_started_recommendation(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, "NST")
    _configure(
        session_factory,
        proj["id"],
        budget="1000.00",
        progress=0,
        actual="0.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 3, 1),
    )
    body = client.get(
        f"{REC}/projects/{proj['id']}",
        headers=admin_headers,
        params={"as_of": "2026-02-01"},
    ).json()
    assert any(r["category"] == "delivery" for r in body["recommendations"])


def test_transformation_recommendations_include_resources(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, "TRC")
    res = client.post(
        RESOURCES,
        headers=admin_headers,
        json={
            "name": "Busy Person",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    ).json()
    with session_factory() as session:
        for _ in range(2):
            session.add(
                ResourceAllocation(
                    organization_id=uuid.UUID(proj["organization_id"]),
                    resource_id=uuid.UUID(res["id"]),
                    project_id=uuid.UUID(proj["id"]),
                    allocation_percent=60,
                    start_date=date(2020, 1, 1),
                    end_date=date(2100, 1, 1),
                )
            )
        session.commit()
    body = client.get(f"{REC}/transformation", headers=admin_headers).json()
    assert any(r["category"] == "resource" for r in body["recommendations"])
    assert client.get(f"{REC}/portfolios/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_transformation_intelligence(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    proj = _project(client, admin_headers, "TIB")
    _configure(
        session_factory,
        proj["id"],
        budget="100000.00",
        progress=25,
        actual="60000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    _set_rollups(session_factory, proj["id"], risk_score=20, issue_count=5)

    body = client.get(TI, headers=admin_headers, params={"as_of": "2026-01-06"}).json()
    assert body["scope"] == "transformation"
    assert body["projects_total"] >= 1
    assert body["projects_high_risk"] >= 1
    assert 0 <= body["success_score"] <= 100
    assert body["success_label"] in {"likely", "at_risk", "unlikely", "unknown"}
    assert "success" in body["narrative"].lower()
    assert isinstance(body["attention"], list) and len(body["attention"]) <= 5
    assert "green" in body["heat_summary"]


def test_portfolio_recommendations(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "RecPort", "code": "RCP"}
    ).json()
    proj = _project(client, admin_headers, "RCX", portfolio_id=port["id"])
    _configure(
        session_factory,
        proj["id"],
        budget="100000.00",
        progress=25,
        actual="60000.00",
        bstart=date(2026, 1, 1),
        bend=date(2026, 1, 11),
    )
    body = client.get(
        f"{REC}/portfolios/{port['id']}",
        headers=admin_headers,
        params={"as_of": "2026-01-06"},
    ).json()
    assert body["scope"] == "portfolio" and body["scope_id"] == port["id"]
    assert body["total"] >= 1
    assert {"cost", "schedule"} <= {r["category"] for r in body["recommendations"]}


# --- Wired variances: benefits (Phase 2a) + KPI (Phase 2c) -----------------
BENEFITS = "/api/v1/benefits"
INITIATIVES = "/api/v1/initiatives"
GOALS = "/api/v1/goals"
KPIS = "/api/v1/kpis"


def test_benefits_variance(client: TestClient, admin_headers: dict[str, str]) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "BenVar", "code": "BVR"}
    ).json()
    proj = _project(client, admin_headers, "BVP", portfolio_id=port["id"])
    client.post(
        BENEFITS,
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "title": "Cost saving",
            "target_value": "100000.00",
            "realized_value": "40000.00",
        },
    )
    body = client.get(f"{VAR}/benefits/projects/{proj['id']}", headers=admin_headers).json()
    assert body["scope"] == "project" and body["benefit_count"] == 1
    assert body["total_target"] == "100000.00" and body["total_realized"] == "40000.00"
    assert body["variance"] == "-60000.00" and body["realization_percent"] == 40.0
    assert body["favourable"] is False

    port_v = client.get(f"{VAR}/benefits/portfolios/{port['id']}", headers=admin_headers).json()
    assert port_v["benefit_count"] == 1 and port_v["total_realized"] == "40000.00"

    trans_v = client.get(f"{VAR}/benefits/transformation", headers=admin_headers).json()
    assert trans_v["scope"] == "transformation" and trans_v["benefit_count"] >= 1

    assert (
        client.get(f"{VAR}/benefits/projects/{uuid.uuid4()}", headers=admin_headers).status_code
        == 404
    )
    assert (
        client.get(f"{VAR}/benefits/portfolios/{uuid.uuid4()}", headers=admin_headers).status_code
        == 404
    )


def test_kpi_variance(client: TestClient, admin_headers: dict[str, str]) -> None:
    init = client.post(INITIATIVES, headers=admin_headers, json={"name": "KPI init"}).json()
    goal = client.post(
        GOALS,
        headers=admin_headers,
        json={"initiative_id": init["id"], "title": "Grow"},
    ).json()
    # One met, one missed.
    client.post(
        KPIS,
        headers=admin_headers,
        json={
            "goal_id": goal["id"],
            "name": "Met",
            "baseline_value": "0",
            "current_value": "100",
            "target_value": "100",
        },
    )
    client.post(
        KPIS,
        headers=admin_headers,
        json={
            "goal_id": goal["id"],
            "name": "Missed",
            "baseline_value": "0",
            "current_value": "40",
            "target_value": "100",
        },
    )

    by_init = client.get(f"{VAR}/kpis/initiatives/{init['id']}", headers=admin_headers).json()
    assert by_init["scope"] == "initiative" and by_init["kpi_count"] == 2
    assert by_init["kpis_on_target"] == 1 and by_init["kpis_off_target"] == 1
    assert by_init["average_attainment"] == 70.0  # (100 + 40) / 2
    missed = next(i for i in by_init["items"] if i["name"] == "Missed")
    assert float(missed["variance"]) == -60.0 and missed["on_target"] is False

    trans = client.get(f"{VAR}/kpis/transformation", headers=admin_headers).json()
    assert trans["scope"] == "transformation" and trans["kpi_count"] >= 2

    assert (
        client.get(f"{VAR}/kpis/initiatives/{uuid.uuid4()}", headers=admin_headers).status_code
        == 404
    )


def test_kpi_variance_portfolio(client: TestClient, admin_headers: dict[str, str]) -> None:
    port = client.post(
        PORTFOLIOS, headers=admin_headers, json={"name": "KPIVarPort", "code": "KVP"}
    ).json()
    init = client.post(
        INITIATIVES,
        headers=admin_headers,
        json={"name": "Portfolio initiative", "portfolio_id": port["id"]},
    ).json()
    goal = client.post(
        GOALS,
        headers=admin_headers,
        json={"initiative_id": init["id"], "title": "Grow"},
    ).json()
    client.post(
        KPIS,
        headers=admin_headers,
        json={
            "goal_id": goal["id"],
            "name": "Met",
            "baseline_value": "0",
            "current_value": "100",
            "target_value": "100",
        },
    )
    client.post(
        KPIS,
        headers=admin_headers,
        json={
            "goal_id": goal["id"],
            "name": "Missed",
            "baseline_value": "0",
            "current_value": "40",
            "target_value": "100",
        },
    )

    body = client.get(f"{VAR}/kpis/portfolios/{port['id']}", headers=admin_headers).json()
    assert body["scope"] == "portfolio" and body["scope_label"] == "KPIVarPort"
    assert body["kpi_count"] == 2 and body["kpis_on_target"] == 1 and body["kpis_off_target"] == 1
    assert body["average_attainment"] == 70.0
    assert (
        client.get(f"{VAR}/kpis/portfolios/{uuid.uuid4()}", headers=admin_headers).status_code
        == 404
    )


def test_board_pack_exports(client: TestClient, admin_headers: dict[str, str]) -> None:
    from io import BytesIO

    from openpyxl import load_workbook

    _project(client, admin_headers, "EXP", budget="100000.00")
    x = client.get("/api/v1/intelligence/exports/board-pack.xlsx", headers=admin_headers)
    assert x.status_code == 200
    assert "spreadsheetml" in x.headers["content-type"]
    wb = load_workbook(BytesIO(x.content))
    assert {
        "Executive Summary",
        "Projects",
        "Benefits",
        "KPIs",
        "Recommendations",
    } <= set(wb.sheetnames)

    p = client.get("/api/v1/intelligence/exports/board-pack.pdf", headers=admin_headers)
    assert p.status_code == 200
    assert p.headers["content-type"] == "application/pdf"
    assert p.content[:5] == b"%PDF-"


def test_resource_demand_forecast(client: TestClient, admin_headers: dict[str, str]) -> None:
    from datetime import date, timedelta

    proj = client.post(
        "/api/v1/projects",
        headers=admin_headers,
        json={"name": "RDF Proj", "code": "RDF"},
    ).json()
    res = client.post(
        "/api/v1/resources",
        headers=admin_headers,
        json={
            "name": "Ada Eng",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    ).json()
    today = date.today()
    r = client.post(
        f"/api/v1/resources/{res['id']}/allocations",
        headers=admin_headers,
        json={
            "project_id": proj["id"],
            "start_date": str(today),
            "end_date": str(today + timedelta(days=6)),
            "allocation_percent": 60,
        },
    )
    assert r.status_code == 201, r.text

    body = client.get(
        "/api/v1/intelligence/resource-forecast?weeks=4", headers=admin_headers
    ).json()
    assert len(body["periods"]) == 4 and body["period_days"] == 7
    row = next(x for x in body["resources"] if x["resource_id"] == res["id"])
    assert row["demand"][0] == 60  # week 0 overlaps the allocation
    assert row["demand"][3] == 0  # later weeks are clear
    assert row["peak_demand"] == 60
    assert body["summary"][0]["total_demand_percent"] >= 60


def test_early_warning_flags_burn_ahead(client: TestClient, admin_headers: dict[str, str]) -> None:
    proj = client.post(
        "/api/v1/projects",
        headers=admin_headers,
        json={"name": "EW Proj", "code": "EWX", "budget": "100000.00"},
    ).json()
    client.patch(
        f"/api/v1/projects/{proj['id']}",
        headers=admin_headers,
        json={"actual_cost": "60000.00", "progress_percent": 30, "status": "active"},
    )
    one = client.get(
        f"/api/v1/intelligence/early-warning/projects/{proj['id']}",
        headers=admin_headers,
    ).json()
    assert one["level"] == "warning"
    assert any(s["type"] == "burn_ahead" for s in one["signals"])
    # It also appears in the transformation report.
    rep = client.get("/api/v1/intelligence/early-warning", headers=admin_headers).json()
    assert rep["projects_warning"] >= 1
    assert any(i["code"] == "EWX" for i in rep["items"])


def test_early_warning_healthy_project_clear(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    proj = client.post(
        "/api/v1/projects",
        headers=admin_headers,
        json={"name": "Healthy", "code": "HLY", "budget": "100000.00"},
    ).json()
    client.patch(
        f"/api/v1/projects/{proj['id']}",
        headers=admin_headers,
        json={"actual_cost": "10000.00", "progress_percent": 20, "status": "active"},
    )
    one = client.get(
        f"/api/v1/intelligence/early-warning/projects/{proj['id']}",
        headers=admin_headers,
    ).json()
    assert one["level"] == "clear" and one["signals"] == []
