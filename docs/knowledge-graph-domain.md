# Knowledge graph and cross-graph links (Phase B slice 2)

This slice introduces the knowledge half of the Innerwork MVP and the first
cross-graph edge between work items and pages.

## Scope

* `Space` — knowledge container, uppercase short `key` (e.g. `DOCS`).
* `Page` — a document inside a space, with a pointer to the current
  immutable version.
* `PageVersion` — immutable snapshot of `(title, body, author, created_at)`
  identified by a monotonically increasing per-page `version_number`.
  Updates never mutate prior versions; they append a new one and advance
  the page header.
* `Link` — a typed edge from a `WorkItem` to a `Page`. Kinds are a small
  closed vocabulary: `documents`, `references`, `implements`, `blocks`.

## REST surface (`/v1/`)

Spaces and pages:

| Method | Path | Status codes |
|--------|------|--------------|
| `GET`  | `/v1/spaces` | 200 |
| `POST` | `/v1/spaces` | 201 / 400 / 409 |
| `GET`  | `/v1/spaces/{space_id}` | 200 / 404 |
| `GET`  | `/v1/spaces/{space_id}/pages` | 200 / 404 |
| `GET`  | `/v1/pages` | 200 |
| `POST` | `/v1/pages` | 201 / 400 / 404 |
| `GET`  | `/v1/pages/{page_id}` | 200 / 404 |
| `PUT`  | `/v1/pages/{page_id}` | 201 / 400 / 404 |
| `GET`  | `/v1/pages/{page_id}/versions` | 200 / 404 |
| `GET`  | `/v1/pages/{page_id}/versions/{version_number}` | 200 / 404 |
| `GET`  | `/v1/pages/{page_id}/links` | 200 / 404 |

Cross-graph links:

| Method | Path | Status codes |
|--------|------|--------------|
| `GET`  | `/v1/links/kinds` | 200 |
| `POST` | `/v1/links` | 201 / 400 / 404 / 409 |
| `GET`  | `/v1/links/{link_id}` | 200 / 404 |
| `DELETE` | `/v1/links/{link_id}` | 204 / 404 |
| `GET`  | `/v1/work_items/{work_item_id}/links` | 200 / 404 |

## Persistence

Three new SQLite tables sit beside the existing work-graph tables and share
the same database file:

* `spaces(space_id PK, key UNIQUE, name, owner, created_at)`
* `pages(page_id PK, space_id FK, current_version, created_at, updated_at)`
* `page_versions(version_id PK, page_id FK, version_number,
  title, body, author, created_at, UNIQUE(page_id, version_number))`
* `work_item_page_links(link_id PK, work_item_id FK, page_id FK, kind,
  created_by, created_at, UNIQUE(work_item_id, page_id, kind))`

Link integrity is enforced both by foreign keys and by an explicit
existence check in the store (which returns clean domain errors so the
API layer can return `404` rather than a SQL integrity error).

## Status-code contract

* `201` on creation (spaces, pages, page versions, links). Page updates
  return `201` because they create a new immutable `PageVersion`.
* `204` on link deletion.
* `400` on malformed input (invalid `kind`, invalid space key, blank
  author).
* `404` when a referenced space, page, work item, version, or link is
  missing.
* `409` on duplicate space `key` or duplicate `(work_item_id, page_id,
  kind)` link triple.

## Non-goals for this slice

* Page hierarchy / parent-child trees.
* Page comments and inline annotations.
* Identity, permissions, and audit (Phase D).
* Idempotency keys for product endpoints (Phase D).
* OpenAPI authored schema for `/v1/` (still broker-only in
  `spec/openapi.yaml`).

These land in follow-up slices once the rest of the Phase B surface is in
place.
