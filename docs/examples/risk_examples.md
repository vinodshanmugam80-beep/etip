# Risk Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `risk:read`,
`risk:create`, `risk:update`, `risk:delete`.

A **risk** belongs to a project. Its exposure is scored `probability × impact`
(each 1–5, so 1–25) and bucketed into a severity band. The project's
`risk_score` rollup tracks the highest open risk.

---

## Raise a risk

`POST /risks` (`risk:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "title": "Key vendor may miss integration deadline",
  "description": "Third-party API not yet stable",
  "category": "external",
  "probability": 4,
  "impact": 5,
  "response_strategy": "mitigate",
  "owner_user_id": null,
  "mitigation_plan": "Build a fallback adapter",
  "target_date": "2026-05-01"
}
```
- `category` ∈ `technical | schedule | cost | resource | scope | external | organizational | other`.
- `response_strategy` ∈ `avoid | mitigate | transfer | accept | escalate`.
- `probability` and `impact` are 1–5. `risk_score` (= product) and `severity`
  are **derived**, never set directly.
- Each risk gets a per-project `number` and starts in status `identified`.
- Unknown project → **404**; unknown `owner_user_id` → **422**.

### Severity bands (from score)
`1–4 → low`, `5–9 → medium`, `10–14 → high`, `15–25 → critical`.

## Status lifecycle

```
identified → analyzing | mitigating | monitoring | closed
analyzing  → mitigating | monitoring | closed
mitigating → monitoring | closed
monitoring → mitigating | closed
closed     → (terminal)
```
Illegal transitions → **422** (`illegal_status_transition`).

## Project `risk_score` rollup

The project's `risk_score` (Module 7 placeholder, now live) is kept equal to the
**highest score among open (non-closed) risks**. Closing or deleting the top
risk drops the rollup to the next; with no open risks it is `0`. Visible on
`GET /projects/{id}`.

## List / search

`GET /risks?project_id=<id>&status=mitigating&category=external&severity=critical&owner_user_id=<id>&q=vendor`
→ **200**, ordered by score (highest first):
```json
{ "items": [ /* Risk */ ], "total": 12, "limit": 50, "offset": 0 }
```

## Update / delete

`PATCH /risks/{id}` (`risk:update`) — partial update; changing `probability` or
`impact` re-scores the risk and refreshes the project rollup. A validated status
transition is applied here too.
`DELETE /risks/{id}` (`risk:delete`) — soft delete; the rollup is refreshed.

## Risk summary

`GET /projects/{project_id}/risk-summary` (`risk:read`) → **200**
```json
{
  "project_id": "<uuid>",
  "open_count": 7,
  "max_score": 20,
  "by_severity": [
    { "severity": "critical", "count": 1 },
    { "severity": "high", "count": 2 },
    { "severity": "medium", "count": 4 }
  ]
}
```
Counts consider **open** (non-closed) risks only.

Deleting a **project** soft-deletes its risks automatically.

## RBAC

The **Member** system role has `risk:read` (list/get/summary succeed) but not
`risk:create`/`update`/`delete` → those return **403**.
