# Intelligence Layer — Performance (EVM) — Examples

**ETIP 2.0 · Phase 1a.** `BASE = http://localhost:8000/api/v1`. All requests
require `Authorization: Bearer <access_token>` and the `intelligence:read`
permission. Every response is a **fresh, live snapshot** — nothing is
precomputed, and no data is modified (pure read).

The Performance Engine computes **Earned Value Management (EVM)** for a project
and aggregates it into program / portfolio / transformation rollups, entirely
from data that already exists in V1 (no schema change):

- **BAC** (Budget at Completion) = `project.budget`
- **EV** (Earned Value) = `progress_percent` × BAC
- **AC** (Actual Cost) = `project.actual_cost` (synced from Finance)
- **PV** (Planned Value) = planned schedule % (from baseline dates, at `as_of`) × BAC

Derived: **SV** = EV−PV · **CV** = EV−AC · **SPI** = EV/PV · **CPI** = EV/AC ·
**EAC** = BAC/CPI · **ETC** = EAC−AC · **VAC** = BAC−EAC · **TCPI**.

---

## Project performance

`GET /intelligence/performance/projects/{project_id}?as_of=2026-06-30`
(`as_of` optional, defaults to today; drives Planned Value.) → **200**
```json
{
  "scope": "project",
  "project_id": "…", "code": "ATLAS", "name": "Atlas migration",
  "as_of": "2026-06-30",
  "evm": {
    "bac": "100000.00", "pv": "50000.00", "ev": "50000.00", "ac": "60000.00",
    "sv": "0.00", "cv": "-10000.00", "spi": 1.0, "cpi": 0.833,
    "eac": "120000.00", "etc": "60000.00", "vac": "-20000.00", "tcpi": 1.25,
    "planned_percent": 0.5, "actual_percent": 0.5
  },
  "effort": { "estimate_hours": "320.00", "logged_hours": "290.00", "effort_burn_ratio": 0.906 },
  "health": { "rag": "red", "drivers": ["SPI 1.00 (on track)", "CPI 0.83 (off track)"] },
  "risk_score": 12, "issue_count": 3
}
```

**Health (RAG)** is driven by the worst available index: `green` ≥ 0.95,
`amber` ≥ 0.85, else `red`. Special states: `not_started` (no cost or progress)
and `unknown` (no baseline schedule and no actual cost). Money values are
fixed-2-decimal strings; indices are floats, or `null` when a divisor is 0
(e.g. `spi` is `null` with no baseline schedule).

## Rollups (aggregated EVM)

Rollups sum BAC/EV/AC (and PV where a baseline exists) across the child
projects, then recompute indices and health at the aggregate level, with a
per-project breakdown.

- `GET /intelligence/performance/programs/{program_id}` — a program's projects.
- `GET /intelligence/performance/portfolios/{portfolio_id}` — a portfolio's projects.
- `GET /intelligence/performance/transformation` — every project in the org.

```json
{
  "scope": "portfolio", "scope_id": "…", "scope_label": "Growth", "as_of": "2026-06-30",
  "project_count": 2,
  "evm": { "bac": "300000.00", "ev": "100000.00", "ac": "100000.00", "cpi": 1.0, … },
  "health": { "rag": "green", "drivers": ["SPI 1.00 (on track)", "CPI 1.00 (on track)"] },
  "breakdown": [
    { "project_id": "…", "code": "PR1", "rag": "amber", "spi": 0.9,  "cpi": 1.25 },
    { "project_id": "…", "code": "PR2", "rag": "green", "spi": 1.0,  "cpi": 0.83 }
  ]
}
```

Unknown project/program/portfolio → **404**.

## Notes

- The engine is **service-independent** (it reads repositories only, like the
  report engine) — the Intelligence Layer stays decoupled from the Project
  module and the architecture acyclic.
- `intelligence:read` is granted to Organization Admin, Project Manager, and
  Member (read-only analytics, consistent with `report:read`).

---

# Variance Engine (Phase 1b)

Derives variances from the same EVM primitives plus project budget/forecast and
resource capacity/allocation. Pure read; `intelligence:read`; optional `as_of`.

Per project, four measures — each `{ label, amount, percent, favourable }`:

