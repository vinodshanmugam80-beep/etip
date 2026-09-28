# AI Copilot — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>` and the `copilot:use` permission (held by
all system roles). Every conversation is **private to its owner**.

The copilot answers natural-language questions **grounded in live platform data**:
it resolves an intent and a target project/portfolio, runs the shared report
engine, and composes a reply from the returned figures — which are also attached
as `grounding` (provenance). The numbers always come from the database.

> **Design note.** Intent classification and phrasing are deterministic and
> rule-based here. An LLM plugs in behind two seams — `classify_intent` and
> answer composition — without changing retrieval, grounding, or persistence.
> Because answers are assembled from real repository data, the surface cannot
> fabricate figures.

---

## Ask a one-off question

`POST /copilot/ask` → **200**
```json
{ "question": "How is ATLAS doing?", "context": {} }
```
```json
{
  "intent": "project_status",
  "answer": "ATLAS (Atlas migration) is active with green health. Budget 100000.00, actual cost 12000.00 (variance 88000.00). Risk score 12, 3 open issue(s).",
  "grounding": {
    "intent": "project_status",
    "parameters": { "project_id": "…" },
    "data": { "code": "ATLAS", "status": "active", "budget": "100000.00", … }
  }
}
```

### What it understands
Intent is classified from the **question text**; the target is resolved from the
text (a project/portfolio **code** like `ATLAS`) or from `context`.

| Ask about… | Example | `intent` |
|------------|---------|----------|
| project status | "how is ATLAS doing?" | `project_status` |
| risks / issues / actions | "open risks for ATLAS" | `raid_summary` |
| milestones | "is ATLAS overdue?" | `milestone_status` |
| logged hours | "hours on ATLAS" | `timesheet_hours` |
| budget / cost | "ATLAS budget" | `financial_summary` |
| a portfolio | "overview of the GROWTH portfolio" | `portfolio_overview` |
| capabilities | "what can you do?" | `help` |

### Resolving the target from context
Context aids **entity** resolution (not intent — the keyword must still be in the
text):
```json
{ "question": "How is it doing?", "context": { "project_id": "…" } }
{ "question": "status?", "context": { "project_code": "ATLAS" } }
```

### Clarification & fallback
- A project-scoped question with no resolvable project → `intent: needs_project`,
  "Which project? Please name it by its code."
- A portfolio question with no resolvable portfolio → `intent: needs_portfolio`.
- No recognizable intent → `intent: unknown`, with guidance.

## Conversations (private, persisted)

- `POST /copilot/conversations` — body `{ "title": "…" }` (defaults to
  "New conversation"). → **201**
- `GET /copilot/conversations` — the caller's own conversations (newest first).
- `GET /copilot/conversations/{id}` — one of the caller's own, else **404**.
- `POST /copilot/conversations/{id}/ask` — answer **and persist** both turns:
  ```json
  { "question": "How is ATLAS doing?", "context": {} }
  ```
  → **200** `{ conversation_id, question, intent, answer, grounding, assistant_message_id }`.
  The user turn and the grounded assistant turn are saved as messages; an
  untouched conversation is auto-titled from its first question.
- `GET /copilot/conversations/{id}/messages` — the turns in order (user, then
  assistant); assistant turns carry `intent` and `grounding`.
- `DELETE /copilot/conversations/{id}` — soft-deletes the conversation and its
  messages.

## Scoping

Conversations are strictly personal: a different user gets **404** on every
conversation route (get, messages, ask, delete) — the resource does not exist
*for them*. Any user with `copilot:use` can still ask their own ad-hoc questions.
