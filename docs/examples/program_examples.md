# Program Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1/programs`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `program:read`,
`program:create`, `program:update`, `program:delete`.

A **program belongs to exactly one portfolio** and groups related projects
toward a shared outcome.

---

## Create a program

`POST /programs` (requires `program:create`) → **201**
```json
{
  "portfolio_id": "<portfolio-uuid>",
  "name": "Cloud Migration",
  "code": "CLOUD",
  "description": "Migrate core systems to the cloud",
  "manager_user_id": null,
  "priority": "high",
  "planned_budget": "1200000.00",
  "currency": "USD",
  "start_date": "2026-02-01",
  "end_date": "2026-11-30"
}
```
The referenced portfolio must exist in the tenant (unknown → **404**). `code`
is unique per organization (duplicate → **409**); an unknown `manager_user_id`
→ **422**; `end_date` before `start_date` → **422**. New programs start in
status `proposed`.

## Status lifecycle

Identical transition rules to portfolios:
```
proposed → active | cancelled
active   → on_hold | closed | cancelled
on_hold  → active | cancelled
closed / cancelled → (terminal)
```
Illegal transitions → **422** (`illegal_status_transition`).

## List / search

`GET /programs?portfolio_id=<id>&status=active&manager_user_id=<id>&q=cloud`
→ **200**
```json
{ "items": [ /* ProgramResponse */ ], "total": 4, "limit": 50, "offset": 0 }
```
Filters: `portfolio_id`, `status`, `manager_user_id`, and `q` (name/code
substring).

## Update / delete

`PATCH /programs/{id}` (`program:update`) — partial update including a validated
status transition and effective date-range check.
`DELETE /programs/{id}` (`program:delete`) → **200** — soft delete.

## Portfolio-deletion guard

Because programs live inside a portfolio, deleting a portfolio that still
contains programs is blocked:
`DELETE /api/v1/portfolios/{id}` → **409** (`portfolio_in_use`). Delete or
reassign the programs first.

## RBAC

The **Member** system role has `program:read` (list/get succeed) but not
`program:create`/`update`/`delete` → those return **403**.
