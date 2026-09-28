#!/usr/bin/env python3
"""Seed a compelling demo dataset into a running ETIP instance.

Run the API first (``uvicorn app.main:app --port 8000``), then::

    python scripts/seed_demo.py

It registers a demo organisation, logs in, and creates portfolios, programs,
projects tuned to green / amber / red health, benefits, an initiative with goals
and KPIs, and a vendor with a contract and purchase order — so the Intelligence
Layer endpoints immediately return a meaningful story.

Uses only the Python standard library; override the target with BASE_URL, e.g.::

    BASE_URL=http://localhost:8000 python scripts/seed_demo.py
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/") + "/api/v1"
ORG = "Demo Transformation Co"
EMAIL = "admin@demo.co"
PASSWORD = "Str0ng-Passphrase!1"

_token: str | None = None


def call(method: str, path: str, body: dict | None = None) -> dict:
    """Make a JSON request; raise with the server message on failure."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if _token:
        req.add_header("Authorization", f"Bearer {_token}")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:  # noqa: BLE001
        detail = exc.read().decode()
        raise SystemExit(f"{method} {path} -> {exc.code}: {detail}") from exc


def login_as(slug: str, email: str, password: str) -> None:
    """Swap the active bearer token to a different user (for approval demos)."""
    global _token
    tokens = call(
        "POST",
        "/auth/login",
        {"organization_slug": slug, "email": email, "password": password},
    )
    _token = tokens["access_token"]


