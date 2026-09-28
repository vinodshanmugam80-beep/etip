# Financial Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `finance:read`,
`finance:create`, `finance:update`, `finance:delete`.

The financial ledger records **budget**, **forecast**, and **actual** cost lines
against a project. The ledger drives the project's `forecast` / `actual_cost`
rollups and a variance summary.

---

## Add a ledger entry

`POST /financial-entries` (`finance:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "entry_type": "actual",
  "category": "labor",
  "amount": "12500.00",
  "currency": "USD",
  "entry_date": "2026-03-31",
  "description": "March engineering time",
  "vendor": ""
}
```
- `entry_type` ∈ `budget | forecast | actual`.
- `category` ∈ `labor | materials | travel | software | hardware | services | overhead | other`.
- `amount` may be **negative** to record a credit or adjustment.
- The entry currency **must match the project currency** (else **422**,
  `currency_mismatch`) so aggregates stay single-currency.
- Unknown project → **404**.

## Rollups are kept in sync

Whenever entries change, the project's rollups are recomputed:
`project.forecast = Σ forecast entries` and
`project.actual_cost = Σ actual entries`. For example, after posting an `80000`
forecast and two actuals (`30000` + `12000`), `GET /projects/{id}` shows
`forecast = 80000.00` and `actual_cost = 42000.00`.

## Financial summary

`GET /projects/{project_id}/financial-summary` (`finance:read`) → **200**
```json
{
  "project_id": "<uuid>",
  "currency": "USD",
  "approved_budget": "100000.00",
  "planned_total": "95000.00",
  "forecast_total": "90000.00",
  "actual_total": "50000.00",
  "budget_variance": "50000.00",
  "forecast_variance": "10000.00",
  "actual_by_category": [
    { "category": "labor", "amount": "40000.00" },
    { "category": "software", "amount": "10000.00" }
  ]
}
```
- `approved_budget` is the **top-down** figure set on the project (Module 7).
- `planned_total` is the **bottom-up** sum of `budget` ledger lines.
- Variances are *remaining against the approved budget* (positive = under):
  `budget_variance = approved_budget − actual_total`,
  `forecast_variance = approved_budget − forecast_total`.
- `actual_by_category` breaks down actual spend, largest first.

## List / update / delete

- `GET /financial-entries?project_id=<id>&entry_type=actual&category=labor` —
  filtered, paginated.
- `GET /financial-entries/{id}` — fetch one.
- `PATCH /financial-entries/{id}` (`finance:update`) — change type, category,
  amount, date, description, or vendor; rollups are refreshed.
- `DELETE /financial-entries/{id}` (`finance:delete`) — soft delete; rollups are
  refreshed (removing the last actual returns `actual_cost` to `0.00`).

Deleting a **project** soft-deletes its ledger entries automatically.

## RBAC

The **Member** system role has `finance:read` (list/get/summary succeed) but not
`finance:create`/`update`/`delete` → those return **403**.
