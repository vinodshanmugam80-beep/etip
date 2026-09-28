# Task Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1/tasks`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `task:read`,
`task:create`, `task:update`, `task:delete`.

A **task belongs to a project**. Tasks may be nested into subtasks.

---

## Create a task

`POST /tasks` (requires `task:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "title": "Design the billing schema",
  "description": "ERD and migration plan",
  "assignee_user_id": null,
  "parent_task_id": null,
  "priority": "high",
  "estimate_hours": "16.00",
  "start_date": "2026-03-02",
  "due_date": "2026-03-09"
}
```
The project must exist (else **404**); each task gets a per-project running
`number` and starts in status `todo`. Unknown `assignee_user_id` → **422**;
`due_date` before `start_date` → **422**.

## Subtasks & hierarchy

Supply `parent_task_id` to nest a task. The parent must be in the **same
project** (else **422**); a task cannot be its own parent, and assigning a
parent that would create a cycle is rejected (**422**).
`GET /tasks/{id}/subtasks` returns the direct children.

## Status lifecycle

```
todo        → in_progress | blocked | cancelled
in_progress → in_review | blocked | done | cancelled
in_review   → in_progress | done | blocked | cancelled
blocked     → todo | in_progress | cancelled
done        → in_progress            (reopen)
cancelled   → (terminal)
```
Illegal transitions → **422** (`illegal_status_transition`).

## List / search

`GET /tasks?project_id=<id>&status=in_progress&priority=high&assignee_user_id=<id>&parent_task_id=<id>&q=schema&limit=50&offset=0`
→ **200**
```json
{ "items": [ /* TaskResponse */ ], "total": 18, "limit": 50, "offset": 0 }
```
Results are ordered by `position`, then task number. Filter by
`assignee_user_id` for a "my tasks" view.

## Update

`PATCH /tasks/{id}` (`task:update`) — partial update of title, description,
assignee, parent, status, priority, `estimate_hours`, `logged_hours`,
`start_date`/`due_date`, and `position` (for ordering).

## Delete & cascades

`DELETE /tasks/{id}` (`task:delete`) → **200**; a task that still has subtasks →
**409** (`task_has_subtasks`). Deleting the **project** soft-deletes all of its
tasks automatically.

## RBAC

The **Member** system role has `task:read` **and** `task:update` (so an assignee
can progress their own work), but not `task:create` or `task:delete` → those
return **403**.
