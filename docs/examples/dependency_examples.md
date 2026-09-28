# Dependency Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `dependency:read`,
`dependency:create`, `dependency:update`, `dependency:delete`.

A **dependency** links a predecessor to a successor of the same kind —
task→task or project→project — with a scheduling relationship and a lag. The
successor depends on the predecessor. The service keeps the dependency graph
**acyclic**.

---

## Create a dependency

`POST /dependencies` (`dependency:create`) → **201**
```json
{
  "entity_type": "task",
  "predecessor_id": "<task-A-uuid>",
  "successor_id": "<task-B-uuid>",
  "dependency_type": "finish_to_start",
  "lag_days": 2
}
```
- `entity_type` ∈ `task | project`. Both endpoints must be of this type.
- `dependency_type` ∈ `finish_to_start | start_to_start | finish_to_finish |
  start_to_finish`.
- `lag_days` may be negative (a lead).

### Validation
- Endpoints must be distinct → self-links are **422**.
- Both endpoints must exist in the tenant → otherwise **404**.
- **Task** dependencies must be within the **same project** → cross-project is
  **422** (`cross_project_dependency`).
- A duplicate edge (same predecessor→successor) is **409**
  (`duplicate_dependency`).
- An edge that would create a **cycle** is **409** (`cycle_detected`).

### Cycle detection
Adding `predecessor → successor` is refused when the successor can already
reach the predecessor by following existing edges. For example, given
`A → B` and `B → C`, adding `C → A` closes the loop `A → B → C → A` and returns
**409**. The direct two-node loop (`A → B` then `B → A`) is caught the same way.
The check runs over the edges of the relevant entity type via a forward graph
traversal from the successor.

## List / filter

`GET /dependencies?entity_type=task&predecessor_id=<id>&successor_id=<id>`
→ **200** `{ "items": [...], "total": n, "limit": 50, "offset": 0 }`.

## Per-entity view

`GET /tasks/{task_id}/dependencies` and `GET /projects/{project_id}/dependencies`
(`dependency:read`) → **200**
```json
{
  "entity_type": "task",
  "entity_id": "<uuid>",
  "predecessors": [ /* edges where this entity is the successor */ ],
  "successors":   [ /* edges where this entity is the predecessor */ ]
}
```

## Update / delete

`PATCH /dependencies/{id}` (`dependency:update`) — only `dependency_type` and
`lag_days` may change; **endpoints are immutable** (changing them could
introduce a cycle, so callers delete and recreate instead).
`DELETE /dependencies/{id}` (`dependency:delete`) — soft delete.

## Cleanup

Deleting a **task** soft-deletes every dependency touching it. Deleting a
**project** soft-deletes its project-level dependency edges *and* the
task-level edges among its tasks.

## Design note

The two endpoints are polymorphic (they reference tasks or projects depending
on `entity_type`), so they are stored as plain UUID columns rather than via
database foreign keys; existence, the same-type and same-project rules, and
acyclicity are all enforced in the service.

## RBAC

The **Member** system role has `dependency:read` (list/get succeed) but not
`dependency:create`/`update`/`delete` → those return **403**.
