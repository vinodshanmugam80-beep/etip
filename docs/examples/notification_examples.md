# Notifications — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `notification:read`,
`notification:update`, `notification:delete` (self-service, held by all roles)
and **`notification:create`** (sending to others, held by admins/PMs).

Notifications are **strictly personal**: every read and write below acts on the
**calling user's own** notifications, enforced in the service regardless of role.

---

## Send a notification (privileged)

`POST /notifications` (`notification:create`) → **200**
```json
{
  "user_id": "<recipient-uuid>",
  "notification_type": "assignment",
  "priority": "normal",
  "title": "You were assigned a task",
  "body": "Task ETIP-42 is now yours.",
  "entity_type": "task",
  "entity_id": "<task-uuid>",
  "link": "/projects/etip/tasks/42"
}
```
- `notification_type` ∈ `assignment | mention | status_change | approval_request
  | approval_decision | due_soon | comment | meeting_invite | system | other`.
- `entity_type`/`entity_id` are an optional pointer back to the triggering entity
  (metadata only — not validated, so it survives the entity being deleted).
- Unknown recipient → **422**.

**Response** distinguishes delivery from suppression:
```json
{ "created": true, "notification": { … }, "detail": "Notification sent." }
```
If the recipient has muted this type, nothing is created:
```json
{ "created": false, "notification": null, "detail": "Suppressed by the recipient's preferences." }
```

Other modules/services send notifications the same way (via the service), so
events across the system — assignments, approvals, meeting invites — become
inbox items.

## My inbox (self-scoped)

- `GET /notifications?status=unread&notification_type=mention` — the caller's own
  notifications (newest first), paginated. A user **never** sees another user's
  notifications, and fetching someone else's by id returns **404**.
- `GET /notifications/unread-count` → `{ "unread": 5 }`.
- `GET /notifications/{id}` — one of the caller's own.

## Changing state

`PATCH /notifications/{id}` (`notification:update`) — body `{ "status": "read" }`.
```
unread   → read | archived
read     → unread | archived
archived → unread | read
```
Marking `read` stamps `read_date`; marking `unread` clears it.

`POST /notifications/read-all` (`notification:update`) → marks every unread
notification of the caller as read; returns how many were affected.

`DELETE /notifications/{id}` (`notification:delete`) — soft-deletes one of the
caller's own.

## Preferences (mute by type)

- `GET /notifications/preferences` (`notification:read`) → the caller's set
  preferences: `[{ "notification_type": "system", "muted": true }, …]`.
- `PUT /notifications/preferences/{notification_type}` (`notification:update`) —
  body `{ "muted": true }`. Muting a type causes future sends of that type to be
  **suppressed** for this user (`created: false`); unmuting restores delivery.

## RBAC & scoping

The **Member** role has `notification:read`, `notification:update`, and
`notification:delete` — full self-service over their own inbox and preferences —
but **not** `notification:create`, so a member cannot send notifications to
others (**403**). Even a user with `notification:create` can only *send* to
others; they still cannot *read* anyone else's inbox.
