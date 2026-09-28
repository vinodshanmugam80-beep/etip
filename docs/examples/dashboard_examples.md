# Dashboards — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `dashboard:read` (view +
render), `dashboard:create`, `dashboard:update` (edits, widgets, set-default),
`dashboard:delete`.

A **dashboard** is a user-configurable layout of **widgets**. A REPORT widget is
backed by a report type and parameters and is rendered live through the report
engine; a TEXT widget carries static content. Dashboards are **owned** and may be
**shared** — visibility mirrors reports, and edits are owner-only.

---

## Create a dashboard

`POST /dashboards` (`dashboard:create`) → **201**
```json
{
  "name": "Delivery overview",
  "description": "My at-a-glance board",
  "is_shared": false,
  "layout": { "columns": 12 }
}
```
New dashboards are private and non-default. `layout` is freeform JSON for the
client's grid.

## Visibility, default, lifecycle

- `GET /dashboards` — dashboards **visible** to the caller: owned **plus**
  shared. `GET /dashboards/{id}` returns a visible dashboard, else **404**.
- `PATCH /dashboards/{id}` (`dashboard:update`) / `DELETE /dashboards/{id}`
  (`dashboard:delete`) — **owner only**; a non-owner who can see a shared
  dashboard (even with `dashboard:update`) gets **403**.
- `POST /dashboards/{id}/set-default` (`dashboard:update`) — marks this as the
  caller's **single** default; any previous default of theirs is cleared.

## Widgets

- `POST /dashboards/{id}/widgets` (`dashboard:update`, owner) → **201**
  - REPORT widget (must include `report_type`):
    ```json
    {
      "title": "Project status",
      "widget_type": "report",
      "report_type": "project_status",
      "parameters": { "project_id": "<uuid>" },
      "position": 1, "width": 6
    }
    ```
    Omitting `report_type` for a report widget → **422**.
  - TEXT widget:
    ```json
    { "title": "Standup notes", "widget_type": "text", "content": "Daily at 9am", "position": 2 }
    ```
- `GET /dashboards/{id}/widgets` (`dashboard:read`) — ordered by `position`.
- `PATCH /dashboards/{id}/widgets/{widget_id}` / `DELETE …` (`dashboard:update`,
  owner) — update fields (report widgets accept `report_type`/`parameters`; text
  widgets accept `content`) or remove.

Deleting a dashboard cascades its widgets.

## Render — the headline

`GET /dashboards/{id}/render` (`dashboard:read`) runs every widget and returns
the dashboard plus each widget's result:
```json
{
  "dashboard": { … },
  "generated_at": "2026-03-11T09:00:00Z",
  "widgets": [
    { "title": "Project status", "widget_type": "report", "data": { "code": "ATLAS", … }, "error": null },
    { "title": "Standup notes", "widget_type": "text", "content": "Daily at 9am" },
    { "title": "Broken", "widget_type": "report", "data": null, "error": "Missing required parameter 'project_id'." }
  ]
}
```
REPORT widgets are assembled through the **same engine** the Reports module uses.
Crucially, a widget that fails to render **captures its `error`** rather than
aborting the whole dashboard — one misconfigured tile never blanks the board.

## RBAC

The **Member** role has `dashboard:read` and `dashboard:create` — members can
create, view (own + shared), and render dashboards — but not `dashboard:update`
or `dashboard:delete` → **403**. Only the **owner** may edit, manage widgets,
set-default, or delete a dashboard, even among users holding those permissions.
