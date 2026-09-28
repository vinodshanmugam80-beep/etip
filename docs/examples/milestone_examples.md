# Milestone Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `milestone:read`,
`milestone:create`, `milestone:update`, `milestone:delete`.

A **milestone** is a named, dated checkpoint on a project — a phase gate,
deliverable, go-live, etc. It tracks a target vs actual date, a status
lifecycle, an optional link to the completing task, and a key-milestone flag.

---

## Create a milestone

`POST /milestones` (`milestone:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "name": "Beta launch",
  "description": "Feature-complete beta to pilot customers",
  "milestone_type": "go_live",
  "target_date": "2026-06-15",
  "owner_user_id": null,
  "task_id": null,
  "is_key": true
}
```
- `milestone_type` ∈ `checkpoint | deliverable | phase_gate | go_live | external | other`.
- `target_date` is **required**. Each milestone gets a per-project `number` and
  starts `planned`.
- Unknown project → **404**; unknown `owner_user_id` → **422**; a `task_id` from
  another project → **422** (`task_project_mismatch`).

## Status lifecycle

```
planned     → in_progress | achieved | missed | cancelled
in_progress → planned | achieved | missed | cancelled
achieved    → in_progress            (reopen)
missed      → in_progress | achieved
cancelled   → (terminal)
```
Moving to `achieved` stamps `actual_date` (unless you supply one); reopening to
`planned`/`in_progress` or marking `missed` clears it. Illegal transitions →
**422**.

## Derived `is_overdue`

Every milestone response includes a computed `is_overdue`: **true** when the
milestone is still open (`planned`/`in_progress`) and its `target_date` is in the
past. Achieving, missing, or cancelling a milestone makes it no longer overdue.

## List / search

`GET /milestones?project_id=<id>&status=planned&milestone_type=go_live&is_key=true&owner_user_id=<id>&q=beta`
→ **200**, ordered by **target date ascending** (soonest first):
```json
{ "items": [ /* Milestone */ ], "total": 9, "limit": 50, "offset": 0 }
```

## Update / delete

`PATCH /milestones/{id}` (`milestone:update`) — partial update of any field plus
the validated status transition and actual-date handling.
`DELETE /milestones/{id}` (`milestone:delete`) — soft delete.

## Milestone summary

`GET /projects/{project_id}/milestone-summary` (`milestone:read`) → **200**
```json
{
  "project_id": "<uuid>",
  "total_count": 12,
  "key_count": 4,
  "overdue_count": 2,
  "by_status": [
    { "status": "planned", "count": 6 },
    { "status": "achieved", "count": 4 },
    { "status": "missed", "count": 2 }
  ]
}
```

Deleting a **project** soft-deletes its milestones automatically.

## RBAC

The **Member** system role has `milestone:read` (list/get/summary succeed) but
not `milestone:create`/`update`/`delete` → those return **403**.
