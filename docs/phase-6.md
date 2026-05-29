# Phase 6 — Cross-graph search, AI context, analytics, permissions

Phase 6 builds the read-side surface on top of the work-and-knowledge MVP:

- **Visibility / read permissions** (`innerwork.permissions`) — tag-based gating
  (`public` / `internal` / `restricted`) with a single `can_read` audit seam.
- **Cross-graph keyword search** (`innerwork.search`) — deterministic, pure-Python
  ranked search over work items, pages and comments.
- **AI-context bundling** (`innerwork.ai_context`) — assemble a token-budgeted,
  permission-filtered, deterministic context bundle around a query or an anchor
  entity for downstream LLM consumption.
- **Domain analytics** (`innerwork.analytics`) — pure-Python rollups for
  projects, spaces and the whole domain, principal-filtered by `can_read`.

All four are exposed through the existing `/v1/` FastAPI router and a new
`X-Innerwork-Principal` request header.

## Module map

| Module                       | Purpose                                                         |
| ---                          | ---                                                             |
| `innerwork/permissions.py`   | `Principal`, `AnonymousPrincipal`, `can_read`, header parsing.  |
| `innerwork/search.py`        | `search_domain()` + `Hit` results, deterministic scoring.       |
| `innerwork/ai_context.py`    | `build_ai_context()` + `ContextBundle` / `ContextEntry`.        |
| `innerwork/analytics.py`     | `domain_rollup()`, `project_rollup()`, `space_rollup()`.        |

The domain store (`innerwork/domain_store.py`) now carries `visibility` and
`members` columns on projects and spaces with additive migrations; defaults
remain `internal` / `[]` so existing rows are picked up without manual
intervention.

## HTTP surface

All endpoints accept an optional `X-Innerwork-Principal: <id>[;g1,g2,...]`
header. A missing or blank header is treated as the anonymous principal and
sees only `public` content. Malformed headers return `400`.

### `GET /v1/search/kinds`

Returns the searchable kinds:

```json
{ "kinds": ["work_item", "page", "comment"] }
```

### `GET /v1/search?q=<query>&kinds=work_item,page&limit=20`

Cross-graph keyword search. Returns ranked hits filtered through `can_read`.

```json
{
  "hits": [
    {
      "kind": "work_item",
      "entity_id": "wa",
      "title": "Login bug",
      "snippet": "...users cannot log in via SSO...",
      "score": 5.3,
      "project_id": "pp"
    }
  ]
}
```

- `kinds` is an optional comma-separated subset of `work_item,page,comment`.
- Invalid kinds, malformed `kinds=` syntax, and bad principal headers return
  `400`.
- A missing query returns `422` (FastAPI validation).

### `POST /v1/ai_context`

Body: `{ "query"?: str, "anchor_kind"?: str, "anchor_id"?: str,
         "token_budget"?: int, "max_items"?: int }`.

At least one of `query` or the `anchor_kind` + `anchor_id` pair must be
supplied. The response is a `ContextBundle.to_dict()`:

```json
{
  "query": "SSO login",
  "anchor_kind": null,
  "anchor_id": null,
  "token_budget": 6000,
  "approx_tokens": 412,
  "truncated": false,
  "omitted_candidates": 0,
  "entries": [
    { "kind": "work_item", "entity_id": "wa", "title": "...", "body": "...",
      "approx_tokens": 31, "provenance": {"reason": "anchor"} }
  ]
}
```

- The anchor is always the first entry; related entities (comments, page
  links, recent transitions) follow in a deterministic order.
- `token_budget` defaults to `DEFAULT_TOKEN_BUDGET` and is approximated via
  `CHARS_PER_TOKEN` until a real tokenizer is wired in Phase 7.
- Validation problems (missing pair, unknown kind, budget out of range)
  return `400`; unreachable entities for the caller's principal return `400`
  (`AIContextError "not readable"`).

### `GET /v1/analytics/domain`

Permission-filtered domain rollup:

```json
{
  "projects": [ { "project_id": "pp", "key": "PUB", "work_item_count": 1, ... } ],
  "spaces":   [ { "space_id": "sp", "key": "SPUB", "page_count": 1, ... } ],
  "work_item_count": 1,
  "page_count": 1,
  "work_items_by_state": { "todo": 1, "in_progress": 0, "done": 0 }
}
```

### `GET /v1/analytics/projects/{project_id}`

Project rollup. Returns `404` when the project does not exist *or* the
caller cannot read it (the two are intentionally indistinguishable to avoid
existence-leak).

### `GET /v1/analytics/spaces/{space_id}`

Space rollup with the same `404` semantics.

## Permission model

Visibility tags:

| Tag          | Who reads                                                  |
| ---          | ---                                                        |
| `public`     | Everyone, including anonymous callers.                     |
| `internal`   | Any non-anonymous principal.                               |
| `restricted` | Principals whose `id` or any of their `groups` appear in   |
|              | the entity's `members` tuple.                              |

`can_read(principal, visibility, members)` is the **single audit gate**. All
search results, analytics rollups and AI-context candidates funnel through it.
Anonymous principals (`AnonymousPrincipal`, `id=""`) can never satisfy the
`restricted` branch even if the empty string appears in a members list.

### Principal header grammar

```
<id>                       → Principal(id=<id>, groups=())
<id>;<g1>,<g2>,...         → Principal(id=<id>, groups=(<g1>, <g2>, ...))
```

- Whitespace around the id, the semicolon and group tokens is stripped.
- Whitespace **inside** the id or any group token raises `ValueError`
  (the API converts this to HTTP `400`).
- Empty group tokens are skipped silently (`eml;,eng,,sec,` → `("eng","sec")`).
- A missing or all-whitespace header is treated as `AnonymousPrincipal`.

## Determinism guarantees

Phase 6 is intentionally embedding-free and FTS-free so the output is
byte-stable across runs:

- Search scoring uses fixed weights (title × 3, body × 1) and stable
  tie-breaking by `(entity_id, kind)`.
- Analytics rollups iterate sorted entity lists; state counters always cover
  the full `WORKFLOW_STATES` set so consumers can rely on the key shape.
- AI-context entry ordering is anchor-first then by `(kind, entity_id)`;
  budget enforcement counts entries in that order so truncation is repeatable.

The same query, principal and seed data therefore produce identical hits,
identical bundles and identical rollups on every call.

## Tests

| Module               | New tests | Focus                                                  |
| ---                  | ---       | ---                                                    |
| `test_permissions`   | 26        | `can_read` matrix, header grammar, `normalize_members`.|
| `test_search`        | 10        | Tokenization, scoring, principal filtering.            |
| `test_analytics`     | 12        | Rollup correctness across visibility tiers.            |
| `test_ai_context`    | 20        | Query/anchor modes, budget cap, permission gating.     |
| `test_phase6_api`    | 22        | Endpoint contracts + principal-header round-trip.      |

Run with:

```
python -m pytest tests/test_permissions.py tests/test_search.py \
                 tests/test_analytics.py tests/test_ai_context.py \
                 tests/test_phase6_api.py
```

All 269 tests in the repo continue to pass.

## Out of scope (deferred)

- Real authentication / signed tokens — Phase 7. The current header is a
  developer-mode convenience and must never face an untrusted network.
- FTS5, embeddings, and tokenizer-accurate budgeting — Phase 7+.
- Per-object ACLs and audit log persistence — Phase 7 (the redaction seam
  lives in `ai_context._collect_candidates`).
