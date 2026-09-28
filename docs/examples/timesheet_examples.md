# Timesheet Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `timesheet:read`,
`timesheet:create`, `timesheet:update`, **`timesheet:approve`**,
`timesheet:delete`.

A **time entry** records hours a user worked on a project (optionally a task) on
a day. Entries move through a submit → approve/reject workflow; logging and
approving are separate rights.

---

## Log a time entry

`POST /timesheets` (`timesheet:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "task_id": null,
  "work_date": "2026-03-02",
  "hours": "6.50",
  "billable": true,
  "activity_type": "development",
  "description": "Implemented the export pipeline"
}
```
- The entry is logged **for the calling user** (`user_id`) and starts `draft`.
- `hours` must be `> 0` and `≤ 24`.
- `activity_type` ∈ `development | design | testing | meeting | management | support | other`.
- Unknown project → **404**; a `task_id` from another project → **422**
  (`task_project_mismatch`).

## Workflow & edit-locking

```
draft     → submitted
submitted → draft (recall) | approved | rejected
rejected  → draft (fix and resubmit)
approved  → (terminal)
```
- Field edits (`hours`, `work_date`, …) are allowed **only** while `draft` or
  `rejected`; editing a submitted/approved entry → **422** (`entry_locked`).
- `draft ↔ submitted` moves go through `PATCH`. Reaching `approved`/`rejected`
  via `PATCH` is refused (**422** `use_decision_endpoint`).

### Separation of duties
Deciding requires the separate `timesheet:approve` permission:
- `POST /timesheets/{id}/approve` — body `{ "decision_notes": "..." }`.
- `POST /timesheets/{id}/reject` — same shape.

Both stamp `approver_user_id` (the caller) and `decided_date`. Only a
`submitted` entry can be decided.

## Task `logged_hours` rollup

Approving a time entry that targets a task rolls its hours into that task's
`logged_hours` (the sum of **approved** entries for the task). Draft/submitted
entries do not count; deleting an approved entry lowers the rollup. Visible on
`GET /tasks/{id}`.

## List / search

`GET /timesheets?project_id=<id>&task_id=<id>&user_id=<id>&status=approved&billable=true&activity_type=development&date_from=2026-03-01&date_to=2026-03-31`
→ **200**, ordered by work date (newest first).

## Summary

`GET /timesheets/summary?project_id=<id>&user_id=<id>&date_from=...&date_to=...`
(`timesheet:read`) → **200**
```json
{
  "total_hours": "128.50",
  "billable_hours": "104.00",
  "approved_hours": "96.00",
  "entry_count": 22,
  "by_status": [
    { "status": "approved", "hours": "96.00", "count": 15 },
    { "status": "submitted", "hours": "24.50", "count": 5 },
    { "status": "draft", "hours": "8.00", "count": 2 }
  ]
}
```

Deleting a **project** soft-deletes its time entries automatically.

## RBAC

The **Member** system role has `timesheet:create`, `timesheet:read`, and
`timesheet:update` — members log, view, and submit their own time — but not
`timesheet:approve` or `timesheet:delete` → those return **403**. Logging time
and approving it are therefore held by different people.
