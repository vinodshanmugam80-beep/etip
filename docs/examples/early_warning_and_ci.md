# Early warning + CI reporters

## Early-warning intelligence
Leading indicators that flag a project **before** it turns red. Rule-based and
transparent (not a black box), each signal carries a recommended action.

- `GET /intelligence/early-warning` — signals across all active projects, with
  `projects_warning` / `projects_watch` counts.
- `GET /intelligence/early-warning/projects/{id}` — signals for one project.

Signals: `schedule_drift` (SPI slipping while still amber), `cost_drift` (CPI
dropping), `burn_ahead` (spend outrunning progress), `risk_exposure` (high open-risk
score), `stalled` (past baseline start, not begun), `deadline_pressure` (deadline
near with low progress). Level is `warning` / `watch` / `clear`.

## CI reporters (GitHub, GitLab, Jenkins)
`scripts/etip_report.py` is CI-agnostic. Reference pipelines in `docs/examples/ci/`:
- `ai-delivery.yml` — GitHub Actions
- `.gitlab-ci.yml` — GitLab CI
- `Jenkinsfile` — Jenkins (declarative)

Each runs the real build/test/QA/deploy/perf steps and reports outcomes + metrics
back to an ETIP build via `X-API-Key` (secrets `ETIP_URL`, `ETIP_API_KEY`, variable
`ETIP_BUILD_ID`).
