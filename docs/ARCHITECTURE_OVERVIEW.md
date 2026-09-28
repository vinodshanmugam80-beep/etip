# ETIP — Architecture Overview

**Enterprise Transformation Intelligence Platform.** A multi-tenant PPM
(project & portfolio management) backend: 25 modules, one coherent codebase,
built in Python 3.12 on FastAPI, SQLAlchemy 2.x, and Pydantic v2.

This document is the map. Per-module request/response detail lives in
`docs/examples/`; conventions live in `docs/STANDARDS.md`; the layer contract
lives in `docs/ARCHITECTURE.md`. This file explains how the whole thing fits.

---

## 1. What it is

ETIP lets an organization plan, execute, govern, and report on a transformation
portfolio. A tenant registers, receives seeded roles, and works down a hierarchy
of **portfolio → program → project**, then manages execution (tasks, sprints,
resources, dependencies, milestones, timesheets), governance (finance, risks,
issues, RAID, change control), and collaboration (documents, meetings,
notifications) — with an intelligence layer on top (reports, dashboards, a
grounded copilot) and an administration surface underneath (audit, diagnostics,
permission reconciliation).

Every request is scoped to one tenant; nothing crosses the organization boundary.

## 2. Layered architecture

The codebase enforces a strict, one-directional dependency flow:

```
   HTTP request
        │
        ▼
   Router (FastAPI)     — thin adapter: validate (Pydantic), call service, map result
        │
        ▼
   Service              — business rules; framework-agnostic; raises domain errors
        │
        ▼
   Repository           — data access; tenant-scoped queries; soft-delete aware
        │
        ▼
   Database (SQLAlchemy ORM)
```

