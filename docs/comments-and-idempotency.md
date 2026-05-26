# Comments & idempotency-keyed mutations (Phase B slice 3)

This slice closes Phase B with comments on work items and pages, and an
idempotency contract on every `/v1/` mutating route.

## Scope

- `WorkItemComment` — append-only comment attached to one `WorkItem`.
- `PageComment` — append-only comment attached to one `Page`.
- `X-Idempotency-Key` is **required** on every `/v1/` mutating route, matching
  the existing `/v2/` broker policy.

Out of scope for this slice: edits, deletes, reactions, mentions, attachments,
visibility scoping (handled in Phase D), search.

## Domain rules

- A comment body is a non-blank string of at most 10 000 characters; trailing
  and leading whitespace is trimmed. Blank or oversized bodies are rejected.
- An author is a non-blank string of at most 200 characters; trimmed similarly.
- A comment's parent (`WorkItem` or `Page`) must already exist. Posting to a
  missing parent returns `404`.
- Comments are append-only. The store assigns `comment_id` (UUID4) and
  `created_at` (UTC ISO-8601). Listings are sorted by `created_at` then
  `comment_id` for deterministic order.

## Persistence

`DOMAIN_SCHEMA_VERSION` bumps to `3` with the following new tables:

- `work_item_comments(comment_id PRIMARY KEY, work_item_id, author, body, created_at)`
  with `FOREIGN KEY(work_item_id)` and index `ix_work_item_comments_work_item`.
- `page_comments(comment_id PRIMARY KEY, page_id, author, body, created_at)`
  with `FOREIGN KEY(page_id)` and index `ix_page_comments_page`.
- `v1_idempotency_keys(scope, key, request_hash, response_body, created_at)`
  with composite `PRIMARY KEY(scope, key)` — backs the new idempotency layer.

## REST API

All routes are mounted under `/v1/`.

| Method | Path | Notes |
| --- | --- | --- |
| `GET`  | `/work_items/{work_item_id}/comments`    | List, sorted by `(created_at, comment_id)`. |
| `POST` | `/work_items/{work_item_id}/comments`    | Requires `X-Idempotency-Key`. `201` on success, `404` for missing parent, `400` for invalid body, `428` if header is missing, `409` if the key is replayed with a different body. |
| `GET`  | `/work_item_comments/{comment_id}`        | Returns the single comment, `404` if unknown. |
| `GET`  | `/pages/{page_id}/comments`               | List. |
| `POST` | `/pages/{page_id}/comments`               | Mirror of work-item comment create. |
| `GET`  | `/page_comments/{comment_id}`             | Single fetch. |

## Idempotency contract for `/v1/` mutations

All mutating `/v1/` routes (`POST` / `PUT` / `DELETE` on projects, work items,
transitions, spaces, pages, links, and now comments) require an
`X-Idempotency-Key` header.

Rules:

- Length: 16 — 128 characters after trimming whitespace.
- Missing header: HTTP `428 Precondition Required`.
- Out-of-range length: HTTP `400 Bad Request`.
- Same `(scope, key)` with the same request body: the original `2xx` response
  is replayed exactly, no side effects.
- Same `(scope, key)` with a different request body: HTTP `409 Conflict`.

`scope` is a per-route string (`projects.create`, `work_items.transition`,
`pages.update`, `links.delete`, `work_item_comments.create`, etc.), so two
different endpoints can reuse the same client-supplied key without collision.

The request hash is `sha256` over a canonical JSON document containing the
scope, path parameters, and request body — that way a replay across a
different `work_item_id` is treated as a different request and won't be
shadowed by an earlier successful response.

## Tests

The `tests/test_comments.py` file covers:

- pure-domain validators for body and author;
- deterministic `to_dict()` for both comment types;
- store create/list/get for both work-item and page comments;
- foreign-key style errors (`WorkItemNotFoundError`, `PageNotFoundError`,
  `CommentNotFoundError`) on missing parent or unknown comment id;
- persistence across `DomainStore` reopen;
- API create/list/get for both comment kinds;
- `404` for missing parent through the API;
- `428` when `X-Idempotency-Key` is omitted;
- replay with the same key + body returns the same `comment_id` and creates
  exactly one row;
- replay with the same key but a different body returns `409`.

Existing `test_domain_api.py` and `test_knowledge_api.py` were updated to
send `X-Idempotency-Key` on every mutating call and now also cover the
`428` and replay/conflict paths for the work-graph endpoints.

## Local CLI demo

```bash
uv run uvicorn innerwork.app:create_app --factory --port 8000

K=$(python -c "import uuid; print(uuid.uuid4().hex)")
curl -sX POST http://127.0.0.1:8000/v1/projects \
  -H "X-Idempotency-Key: $K" \
  -H "Content-Type: application/json" \
  -d '{"key":"ENG","name":"Engineering","owner":"eml"}'

# Replaying the same call returns the original body, no duplicate row.
curl -sX POST http://127.0.0.1:8000/v1/projects \
  -H "X-Idempotency-Key: $K" \
  -H "Content-Type: application/json" \
  -d '{"key":"ENG","name":"Engineering","owner":"eml"}'
```

## Follow-up work

- Phase D thin slice: local identity + per-project / per-space permissions +
  audit rows on every `/v1/` mutation, with comments inheriting parent ACLs.
- Comment editing / soft delete with a revision history (only after Phase D so
  we know who is allowed to edit what).
- Surface `/v1/` paths in the authored `spec/openapi.yaml` once Phase D
  stabilises the schema.
- Phase C product frontend after Phase D.
