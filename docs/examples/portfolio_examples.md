# Portfolio Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1/portfolios`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `portfolio:read`,
`portfolio:create`, `portfolio:update`, `portfolio:delete`.

---

## Create a portfolio

`POST /portfolios` (requires `portfolio:create`) → **201**
```json
{
  "name": "Digital Transformation",
  "code": "DX",
  "description": "Enterprise-wide digital initiatives",
  "owner_user_id": null,
  "priority": "high",
  "planned_budget": "2500000.00",
  "currency": "USD",
  "start_date": "2026-01-01",
  "end_date": "2026-12-31"
}
```
New portfolios start in status `proposed`. `code` is unique per organization
(duplicate → **409**); an unknown `owner_user_id` → **422**; `end_date` before
`start_date` → **422**.

## Status lifecycle

`PATCH /portfolios/{id}` with `{ "status": "active" }`. Allowed transitions:

```
proposed → active | cancelled
active   → on_hold | closed | cancelled
on_hold  → active | cancelled
closed   → (terminal)
cancelled→ (terminal)
```
An illegal transition (e.g. `proposed → closed`, or anything out of a terminal
state) → **422** with error code `illegal_status_transition`.

## List / search

`GET /portfolios?q=digital&status=active&owner_user_id=<id>&limit=50&offset=0`
→ **200**
```json
{ "items": [ /* PortfolioResponse */ ], "total": 12, "limit": 50, "offset": 0 }
```
`q` matches name or code (case-insensitive); `status` and `owner_user_id`
filter the results.

## Update

`PATCH /portfolios/{id}` (`portfolio:update`) — partial update of any field
including `owner_user_id`, `priority`, `health`, `planned_budget`, `currency`,
and dates. Date validation runs against the **effective** range, so setting only
`end_date` earlier than the stored `start_date` → **422**.

## Strategic objectives

`POST /portfolios/{id}/objectives` (`portfolio:update`) → **201**
```json
{ "title": "Reduce cycle time", "description": "…", "weight": 40 }
```
`weight` is 0–100 (out of range → **422**).
`GET /portfolios/{id}/objectives` lists them.
`DELETE /portfolios/{id}/objectives/{objective_id}` removes one → **200**.

## Delete

`DELETE /portfolios/{id}` (`portfolio:delete`) → **200** — soft-deletes the
portfolio and cascades its objectives.

## RBAC

The **Member** system role has `portfolio:read` (list/get succeed) but not
`portfolio:create`/`update`/`delete` → those return **403**.
