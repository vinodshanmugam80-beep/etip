# AI Delivery — Examples

**ETIP 2.0.** `BASE = http://localhost:8000/api/v1`. `build:read` (Org Admin, PM,
Member) to view; `build:manage` (Org Admin, PM) to create builds and report runs.

ETIP is the **control plane** for AI-assisted software delivery — it plans, tracks
and governs a **generate → test → deploy** pipeline for an application, website,
web app, mobile app or API/service. It does **not** itself generate code or deploy:
external AI codegen tools, AI test tools and CI/CD systems authenticate (typically
with an **API key**) and report progress by creating pipeline runs. ETIP advances
the build's lifecycle and fires `build.deployed` / `build.failed` webhooks.

---

## Open a build request
`POST /builds` (`build:manage`) → **201**
```json
{ "title": "Customer portal web app", "target_type": "web_app",
  "spec": "React portal with SSO and a dashboard", "repository_url": "https://github.com/acme/portal",
  "project_id": "<optional ETIP project to link to>" }
```
`target_type`: `web_app` · `website` · `mobile_app` · `api_service` · `other`.
Status starts at `requested`.

## Report a pipeline run (external AI / CI-CD tools)
Your AI codegen tool, AI test runner and CI/CD pipeline call this — usually
authenticated with `X-API-Key` (see the API keys doc):
`POST /builds/{id}/runs` (`build:manage`) → **201**
```json
{ "stage": "deploy", "status": "passed", "provider": "github-actions",
  "external_ref": "gha-1234", "logs_url": "https://…", "message": "Deployed to staging" }
```
`stage`: `generate` · `test` · `deploy`. `status`: `running` · `passed` · `failed`.

Runs advance the build automatically:

| stage / status | build becomes | event fired |
|---|---|---|
| generate / passed | `generated` | — |
| test / passed | `tested` | — |
| deploy / passed | `deployed` | `build.deployed` |
| any / failed | `failed` | `build.failed` |

A `deployed`, `failed` or `cancelled` build is terminal and rejects further runs (**409**).

## Track & govern
- `GET /builds?status=deployed&target_type=web_app&project_id=…` — filter the portfolio of builds.
- `GET /builds/{id}` · `PATCH /builds/{id}` · `POST /builds/{id}/cancel`.
- `GET /builds/{id}/runs` — the full generate/test/deploy history.
- `build.deployed` / `build.failed` flow through the transactional outbox to your
  webhook subscribers (Slack/Teams/Jira), delivered by Celery beat.

## Honest scope
ETIP is the system-of-record, governance and integration hub for AI delivery — the
actual code generation, AI testing and deployment are performed by the external
tools that plug in via these hooks (REST API in, webhooks out, API-key auth).

---

## ETIP-run generation (the "generate" stage)

ETIP can perform the *generate* stage itself via a **pluggable code-generation
provider** (`app/modules/aidelivery/codegen.py`):

- **`template`** (default, no key) — a deterministic scaffold generator. Produces a
  real, runnable single-file `index.html` for web/website/mobile targets, or a
  FastAPI `main.py` + `requirements.txt` for `api_service`. Always works.
- **`anthropic` / `openai`** — calls a configured LLM to generate the app from the
  build's `spec`. Activated by settings; the HTTP call is isolated (and mockable):

```
CODEGEN_PROVIDER=anthropic
CODEGEN_API_KEY=sk-...          # your key — enables real LLM generation
CODEGEN_MODEL=claude-sonnet-4-6
```

Run it:
`POST /builds/{id}/generate` (`build:manage`) → **200**
```json
{ "build_request_id": "…", "status": "generated", "provider": "template",
  "summary": "Generated a single-file web app scaffold (index.html).",
  "files": { "index.html": "<!doctype html>…" } }
```
This records a `generate` pipeline run, stores the output on the build, and advances
its status to `generated`. **Honest scope:** with no key it emits a real scaffold;
plug in your LLM key and it generates the full app from the spec. ETIP orchestrates,
governs and stores; the model does the authoring.

---

## Full SDLC lifecycle

The pipeline models the whole software lifecycle. External CI/CD + test tools
(authenticated via API keys) report each stage; ETIP advances the build and stores
metrics.

**Stages** (`POST /builds/{id}/runs` with a `stage` + `status` + optional `metrics`):
`generate` → `build` (compile) → `unit_test` → `qa` → `deploy` → `perf_test`.

| stage / status | build becomes | notes |
|---|---|---|
| generate / passed | generated | |
| build / passed | built | compile step |
| unit_test / passed | tested | report `metrics: {tests, passed, coverage}` |
| qa / passed | qa_passed | |
| deploy / passed | deployed | fires `build.deployed` |
| perf_test / passed | validated | report `metrics: {p95_ms, rps, error_rate}` |
| any / failed | failed | fires `build.failed` |

**Multiple environments** — record deploys per environment:
`POST /builds/{id}/deployments` → `{ "environment": "staging", "status": "deployed", "release_version": "1.2.0", "url": "https://staging.example.com" }`
(`environment`: `dev` · `staging` · `production`). `GET /builds/{id}/deployments` lists them.

**Code editor** — `GET /builds/{id}/files` returns the current source files; `PUT
/builds/{id}/files` saves edits (used by the dashboard's in-browser editor).

**Dashboard** — the **AI Delivery** tab shows the build list, a pipeline stage
board, the code editor, per-stage metrics, and per-environment deployments.

**Honest scope:** ETIP orchestrates, edits, governs, stores and visualizes the
lifecycle and its metrics. The actual compile / test / deploy / load-test execution
is performed by your CI/CD and test tools (which report results via these hooks) or
the provider seams — not simulated inside ETIP.

---

## Reference CI/CD: make your pipeline ETIP's executor

Two files turn a real pipeline into the executor behind this control plane:

- `scripts/etip_report.py` — a stdlib reporter that calls ETIP's API with an API key.
- `docs/examples/ci/ai-delivery.yml` — a reference GitHub Actions workflow.

**Setup (once):** in ETIP, open the build in the AI Delivery tab and issue an API
key (API Keys tab). In your app repo's Actions settings add secrets `ETIP_URL`,
`ETIP_API_KEY` and variable `ETIP_BUILD_ID`. Copy both files into the app repo.

**Then, on every push**, your real build/test/deploy runs and reports back:
```bash
python scripts/etip_report.py run    --stage build     --status passed
python scripts/etip_report.py run    --stage unit_test --status passed --metrics '{"coverage": 91.4}'
python scripts/etip_report.py run    --stage qa        --status passed
python scripts/etip_report.py deploy --environment staging --url https://staging.example.com
python scripts/etip_report.py run    --stage perf_test --status passed --metrics '{"p95_ms": 180, "rps": 500}'
```
ETIP advances the build through the lifecycle, records per-environment deployments
and metrics, and fires `build.deployed` / `build.failed` webhooks — so your actual
CI/CD does the work and ETIP governs and reports it.
