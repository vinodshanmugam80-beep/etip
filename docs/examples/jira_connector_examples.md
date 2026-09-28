# Jira Connector — Examples

**ETIP 2.0.** A packaged, two-way Jira sync built on ETIP's open hooks. Configuring
it requires `integration:manage`. `BASE = http://localhost:8000/api/v1`.

## 1. Connect Jira (admin, once)
`PUT /integrations/jira/config`
```json
{ "base_url": "https://your-org.atlassian.net", "project_key": "ETIP",
  "user_email": "bot@your-org.com", "api_token": "<Jira API token>",
  "webhook_secret": "<random secret>", "default_project_id": "<ETIP project uuid>",
  "is_enabled": true }
```
The **API token is never returned** (`GET` shows `token_set` only, and a `PUT` that
omits the token keeps the stored one). `default_project_id` is the ETIP project that
inbound Jira issues become tasks under.

## 2. Inbound — Jira issue → ETIP task
In Jira, add a webhook pointing at:
`{BASE}/integrations/jira/webhook/{organization_id}?secret=<webhook_secret>`
On `jira:issue_created` / `issue_updated`, ETIP upserts the matching task
(idempotent via an external-link map; Jira status → ETIP task status). A wrong secret
is rejected (401).

## 3. Outbound — ETIP task → Jira issue
`POST /integrations/jira/tasks/{task_id}/push` — creates the Jira issue in
`project_key` (or updates it if already linked) and records the link, so repeated
pushes update rather than duplicate.

## Honest scope
- Built on the REST API + webhook hooks; the Jira REST calls are covered by tests via
  a mock. **Validate against a live Jira Cloud instance in staging** — confirm the
  API token, webhook secret, and issue-type/status names for your project.
- v1 syncs summary, description and status for tasks; richer field mapping and status
  *transitions* are a follow-up.
