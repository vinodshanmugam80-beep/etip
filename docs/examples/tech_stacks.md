# AI codegen — technology coverage

AI Delivery builds can target a **tech stack**; the generator emits a runnable
scaffold **plus a starter test** for it, and the LLM provider (when configured) is
prompted with the stack.

- `GET /api/v1/builds/tech-stacks` — the catalogue, grouped by category (29 stacks).
- `POST /api/v1/builds/detect-stack {"filenames":[...]}` — infer the stack + test
  framework from a repo's file list (e.g. `go.mod` → go-http/gotest, `next.config.js`
  → nextjs/jest, `pom.xml` → java-spring/junit).
- Create a build with `tech_stack`, then `POST /builds/{id}/generate`.

**Stacks (56):** static-html, react, vue, svelte, angular, nextjs, remix, sveltekit
(web); python-fastapi, python-fastapi-sqlmodel, python-flask, python-django,
node-express, nestjs, go-http, go-gin, java-spring, java-spring-jpa, kotlin-ktor,
dotnet-minimal, ruby-sinatra, php, php-laravel, rust-axum (backend/API); flutter,
react-native, swiftui (mobile); rust-cli (systems); data-python (data/ML); C, C++, Shell (systems).

**Starter tests** are added per language: pytest, jest, go test, JUnit, cargo test,
xUnit, PHPUnit, flutter_test, XCTest — so the pipeline has something to run.

Adding a stack (or a test framework) is a one-entry change in
`app/modules/aidelivery/codegen.py`.

## Depth + pipeline
- **Richer LLM generation** — the LLM provider now sends a **stack-aware prompt** that
  asks for a complete, multi-file app (CRUD, validation, DB wiring, JWT auth for
  backends; list/form/state for frontends) and returns a `{path: content}` map that
  ETIP parses into multiple files.
- **Test plan** — `GET /api/v1/builds/{id}/test-plan` returns the framework + command a
  CI runner uses (e.g. `pytest -q`, `go test ./...`, `npm test`).
- **Gate on tests** — set `gate_require_tests: true` on a build and a **production
  deploy is blocked until the latest `unit_test` run passes** (alongside coverage / p95).
