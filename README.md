## Quick start (one command)

**macOS / Linux:** `./run.sh`  **Windows:** double-click `run.bat`

This creates the virtual environment, installs, migrates, seeds demo data (first run), starts the server, and opens the dashboard at http://localhost:8000/. Sign in with org `demo-transformation-co`, `admin@demo.co` / `Str0ng-Passphrase!1`.

# ETIP — Enterprise Transformation Intelligence Platform

**Plan. Execute. Govern. Transform.**

An enterprise Project, Program, Portfolio & Transformation Management platform.
Built as a modular monolith with clean architecture, multi-tenancy, and
enterprise-grade security.

> **Status:** All **25** modules complete (Auth, Organization, User, Roles &
> Permissions, Portfolio, Program, Project, Task, Sprint, Resource, Finance,
> Risk, Issue, RAID, Change Requests, Dependencies, Milestones, Timesheets,
> Documents, Meetings, Notifications, Reports, Dashboards, AI Copilot,
> Administration) — built and tested (252 integration tests, ~96% coverage,
> `ruff`/`mypy --strict` clean, 23-migration chain applying with working
> downgrades).
>
> **ETIP 2.0 (in progress):** an additive Intelligence Layer is layered on top
> without modifying V1. **Phase 1 (Intelligence core) is complete** — Performance
> (EVM), Variance, Forecast, Executive KPI + Heat Map, and Recommendation +
> Transformation Intelligence engines: EVM health, variance, forecasts, RAG heat
> maps, an executive scorecard, prioritised recommendations, and a consolidated
> transformation briefing. Shared EVM primitives in `intelligence/evm.py`; all
> engines are service-independent and pure read (no schema change). 274 tests.
>
> **Phase 2a — Benefits Realization & ROI** is complete: a new `benefits` table
> and module (categories, lifecycle, target/realised/investment) with computed
> realisation %, ROI and benefits variance, plus project/program/portfolio
> rollups. First Phase 2 schema change — 24-migration chain. 285 tests.
>
> **Phase 2b — Skills Matrix** is complete: new `skills` and `resource_skills`
> tables — a skill catalogue plus per-resource proficiency — with the
> resources×skills matrix, skill coverage (staffing), and skill capacity supply.
> Additive over Module 10 (its freeform `skills` JSON is untouched). 25-migration
> chain. 292 tests.
>
> **Phase 2c — Strategic Initiatives / Business Goals** completes Phase 2: new
> `strategic_initiatives`, `business_goals` and `goal_kpis` tables forming an
> Initiative → Goal → KPI hierarchy, with computed KPI attainment, variance and
> target-met — the data source that unblocks KPI-vs-target variance. 26-migration
> chain. 301 tests.
>
> **Phase 3a — Stage-Gate / Workflow / Approval engine** is complete: new
> `workflow_definitions`, `workflow_stages`, `workflow_instances` and
> `gate_approvals` tables — a reusable governance workflow any record can attach
> to, with ordered gates, approval decisions and enforced separation of duties
> (the approver can't be the initiator). 27-migration chain. 313 tests.
>
> **Phase 3b — Vendor / Procurement / Contracts** completes Phase 3: new
> `vendors`, `contracts` and `purchase_orders` tables — suppliers, agreements and
> spend commitments (committed vs invoiced → outstanding), with vendor-spend,
> contract-utilization and project-procurement rollups. 28-migration chain. 322 tests.

---

## Tech stack

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL, Redis,
Celery, RabbitMQ, Pydantic v2, JWT/OAuth2, Argon2, TOTP MFA.
**Infra:** Docker, Docker Compose, Nginx, GitHub Actions, Prometheus, Grafana.

See `docs/ARCHITECTURE.md` and `docs/STANDARDS.md` for the full design.

---

## Quickstart (local, without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# For a quick spin-up without Postgres you may set:
#   DATABASE_URL=sqlite:///./etip.db
# Generate a real secret:
#   python -c "import secrets; print(secrets.token_hex(32))"  -> JWT_SECRET_KEY

alembic upgrade head
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** for Swagger UI.

## Quickstart (Docker Compose)

```bash
cp .env.example .env      # set JWT_SECRET_KEY
docker compose up --build
# API:      http://localhost:8000/docs
# RabbitMQ: http://localhost:15672  (guest/guest)
```

## Run the tests

```bash
APP_ENV=test JWT_SECRET_KEY=test-secret-key-32-bytes-long-xxxx \
  pytest --cov=app --cov-report=term-missing
```

By default the suite runs on an isolated in-memory SQLite database. To run it
against **PostgreSQL** (as CI does), point it at a Postgres DSN:

```bash
TEST_DATABASE_URL=postgresql+psycopg://etip:etip@localhost:5432/etip_test \
APP_ENV=test JWT_SECRET_KEY=test-secret-key-32-bytes-long-xxxx pytest -q
```

The GitHub Actions pipeline (`.github/workflows/ci.yml`) runs lint, `mypy
--strict`, the migration chain, and the full test suite **on PostgreSQL 16** on
every push and pull request.

## Seed a demo dataset

With the server running, populate a realistic demo (portfolios, green/amber/red
projects, benefits, an initiative with KPIs, a vendor with a contract and PO):

```bash
python scripts/seed_demo.py     # prints login details + intelligence URLs to try
```

## Executive dashboard (read-only UI)

The app serves a single-page executive dashboard — a read-only "face" over the
Intelligence Layer — at the site root:

```
http://localhost:8000/            # redirects to /dashboard
```

Sign in with your org slug + admin credentials (pre-filled with the demo values
if you ran `seed_demo.py`). It renders transformation health (RAG, SPI/CPI,
success score), the project portfolio with earned-value health, benefits
realization, KPI attainment, and prioritized recommendations — all live from the
API. No build step; it is plain HTML/JS served same-origin by the app.

---

## Try the auth flow

```bash
BASE=http://localhost:8000/api/v1

# 1) Register an organization + admin
curl -s -X POST $BASE/auth/register -H 'Content-Type: application/json' -d '{
  "organization_name": "Contoso Ltd",
  "admin_email": "admin@contoso.com",
  "admin_full_name": "Ada Admin",
  "password": "Str0ng-Passphrase!"
}'

# 2) Log in
curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' -d '{
  "organization_slug": "contoso-ltd",
  "email": "admin@contoso.com",
  "password": "Str0ng-Passphrase!"
}'
# -> { "access_token": "...", "refresh_token": "...", "token_type": "bearer", "expires_in": 900 }

# 3) Call a protected endpoint
curl -s $BASE/auth/me -H "Authorization: Bearer <access_token>"
```

See `docs/examples/auth_examples.md` for full request/response samples.

---

## Project structure

```
app/
  core/          config, security, logging, exceptions, middleware, DI
  db/            declarative base + audit mixins, session, unit of work
  repositories/  generic repository base
  modules/
    auth/        model, schemas, repository, service, router, seeds
    organization/ business units, departments, settings, memberships
    user/        admin user CRUD, search, roles, password management
    rbac/        custom roles, permission grants, catalogue
    portfolio/   portfolios, status lifecycle, strategic objectives
    program/     programs nested under portfolios
    project/     projects, team members, comments, tags, custom fields
    task/        tasks, subtasks, assignees, lifecycle, estimates
    sprint/      sprints, lifecycle, task assignment
    resource/    resources, allocations, over-allocation detection
    finance/     cost ledger, rollups, financial summary
    risk/        risk register, probability×impact scoring, rollup
    issue/       issue tracker, workflow, issue_count rollup
    raid/        RAID log: actions, decisions, consolidated summary
    change/      change requests, approval workflow, separation of duties
    dependency/  cross-entity dependencies, cycle detection
    milestone/   schedule checkpoints, overdue tracking, summary
    timesheet/   time entries, approval workflow, hours rollup
    document/    attachment metadata, polymorphic owners, versioning
    meeting/     meetings, attendees, action items into the RAID log
    notification/ per-user inbox, read state, mute preferences
    report/      saved report definitions, cross-module report engine
    dashboard/   configurable widget layouts rendered via the report engine
    copilot/     grounded NL assistant over the report engine + conversations
    admin/       audit-log access, overview, diagnostics, permission reconcile
    intelligence/ ETIP 2.0 analytics layer; engines/performance.py = EVM engine
    benefit/     ETIP 2.0 benefits realization & ROI (target/realised/variance)
    skill/       ETIP 2.0 skills matrix (catalogue, proficiency, capacity)
    initiative/  ETIP 2.0 strategic initiatives → business goals → KPIs
    workflow/    ETIP 2.0 stage-gate governance (definitions, gates, approvals)
    vendor/      ETIP 2.0 vendor / procurement / contracts (POs, spend rollups)
    integration/ ETIP 2.0 Integration Hub — outbound webhooks (HMAC-signed, retry/backoff)
    apikey/      ETIP 2.0 API keys — service-account auth (X-API-Key) for external tools
    sso/         ETIP 2.0 SSO — per-tenant OIDC single sign-on with JIT provisioning
    aidelivery/  ETIP 2.0 AI Delivery — control plane + pluggable code-gen (template / LLM via CODEGEN_API_KEY)
                 + transactional outbox (app/db/base.py OutboxEvent) — auto-fires webhooks on domain events
                 + Celery beat auto-dispatch (app/modules/integration/tasks.py): dispatch every 60s, retries every 5m
                 + intelligence/engines/resource_forecast.py (time-phased demand)
  api/v1/        versioned router aggregation
  main.py        application factory
alembic/         migration environment + versions
tests/           integration tests + fixtures
docs/            ARCHITECTURE.md, STANDARDS.md, examples/
deploy/          nginx config
.github/         CI pipeline
```

## License

Proprietary — © ETIP.
