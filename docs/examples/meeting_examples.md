# Meeting Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `meeting:read`,
`meeting:create`, `meeting:update`, `meeting:delete`.

A **meeting** is a scheduled gathering on a project, with an agenda, a schedule,
minutes, attendees, and action items. Action items agreed in a meeting are
created as **RAID actions** tagged with the meeting they came from.

---

## Schedule a meeting

`POST /meetings` (`meeting:create`) → **201**
```json
{
  "project_id": "<project-uuid>",
  "title": "Sprint 12 review",
  "meeting_type": "review",
  "location": "https://meet.example.com/abc",
  "agenda": "Demo, metrics, next-sprint scope",
  "scheduled_start": "2026-03-10T15:00:00Z",
  "scheduled_end": "2026-03-10T16:00:00Z",
  "organizer_user_id": null
}
```
- `meeting_type` ∈ `standup | planning | review | retrospective | status | stakeholder | kickoff | other`.
- Each meeting gets a per-project `number` and starts `scheduled`.
- `organizer_user_id` defaults to the caller; the organizer is auto-invited as
  an **accepted** attendee.
- Unknown project → **404**; unknown organizer → **422**;
  `scheduled_end ≤ scheduled_start` → **422**.

## Status lifecycle

```
scheduled   → in_progress | completed | cancelled
in_progress → completed | cancelled
completed / cancelled → (terminal)
```
Moving to `in_progress` stamps `actual_start`; moving to `completed` stamps
`actual_end` (and `actual_start` if it was skipped). Illegal transitions →
**422**. Editing the schedule so `scheduled_end ≤ scheduled_start` → **422**
(`invalid_schedule`).

Record minutes with a normal update: `PATCH /meetings/{id}` with `{ "minutes": "…" }`.

## List / search

`GET /meetings?project_id=<id>&status=scheduled&meeting_type=review&date_from=2026-03-01T00:00:00Z&date_to=2026-03-31T23:59:59Z&q=sprint`
→ **200**, ordered by scheduled start (soonest first).

## Attendees

- `POST /meetings/{id}/attendees` (`meeting:update`) — body
  `{ "user_id": "<uuid>", "role": "required" }`. Roles: `organizer | required |
  optional | presenter`. A second invite for the same user → **409**
  (`duplicate_attendee`); unknown user → **422**.
- `GET /meetings/{id}/attendees` (`meeting:read`) — list.
- `PATCH /meetings/{id}/attendees/{attendee_id}` (`meeting:update`) — set
  `role`, `response` (`no_response | accepted | declined | tentative`), or
  `attended`.
- `DELETE /meetings/{id}/attendees/{attendee_id}` (`meeting:update`) — remove.

## Action items → the RAID log

`POST /meetings/{id}/action-items` (`meeting:update`) → **201**
```json
{
  "title": "Follow up with vendor",
  "description": "Confirm the revised SLA",
  "priority": "high",
  "owner_user_id": null,
  "due_date": "2026-03-17"
}
```
This creates a first-class **RAID action** on the meeting's project, tagged with
`source_meeting_id`. It appears in:
- `GET /meetings/{id}/action-items` (this meeting's items), and
- `GET /actions?project_id=<id>` (the project's RAID log) — each carrying
  `source_meeting_id` pointing back at the meeting.

## Delete

`DELETE /meetings/{id}` (`meeting:delete`) — soft-deletes the meeting and its
attendees. Deleting a **project** soft-deletes its meetings automatically.
Action items already raised remain in the RAID log as project actions.

## RBAC

The **Member** system role has `meeting:read`, `meeting:create`, and
`meeting:update` — members can schedule meetings, manage attendees, and raise
action items — but not `meeting:delete` → that returns **403**.
