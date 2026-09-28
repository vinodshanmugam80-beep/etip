# Project Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1/projects`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `project:read`,
`project:create`, `project:update`, `project:delete`.

The project is the operational unit of delivery. It may belong to a portfolio
and/or a program and to a department.

---

## Create a project

`POST /projects` (requires `project:create`) → **201**
```json
{
  "name": "Billing Platform Rebuild",
  "code": "BILL",
  "description": "Replace the legacy billing engine",
  "portfolio_id": null,
  "program_id": null,
  "department_id": null,
  "sponsor_user_id": null,
  "manager_user_id": null,
  "stage": "planning",
  "priority": "high",
  "budget": "750000.00",
  "forecast": "780000.00",
  "currency": "USD",
  "start_date": "2026-03-01",
  "end_date": "2026-12-15",
  "tags": ["finance", "modernization"],
  "custom_fields": {"cost_center": "CC-4471"}
}
```
Each project gets an auto-assigned per-tenant running `number` and starts in
status `proposed`, stage `initiation` (unless overridden). `code` is unique per
organization (duplicate → **409**). `tags` are trimmed and de-duplicated.

### Hierarchy consistency
- If `program_id` is supplied, the project's **portfolio is derived from the
  program**; an explicit `portfolio_id` that disagrees → **422**
  (`hierarchy_mismatch`).
- Unknown `portfolio_id` / `program_id` → **404**; unknown `department_id`,
  `sponsor_user_id`, or `manager_user_id` → **422**.
- `end_date` before `start_date` (or the baseline equivalents) → **422**.

Portfolio and program are set at creation and are **immutable** on update.

## Status lifecycle & progress

`PATCH /projects/{id}` with `{ "status": "active" }`. Same transition rules as
portfolios/programs (`proposed → active → on_hold ↔ active → closed`,
`cancelled` from live states, terminal `closed`/`cancelled`); illegal moves →
**422**. `progress_percent` is 0–100 (out of range → **422**).

## List / search

`GET /projects?q=billing&status=active&stage=execution&portfolio_id=<id>&program_id=<id>&manager_user_id=<id>&limit=50&offset=0`
→ **200**
```json
{ "items": [ /* ProjectResponse */ ], "total": 37, "limit": 50, "offset": 0 }
```
Results are ordered by project number (newest first).

## Team members

`POST /projects/{id}/team` (`project:update`) → **201**
```json
{ "user_id": "<uuid>", "role_label": "Tech Lead", "allocation_percent": 50 }
```
User must be in the tenant (else **422**); duplicate membership → **409**;
`allocation_percent` is 0–100.
`GET /projects/{id}/team` lists; `DELETE /projects/{id}/team/{user_id}` removes.

## Comments

`POST /projects/{id}/comments` (`project:read` — participants may comment) →
**201** `{ "body": "Kickoff scheduled for Monday." }` (authored by the caller).
`GET /projects/{id}/comments` lists newest-first;
`DELETE /projects/{id}/comments/{comment_id}` (`project:update`) removes.

## Delete & parent guards

`DELETE /projects/{id}` (`project:delete`) → **200** (cascades team members and
comments). A **portfolio** or **program** that still contains projects cannot be
deleted → **409** (`portfolio_in_use` / `program_in_use`).

## Rollup fields

`risk_score` and `issue_count` are exposed on the project (default `0`) and are
maintained by the Risk and Issue modules (12–13); they are not set directly here.

## RBAC

The **Member** system role has `project:read` (list/get/comment succeed) but not
`project:create`/`update`/`delete` → those return **403**.
