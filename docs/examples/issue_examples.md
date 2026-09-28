# Issue Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `issue:read`,
`issue:create`, `issue:update`, `issue:delete`.

An **issue** is a defect, incident, or request raised against a project and
optionally linked to a task. The project's `issue_count` rollup tracks open
(non-closed) issues.

---

## Raise an issue

`POST /issues` (`issue:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "task_id": null,
  "title": "Checkout page 500s under load",
  "description": "Reproducible above ~200 rps",
  "issue_type": "bug",
  "severity": "high",
  "priority": "high",
  "assignee_user_id": null,
  "due_date": "2026-04-10"
}
```
- `issue_type` ∈ `bug | incident | improvement | question | other`.
- `severity` / `priority` ∈ `low | medium | high | critical`.
- Each issue gets a per-project `number`, starts `open`, and is stamped with the
  caller as `reporter_user_id`.
- Unknown project → **404**; unknown `assignee_user_id` → **422**.
- If `task_id` is given it must exist and belong to the **same project** (else
  **404** / **422** `task_project_mismatch`). Deleting that task later unlinks
  the issue (it stays with the project).

## Status workflow

```
open        → in_progress | resolved | closed
in_progress → open | resolved | closed
resolved    → in_progress | closed        (reopen via in_progress)
closed      → in_progress                 (reopen)
```
Illegal transitions → **422**. Moving to `resolved` stamps `resolved_date`;
reopening to `open`/`in_progress` clears it. Set `resolution` text alongside the
status change.

## Project `issue_count` rollup

The project's `issue_count` (Module 7 placeholder, now live) equals the number
of **open (non-closed)** issues, refreshed on every create/update/delete. A
`resolved`-but-not-`closed` issue still counts as open. Visible on
`GET /projects/{id}`.

## List / search

`GET /issues?project_id=<id>&task_id=<id>&status=open&issue_type=bug&severity=critical&priority=high&assignee_user_id=<id>&q=checkout`
→ **200**, ordered by issue number (newest first):
```json
{ "items": [ /* Issue */ ], "total": 23, "limit": 50, "offset": 0 }
```

## Update / delete

`PATCH /issues/{id}` (`issue:update`) — partial update of any field plus the
validated status transition and resolution handling.
`DELETE /issues/{id}` (`issue:delete`) — soft delete; the rollup is refreshed.

## Issue summary

`GET /projects/{project_id}/issue-summary` (`issue:read`) → **200**
```json
{
  "project_id": "<uuid>",
  "open_count": 5,
  "total_count": 8,
  "by_status": [
    { "status": "open", "count": 3 },
    { "status": "in_progress", "count": 2 },
    { "status": "closed", "count": 3 }
  ]
}
```

Deleting a **project** soft-deletes its issues automatically.

## RBAC

The **Member** system role has `issue:read`, `issue:create`, **and**
`issue:update` — so members can raise and work issues — but not `issue:delete`
→ that returns **403**.
