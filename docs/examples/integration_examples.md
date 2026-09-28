# Integration Hub (Outbound Webhooks) — Examples

**ETIP 2.0 · Phase 5.** `BASE = http://localhost:8000/api/v1`. Requires
`Authorization: Bearer <token>`. Permissions: `integration:read` (Org Admin, PM,
Member), `integration:manage` (Org Admin, PM).

Push ETIP events to Slack, Teams, Jira or any HTTPS endpoint. An endpoint
subscribes to event types; when an event is published, ETIP POSTs a JSON payload
signed with the endpoint's secret (`X-ETIP-Signature: sha256=…`) and records the
delivery. Live delivery depends on the deployment's network egress.

---

## Event catalogue
`GET /integrations/events` → the subscribable events:
`project.created`, `project.updated`, `risk.raised`, `benefit.realized`,
`workflow.approved`, `milestone.overdue`.

## Register a webhook
`POST /integrations/webhooks` (`integration:manage`) → **201**
```json
{ "name": "Slack alerts", "target_url": "https://hooks.example.com/abc",
  "secret": "signing-secret", "event_types": ["risk.raised", "benefit.realized"] }
```
`target_url` must be http(s); unknown event types → **422**. The `secret` is never
returned — responses expose only `secret_set: true`.
`GET /integrations/webhooks?is_active=true`, `GET/PATCH/DELETE
/integrations/webhooks/{id}` (delete cascades its deliveries).

## Test a webhook
`POST /integrations/webhooks/{id}/test` → sends a synthetic ping and returns the
delivery record (`status: delivered|failed`, `status_code`, `error`).

## Publish an event
`POST /integrations/events/publish` (`integration:manage`) → **200**
```json
{ "event_type": "risk.raised", "payload": { "project": "ATLAS", "severity": "high" } }
```
```json
{ "event_type": "risk.raised", "endpoints_matched": 1, "delivered": 1, "failed": 0,
  "deliveries": [ { "status": "delivered", "status_code": 200, "event_type": "risk.raised" } ] }
```
Only active endpoints subscribed to the event receive it. The signed body is:
```json
{ "event": "risk.raised", "organization_id": "…", "timestamp": "…", "data": { … } }
```

## Delivery log
`GET /integrations/webhooks/deliveries?endpoint_id=…&status=failed` — a paginated,
filterable audit of every delivery attempt (status, code, attempts, error).

## Scope note
This delivers **outbound** webhooks on demand (test / publish). Auto-emitting
events from domain mutations (e.g. firing `project.created` when a project is
created) is a documented seam — wire `IntegrationService.publish(...)` into the
relevant services as a follow-up.

---

## Transactional outbox (auto-fired events)

Domain mutations record events in the **same transaction** as the change (via the
Unit of Work), so an event is never lost or emitted for rolled-back work — and the
request never blocks on webhook delivery. A worker/cron then dispatches them.

Auto-emitted today: `project.created` (project create), `risk.raised` (risk
create), `benefit.realized` (benefit fully realized), `workflow.approved` (gate
approval).

- `GET /integrations/outbox` — list queued/dispatched events.
- `POST /integrations/outbox/dispatch` — deliver pending events to subscribers
  (drive from a scheduler / Celery beat / cron):
  ```json
  { "dispatched": 5, "deliveries_created": 1 }
  ```
Mutations write to the outbox instantly; delivery (with the existing HMAC signing +
retry/backoff) happens out-of-band on dispatch.

## Hands-free scheduling (Celery beat)

In deployment the webhook system runs on its own — no manual dispatch needed:

- **`etip.integration.dispatch_outbox`** runs every **60s**, delivering pending
  outbox events to subscribers across all tenants.
- **`etip.integration.retry_due`** runs every **5 minutes**, retrying failed
  deliveries whose exponential-backoff window has elapsed.

Both are defined in `app/modules/integration/tasks.py` and scheduled via
`celery_app.conf.beat_schedule` (see `app/worker.py`). `docker-compose.yml` runs a
dedicated **`beat`** service alongside the `worker`. The orchestration is factored
into plain functions (`dispatch_all_pending`, `retry_all_due`) so it is unit-tested
without a broker; the `POST /integrations/outbox/dispatch` endpoint remains for
manual / on-demand runs.