The **one rule that shapes everything**: a service may depend on another
module's **repository**, but never on another module's **service**. This keeps
the dependency graph acyclic. When a feature needs shared cross-module logic
(assembling a report from nine modules' data), that logic is extracted into a
**service-independent helper** — `ReportEngine` — which both the Reports and
Dashboards services, and the Copilot, use. No cycles, ever.

Cross-module reads use string foreign keys or plain UUID columns (never Python
imports between models), so modules stay independently migratable.

## 3. The 25 modules, by layer

**Identity & access**
1. Auth — tenant registration, Argon2id passwords, JWT access/refresh with
   rotation + reuse-detection, TOTP MFA, lockout, RBAC.
2. Organization — business units, hierarchical departments, settings.
3. User — admin user lifecycle, roles, password reset.
4. Roles & Permissions (`rbac`) — custom roles, grant/revoke, system-role guards.

**Portfolio hierarchy**
5. Portfolio · 6. Program · 7. Project (the flagship aggregate: health, stage,
budget/forecast/actual rollups, team, comments).

**Execution & scheduling**
8. Task · 9. Sprint · 10. Resource (allocation, over-allocation sweep) ·
16. Dependency (polymorphic, cycle detection) · 17. Milestone · 18. Timesheet
(submit → approve workflow, hours rollup).

**Governance & control**
11. Finance (ledger + rollup) · 12. Risk (score, syncs project) · 13. Issue ·
14. RAID (actions + decisions) · 15. Change Request (separation of duties).

**Collaboration**
19. Documents (version lineages) · 20. Meetings (attendees; action items flow
into the RAID log) · 21. Notifications (per-user inbox, mute preferences).

**Intelligence**
22. Reports (saved definitions + a cross-module engine) · 23. Dashboards (widget
layouts rendered live via the engine) · 24. AI Copilot (grounded NL assistant).

**Administration**
25. Admin — audit-log access, governance overview, diagnostics, permission
reconciliation.

## 4. Cross-cutting patterns

These recur by design; recognizing them makes any module predictable.

- **Rollups.** A source module owns detail records and writes a summary field on
  the project: `forecast`/`actual_cost` ← Finance, `risk_score` ← max open Risk,
  `issue_count` ← open Issues, `logged_hours` ← approved Timesheets.
- **Deletion taxonomy.** Deleting a parent **blocks** (409) on independently
  managed children, **cascade-soft-deletes** intrinsic children, and
  **unassigns** associations. Project delete cascades tasks, financials, risks,
  issues, RAID, changes, dependencies, milestones, meetings, time entries.
- **Separation of duties.** Approvals (Change, Timesheet) require a distinct
  `*:approve` permission and dedicated endpoints; a plain status PATCH is
  refused.
- **Per-record ownership scoping.** Coarse RBAC gates the endpoint; the service
  scopes personal resources to the caller. Fetching another user's resource
  returns **404**, not 403 — it doesn't exist *for you*. Used by Notifications,
  Reports, Dashboards, and Copilot conversations. Reports/Dashboards add a
  *shared* dimension (visible if owned **or** shared) while keeping edit/delete
  owner-only.
- **The report engine as a shared read-side.** `ReportEngine` composes six report
  types from nine modules' repositories. Reports run and save it; Dashboards
  render widgets through it; the Copilot answers questions with it — all without
  a service-to-service dependency.
- **Grounded answers.** The Copilot never invents figures: it resolves intent and
  entity, runs the engine, and composes replies from real data, attaching that
  data as `grounding`. Classification and phrasing are the only pluggable
  (LLM-ready) seams.

## 5. Request lifecycle

1. Middleware assigns a request id and logs the request.
2. The router's `require_permission(...)` dependency authenticates the JWT,
   loads the current user, and checks the permission.
3. A per-request **Unit of Work** opens one session / one transaction.
4. The service runs business rules against repositories, and calls
   `uow.record_audit(...)` on every mutation.
5. The router calls `uow.commit()`; domain exceptions are mapped by a central
   handler to `{"error": {code, message, details}}`.

Every mutation, in every module, appends to an **append-only audit log** — which
Module 25 finally exposes for reading.

## 6. Data & security model

- **Multi-tenancy.** `TenantMixin` puts `organization_id` on tenant-owned
  entities; `BaseRepository` scopes every query to it. Permissions are the one
  global catalogue; roles and their grants are per-tenant.
- **Soft deletes + optimistic locking.** `BaseEntity` carries `is_deleted`,
  audit columns, and a `version` column for optimistic concurrency.
- **RBAC.** System roles (Organization Admin = all permissions, Project Manager,
  Member) are seeded at registration. Custom roles are per-tenant.
- **Auth.** Argon2id hashing, short-lived access tokens, rotating refresh tokens
  with reuse-detection, optional TOTP MFA, and account lockout.

## 7. Operations

- **Migrations.** Alembic; an `_include_object` hook keeps autogenerated
  migrations clean on SQLite (the CI/dev database). The chain applies forward and
  downgrades cleanly.
- **Permission reconciliation.** New modules add permissions and system-role
  grants that only reach a tenant at registration. `POST
  /admin/reconcile-permissions` backfills them for an existing tenant, and an
  optional **startup job** (`reconcile_on_startup`) self-heals *every* tenant on
  boot. Both are idempotent and never remove custom grants.
- **Health.** `GET /health` is an unauthenticated liveness probe;
  `GET /admin/diagnostics` adds an authenticated readiness check with live DB
  connectivity.
- **Quality gate.** Every module ships green: `ruff` + `ruff format` +
  `mypy --strict` + `pytest`. ~245 integration tests, ~96% coverage.

## 8. Extending the platform

A new module follows the same shape every time: create `app/modules/<name>/`
(models, schemas, repository, service, router, `__init__`); include the router
in `app/api/v1/router.py`; register models in `alembic/env.py`; add `<name>:*`
permissions to `app/modules/auth/seeds.py`; add a dependency provider in
`app/core/dependencies.py`; generate a migration; write tests; document in
`docs/examples/`. The layer contract and the patterns above do the rest.
