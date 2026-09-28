# API Keys (Service-Account Auth) — Examples

**ETIP 2.0.** `BASE = http://localhost:8000/api/v1`. Managing keys requires
`apikey:manage` (Org Admin). External tools then authenticate with the key via the
`X-API-Key` header — no human login.

A key acts as a **user identity** (a service-account user is recommended); its
effective permissions are that user's roles. Only a SHA-256 hash is stored — the
plaintext secret is shown **once**, at creation.

---

## Issue a key
`POST /api-keys` (`apikey:manage`) → **201**
```json
{ "name": "Jira Integration", "user_id": "<service-account user, optional>", "expires_date": "2027-01-01" }
```
Response (the only time the secret appears):
```json
{ "id": "…", "name": "Jira Integration", "prefix": "etip_oGnp1ek",
  "is_active": true, "api_key": "etip_XXXXXXXX…" }
```
`GET /api-keys` lists keys (metadata only — never the secret or hash).
`POST /api-keys/{id}/revoke` deactivates a key; `DELETE /api-keys/{id}` removes it.

## Authenticate with a key
Send the plaintext key in the `X-API-Key` header on any REST call:
```bash
curl https://…/api/v1/projects -H "X-API-Key: etip_XXXXXXXX…"
```
- Works anywhere a bearer JWT works; RBAC is enforced via the linked user's roles.
- Invalid, revoked, expired, or inactive-user keys → **401**.

## Why it matters
This is the inbound half of the integration story: Jira, Microsoft Project, Azure
DevOps, CI pipelines and data jobs can call the ETIP REST API securely without a
human account — issue a scoped, revocable, optionally-expiring key per system.