- **schedule** — SV = EV − PV (`amount`/`percent` are `null` with no baseline)
- **cost** — CV = EV − AC
- **budget** — `budget` − `forecast`
- **forecast** — `forecast` − EAC (manual forecast vs EVM estimate)

`favourable` is `true` when the amount is ≥ 0 (ahead / under / covered).

`GET /intelligence/variance/projects/{project_id}` → **200**
```json
{
  "scope": "project", "code": "ATLAS", "as_of": "2026-06-30",
  "schedule": { "label": "Schedule variance (SV = EV - PV)", "amount": "0.00", "percent": 0.0, "favourable": true },
  "cost":     { "label": "Cost variance (CV = EV - AC)",     "amount": "-10000.00", "percent": -20.0, "favourable": false },
  "budget":   { "label": "Budget variance (budget - forecast)", "amount": "-10000.00", "percent": -10.0, "favourable": false },
  "forecast": { "label": "Forecast variance (forecast - EAC)",  "amount": "-10000.00", "percent": -9.09, "favourable": false }
}
```

**Rollups** aggregate the amounts across child projects (with a per-project
breakdown) and recompute percentages from the totals:

- `GET /intelligence/variance/programs/{program_id}`
- `GET /intelligence/variance/portfolios/{portfolio_id}`
- `GET /intelligence/variance/departments/{department_id}` (projects whose `department_id` matches)
- `GET /intelligence/variance/transformation` (organization-wide)

**Resource capacity variance** — allocation vs 100% for active resources, as of a date:

`GET /intelligence/variance/resources` → **200**
```json
{
  "scope": "resource", "as_of": "2026-06-30",
  "resource_count": 12, "over_allocated": 2, "under_utilized": 7, "balanced": 3,
  "items": [
    { "resource_id": "…", "name": "Ada", "capacity_percent": 100, "allocated_percent": 120, "variance_percent": -20, "status": "over_allocated" }
  ]
}
```

Unknown project/program/portfolio/department → **404**.

## Now wired (previously deferred)

**Benefits variance** and **KPI-vs-target variance** — deferred here in Phase 1b
pending their data sources — are now live, reading the Phase 2a `benefits` and
Phase 2c `goal_kpis` tables. See the "Wired variances" section at the end of this
document for the endpoints and payloads.

---

# Forecast Engine (Phase 1c)

Projects outcomes from the EVM trajectory. Pure read; `intelligence:read`;
optional `as_of`.

`GET /intelligence/forecast/projects/{project_id}` → **200**
```json
{
  "scope": "project", "code": "ATLAS", "as_of": "2026-01-06",
  "schedule": {
    "baseline_end": "2026-01-11", "forecast_completion": "2026-01-21",
    "slippage_days": 10, "will_slip": true, "basis": "SPI 0.50"
  },
  "budget": {
    "bac": "100000.00", "forecast_cost": "160000.00",
    "overrun_amount": "60000.00", "overrun_percent": 60.0, "will_overrun": true
  }
}
```
- **Schedule** — forecast completion = baseline_start + (baseline_days / SPI);
  `slippage_days` vs baseline end. `basis` is `SPI x.xx`, or `completed`,
  `no baseline schedule`, `insufficient data (no SPI)` when it can't be computed.
- **Budget** — `forecast_cost` = EAC (BAC / CPI); `overrun_amount` = EAC − BAC.

**Rollups** (`/forecast/programs|portfolios/{id}`) sum EAC and BAC, count
`projects_overrunning` / `projects_slipping`, report `worst_slippage_days`, and
list a per-project breakdown.

**Transformation** (`/forecast/transformation`) adds a heuristic success outlook
and a resource-shortage signal:
```json
{
  "scope": "transformation", "as_of": "2026-01-06", "project_count": 12,
  "forecast_cost": "…", "budget_overrun": "…",
  "projects_overrunning": 3, "projects_slipping": 5, "worst_slippage_days": 22,
  "success_score": 63, "success_label": "at_risk",
  "resource_shortage": { "over_allocated": 2, "total_excess_percent": 40, "shortage": true }
}
```
`success_score` (0–100) is a documented heuristic — 0.35·SPI + 0.35·CPI +
0.30·(green-project ratio), normalised — labelled `likely` (≥70), `at_risk`
(≥40) or `unlikely`.

