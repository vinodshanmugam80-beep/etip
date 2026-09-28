# Sprint Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1/sprints`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `sprint:read`,
`sprint:create`, `sprint:update`, `sprint:delete`.

A **sprint is a time-boxed iteration within a project**. Tasks are assigned to a
sprint; a project may have at most one active sprint at a time.

---

## Create a sprint

`POST /sprints` (requires `sprint:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "name": "Sprint 1",
  "goal": "Ship the billing schema and API skeleton",
  "start_date": "2026-03-02",
  "end_date": "2026-03-15",
  "capacity_hours": "160.00"
}
```
The project must exist (else **404**); each sprint gets a per-project running
`number` and starts in status `planned`. `end_date` before `start_date` → **422**.

## Status lifecycle & the single-active rule

```
planned   → active | cancelled
active    → completed | cancelled
completed / cancelled → (terminal)
```
`PATCH /sprints/{id}` with `{ "status": "active" }`. Illegal transitions →
**422**. Activating a sprint while the project already has an active sprint →
**409** (`active_sprint_exists`) — complete or cancel the current one first.

## List / search

`GET /sprints?project_id=<id>&status=active&limit=50&offset=0` → **200**
```json
{ "items": [ /* SprintResponse */ ], "total": 6, "limit": 50, "offset": 0 }
```

## Task assignment

`POST /sprints/{sprint_id}/tasks/{task_id}` (`sprint:update`) → **200** — assigns
the task; the task must belong to the **same project** as the sprint (else
**422**, `task_project_mismatch`). Returns the updated task (with `sprint_id`).

`DELETE /sprints/{sprint_id}/tasks/{task_id}` (`sprint:update`) → **200** —
removes the task from the sprint (the task stays in its project). If the task is
not assigned to this sprint → **404**.

`GET /sprints/{sprint_id}/tasks` (`sprint:read`) → **200**
```json
{ "sprint_id": "<uuid>", "tasks": [ /* TaskResponse */ ] }
```

The task endpoint also supports `GET /api/v1/tasks?sprint_id=<id>` for the same
set, so a sprint board can be built from either side.

## Delete

`DELETE /sprints/{id}` (`sprint:delete`) → **200** — soft-deletes the sprint and
**unassigns its tasks** (the tasks belong to the project and survive).

## RBAC

The **Member** system role has `sprint:read` (list/get succeed) but not
`sprint:create`/`update`/`delete` → those return **403**.
