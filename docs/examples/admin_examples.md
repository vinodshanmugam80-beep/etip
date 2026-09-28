# Administration — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Reads require `admin:read`; the
permission reconciliation requires `admin:manage`. Both are held only by the
**Organization Admin** role.

The Administration module is the operational surface over the tenant: read access
to the audit log every service writes, a governance overview, system
diagnostics, and reconciliation of the permission catalogue for existing tenants.

---

## Audit log

Every mutating operation across the platform appends an entry to an append-only
audit log (never updated or deleted). This module reads it, tenant-scoped.

`GET /admin/audit-logs` (`admin:read`) — filterable, newest first:
```
?entity_type=Project&action=create&actor_id=<uuid>&entity_id=<uuid>
&date_from=2026-01-01T00:00:00Z&date_to=2026-12-31T23:59:59Z&limit=50&offset=0
```
```json
{
  "items": [
    {
      "id": "…", "actor_id": "…", "entity_type": "Project", "entity_id": "…",
      "action": "create", "summary": "Created project 'Atlas'",
      "created_date": "2026-03-01T09:00:00Z"
    }
  ],
  "total": 128, "limit": 50, "offset": 0
}
```
`GET /admin/audit-logs/{entry_id}` (`admin:read`) — a single entry, else **404**.

## Governance overview

`GET /admin/overview` (`admin:read`) → **200**
```json
{
  "total_users": 42, "active_users": 39,
  "roles": 3, "projects": 17, "portfolios": 4,
  "audit_entries": 1280, "permission_catalogue_size": 90
}
```

## Diagnostics

`GET /admin/diagnostics` (`admin:read`) → **200** — runs a live DB connectivity
check:
```json
{ "status": "healthy", "database": "ok", "app_name": "…", "app_env": "production", "server_time": "2026-03-01T09:00:00Z" }
```
(The unauthenticated liveness probe remains at `GET /health`.)

## Permission reconciliation

New modules add permissions and system-role grants, but those only reach a tenant
**at registration**. A tenant created before a later module never received that
module's permissions on its system roles. Reconciliation backfills them.

`POST /admin/reconcile-permissions` (`admin:manage`) → **200**
```json
{
  "permissions_created": 4,
  "total_grants_added": 11,
  "roles": [
    { "role": "Organization Admin", "grants_added": 4 },
    { "role": "Project Manager", "grants_added": 5 },
    { "role": "Member", "grants_added": 2 }
  ],
  "detail": "Permission catalogue reconciled for this organization."
}
```
It (1) creates any catalogue permission missing globally, and (2) grants each
system role any catalogue-defined permission it lacks. **Extra/custom grants are
never removed.** Running it again is a no-op (`total_grants_added: 0`) —
idempotent by design.

## RBAC

Every route here is **Organization-Admin only**. A Member or Project Manager
(lacking `admin:read` / `admin:manage`) receives **403** on all of them.
