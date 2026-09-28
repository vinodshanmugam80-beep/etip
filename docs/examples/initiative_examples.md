# Strategic Initiatives / Business Goals / KPIs — Examples

**ETIP 2.0 · Phase 2c.** `BASE = http://localhost:8000/api/v1`. Requires
`Authorization: Bearer <token>`. Permissions: `initiative:read` (Org Admin, PM,
Member), `initiative:manage` (Org Admin, PM).

A three-level strategic layer above the portfolio hierarchy:
**StrategicInitiative → BusinessGoal → GoalKPI**. Each KPI carries baseline,
current and target values, yielding **attainment %, variance and target-met** —
the data source for KPI-vs-target variance. Additive: the Portfolio module's
`PortfolioObjective` is untouched.

---

## Initiatives

`POST /initiatives` (`initiative:manage`) → **201**
```json
{ "name": "Digital-first transformation", "status": "active", "priority": "high",
  "portfolio_id": "…", "sponsor_user_id": "…", "target_date": "2027-06-30" }
```
An unknown `portfolio_id` / `sponsor_user_id` → **422**. Statuses: proposed,
active, on_hold, completed, cancelled.
`GET /initiatives?status=active&portfolio_id=…`, `GET/PATCH/DELETE
/initiatives/{id}` (delete cascades goals + KPIs).

## Goals (under an initiative)

`POST /goals` (`initiative:manage`) → **201**
```json
{ "initiative_id": "…", "title": "Grow online revenue", "category": "growth" }
```
Unknown initiative → **404**. `GET /initiatives/{id}/goals`, `GET/PATCH/DELETE
/goals/{id}`.

## KPIs (on a goal)

`POST /kpis` (`initiative:manage`) → **201**
```json
{ "goal_id": "…", "name": "Online revenue", "unit": "USD",
  "direction": "increase", "baseline_value": "0", "current_value": "50", "target_value": "100" }
```
The response adds computed fields:
```json
{ "name": "Online revenue", "current_value": "50.0000", "target_value": "100.0000",
  "attainment_percent": 50.0,   // progress baseline → target
  "variance": "-50",            // current - target
  "target_met": false }
```
- **increase**: attainment = (current − baseline) / (target − baseline).
- **decrease** (lower is better, e.g. defect rate): attainment = (baseline −
  current) / (baseline − target); target_met when current ≤ target.

`POST /kpis/{id}/measurement` records a new `current_value`;
`GET /goals/{id}/kpis`, `GET/PATCH/DELETE /kpis/{id}`.

## Attainment rollups

`GET /goals/{goal_id}/summary` → KPI count, KPIs met, average attainment.
`GET /initiatives/{initiative_id}/summary` → **200**
```json
{
  "initiative_id": "…", "name": "Digital-first transformation", "status": "active",
  "goal_count": 3, "kpi_count": 8, "kpis_met": 5, "average_attainment": 78.5,
  "goals": [ { "goal_id": "…", "title": "Grow online revenue", "kpi_count": 2, "kpis_met": 1, "average_attainment": 75.0 } ]
}
```

## What this unblocks

The KPI target-vs-current model here is exactly the source the Intelligence
Layer's **KPI-vs-target variance** (deferred in Phase 1d) needs. Wiring KPI
variance into the analytics engines is now a natural follow-up, no longer a
placeholder.
