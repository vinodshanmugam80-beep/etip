# RAID Log — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `raid:read`,
`raid:create`, `raid:update`, `raid:delete`.

RAID = **R**isks, **A**ctions, **I**ssues, **D**ecisions. Risks and Issues have
their own modules (12, 13); this module owns **Actions** and **Decisions** and
exposes a consolidated per-project RAID summary across all four quadrants.

---

## Actions

### Raise an action
`POST /actions` (`raid:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "title": "Confirm data-migration window with ops",
  "description": "Need a 4h maintenance slot",
  "priority": "high",
  "owner_user_id": null,
  "due_date": "2026-04-05"
}
```
Each action gets a per-project `number` and starts `open`. Unknown project →
**404**; unknown `owner_user_id` → **422**.

### Workflow
```
open        → in_progress | done | cancelled
in_progress → open | done | cancelled
done        → in_progress          (reopen)
cancelled   → (terminal)
```
Marking an action `done` stamps `completed_date`; reopening to `open`/
`in_progress` clears it. Illegal transitions → **422**.

`GET /actions?project_id=<id>&status=open&owner_user_id=<id>&q=migration`,
`GET /actions/{id}`, `PATCH /actions/{id}`, `DELETE /actions/{id}`.

## Decisions

### Log a decision
`POST /decisions` (`raid:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "title": "Adopt event-sourced billing",
  "description": "Use an append-only ledger for billing state",
  "rationale": "Auditability and replay outweigh added complexity",
  "decided_by_user_id": null
}
```
Each decision gets a per-project `number` and starts `proposed`.

### Lifecycle
```
proposed  → decided | rejected
decided   → superseded
superseded / rejected → (terminal)
```
Moving to `decided` stamps `decision_date`. Illegal transitions → **422**.

`GET /decisions?project_id=<id>&status=decided&q=billing`,
`GET /decisions/{id}`, `PATCH /decisions/{id}`, `DELETE /decisions/{id}`.

## Consolidated RAID summary

`GET /projects/{project_id}/raid` (`raid:read`) → **200**
```json
{
  "project_id": "<uuid>",
  "risks":     { "open_count": 3, "total_count": 5 },
  "actions":   { "open_count": 4, "total_count": 9 },
  "issues":    { "open_count": 6, "total_count": 12 },
  "decisions": { "open_count": 1, "total_count": 4 }
}
```
"Open" means: risks not `closed`, actions `open`/`in_progress`, issues not
`closed`, decisions still `proposed`. This single call reads across the Risk,
Issue, Action and Decision registers.

Deleting a **project** soft-deletes its actions and decisions automatically
(risks and issues are cascaded by their own modules).

## RBAC

The **Member** system role has `raid:read` **and** `raid:update` — so members
can progress actions assigned to them — but not `raid:create` or `raid:delete`
→ those return **403**.
