# Reports — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `report:read` (view + run),
`report:create`, `report:update`, `report:delete`.

A **report definition** is a saved, re-runnable configuration: a report type
plus JSON parameters. Definitions are **owned** by their creator and may be
**shared** with the organization. Running a report assembles a fresh result from
current data across other modules — nothing is precomputed.

---

## Save a report definition

`POST /reports` (`report:create`) → **201**
```json
{
  "name": "Weekly project status",
  "description": "Status snapshot for the Atlas project",
  "report_type": "project_status",
  "parameters": { "project_id": "<project-uuid>" },
  "is_shared": true
}
```
`report_type` ∈ `project_status | raid_summary | timesheet_hours |
milestone_status | financial_summary | portfolio_overview`.

## Visibility & ownership

- `GET /reports?report_type=raid_summary` — definitions **visible** to the
  caller: the ones they own **plus** any that are `is_shared`.
- `GET /reports/{id}` — visible definition, else **404**.
- `PATCH /reports/{id}` (`report:update`) / `DELETE /reports/{id}`
  (`report:delete`) — **owner only**. A non-owner who can otherwise see a shared
  report (even with `report:update`) gets **403** — visibility is not ownership.

## Run a report

`POST /reports/{id}/run` (`report:read`) runs a saved definition and stamps its
`last_run_date`. `POST /reports/run` runs an ad-hoc report without saving:
```json
{ "report_type": "raid_summary", "parameters": { "project_id": "<uuid>" } }
```
Both return a **result envelope**:
```json
{
  "report_type": "raid_summary",
  "generated_at": "2026-03-11T09:00:00Z",
  "parameters": { "project_id": "<uuid>" },
  "data": { … }
}
```

### Parameter validation
Missing a required parameter → **422** (`missing_parameter`); a malformed id or
date → **422** (`invalid_parameter`); an unknown project/portfolio → **404**.

## The report types

| Type | Required params | `data` shape (summary) |
|------|-----------------|------------------------|
| `project_status` | `project_id` | code, name, status, stage, health, budget/forecast/actual_cost, cost_variance, risk_score, issue_count, baseline & actual dates |
| `raid_summary` | `project_id` | risks/actions/issues/decisions, each with open/total counts (risks also `max_open_score`) |
| `timesheet_hours` | `project_id` **or** `user_id` (optional `date_from`/`date_to`) | total_hours, billable_hours, by_status |
| `milestone_status` | `project_id` | total, key, overdue, by_status |
| `financial_summary` | `project_id` | budget, forecast, actual_cost, cost_variance, actual_by_category |
| `portfolio_overview` | `portfolio_id` | project_count, by_status, by_health, total_budget, total_actual_cost |

Money values are returned as fixed-2-decimal strings; dates as ISO-8601.

## RBAC

The **Member** role has `report:read` and `report:create` — members can create,
view (own + shared), and run reports — but not `report:update` or
`report:delete` → **403**. Only the definition's **owner** can edit or delete it,
even among users who hold those permissions.