def main() -> None:
    global _token
    today = date.today()

    # 1) Organisation + admin (ignore "already exists" so re-runs are friendly).
    try:
        call(
            "POST",
            "/auth/register",
            {
                "organization_name": ORG,
                "admin_email": EMAIL,
                "admin_full_name": "Demo Admin",
                "password": PASSWORD,
            },
        )
        print(f"Registered organisation: {ORG}")
    except SystemExit as exc:
        if "409" not in str(exc):
            raise
        print("Organisation already exists — continuing.")

    slug = ORG.lower().replace(" ", "-")
    tokens = call(
        "POST",
        "/auth/login",
        {
            "organization_slug": slug,
            "email": EMAIL,
            "password": PASSWORD,
        },
    )
    _token = tokens["access_token"]
    print("Logged in.")

    # 2) Portfolio + program.
    pf = call("POST", "/portfolios", {"name": "Digital Transformation", "code": "DTX"})
    pg = call(
        "POST",
        "/programs",
        {
            "name": "Core Platform",
            "code": "CORE",
            "portfolio_id": pf["id"],
        },
    )

    # 3) Projects tuned to distinct health signals.
    def make_project(
        code: str,
        name: str,
        budget: str,
        actual: str,
        progress: int,
        start_off: int,
        end_off: int,
    ) -> dict:
        project = call(
            "POST",
            "/projects",
            {
                "name": name,
                "code": code,
                "portfolio_id": pf["id"],
                "program_id": pg["id"],
                "budget": budget,
                "baseline_start_date": str(today - timedelta(days=start_off)),
                "baseline_end_date": str(today + timedelta(days=end_off)),
            },
        )
        # actual_cost and progress are set post-creation (update-only fields).
        return call(
            "PATCH",
            f"/projects/{project['id']}",
            {
                "actual_cost": actual,
                "progress_percent": progress,
            },
        )

    green = make_project("ATLAS", "Atlas Platform", "200000.00", "70000.00", 78, 120, 40)
    amber = make_project("BEACON", "Beacon Rollout", "150000.00", "95000.00", 52, 120, 30)
    red = make_project("CIRRUS", "Cirrus Migration", "100000.00", "78000.00", 22, 150, 20)
    print("Created 3 projects (green / amber / red).")

    # 4) Benefits with realistic realisation / ROI.
    call(
        "POST",
        "/benefits",
        {
            "project_id": green["id"],
            "title": "Support cost reduction",
            "category": "financial",
            "target_value": "120000.00",
            "realized_value": "90000.00",
            "investment_cost": "40000.00",
        },
    )
    call(
        "POST",
        "/benefits",
        {
            "project_id": amber["id"],
            "title": "Cycle-time improvement",
            "category": "operational",
            "target_value": "80000.00",
            "realized_value": "30000.00",
            "investment_cost": "25000.00",
        },
    )
    call(
        "POST",
        "/benefits",
        {
            "project_id": red["id"],
            "title": "Revenue uplift",
            "category": "strategic",
            "target_value": "150000.00",
            "realized_value": "20000.00",
            "investment_cost": "60000.00",
        },
    )
    print("Created benefits.")

    # 4b) A second portfolio so the dashboard's portfolio selector is meaningful.
    pf2 = call("POST", "/portfolios", {"name": "Customer Experience", "code": "CXP"})
    cx = call(
        "POST",
        "/projects",
        {
            "name": "Helix Portal",
            "code": "HELIX",
            "portfolio_id": pf2["id"],
            "budget": "80000.00",
            "baseline_start_date": str(today - timedelta(days=90)),
            "baseline_end_date": str(today + timedelta(days=60)),
        },
    )
    call(
        "PATCH",
        f"/projects/{cx['id']}",
        {"actual_cost": "30000.00", "progress_percent": 60},
    )
    call(
        "POST",
        "/benefits",
        {
            "project_id": cx["id"],
            "title": "NPS uplift",
            "category": "customer",
            "target_value": "50000.00",
            "realized_value": "25000.00",
            "investment_cost": "15000.00",
        },
    )
    print("Created a second portfolio (Customer Experience).")

    # 7b) Resources + allocations so resource variance, skills capacity and the
    #     resource demand forecast have data to work with.
    r1 = call(
        "POST",
        "/resources",
        {
            "name": "Ada Engineer",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    )
    r2 = call(
        "POST",
        "/resources",
        {
            "name": "Ben Analyst",
            "resource_type": "employee",
            "capacity_hours_per_week": "40.00",
        },
    )
    call(
        "POST",
        f"/resources/{r1['id']}/allocations",
        {
            "project_id": green["id"],
            "start_date": str(today - timedelta(days=7)),
            "end_date": str(today + timedelta(days=35)),
            "allocation_percent": 60,
            "role_label": "Backend Lead",
        },
    )
    call(
        "POST",
        f"/resources/{r2['id']}/allocations",
        {
            "project_id": red["id"],
            "start_date": str(today),
            "end_date": str(today + timedelta(days=21)),
            "allocation_percent": 50,
            "role_label": "Analyst",
        },
    )
    print("Created resources and allocations.")

    # 8) A read-only "Executive Viewer" persona to demo role-based dashboard views.
    try:
        viewer_role = call(
            "POST",
            "/roles",
            {
                "name": "Executive Viewer",
                "description": "Read-only executive access (intelligence only).",
                "permissions": ["intelligence:read"],
            },
        )
        call(
            "POST",
            "/users",
            {
                "email": "viewer@demo.co",
                "full_name": "Val Viewer",
                "password": PASSWORD,
                "role_ids": [viewer_role["id"]],
            },
        )
        print("Created read-only Viewer persona (viewer@demo.co).")
    except SystemExit as exc:
        if "409" not in str(exc):
            raise

    # 9) A demo webhook + one delivery so the Integration Hub tab has data.
    try:
        hook = call(
            "POST",
            "/integrations/webhooks",
            {
                "name": "Ops Slack",
                "target_url": "https://hooks.example.com/etip-demo",
                "secret": "demo-signing-secret",
                "event_types": ["risk.raised", "benefit.realized"],
            },
        )
        call("POST", f"/integrations/webhooks/{hook['id']}/test")
        print("Created a demo webhook (Ops Slack) with a test delivery.")
    except SystemExit as exc:
        if "409" not in str(exc):
            raise

    # 5) Strategic initiative -> goals -> KPIs.
    init = call(
        "POST",
        "/initiatives",
        {
            "name": "Customer-first transformation",
            "status": "active",
            "priority": "high",
            "portfolio_id": pf["id"],
        },
    )
    goal = call(
        "POST",
        "/goals",
        {
            "initiative_id": init["id"],
            "title": "Improve customer satisfaction",
            "category": "customer",
        },
    )
    call(
        "POST",
        "/kpis",
        {
            "goal_id": goal["id"],
            "name": "NPS",
            "unit": "pts",
            "direction": "increase",
            "baseline_value": "20",
            "current_value": "38",
            "target_value": "50",
        },
    )
    call(
        "POST",
        "/kpis",
        {
            "goal_id": goal["id"],
            "name": "Support cost per ticket",
            "unit": "USD",
            "direction": "decrease",
            "baseline_value": "18",
            "current_value": "14",
            "target_value": "10",
        },
    )
    print("Created initiative, goal and KPIs.")

    # 6) Vendor -> contract -> purchase order.
    vendor = call(
        "POST",
        "/vendors",
        {
            "name": "Northwind Consulting",
            "code": "NWC",
            "category": "prof_services",
        },
    )
    contract = call(
        "POST",
        "/contracts",
        {
            "vendor_id": vendor["id"],
            "title": "Delivery partner MSA",
            "project_id": red["id"],
            "contract_type": "time_and_materials",
            "value": "250000.00",
        },
    )
    po = call(
        "POST",
        "/purchase-orders",
        {
            "vendor_id": vendor["id"],
            "contract_id": contract["id"],
            "project_id": red["id"],
            "reference": "PO-1001",
            "committed_amount": "180000.00",
        },
    )
    call("POST", f"/purchase-orders/{po['id']}/invoice", {"invoiced_amount": "95000.00"})
    print("Created vendor, contract and purchase order.")

    # 7) Metric history so the dashboard sparklines show a real trend.
    result = call("POST", "/intelligence/metrics/backfill-demo?days=12")
    print(f"Captured {result.get('captured', 0)} metric snapshots (12-day trend).")

    # 7b) SDLC stage-gate governance: put every project under the canonical
    #     six-gate SDLC workflow and record realistic approvals so the
    #     Governance tab shows projects at different phases — including gates
    #     awaiting sign-off and one rejected gate.
    definition = call("POST", "/workflows/setup-sdlc")
    stages = call("GET", f"/workflows/{definition['id']}/stages")
    print(f"SDLC stage-gate workflow ready ({len(stages)} gates).")

    # A PMO initiator starts the workflows; the admin approves them — so the
    # engine's separation-of-duties rule (approver != initiator) is satisfied.
    try:
        pmo_role = call(
            "POST",
            "/roles",
            {
                "name": "PMO Lead",
                "description": "Runs governance workflows (initiator).",
                "permissions": [
                    "workflow:manage",
                    "workflow:read",
                    "project:read",
                    "milestone:read",
                    "milestone:update",
                ],
            },
        )
        call(
            "POST",
            "/users",
            {
                "email": "pmo@demo.co",
                "full_name": "Priya PMO",
                "password": PASSWORD,
                "role_ids": [pmo_role["id"]],
            },
        )
        print("Created PMO initiator persona (pmo@demo.co).")
    except SystemExit as exc:
        if "409" not in str(exc):
            raise

    # proj  → (gates to approve, then reject the next gate?)
    plan = [
        (green, 4, False),  # ATLAS — advanced, pending at UAT
        (amber, 2, False),  # BEACON — pending at Development
        (cx, 3, False),  # HELIX — pending at QA
        (red, 1, True),  # CIRRUS — approved 1, then rejected at Design review
    ]
    for project, approvals, reject_next in plan:
        login_as(slug, "pmo@demo.co", PASSWORD)  # initiator
        instance = call(
            "POST",
            "/workflows/instances",
            {
                "definition_id": definition["id"],
                "entity_type": "Project",
                "entity_id": project["id"],
            },
        )
        login_as(slug, EMAIL, PASSWORD)  # approver (admin)
        for _ in range(approvals):
            call(
                "POST",
                f"/workflows/instances/{instance['id']}/decision",
                {"decision": "approved", "comment": "Gate criteria met — approved."},
            )
        if reject_next:
            call(
                "POST",
                f"/workflows/instances/{instance['id']}/decision",
                {
                    "decision": "rejected",
                    "comment": "Design does not meet NFRs — sent back for rework.",
                },
            )
    print("Recorded SDLC gate approvals across projects (incl. 1 rejection).")

    # 7c) Financial (billing) milestones linked to deliverables, gated by a
    #     deliverable-acceptance workflow that releases the payment on sign-off.
    #     PMO submits each deliverable (initiator); the admin accepts the gate(s)
    #     and releases the payment — so separation of duties holds throughout.
    def make_fin_milestone(
        project: dict, name: str, deliverable: str, amount: str, days_out: int
    ) -> dict:
        return call(
            "POST",
            "/milestones",
            {
                "project_id": project["id"],
                "name": name,
                "milestone_type": "deliverable",
                "deliverable": deliverable,
                "payment_amount": amount,
                "currency": "USD",
                "target_date": str(today + timedelta(days=days_out)),
                "is_key": True,
            },
        )

    # (project, name, deliverable, amount, days_out, gates_to_approve, reject?, release?)
    fin_plan = [
        (
            green,
            "Phase 1 delivery",
            "Design pack + working beta, signed off",
            "60000.00",
            20,
            2,
            False,
            True,
        ),
        (
            amber,
            "UAT completion",
            "UAT sign-off report accepted by business",
            "40000.00",
            35,
            1,
            False,
            False,
        ),
        (
            cx,
            "Go-live cutover",
            "Production cutover runbook executed",
            "30000.00",
            25,
            0,
            False,
            False,
        ),
        (
            red,
            "Data migration",
            "Validated migrated dataset reconciliation",
            "25000.00",
            15,
            0,
            True,
            False,
        ),
    ]
    for (
        project,
        name,
        deliverable,
        amount,
        days_out,
        approvals,
        reject,
        release,
    ) in fin_plan:
        ms = make_fin_milestone(project, name, deliverable, amount, days_out)
        # PMO submits the deliverable for acceptance (becomes the initiator).
        login_as(slug, "pmo@demo.co", PASSWORD)
        ms = call("POST", f"/milestones/{ms['id']}/submit-for-acceptance")
        # Admin accepts the gate(s) / rejects, then releases payment where due.
        login_as(slug, EMAIL, PASSWORD)
        inst = ms["acceptance_instance_id"]
        for _ in range(approvals):
            call(
                "POST",
                f"/workflows/instances/{inst}/decision",
                {
                    "decision": "approved",
                    "comment": "Deliverable meets acceptance criteria.",
                },
            )
        if reject:
            call(
                "POST",
                f"/workflows/instances/{inst}/decision",
                {
                    "decision": "rejected",
                    "comment": "Reconciliation gaps — returned for rework.",
                },
            )
        if release:
            call("POST", f"/milestones/{ms['id']}/release-payment")
    # One more that is created but not yet submitted (draft billing milestone).
    make_fin_milestone(green, "Phase 2 delivery", "Scaled rollout to all regions", "50000.00", 60)
    print("Created financial milestones with deliverable acceptance (released/pending/rejected).")

    # 7d) Per-project KPIs so each project can be managed with its own scorecard.
    def kpi(
        project: dict,
        name: str,
        unit: str,
        direction: str,
        baseline: str,
        current: str,
        target: str,
    ) -> None:
        call(
            "POST",
            f"/projects/{project['id']}/kpis",
            {
                "name": name,
                "unit": unit,
                "direction": direction,
                "baseline_value": baseline,
                "current_value": current,
                "target_value": target,
            },
        )

    kpi(green, "Automated test coverage", "%", "increase", "40", "82", "85")
    kpi(green, "Mean time to restore", "min", "decrease", "120", "45", "30")
    kpi(green, "Adoption rate", "%", "increase", "0", "68", "80")
    kpi(amber, "Defect escape rate", "per release", "decrease", "12", "7", "3")
    kpi(amber, "Cycle time", "days", "decrease", "18", "13", "8")
    kpi(red, "Data quality score", "%", "increase", "55", "61", "95")
    kpi(red, "Migration completeness", "%", "increase", "0", "22", "100")
    kpi(cx, "CSAT", "score", "increase", "3.2", "4.1", "4.5")
    kpi(cx, "Page load time", "ms", "decrease", "2400", "1300", "900")
    print("Created per-project KPIs (scorecards).")

    # 8) Summary + what to open.
    print("\n" + "=" * 60)
    print("Demo data ready. Sign in with:")
    print(f"  organization_slug: {slug}")
    print(f"  email:             {EMAIL}")
    print(f"  password:          {PASSWORD}")
    print(f"  read-only viewer:  viewer@demo.co / {PASSWORD}  (role-based view demo)")
    print("\nTry these (Swagger at /docs, or curl with a bearer token):")
    print("  GET /api/v1/workflows/governance   (SDLC stage-gate approvals)")
    print("  GET /api/v1/milestones/financial   (financial milestones + deliverable acceptance)")
    print(f"  GET /api/v1/projects/{green['id']}/kpis   (per-project KPI scorecard)")
    print("  GET /api/v1/intelligence/transformation")
    print("  GET /api/v1/intelligence/recommendations/transformation")
    print(f"  GET /api/v1/intelligence/performance/projects/{red['id']}")
    print(f"  GET /api/v1/intelligence/variance/benefits/portfolios/{pf['id']}")
    print(f"  GET /api/v1/intelligence/variance/kpis/initiatives/{init['id']}")
    print(f"  GET /api/v1/vendors/{vendor['id']}/spend")
    print("=" * 60)


if __name__ == "__main__":
    main()
