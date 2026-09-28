# Authentication — Example Requests & Responses

All examples assume `BASE = http://localhost:8000/api/v1`.

---

## Register organization + admin

`POST /auth/register` → **201 Created**

Request:
```json
{
  "organization_name": "Contoso Ltd",
  "admin_email": "admin@contoso.com",
  "admin_full_name": "Ada Admin",
  "password": "Str0ng-Passphrase!"
}
```

Response:
```json
{
  "id": "a3f1c9e2-...",
  "organization_id": "6b21d0aa-...",
  "email": "admin@contoso.com",
  "full_name": "Ada Admin",
  "is_active": true,
  "mfa_enabled": false,
  "last_login_at": null,
  "roles": [{ "id": "…", "name": "Organization Admin", "is_system": true }]
}
```

Duplicate organization → **409 Conflict**
```json
{ "error": { "code": "conflict", "message": "An organization with slug 'contoso-ltd' already exists.", "details": { "slug": "contoso-ltd" } } }
```

Weak password → **422 Unprocessable Entity** (schema validation).

---

## Login

`POST /auth/login` → **200 OK**

Request:
```json
{
  "organization_slug": "contoso-ltd",
  "email": "admin@contoso.com",
  "password": "Str0ng-Passphrase!"
}
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1Ni...",
  "refresh_token": "eyJhbGciOiJIUzI1NiI...",
  "token_type": "bearer",
  "expires_in": 900
}
```

Wrong password → **401** `{ "error": { "code": "authentication_error", ... } }`
MFA-enabled account without a code → **401** `code: "mfa_required"`
Locked account (>5 failures) → **401** `code: "account_locked"`

---

## Current user

`GET /auth/me` with `Authorization: Bearer <access_token>` → **200 OK**
returns the `UserResponse` shown above. Missing/invalid token → **401**.

---

## Refresh (rotation + reuse detection)

`POST /auth/refresh` → **200 OK**

Request: `{ "refresh_token": "<refresh_token>" }`
Response: a **new** access/refresh pair; the presented refresh token is revoked.

Replaying an already-rotated token → **401** and revokes the entire token
family (theft countermeasure).

---

## Logout

`POST /auth/logout` with `{ "refresh_token": "<refresh_token>" }` → **200 OK**
`{ "detail": "Logged out." }` (idempotent; revokes the token).

---

## MFA enrolment

`POST /auth/mfa/enroll` (bearer) → **200 OK**
```json
{ "secret": "JBSWY3DPEHPK3PXP", "otpauth_uri": "otpauth://totp/ETIP:admin@contoso.com?secret=...&issuer=ETIP" }
```

`POST /auth/mfa/verify` (bearer) with `{ "code": "123456" }` → **200 OK**
`{ "detail": "MFA enabled." }`. Subsequent logins then require `mfa_code`.
