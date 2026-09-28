# Organization Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1/organization`. All requests require
`Authorization: Bearer <access_token>`. Writes require the
`organization:update` permission; reads require `organization:read`.

---

## Business units

`POST /business-units` → **201**
```json
{ "name": "Technology", "code": "TECH", "description": "Engineering teams" }
```
Codes are normalised to upper-case and must be unique per organization
(duplicate → **409**). `DELETE` is blocked with **409** while departments still
reference the unit.

## Departments

`POST /departments` → **201**
```json
{
  "name": "Platform Engineering",
  "code": "PLAT",
  "business_unit_id": "…",
  "parent_department_id": null,
  "head_user_id": null
}
```

Hierarchy rules (enforced in the service layer):
- A department cannot be its own parent → **422**.
- Assigning a parent that would create a cycle → **422**.
- Deleting a department that has children → **409**.
- Referencing an unknown business unit / parent → **404**.

`GET /departments?business_unit_id=<id>` filters by business unit.

## Settings

`GET /settings` returns the tenant settings, creating defaults
(`USD`, `UTC`, fiscal year starting January) on first access.

`PUT /settings` → **200**
```json
{ "currency": "eur", "fiscal_year_start_month": 4, "week_start_day": 1 }
```
`currency` is upper-cased; `fiscal_year_start_month` must be 1–12 (else **422**).

## Department memberships

`POST /departments/{id}/members` → **201**
```json
{ "user_id": "…", "is_primary": true }
```
Setting `is_primary` clears the primary flag on the user's other memberships
(single-primary invariant). Duplicate membership → **409**; unknown user →
**422**.

`GET /departments/{id}/members` lists memberships.
`DELETE /departments/{id}/members/{user_id}` removes one → **200**.

## RBAC

A user holding only the seeded **Member** role can read organization structure
but receives **403** (`permission_denied`) on any create/update/delete.
