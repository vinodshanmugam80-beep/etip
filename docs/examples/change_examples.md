# Change Request Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `change:read`,
`change:create`, `change:update`, **`change:approve`**, `change:delete`.

A **change request** is a formal, auditable request to change a project's scope,
schedule, budget, or resources. Raising/editing and **deciding** are separate
rights (separation of duties).

---

## Raise a change request

`POST /change-requests` (`change:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "title": "Add SSO to phase 1 scope",
  "description": "Enterprise customers require SAML at launch",
  "reason": "Unblocks three enterprise deals",
  "change_type": "scope",
  "priority": "high",
  "schedule_impact_days": 15,
  "cost_impact": "40000.00",
  "impact_summary": "Two extra sprints; one contractor",
  "approver_user_id": null,
  "target_date": "2026-06-01"
}
```
- `change_type` ∈ `scope | schedule | budget | resource | quality | other`.
- Impact fields are **signed**: negative `schedule_impact_days` means
  acceleration, negative `cost_impact` means a saving.
- Each request gets a per-project `number`, starts as `draft`, and is stamped
  with the caller as `requested_by_user_id`.
- Unknown project → **404**; unknown `approver_user_id` → **422**.

## Approval workflow

```
draft        → submitted | cancelled
submitted    → under_review | approved | rejected | cancelled
under_review → approved | rejected | cancelled
approved     → implemented | cancelled
rejected / implemented / cancelled → (terminal)
```

### Separation of duties
`PATCH /change-requests/{id}` (`change:update`) moves a request through the
workflow **except** to `approved`/`rejected` — attempting that returns **422**
(`use_decision_endpoint`). Deciding is done via dedicated endpoints that require
the separate `change:approve` permission:

- `POST /change-requests/{id}/approve` — body `{ "decision_notes": "..." }` →
  sets `approved`, stamps `approver_user_id` (the caller) and `decided_date`.
- `POST /change-requests/{id}/reject` — same shape → sets `rejected`.

A request must be `submitted` or `under_review` to be decided (approving a
`draft` → **422**).

## List / search

`GET /change-requests?project_id=<id>&status=submitted&change_type=scope&priority=high&q=sso`
→ **200**, ordered by number (newest first).

## Change summary

`GET /projects/{project_id}/change-summary` (`change:read`) → **200**
```json
{
  "project_id": "<uuid>",
  "pending_count": 3,
  "total_count": 11,
  "by_status": [
    { "status": "draft", "count": 1 },
    { "status": "submitted", "count": 2 },
    { "status": "approved", "count": 5 },
    { "status": "implemented", "count": 3 }
  ]
}
```
`pending_count` counts requests still awaiting a decision
(`draft`/`submitted`/`under_review`).

Deleting a **project** soft-deletes its change requests automatically.

## RBAC

The **Member** system role has `change:read` **and** `change:create` — members
can raise change requests — but not `change:update`, `change:approve`, or
`change:delete` → those return **403**. This enforces that the person raising a
change is not the person who approves it.
