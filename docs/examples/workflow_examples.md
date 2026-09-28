# Stage-Gate / Workflow / Approval — Examples

**ETIP 2.0 · Phase 3a.** `BASE = http://localhost:8000/api/v1`. Requires
`Authorization: Bearer <token>`. Permissions: `workflow:read` (Org Admin, PM,
Member), `workflow:manage` (Org Admin, PM — definitions & running instances),
`workflow:approve` (Org Admin, PM — gate decisions).

A generic, reusable governance workflow that any record can attach to. A
**definition** owns ordered **stages** (gates); an **instance** runs a definition
against a polymorphic subject (`entity_type` + `entity_id`); a **gate approval**
records each approve/reject. This generalises the bespoke approvals in the Change
and Timesheet modules without modifying them.

---

## Definitions & stages

`POST /workflows` (`workflow:manage`) → **201**
```json
{ "name": "Project stage gate", "entity_type": "Project", "is_active": true }
```
`POST /workflows/{definition_id}/stages` — add ordered gates:
```json
{ "name": "Business case", "sequence": 1, "requires_approval": false }
{ "name": "Investment review", "sequence": 2, "requires_approval": true }
```
`GET /workflows/{id}/stages` returns them ordered by `sequence`.
`GET /workflows?entity_type=Project&is_active=true`, `PATCH`/`DELETE
/workflows/{id}` (delete cascades stages & instances), `PATCH`/`DELETE
/workflows/stages/{stage_id}`.

## Running an instance

`POST /workflows/instances` (`workflow:manage`) → **201** — starts at the first
stage; `started_by` is recorded for separation of duties:
```json
{ "definition_id": "…", "entity_type": "Project", "entity_id": "…" }
```
Start fails **422** if the definition is inactive or has no stages, **404** if it
doesn't exist.

`POST /workflows/instances/{id}/advance` (`workflow:manage`) — moves past a
**non-approval** stage; advancing past the last stage completes the instance
(`status: completed`, `current_stage_id: null`). Advancing on an approval stage →
**409**.

## Gate decisions (with separation of duties)

`POST /workflows/instances/{id}/decision` (`workflow:approve`) → **200**
```json
{ "decision": "approved", "comment": "Funding confirmed" }
```
- **approved** → advances to the next stage (or completes).
- **rejected** → `status: rejected` (terminal).
- The current stage must require approval, else **409**.
- **Separation of duties:** the initiator can't approve their own instance — if
  the approver equals `started_by`, the call is **409**. A different user holding
  `workflow:approve` must decide.

`GET /workflows/instances/{id}/approvals` → the full decision history:
```json
[ { "stage_id": "…", "decision": "approved", "approver_user_id": "…", "comment": "Funding confirmed" } ]
```

`POST /workflows/instances/{id}/cancel` → `status: cancelled`. Any action on a
finished instance (completed / rejected / cancelled) → **409**.

`GET /workflows/instances?entity_type=Project&entity_id=…&status=in_progress&definition_id=…`
lists instances with filters.

## Why it matters

One governance engine replaces per-module approval code: attach a stage-gate to
projects today and to any future record type tomorrow, with a consistent,
auditable trail and enforced separation of duties everywhere.
