# Roles & Permissions — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `role:read`,
`role:create`, `role:update`, `role:delete`. The permission catalogue is
global (identical for every tenant) and read-only.

---

## Permission catalogue

`GET /permissions` (requires `role:read`) → **200**
```json
[
  { "id": "…", "code": "organization:read", "description": "View organization settings" },
  { "id": "…", "code": "project:create", "description": "Create projects" }
]
```
Returned in stable (code-sorted) order.

## Create a custom role

`POST /roles` (requires `role:create`) → **201**
```json
{
  "name": "Portfolio Analyst",
  "description": "Read-only across portfolios",
  "permissions": ["project:read", "organization:read"]
}
```
Role names are unique per organization (duplicate → **409**); every permission
code must exist in the catalogue (unknown → **422**).

## List / get

`GET /roles?limit=50&offset=0` → **200** — returns both system and custom roles,
each with an `is_system` flag and its `permissions`.
`GET /roles/{id}` → **200** | unknown → **404**.

## Update & permissions

`PATCH /roles/{id}` (`role:update`) — update `name` / `description`.
`PUT /roles/{id}/permissions` — replace the full permission set:
```json
{ "permissions": ["project:read", "project:update"] }
```
`POST /roles/{id}/permissions/{code}` — grant one permission (idempotent).
`DELETE /roles/{id}/permissions/{code}` — revoke one permission (idempotent).

## System-role protection

The seeded system roles (**Organization Admin**, **Project Manager**,
**Member**) are immutable: any `PATCH`, permission change, or `DELETE` returns
**409** with error code `protected_role`.

## Delete

`DELETE /roles/{id}` (`role:delete`) → **200** for a custom role.
- A role still assigned to any user → **409** (`role_in_use`); reassign those
  users first (e.g. via `PUT /users/{id}/roles`).
- A system role → **409** (`protected_role`).

## RBAC

`role:read` (held by e.g. the **Project Manager** system role) allows listing
and viewing roles, but creating/updating/deleting requires the respective
`role:create` / `role:update` / `role:delete` permission — otherwise **403**.
