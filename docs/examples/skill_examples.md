# Skills Matrix — Examples

**ETIP 2.0 · Phase 2b.** `BASE = http://localhost:8000/api/v1`. Requires
`Authorization: Bearer <token>`. Permissions: `skill:read` (Org Admin, PM,
Member), `skill:manage` (Org Admin, PM).

A **skill** is an org-level catalogue entry; a **resource-skill assignment**
links a resource to a skill with a proficiency (1–5). Together they form the
skills matrix. This is additive — the Resource module's freeform `skills` JSON
list is left untouched.

---

## Skill catalogue

`POST /skills` (`skill:manage`) → **201**
```json
{ "name": "Python", "category": "technical", "description": "Backend" }
```
Names are unique per tenant (case-insensitive) → duplicate is **409**.
Categories: technical, functional, domain, leadership, other.
`GET /skills?query=py&category=technical&limit=50&offset=0` (`skill:read`),
`GET /skills/{id}`, `PATCH /skills/{id}`, `DELETE /skills/{id}` (soft-delete →
**204**, cascades its assignments).

## Assignments

`POST /skills/assignments` (`skill:manage`) → **201**
```json
{ "resource_id": "…", "skill_id": "…", "proficiency": 4, "years_experience": "3.5" }
```
Duplicate (resource, skill) → **409**; unknown resource or skill → **404**.
`PATCH /skills/assignments/{id}`, `DELETE /skills/assignments/{id}`,
`GET /skills/resources/{resource_id}` (a resource's skills).

## Matrix

`GET /skills/matrix` (`skill:read`) → **200**
```json
{
  "skills": [ { "id": "…", "name": "Python", "category": "technical" }, { "id": "…", "name": "SQL" } ],
  "rows": [
    { "resource_id": "…", "resource_name": "Engineer One",
      "skills": [ { "skill_id": "…", "skill_name": "Python", "proficiency": 5 },
                  { "skill_id": "…", "skill_name": "SQL", "proficiency": 3 } ] },
    { "resource_id": "…", "resource_name": "Engineer Two",
      "skills": [ { "skill_id": "…", "skill_name": "Python", "proficiency": 2 } ] }
  ]
}
```

## Coverage (staffing)

`GET /skills/{skill_id}/resources?min_proficiency=3` (`skill:read`) → resources
holding the skill at or above a proficiency, highest first:
```json
{
  "skill_id": "…", "skill_name": "Python", "min_proficiency": 3,
  "resource_count": 1,
  "resources": [ { "resource_id": "…", "resource_name": "Engineer One", "proficiency": 5, "years_experience": "3.5" } ]
}
```

## Capacity supply

`GET /skills/capacity` (`skill:read`) → per-skill supply — how many resources
hold it and their combined weekly capacity:
```json
{
  "as_of": "2026-06-30",
  "items": [
    { "skill_id": "…", "skill_name": "Python", "category": "technical",
      "resource_count": 2, "total_capacity_hours": "60.00", "average_proficiency": 3.5 },
    { "skill_id": "…", "skill_name": "SQL", "category": "technical",
      "resource_count": 1, "total_capacity_hours": "40.00", "average_proficiency": 3.0 }
  ]
}
```

## Scope note

Phase 2b delivers the skills matrix and skill **capacity supply**. Time-phased
resource **demand** forecasting (projecting allocation demand per period against
capacity) is a natural follow-up that builds on the allocation date-ranges from
Module 10 — not fabricated here.
