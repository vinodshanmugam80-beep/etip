# Benefits Realization & ROI — Examples

**ETIP 2.0 · Phase 2a.** `BASE = http://localhost:8000/api/v1`. Requires
`Authorization: Bearer <token>`. Permissions: `benefit:read` (Org Admin, PM,
Member), `benefit:create` / `benefit:update` / `benefit:delete` (Org Admin, PM).

A **benefit** is an expected outcome delivered through a project, tracked from
plan to realisation. Money fields are fixed-2-decimal; realisation %, ROI and
variance are **computed** from target / realised / investment.

---

## Create

`POST /benefits` (`benefit:create`) → **201**
```json
{
  "project_id": "…", "title": "Support cost reduction",
  "category": "financial", "status": "planned",
  "target_value": "100000.00", "realized_value": "40000.00",
  "investment_cost": "20000.00", "target_date": "2026-12-31"
}
```
The response adds the derived fields:
```json
{
  "id": "…", "title": "Support cost reduction", "status": "planned",
  "target_value": "100000.00", "realized_value": "40000.00", "investment_cost": "20000.00",
  "realization_percent": 40.0,
  "roi_percent": 100.0,          // (realised - investment) / investment
  "variance": "-60000.00"        // realised - target (negative = shortfall)
}
```
`realization_percent` / `roi_percent` are `null` when target / investment is 0.
Categories: financial, operational, strategic, customer, compliance,
risk_reduction. Creating under an unknown project → **404**.

## Record realisation

`POST /benefits/{id}/realization` (`benefit:update`) → **200** — records realised
value and **auto-advances status** (partially_realized when 0 < realised <
target, realized when realised ≥ target) unless a `status` is supplied:
```json
{ "realized_value": "100000.00" }
```
Status follows a validated lifecycle (planned → in_progress → partially_realized
→ realized, with at_risk / missed branches); realized and missed are terminal, so
e.g. realized → planned → **422**.

## Search & get

`GET /benefits?project_id=…&category=financial&status=realized&owner_user_id=…&limit=50&offset=0`
(`benefit:read`) → paginated. `GET /benefits/{id}`, `PATCH /benefits/{id}`,
`DELETE /benefits/{id}` (soft-delete → **204**).

## Realisation rollups

`GET /benefits/summary/projects/{project_id}` (also `/summary/programs/{id}` and
`/summary/portfolios/{id}`, aggregating the scope's projects) → **200**
```json
{
  "scope": "portfolio", "benefit_count": 2,
  "total_target": "200000.00", "total_realized": "100000.00", "total_investment": "50000.00",
  "realization_percent": 50.0, "roi_percent": 100.0, "variance": "-100000.00",
  "count_by_status": { "realized": 1, "in_progress": 1 }
}
```

## What this unblocks

This is the data source the Intelligence Layer's **benefits variance** (deferred
in Phase 1b) needs, and it enriches the transformation-success outlook. Wiring
benefits into those engines is a natural follow-up.