Unknown project/program/portfolio → **404**.

## Deferred (honest note)

The charter also lists **critical-path delays** and **customer escalation**.
Neither is produced: a credible critical-path forecast needs proper CPM
scheduling data, and customer escalation has no signal source in the platform
yet. The engine does not fabricate predictions it cannot ground.

---

# Heat Map Engine (Phase 1d)

RAG heat maps for at-a-glance hot-spot detection. Pure read; `intelligence:read`;
optional `as_of`.

**Dimensional grids** — each project scored across Schedule, Cost, Budget, Overall:

`GET /intelligence/heatmap/portfolios/{portfolio_id}`
(also `/heatmap/programs/{program_id}` and `/heatmap/transformation`) → **200**
```json
{
  "scope": "portfolio", "scope_label": "Growth", "as_of": "2026-06-30",
  "columns": ["Schedule", "Cost", "Budget", "Overall"],
  "summary": { "green": 4, "amber": 2, "red": 1, "not_started": 0, "unknown": 0 },
  "cells": [
    { "row_key": "…", "row_label": "ATLAS", "column": "Schedule", "rag": "green", "detail": "SPI 1.02" },
    { "row_key": "…", "row_label": "ATLAS", "column": "Cost", "rag": "amber", "detail": "CPI 0.88" }
  ]
}
```
Cell RAG uses the shared thresholds (green ≥ 0.95, amber ≥ 0.85). Budget RAG bands
the projected overrun: ≤ 0 green, ≤ 10% amber, else red.

**Risk matrix** — the classic probability × impact grid of open-risk counts:

`GET /intelligence/heatmap/risk` → **200**
```json
{
  "scope": "risk", "as_of": "2026-06-30", "max_probability": 5, "max_impact": 5,
  "total_open": 18,
  "cells": [
    { "probability": 2, "impact": 2, "count": 4, "severity": "low" },
    { "probability": 5, "impact": 5, "count": 1, "severity": "critical" }
  ]
}
```

**Resource utilisation** — each active resource by allocation (over → red,
under → amber, balanced → green): `GET /intelligence/heatmap/resources`.

Unknown portfolio/program → **404**.

---

# Executive KPI Engine (Phase 1d)

An executive scorecard composed from the Performance, Forecast and Variance
engines plus open-risk / open-issue / overdue-milestone counts. Pure read;
`intelligence:read`; optional `as_of`.

`GET /intelligence/kpi/executive` (and `/kpi/portfolios/{portfolio_id}`) → **200**
```json
{
  "scope": "transformation", "scope_label": "Transformation", "as_of": "2026-06-30",
  "groups": [
    { "name": "Delivery", "items": [
      { "key": "projects_total", "label": "Projects", "value": "17" },
      { "key": "projects_red", "label": "Red projects", "value": "3", "rag": "red" },
      { "key": "success_outlook", "label": "Transformation success", "value": "at_risk", "unit": "63/100", "rag": "amber" }
    ]},
    { "name": "Financials", "items": [
      { "key": "cpi", "label": "CPI", "value": "0.88", "rag": "amber" },
      { "key": "budget_overrun", "label": "Budget overrun", "value": "40000.00", "unit": "currency", "rag": "red" }
    ]},
    { "name": "Schedule", "items": [ { "key": "projects_slipping", "label": "Projects slipping", "value": "5", "rag": "red" } ] },
    { "name": "Risk & Issues", "items": [ { "key": "high_risks", "label": "High/critical risks", "value": "2", "rag": "red" } ] },
    { "name": "Resources", "items": [ { "key": "over_allocated", "label": "Over-allocated resources", "value": "2", "rag": "red" } ] }
  ]
}
```
The portfolio scorecard omits the org-wide **Resources** group and is scoped to
that portfolio's projects; an unknown portfolio → **404**.

## Deferred (honest note)

**KPI variance against explicit targets** is not produced: no KPI-target model
exists yet (it arrives with Business Goals, roadmap Phase 2c). KPIs here are
RAG-rated against sensible performance thresholds, never against invented
targets. This is also the honest home for the "KPI Variance" deferred in Phase 1b.

---

# Recommendation Engine (Phase 1e)

