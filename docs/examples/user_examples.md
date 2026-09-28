# User Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1/users`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `user:create`,
`user:read`, `user:update`, `user:delete`. The self-service password change is
available to any authenticated user for their own account.

---

## Create a user

`POST /users` → **201** (requires `user:create`)
```json
{
  "email": "member@contoso.com",
  "full_name": "Mel Member",
  "password": "Initial-Passphrase!1",
  "role_ids": [],
  "must_change_password": true
}
```
Email is unique per organization (duplicate → **409**); the password must meet
the strength policy (**422** otherwise); unknown `role_ids` → **422**.

## List & search

`GET /users?q=alice&is_active=true&limit=50&offset=0` → **200**
```json
{ "items": [ /* UserResponse */ ], "total": 3, "limit": 50, "offset": 0 }
```
`q` matches email or full name (case-insensitive substring).

## Get / update

`GET /users/{id}` → **200** | unknown → **404**.
`PATCH /users/{id}` (partial: `full_name`, `email`, `is_active`) → **200**;
changing to an email already in use → **409**.

## Activation

`POST /users/{id}/deactivate` → **200** — sets `is_active=false` **and revokes
the user's refresh tokens**; the user can no longer log in.
`POST /users/{id}/activate` → **200** restores access.
Deactivating **your own** account → **422** (self-lockout guard).

## Roles

`PUT /users/{id}/roles` → **200** — replaces the full role set.
```json
{ "role_ids": ["<role-uuid>"] }
```
Any unknown role id → **422**.

## Passwords

`POST /users/{id}/reset-password` (admin, `user:update`) → **200** — sets a new
password, flags `must_change_password`, and revokes the user's sessions.
```json
{ "new_password": "Reset-Passphrase!2" }
```

`POST /users/me/change-password` (self) → **200**
```json
{ "current_password": "…", "new_password": "New-Passphrase!3" }
```
Wrong current password → **401**. On success, all of the user's sessions are
revoked.

## Delete

`DELETE /users/{id}` (`user:delete`) → **200** — soft delete; deleting **your
own** account → **422**.

## RBAC

A **Member**-role user has `user:read` (list/get succeed) but not
`user:create`/`update`/`delete` → those return **403** (`permission_denied`).
