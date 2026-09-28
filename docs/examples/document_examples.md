# Document Management — Example Requests & Responses

`BASE = http://localhost:8000/api/v1`. All requests require
`Authorization: Bearer <access_token>`. Permissions: `document:read`,
`document:create`, `document:update`, `document:delete`.

A **document** is attachment **metadata**: the file bytes live in object storage
(S3/GCS/…), referenced by `storage_key`. Documents attach polymorphically to any
supported entity and support versioning.

> **Scope note.** This module manages metadata only. A real deployment pairs it
> with an object store and a presigned-URL upload/download flow; the bytes
> themselves are never handled here.

---

## Register a document

`POST /documents` (`document:create`) → **201**
```json
{
  "owner_type": "project",
  "owner_id": "<owner-uuid>",
  "name": "Statement of Work.pdf",
  "description": "Signed SOW",
  "storage_key": "org/proj/sow-v1.pdf",
  "content_type": "application/pdf",
  "size_bytes": 248193,
  "checksum": ""
}
```
- `owner_type` ∈ `project | task | risk | issue | change_request | milestone`.
  The owner must exist in the tenant → otherwise **404**.
- `storage_key` is unique per organization → a duplicate is **409**
  (`duplicate_storage_key`).
- The first revision starts at `revision: 1`, `is_current: true`, with a fresh
  `lineage_id` and `uploaded_by_user_id` set to the caller.

## Versioning

Revisions of one logical document share a `lineage_id`. Exactly one revision is
`is_current`; `supersedes_id` points at the immediate predecessor.

`POST /documents/{id}/versions` (`document:create`) → **201**
```json
{
  "storage_key": "org/proj/sow-v2.pdf",
  "content_type": "application/pdf",
  "size_bytes": 251020,
  "description": "Countersigned SOW"
}
```
- Creates a new revision (`revision` = previous max + 1), marks it current, sets
  `supersedes_id` to the prior revision, and demotes the old current one.
- `name` is inherited from the base document unless overridden.
- A duplicate `storage_key` is **409**.

`GET /documents/{id}/versions` (`document:read`) → **200** — every revision in
the lineage, newest first.

## Promote-on-delete

`DELETE /documents/{id}` (`document:delete`) soft-deletes the document. If the
deleted revision was the **current** one, the next-highest surviving revision in
the lineage is automatically promoted to current — so a lineage always has a
current revision until its last one is removed.

## List / search

`GET /documents?owner_type=project&owner_id=<id>&content_type=application/pdf&is_current=true&q=sow`
→ **200**, newest first:
```json
{ "items": [ /* Document */ ], "total": 5, "limit": 50, "offset": 0 }
```
Use `is_current=true` to list only the latest revision of each document.

## Update metadata

`PATCH /documents/{id}` (`document:update`) — only `name` and `description` are
editable; `storage_key`, `revision`, and lineage are immutable.

## Cascade

Deleting a **project** soft-deletes documents owned by that project and by its
tasks. (Documents attached to other entity types reference their owners
directly; like the dependency module's polymorphic edges, these are cleaned when
those owners are removed.)

## RBAC

The **Member** system role has `document:create` and `document:read` — members
attach and view files — but not `document:update` or `document:delete` → those
return **403**.
