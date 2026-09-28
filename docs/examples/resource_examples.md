# Resource Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `resource:read`,
`resource:create`, `resource:update`, `resource:delete`. Allocation operations
are resource mutations and require `resource:update`.

A **resource** is an allocatable person or asset. An **allocation** books a
resource onto a project for a date range at a percentage of capacity.

---

## Create a resource

`POST /resources` (`resource:create`) → **201**
```json
{
  "name": "Ada Engineer",
  "user_id": null,
  "department_id": null,
  "resource_type": "employee",
  "capacity_hours_per_week": "40.00",
  "cost_rate": "120.00",
  "currency": "USD",
  "skills": ["python", "postgres"]
}
```
`resource_type` ∈ `employee | contractor | vendor | equipment`. `skills` are
lower-cased and de-duplicated. If `user_id` is given it must belong to the
tenant (else **422**) and must not already back another resource (else **409**).
A resource without a `user_id` models an external contractor or a piece of
equipment.

`GET /resources?q=ada&resource_type=employee&department_id=<id>&is_active=true`
returns a paginated page. `GET /resources/{id}`, `PATCH /resources/{id}`, and
`DELETE /resources/{id}` behave conventionally. Deletion is blocked while the
resource still has allocations → **409** (`resource_in_use`).

## Allocate a resource

`POST /resources/{resource_id}/allocations` (`resource:update`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "start_date": "2026-03-01",
  "end_date": "2026-05-31",
  "allocation_percent": 50,
  "role_label": "Backend Lead",
  "notes": ""
}
```
The project must exist (else **404**). `allocation_percent` is 1–100.

### Over-allocation detection

A resource can never be committed beyond **100%** at any instant. When an
allocation is created or updated, the service runs a sweep line over the day
boundaries of the new allocation and every overlapping existing allocation and
verifies the running total stays ≤ 100. Examples for one resource:

- `60%` Jan–Mar, then `60%` Jan–Mar → **422** (`over_allocation`, would hit
  120%). A further `40%` Jan–Mar succeeds (exactly 100%).
- `50%` Jan–Mar plus `60%` Mar–May → **422** (they overlap in March at 110%). A
  `40%` Mar–May succeeds (90% in the overlap).
- `100%` Jan–Mar and `100%` Apr–Jun → both succeed (no overlap).

The error payload includes the peak percentage and the date it occurs:
```json
{ "error": { "code": "over_allocation",
             "details": { "peak_percent": 110, "on": "2026-03-01" } } }
```

## Managing allocations

- `GET /allocations?resource_id=<id>&project_id=<id>` — list/filter.
- `GET /allocations/{id}` — fetch one.
- `PATCH /allocations/{id}` — change dates/percent/role/notes; the ceiling is
  re-checked, excluding the allocation itself so editing its own notes never
  self-conflicts.
- `DELETE /allocations/{id}` — soft delete.

Deleting a **project** soft-deletes its allocations automatically, freeing the
resources.

## RBAC

The **Member** system role has `resource:read` (list/get succeed) but not
`resource:create`/`update`/`delete` → those return **403**.
