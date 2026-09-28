# ETIP — Engineering Standards

Binding standards for every module. "Production quality, no placeholders, no
TODOs" is enforced by review and CI.

---

## 1. Coding standards

- **Python 3.11+**, modern typing (`X | None`, `list[X]`, `Mapped[...]`).
- **Every public class and function has a docstring** describing purpose,
  parameters, returns and raised exceptions.
- **Full type hints** on every function signature; `mypy --strict` in CI.
- **No business logic in routers**; no SQL in services; no framework imports in
  the service layer.
- **No duplicated logic** — shared behaviour lives in `BaseEntity`,
  `BaseRepository`, `UnitOfWork`, and `app/core`.
- **No `TODO`/`FIXME`/placeholder** code merges to `main`.
- **Formatting & linting** — `ruff format` + `ruff check` (rules: `E,F,I,N,UP,
  B,C4`), zero warnings.

## 2. Naming standards

| Element | Convention | Example |
| --- | --- | --- |
| Module package | singular, snake_case | `app/modules/project/` |
| ORM model | PascalCase, singular | `RefreshToken` |
| Table name | snake_case, plural | `refresh_tokens` |
| Pydantic request | `<Action><Entity>Request` | `RegisterOrganizationRequest` |
| Pydantic response | `<Entity>Response` | `UserResponse` |
| Repository | `<Entity>Repository` | `UserRepository` |
| Service | `<Context>Service` | `AuthService` |
| Permission code | `resource:action` | `project:create` |
| Boolean column | `is_` / `has_` prefix | `is_deleted` |
| Timestamp column | `_date` / `_at` suffix | `created_date`, `locked_until` |

## 3. API standards

- **Base path** `/api/v1`. Nouns, plural resources; verbs only for actions that
  are not CRUD (`/auth/login`, `/mfa/verify`).
- **Status codes** — `201` create, `200` read/update, `204` delete, `4xx`
  client errors via the domain-exception envelope, `5xx` server errors.
- **Every endpoint** has: a `summary`, a `response_model`, request/response
  schemas with `json_schema_extra` examples (rendered in Swagger), and tests.
- **Consistent error envelope**: `{ "error": { code, message, details } }`.
- **Pagination** via `limit`/`offset`; **sorting** and **filtering** via typed
  query params. Never accept `organization_id` from the client — it is bound
  from the token.
- **OpenAPI** is generated at `/api/v1/openapi.json`; Swagger UI at `/docs`,
  ReDoc at `/redoc`.

## 4. Per-module deliverables

Every module ships **all** of: SQLAlchemy model, Pydantic schemas, repository,
service, router, Alembic migration, unit + integration tests, Swagger examples,
and example request/response docs. No file is skipped.

## 5. Testing strategy

- **Pyramid** — many fast unit tests (services with fakes), fewer integration
  tests (full ASGI app against an in-memory DB), a thin end-to-end layer.
- **Integration tests drive the real app** through HTTP via `TestClient`, so
  routing, validation, DI, middleware, and error handling are all exercised.
- **Coverage gate** — CI fails under 85%. (Auth module currently 93%.)
- **Security-critical paths are explicitly tested**: token rotation, refresh
  reuse detection, RBAC denial, MFA enforcement, account lockout.
- Tests are deterministic and isolated (fresh schema per test, no shared state).

## 6. Versioning strategy

- **API** — URL-versioned (`/api/v1`). Breaking changes introduce `/api/v2`;
  the previous version is supported through a documented deprecation window.
- **Application** — Semantic Versioning (`MAJOR.MINOR.PATCH`).
- **Database** — Alembic migrations are the single source of truth; every
  schema change is a migration, forward-only in production. `Base.metadata`
  is never used to create schema outside tests.
- **Data concurrency** — per-row optimistic locking via the `version` column.

## 7. Branching strategy

**Trunk-based with short-lived branches.**

- `main` is always releasable and protected (no direct pushes).
- Work happens on `feature/<ticket>-<slug>`, `fix/<ticket>-<slug>`,
  `chore/<slug>`; branches are short-lived and rebased on `main`.
- Merges are squash-merges via reviewed Pull Requests; at least one approval and
  green CI are required.
- Releases are cut from `main` and tagged `vMAJOR.MINOR.PATCH`.
- Commit messages follow **Conventional Commits** (`feat:`, `fix:`, `refactor:`,
  `test:`, `docs:`, `chore:`).

## 8. CI/CD pipeline

Implemented in `.github/workflows/ci.yml`. On every push and PR:

1. **Lint** — `ruff check` + `ruff format --check`.
2. **Type check** — `mypy --strict`.
3. **Test** — `pytest` with coverage against a Postgres service container;
   the coverage gate fails the build under threshold.
4. **Migrations** — `alembic upgrade head` on a clean database to prove
   migrations apply.
5. **Build** — build the Docker image (on `main`).
6. **Publish/Deploy** — push the image and roll out (environment-gated;
   staging auto, production on manual approval).

Secrets come from the CI secret store; nothing sensitive is committed.