Turns the analytics into prioritised, auditable recommendations via transparent
rules (no black box) — every item carries its rationale and a suggested action.
Pure read; `intelligence:read`; optional `as_of`.

`GET /intelligence/recommendations/projects/{project_id}`
(also `/recommendations/portfolios/{portfolio_id}` and `/recommendations/transformation`)
→ **200**
```json
{
  "scope": "project", "scope_label": "Atlas migration", "as_of": "2026-01-06",
  "total": 4,
  "recommendations": [
    {
      "subject_type": "project", "subject_label": "ATLAS",
      "category": "cost", "priority": "high",
      "title": "Cost performance below plan",
      "rationale": "CPI is 0.42 (< 0.95).",
      "recommended_action": "Review the cost baseline and EAC; identify overspend drivers."
    },
    {
      "subject_type": "project", "subject_label": "ATLAS",
      "category": "schedule", "priority": "high",
      "title": "Schedule performance below plan",
      "rationale": "SPI is 0.50 (< 0.95).",
      "recommended_action": "Build a recovery plan; re-sequence or add capacity to the critical work."
    }
  ]
}
```
Rules cover cost (CPI), schedule (SPI), projected budget overrun, risk exposure
(risk_score band), open-issue volume, and not-started-past-baseline; the
transformation scope adds a resource-rebalancing rule. Results are sorted
high → low priority. Unknown project/portfolio → **404**.

---

# Transformation Intelligence Engine (Phase 1e)

A single consolidated executive briefing composing the Performance, Forecast,
Heat Map and Recommendation engines with the project risk/issue rollups. The
`narrative` is a deterministic template over the numbers (not an LLM), so the
briefing is reproducible. Pure read; `intelligence:read`; optional `as_of`.

`GET /intelligence/transformation` → **200**
```json
{
  "scope": "transformation", "as_of": "2026-01-06",
  "health": { "rag": "red", "drivers": ["SPI 0.50 (off track)", "CPI 0.42 (off track)"] },
  "spi": 0.5, "cpi": 0.42,
  "success_score": 38, "success_label": "unlikely",
  "bac": "100000.00", "forecast_cost": "240000.00", "budget_overrun": "140000.00",
  "projects_total": 1, "projects_red": 1, "projects_high_risk": 1, "open_issues": 5,
  "resource_shortage": { "over_allocated": 0, "total_excess_percent": 0, "shortage": false },
  "heat_summary": { "green": 0, "amber": 0, "red": 1, "not_started": 0, "unknown": 0 },
  "narrative": "Transformation success is unlikely (38/100). 1 of 1 projects are red. Forecast is over budget by 140000.00. 1 project(s) carry high risk exposure.",
  "attention": [ "…top prioritised recommendations…" ]
}
```

This completes **Phase 1 — the Intelligence core**. All five engines are
service-independent (they read repositories, never services), share one EVM base,
and require no schema change.

---

# Wired variances — Benefits & KPI (uses Phase 2a / 2c data)

Two variances deferred earlier are now live. Pure read; `intelligence:read`.

**Benefits variance** (realised vs target, from the `benefits` table):
`GET /intelligence/variance/benefits/projects/{project_id}` (also
`/benefits/portfolios/{portfolio_id}` and `/benefits/transformation`) → **200**
```json
{
  "scope": "project", "scope_label": "Atlas", "benefit_count": 1,
  "total_target": "100000.00", "total_realized": "40000.00",
  "variance": "-60000.00", "realization_percent": 40.0, "favourable": false
}
```

**KPI variance** (current vs target, from the `goal_kpis` table):
`GET /intelligence/variance/kpis/transformation` (also
`/kpis/initiatives/{initiative_id}`) → **200**
```json
{
  "scope": "initiative", "scope_label": "KPI init", "kpi_count": 2,
  "kpis_on_target": 1, "kpis_off_target": 1, "average_attainment": 70.0,
  "items": [
    { "name": "Missed", "unit": "", "current_value": "40.0000",
      "target_value": "100.0000", "variance": "-60", "attainment_percent": 40.0, "on_target": false }
  ]
}
```

Unknown project/portfolio/initiative → **404**. Both reuse the shared KPI
attainment logic and the benefit repository's aggregate totals — no schema
change, no new tables.
