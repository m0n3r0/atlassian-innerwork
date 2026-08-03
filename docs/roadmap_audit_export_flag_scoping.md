# Roadmap item: audit-export-flag — optional audit-log inclusion in portability payload — PM scoping

**Status:** PM scoping (pre-implementation). Source: `docs/roadmap.md` → "Directional next" → Portability format (`slug=audit-export-flag`).
**Parent:** post-launch backlog item; no phase number. Implementation task `t_bb334626` branches from `main` on `feat/audit-export-flag`.
**Audience:** the implementation worker (atlassianeng). Read this end-to-end before touching files.

---

## §0 Honest baseline (what the repo already has, today)

Verified against `main` at commit `77fa17d` on 2026-08-04.

| Asset | Present? | Path | Notes |
|---|---|---|---|
| Portability envelope | ✅ | `src/innerwork/portability.py` (455 lines) | `PORTABILITY_FORMAT_VERSION = 1`; `_COLLECTION_ORDER` = 9 domain collections (projects, work_items, transitions, spaces, pages, page_versions, links, work_item_comments, page_comments); `export_domain(store)` → deterministic dict; `export_domain_json(store, *, indent=2)`; `import_domain(store, payload)` with `_validate_envelope` (strict `format_version`/`schema_version` equality), `_validate_fresh_target` (all 9 tables empty), FK-safe insert order, `_rebuild_project_sequences` + `_bump_autoincrement`; `DomainImportError`. `_audit_portability` emits `portability_export`/`portability_import` events into the store's audit sink when one is wired. |
| Audit pipeline | ✅ | `src/innerwork/audit.py` (443 lines) | `AUDIT_SCHEMA_VERSION = 1`; closed `AUDIT_SURFACES` = {`jira_workflow`, `confluence_page`, `mention`, `permission_change`, `portability_export`, `portability_import`}; frozen `AuditEvent(event_id, ts, actor, actor_kind∈{system,user,service}, surface, entity_kind, entity_id, action, before, after, metadata)` with `as_jsonable()`; `make_event` validates surface/actor_kind/non-blank fields in `__post_init__`; sinks: `SqliteAuditSink` (audit_log table, `event_id` PK, append-only SQL triggers `audit_log_no_update`/`audit_log_no_delete`, `query()` ordered by `ts, rowid`, `export_jsonl`), `JsonlAuditSink`, `MemoryAuditSink`. **This file is read-only for this task** — export/import consume the existing sink API; nothing in the pipeline changes. |
| Sink wiring | ⚠️ | `src/innerwork/domain_store.py:110` | `DomainStore.audit_sink: Any = None`; wiring is operator responsibility after construction (`store.audit_sink = SqliteAuditSink(path)`). The CLI (`_domain_dispatch`) **never wires a sink today** — audit F1 finding (`docs/audit/2026-08-03-security.md`) documents this: `project-create` / `work-item-create` / `work-item-transition` / `export` emit **zero** audit rows via the shipped CLI, and recommends adding `--audit-log <path>` + `INNERWORK_AUDIT_DB`. **This task implements that F1 recommendation as a prerequisite** (see §2). |
| Field ACL / redaction | ✅ | `src/innerwork/field_acl.py` (143 lines) | `PRIVACY_FIELDS` includes `("AuditEvent", "actor")` → `readable_by={system, service}`, `redact_with="[redacted-actor]"`; `redact_for(actor_kind, entity_kind, payload)` shallow-copies and substitutes denied fields; `system` actor bypasses all ACLs. Used by serializers (`domain_api.py`, `knowledge.py`); the portability export does **not** currently apply it. **Read-only for this task** — the export path becomes a new *caller*. |
| CLI scaffold | ✅ | `src/innerwork/cli.py` (470 lines) | `argparse` subcommands; `export` (`--database-url`, `--out`) → `export_domain_json(store, indent=2)`; `import <input>` → `import_domain_json(store, raw)`; `_domain_dispatch` builds `DomainStore(_resolve_database_url(args))`; `DomainImportError` → stderr + exit 2; success → `_print_json`. |
| Round-trip precedent | ✅ | `tests/test_portability.py` (15 tests) + `tests/test_audit.py` (9 tests) | `test_round_trip_re_export_is_byte_identical` is the canonical gate: export → import into fresh store → re-export → byte-identical. `_seed` helper touches every collection. Audit tests cover sinks, append-only triggers, `export_jsonl`. |
| Audit-bearing snapshot fixtures | ❌ | n/a | No fixture with `format_version` 2 + `audit` collection exists. `tests/fixtures/synthetic_migration.json` is `format_version` 1 (9 collections, no audit). |
| `--include-audit` anywhere | ❌ | n/a | No flag, no parameter, no collection key. The roadmap bullet is unimplemented. |

**Implication.** A contained, additive slice: `portability.py` gains an optional `include_audit` path (export collection + import restore), `cli.py` gains `--include-audit` on `export` plus the audit-F1 sink-wiring mechanism (`--audit-log` / `INNERWORK_AUDIT_DB`), one new test file, one fixture pair, one migration-guide section, one changelog entry, and small honesty edits to `docs/roadmap.md` + `docs/threat-model.md`. The audit pipeline, domain store, domain model, and field-ACL are untouched.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `docs/roadmap_audit_export_flag_scoping.md` | (this file) | n/a | Exists at PM-scoping time. Implementation worker does not modify. |
| 2 | `src/innerwork/portability.py` | **edit** | +~120 lines | The core change. See §3/§4/§5 for exact semantics. |
| 3 | `src/innerwork/cli.py` | **edit** | +~40 lines | `export` gains `--include-audit`; `export` and `import` gain `--audit-log`; `_domain_dispatch` wires `SqliteAuditSink` from `--audit-log`/`INNERWORK_AUDIT_DB`. See §2. |
| 4 | `tests/test_portability_audit.py` | **new** | ~320 lines | API-level + CLI-level tests per §6. |
| 5 | `tests/fixtures/audit_export/` | **new** | 2 files | `with_audit_v2.json` (format_version 2, all 9 domain collections + `audit` collection spanning several surfaces) and `without_audit_v1.json` (format_version 1, no audit key — the legacy-shape reference). See §6. |
| 6 | `docs/migration-guide.md` | **edit** | +~65 lines | New section after §5 "CSV/TSV importer" — "§6 Audit-bearing export (`export --include-audit`)" (renumber current §6–§9 → §7–§10). Update §1 to state audit rows are **not** part of the default portable surface. |
| 7 | `CHANGELOG.md` | **edit** | +~8 lines | Under `[Unreleased]`, add `### Added — Audit-bearing portability export` (after the CSV importer subsection) enumerating the flag, the format_version 2 scheme, the audit collection, the F1 sink wiring, tests, and docs. No version bump. |
| 8 | `docs/roadmap.md` | **edit (optional, recommended)** | −1/+3 lines | After the PR merges, move the "Consider adding optional, opt-in inclusion of audit log rows…" bullet from "Directional next → Portability format" into the "Shipped through Phase 10" list as a post-phase-10 addition. Same PR, tiny diff. |
| 9 | `docs/threat-model.md` | **edit (optional, recommended)** | +~6 lines | §6.1: update the operator-wiring gap note to point at the new `--audit-log` / `INNERWORK_AUDIT_DB` mechanism. §4 "Information disclosure (PII in exports)" row: note that `export --include-audit` runs audit rows through `redact_for` with the operator actor kind. |

**Files that LOOK like they should be touched but MUST NOT be touched.**

| Path | Why not |
|---|---|
| `src/innerwork/audit.py` | The pipeline is the *source of truth* this feature consumes. Export reads via `SqliteAuditSink.query()` / `MemoryAuditSink.query()`; import restores via `sink.record(make_event(...))`. `make_event` already validates surface/actor_kind/non-blank fields, which is exactly the strict import validation the SEC gate demands. No new surface, no schema change, no new sink API. |
| `src/innerwork/field_acl.py` | Redaction logic exists; the export path becomes a caller. Read-only. |
| `src/innerwork/domain_store.py`, `src/innerwork/domain.py`, `src/innerwork/domain_api.py`, `src/innerwork/app.py` | Domain core + HTTP surface unchanged. Sink wiring in `_domain_dispatch` uses the existing `store.audit_sink` attribute. |
| `src/innerwork/migrators/*` | Adapters from foreign JSON shapes; unrelated. |
| `tests/test_portability.py`, `tests/test_audit.py`, `tests/fixtures/synthetic_migration.json` | Existing suites stay untouched; new suite lives in `tests/test_portability_audit.py` + `tests/fixtures/audit_export/`. The synthetic fixture stays format_version 1. |
| `pyproject.toml`, `.github/workflows/*` | No new dependency (stdlib `json` + existing modules suffice), no CI change. |
| `scripts/backup.py` | Already dumps audit JSONL via `SqliteAuditSink.export_jsonl`; unrelated to the portability envelope. |

---

## §2 CLI surface (locked)

### 2.1 `innerwork export`

```
innerwork export [--database-url sqlite:///...] [--out PATH] [--include-audit] [--audit-log PATH]
```

- `--include-audit` (store_true): include the store's audit log rows in the envelope and bump `format_version` to 2 (§3). **Default behavior is unchanged**: without the flag the output is byte-identical to today (format_version 1, 9 collections, no `audit` key).
- `--audit-log <path>` (new, both `export` and `import`): path to the SQLite audit DB. When present, `_domain_dispatch` wires `store.audit_sink = SqliteAuditSink(path)` **before** calling the portability functions (implements audit F1 finding). Env fallback: `INNERWORK_AUDIT_DB`. Explicit flag wins over env.
- **Error contract:** `export --include-audit` with **no** sink configured (no `--audit-log`, no `INNERWORK_AUDIT_DB`) → stderr message + exit 2: `error: --include-audit requires an audit sink; pass --audit-log or set INNERWORK_AUDIT_DB`. An export that silently emits an empty audit collection because no sink was wired would be dishonest; loud beats guessing.
- `--out` behavior unchanged; stdout behavior unchanged. No new secrets handling: the flag reads the audit DB and writes the envelope; nothing reads credentials.

### 2.2 `innerwork import`

```
innerwork import <input.json> [--database-url sqlite:///...] [--audit-log PATH]
```

- Format is self-describing (format_version 1 vs 2), so **no new flag on import**.
- Format_version 1 payload → exactly today's behavior (9 collections, no audit; `--audit-log` is a no-op for v1, though it may still be passed to wire a sink for subsequent writes).
- Format_version 2 payload → domain rows restored as today **and** the `audit` collection restored into the wired sink (§4). If the payload contains an `audit` collection with ≥1 row and **no** sink is configured → `DomainImportError` → stderr + exit 2: `error: payload contains audit rows but no audit sink configured; pass --audit-log or set INNERWORK_AUDIT_DB`. Restoring audit rows into a store with no sink would silently drop them — that violates "without duplication or loss".
- `DomainImportError` (including all new audit-validation errors in §4) → stderr + exit 2, nothing written.

### 2.3 Wiring rule (shared)

`_domain_dispatch` resolves the sink once per invocation: `path = args.audit_log or os.environ.get("INNERWORK_AUDIT_DB")`; if set, `store.audit_sink = SqliteAuditSink(path)` (constructor creates parent dirs + schema). This makes the CLI emit audit rows for writes (F1 fix) *and* makes `export --include-audit` / v2 import meaningful. Store construction and all other dispatch logic unchanged.

---

## §3 format_version scheme and envelope shape (locked)

### 3.1 Version constants

- `PORTABILITY_FORMAT_VERSION = 1` **stays** — the default, audit-free wire format. All existing snapshots and `tests/fixtures/synthetic_migration.json` remain v1.
- New constant: `PORTABILITY_FORMAT_VERSION_AUDIT = 2`. Emitted **only** when `include_audit=True` on export.
- `schema_version` stays `DOMAIN_SCHEMA_VERSION` (= 4) in both formats — the domain schema does not change; audit rows are an envelope-level addition, not a DB-schema change.
- `__all__` gains `PORTABILITY_FORMAT_VERSION_AUDIT`.

### 3.2 Envelope shape (additive)

Format_version 2 payload = format_version 1 payload **plus one trailing key**:

```json
{
  "format_version": 2,
  "schema_version": 4,
  "projects": [...],
  "work_items": [...],
  "transitions": [...],
  "spaces": [...],
  "pages": [...],
  "page_versions": [...],
  "links": [...],
  "work_item_comments": [...],
  "page_comments": [...],
  "audit": [ ...audit rows, §3.3... ]
}
```

- The `audit` key is **appended last**, after `page_comments`. It is **not** added to `_COLLECTION_ORDER` (that tuple drives both default export emission and the FK-safe domain insert order — adding `audit` to it would change default export bytes and break the byte-identical invariant). Audit restore is a separate pass (§4) that does not participate in domain FK ordering.
- Default export (`include_audit=False`) emits `format_version` 1 and **no** `audit` key — byte-identical to current `main`.
- `export_domain(store, *, include_audit=False, audit_actor_kind="system")` and `export_domain_json(store, *, indent=2, include_audit=False, audit_actor_kind="system")` are the new signatures (keyword-only additions; all existing call sites keep working unchanged).

### 3.3 Audit row schema (locked)

Each element of `audit` is exactly the JSON form of one `AuditEvent` (same field set and order as `AuditEvent.as_jsonable()`, which is `dataclasses.asdict` field order — `json.dumps(sort_keys=False)` preserves it):

```json
{
  "event_id": "uuid-string",
  "ts": 1785778000.123,
  "actor": "alice",
  "actor_kind": "user",
  "surface": "jira_workflow",
  "entity_kind": "WorkItem",
  "entity_id": "wi-1",
  "action": "transition",
  "before": {"state": "todo"},
  "after": {"state": "in_progress"},
  "metadata": {"transition_id": 1, "reason": "kickoff"}
}
```

Rules:

1. **Eligibility = whatever the sink holds.** The exported rows are `store.audit_sink.query()` unfiltered (all surfaces, all actors), in the sink's native order (`ORDER BY ts, rowid` for SQLite; insertion order for memory). There is **no surface allowlist and no surface synthesis**: the envelope carries the `surface` field verbatim. Today the wired surfaces that can produce rows are `jira_workflow` (transitions), `confluence_page` (page create/update), `mention` (dispatch), `portability_export`/`portability_import` (this feature's own events). `permission_change` is reserved in `AUDIT_SURFACES` but **not wired** (documented gap, `docs/threat-model.md` §5) — no such rows exist today, and this task does **not** add that wiring. "Visibility changes" are likewise **not** a distinct surface in the pipeline today; the export cannot and must not fabricate them. When/if `permission_change` wiring lands later, its rows flow through this same surface-agnostic export unchanged.
2. **before/after/metadata** are `null` or JSON objects, emitted verbatim from the stored event (the sink already stores them as JSON via `_dumps_or_none` / `json.dumps(sort_keys=True)`). Round-tripping through the envelope is lossless for these fields because import reconstructs via `make_event` and `record()` re-serializes them the same way.
3. **Ordering** is the sink's query order — deterministic for a given sink state.
4. **Counts are derived, never asserted.** The export does not print or embed a total; tests and docs derive counts from `len(store.audit_sink.query())` / `len(payload["audit"])`.

### 3.4 Redaction on export (SEC gate)

- Every exported audit row is passed through `field_acl.redact_for(audit_actor_kind, "AuditEvent", row)` **before** being added to the envelope (import from `.field_acl`; `audit_actor_kind` defaults to `"system"`).
- Default (`"system"`): `FieldACL.is_readable` bypasses for `system` → rows are verbatim. This matches the operator context: the CLI operator already has direct filesystem access to the audit DB, so the envelope introduces no new disclosure surface for the operator. Documented in the migration guide as operator responsibility (same posture as the existing threat-model row "partial — operator must invoke").
- Non-system actor kinds (future API/HTTP callers passing e.g. `"user"`) get the existing policy applied — `("AuditEvent", "actor")` → `"[redacted-actor]"`. The mechanism is real and tested (§6), not decorative.
- The CLI does **not** expose an `--audit-actor-kind` flag in this slice; the parameter exists for API-level callers.

---

## §4 Import semantics for audit rows (locked)

`import_domain(store, payload)` gains audit handling; `import_domain_json` passes through unchanged.

1. **Envelope validation (`_validate_envelope`).** Accept `format_version ∈ {1, 2}` (today: strict equality with 1). Version is authoritative:
   - v1 payload with an `audit` key → `DomainImportError("audit collection requires format_version 2")`.
   - v2 payload **without** `audit` key → `DomainImportError("format_version 2 payload must include an audit collection")`.
   - v2 `audit` not a list → `DomainImportError("collection 'audit' must be a list")`.
   - `schema_version` mismatch still rejected exactly as today (both formats).
2. **Strict row validation (no event injection).** Each audit row is validated **before any write** by reconstructing through `make_event(actor=…, actor_kind=…, surface=…, entity_kind=…, entity_id=…, action=…, before=…, after=…, metadata=…, ts=…, event_id=…)` with all fields taken from the row. `AuditEvent.__post_init__` then enforces: `surface ∈ AUDIT_SURFACES` (unknown surface → `ValueError`), `actor_kind ∈ {system,user,service}`, non-blank `actor`/`entity_kind`/`entity_id`/`action`. Any violation → `DomainImportError` naming the offending row index and field. This is the closed-enum gate the SEC gate requires: an attacker cannot inject a row with an invented surface or actor kind.
   - Row type check: every element of `audit` must be a JSON object; otherwise `DomainImportError`.
   - `ts` must be a number; `before`/`after` must be `null` or objects; `metadata` must be an object (missing → `{}`), else `DomainImportError`.
3. **Conflict pre-check (all-or-nothing).** Before writing anything, the sink's existing `event_id`s are read once; any payload `event_id` already present → `DomainImportError("audit event_id <id> already exists in the audit sink")`, **nothing written** (domain rows included — the check runs in the same all-or-nothing phase as `_validate_fresh_target`, before any INSERT). This preserves "without duplication" for the common re-import/overlay case while keeping the fresh-target spirit; the sink itself is never mutated on a rejected import.
4. **Restore pass.** After the 9 domain collections are inserted and sequences rebuilt, audit rows are recorded in payload order via `sink.record(event)` (append-only INSERT; the SQL triggers remain intact and are re-asserted by tests). The `portability_import` audit event from `_audit_portability` is recorded **after** the restore pass, so an import's own event never collides with a payload row.
5. **Fresh-target check unchanged.** `_validate_fresh_target` still requires the 9 domain tables empty. The audit sink is **not** required to be empty (only event_id-conflict-free, step 3) — an operator may import into a store whose sink already holds unrelated rows; those rows are preserved (append-only).
6. **No sink wired + v2 payload with rows** → `DomainImportError` (see §2.2). v2 payload with an empty `audit: []` is valid without a sink (nothing to restore).

### Round-trip semantics (criterion 4, honest version)

- Export (`--include-audit`) snapshots the sink **before** emitting its own `portability_export` event (`export_domain_json` builds the payload first, then calls `_audit_portability`), so a payload never contains the export event it just triggered.
- Because every export appends a `portability_export` row and every import appends a `portability_import` row, **audit-bearing exports are not byte-stable across repeated export/import cycles by design** — the sink is append-only and each cycle grows it by exactly one portability event. This is correct append-only behavior, not a defect, and the scoping docs must say so.
- The round-trip guarantee is therefore: **no loss, no duplication** — after import, every `event_id` from the payload's `audit` collection exists in the sink exactly once (plus, if you re-export, the portability events accumulated since). The domain collections (all 9) still round-trip byte-identical in every case (criterion 1's byte-identical invariant is scoped to default exports; the audit round-trip gate is set-preservation, per §6).
- `_audit_portability` metadata keeps recording `format_version` — it must record the **effective** version (2 for audit-bearing exports) so the audit trail itself distinguishes audit-bearing exports.

---

## §5 Honest gap calls (decide-and-document, locked for v1)

| Topic | Decision | Rationale |
|---|---|---|
| Not a compliance export | **Documented, never claimed otherwise.** Migration guide + changelog state: "opt-in operational convenience for moving a self-hosted store between hosts — **not** a compliance/legal export; no certifications are claimed or implied." | Anti-hallucination rule. The append-only triggers are a soft guard, not a WORM boundary (threat-model §5). |
| Not exported by default | **`--include-audit` is the only way** audit rows leave the store. Default export byte-identical to today. | Criterion 1 + anti-hallucination rule. |
| Portability events in the audit collection | **Included** (surface-agnostic — the sink holds them, so the envelope carries them). Consequence: audit-bearing exports grow by one row per cycle; documented, never hidden. | Roadmap explicitly lists portability events as eligible. Excluding them would require a surface filter, which invites drift and lies about what the sink holds. |
| `permission_change` / "visibility changes" | **Not synthesized.** The surface is reserved-but-unwired today; the export carries only rows that actually exist. | Honesty: no fabricated event types. Criterion 3 says "per the audit pipeline" — the pipeline has no visibility-change surface. |
| Redaction default | `audit_actor_kind="system"` → verbatim, operator responsibility (same posture as existing export PII row). Non-system kinds redact per `DEFAULT_POLICY`. | The operator already owns the audit DB file; the envelope adds no new disclosure for them. Mechanism exists and is tested. |
| `event_id` conflicts on import | **Loud error, nothing written.** | Duplication is forbidden by criterion 4; silent skip would be data loss. All-or-nothing matches `_validate_fresh_target` posture. |
| CLI requires explicit sink for `--include-audit` | **Exit 2 when unconfigured.** | An empty audit collection caused by missing wiring would be a silent lie. The F1 fix gives operators the mechanism. |
| `--audit-actor-kind` CLI flag | **Not shipped.** API parameter only. | Keeps the CLI surface minimal; no current caller needs it. |
| Audit collection position | Trailing key, not in `_COLLECTION_ORDER`. | Preserves default byte-identity and FK ordering; audit restore is a separate pass. |

---

## §6 Test plan

Fixtures (`tests/fixtures/audit_export/`):

| File | Contents |
|---|---|
| `with_audit_v2.json` | `format_version: 2`, `schema_version: 4`, all 9 domain collections (small, FK-consistent — reuse the shape of `_seed` in `tests/test_portability.py`), plus `audit` with **4 rows spanning distinct surfaces/actor kinds**: `jira_workflow` (user, before/after `state`), `confluence_page` (user, `after` + metadata `version_id`), `mention` (system, metadata refs), `portability_export` (system). Counts derive from the fixture's real length. |
| `without_audit_v1.json` | `format_version: 1`, same 9 collections, **no** `audit` key — the legacy-shape reference for "old-format importers still accept old snapshots" and for the default-off invariant. |

Error-case payloads (malformed v2, unknown surface, bad actor_kind, v1-with-audit-key, event_id conflict) are built as inline dicts inside the tests — they are 10–20 lines each and don't deserve checked-in fixtures (same call as the CSV importer's error inputs).

| Test | Asserts |
|---|---|
| `test_default_export_unchanged_byte_identical` | `export_domain_json(store)` on a seeded store: `format_version == 1`, no `audit` key, output equal to the current-shape envelope (9 collections). This is the default-off invariant. |
| `test_include_audit_bumps_format_version_and_appends_collection` | `export_domain(store, include_audit=True)`: `format_version == 2`, `audit` key present and last, is a list. |
| `test_export_audit_requires_wired_sink` | `export_domain(store, include_audit=True)` with `store.audit_sink is None` → error mentioning the sink. |
| `test_export_audit_rows_match_sink` | Seed a store + `MemoryAuditSink` with N events across surfaces (via `store._audit` or direct `sink.record(make_event(...))`); export with audit → `len(payload["audit"]) == len(sink.query())` (derived, not hard-coded); each row's fields (surface, actor, entity_id, before/after, metadata) equal the source event's. |
| `test_export_audit_includes_portability_events` | After one plain `export_domain_json(store)` with a wired sink, re-export with `include_audit=True` → the audit collection contains the `portability_export` row from the first export (surface `portability_export`, actor `portability`). |
| `test_export_audit_redaction_system_verbatim` | `include_audit=True` default → actor fields verbatim. |
| `test_export_audit_redaction_user_masks_actor` | `export_domain(store, include_audit=True, audit_actor_kind="user")` → every row's `actor` == `"[redacted-actor]"`; other fields unchanged. |
| `test_import_v1_legacy_payload_still_works` | `import_domain` with `without_audit_v1.json` → counts equal the fixture's real row counts; re-export byte-identical; **no** audit collection in the re-export. (Old-format importers still accept old snapshots.) |
| `test_import_v1_rejects_audit_key` | v1 payload + `audit` key → `DomainImportError`. |
| `test_import_v2_requires_audit_key` | v2 payload without `audit` → `DomainImportError`. |
| `test_import_v2_restores_audit_rows` | Fresh store + wired `MemoryAuditSink`; import `with_audit_v2.json` → `len(sink.query()) == len(payload["audit"])`; every payload `event_id` present exactly once; domain counts correct. |
| `test_import_v2_no_sink_errors` | v2 payload with rows + `audit_sink is None` → `DomainImportError`; store untouched. |
| `test_import_v2_empty_audit_no_sink_ok` | v2 payload with `audit: []` + no sink → succeeds (nothing to restore). |
| `test_import_v2_rejects_unknown_surface` | Row with `surface: "bogus"` → `DomainImportError` naming the row (no event injection). |
| `test_import_v2_rejects_bad_actor_kind` | Row with `actor_kind: "root"` → `DomainImportError`. |
| `test_import_v2_rejects_malformed_row` | Non-object element; missing `actor`; non-number `ts`; non-object `metadata` → `DomainImportError` each, naming the row. |
| `test_import_v2_event_id_conflict_writes_nothing` | Sink pre-seeded with one of the payload's event_ids → `DomainImportError`; **no** domain rows and **no** audit rows written (all-or-nothing). |
| `test_round_trip_audit_no_loss_no_duplication` | Seed store A + sink SA → `export_domain_json(A, include_audit=True)` (P1) → fresh store B + fresh sink SB → `import_domain_json(B, P1)` → `export_domain_json(B, include_audit=True)` (P2). Asserts: (1) P2's 9 domain collections byte-identical to P1's; (2) every P1 `audit` event_id present in SB exactly once; (3) P2 `audit` event_ids ⊇ P1's, with exactly the expected `portability_import` (from the import) and `portability_export` (from P2's own export) added — count asserted as `len(P1["audit"]) + 2` only because the test controls every intervening write. |
| `test_sink_stays_append_only_after_restore` | After v2 import into a real `SqliteAuditSink`, `UPDATE`/`DELETE` on `audit_log` still `RAISE(ABORT)` (triggers intact). |
| `test_cli_export_include_audit` | `main([...])` or subprocess: seed DB + `--audit-log` sink with rows → `export --include-audit --audit-log <path> --database-url sqlite:///...` → exit 0, stdout JSON `format_version == 2`, `audit` present. |
| `test_cli_export_include_audit_no_sink_exit_2` | `export --include-audit` with neither flag nor env → exit 2, stderr names `--audit-log`/`INNERWORK_AUDIT_DB`. |
| `test_cli_export_default_no_audit_key` | `export` without the flag → exit 0, `format_version == 1`, no `audit` key. |
| `test_cli_import_audit_snapshot` | `import with_audit_v2.json --audit-log <path>` → exit 0, summary JSON imported counts include audit rows; sink holds them. |
| `test_cli_import_v2_no_sink_exit_2` | `import with_audit_v2.json` with no sink → exit 2, stderr message. |
| `test_cli_audit_log_flag_wires_sink_for_writes` | `project-create --audit-log <path>` → later `export --include-audit --audit-log <path>` includes the `jira_workflow`/creation surface rows the CLI write emitted (F1 fix verified end-to-end). |

---

## §7 Anti-hallucination checklist

Implementation worker MUST run each check and quote the (empty / verified) output in the PR description.

| Check | Command |
|---|---|
| No compliance-export claim | `grep -RInE "compliance|compliant|certified|certification|legal export" docs/migration-guide.md CHANGELOG.md src/innerwork/portability.py` returns nothing beyond the explicit "**not** a compliance/legal export" sentence. Certification-framework names are already enforced repo-wide by `scripts/check_anti_hallucination.py` (CI runs it on every PR); this doc contains none of them. |
| No default-export claim | `grep -RInE "audit.*(exported|included).*default|default.*(audit|include)" src/innerwork/ docs/migration-guide.md CHANGELOG.md` returns nothing asserting audit exports by default. |
| No fabricated counts | `grep -RInE "[0-9]+ audit (rows|events|records)|audit.*[0-9]+ rows" src/innerwork/portability.py tests/test_portability_audit.py` returns nothing; every count is `len(...)` of the sink/payload. |
| No envelope break | `git diff main -- src/innerwork/portability.py` shows `_COLLECTION_ORDER` unchanged and default `export_domain` output unchanged (only additive keyword params + the v2 branch). |
| No new dependency / no network | `grep -RInE "httpx|requests|urllib|socket|http://|https://" src/innerwork/portability.py` returns nothing; imports stay stdlib + local modules (`json`, `field_acl`, `audit`, `domain_store`). |
| Files-touched boundary | `git diff --stat main` shows exactly: `src/innerwork/portability.py`, `src/innerwork/cli.py`, `tests/test_portability_audit.py`, `tests/fixtures/audit_export/*`, `docs/migration-guide.md`, `CHANGELOG.md`, optional `docs/roadmap.md`, optional `docs/threat-model.md`. Nothing else. |
| Audit pipeline untouched | `git diff main -- src/innerwork/audit.py src/innerwork/field_acl.py src/innerwork/domain_store.py src/innerwork/domain.py` is empty. |

---

## §8 Acceptance gates (must hold before opening PR)

| Gate | Verification |
|---|---|
| Default-off invariant | `test_default_export_unchanged_byte_identical` + `test_cli_export_default_no_audit_key` pass; existing `tests/test_portability.py` untouched and green. Existing snapshots round-trip byte-identical. |
| Version marker | `test_include_audit_bumps_format_version_and_appends_collection` + `test_import_v1_legacy_payload_still_works` pass: v1↔v2 distinguished by `format_version`; old snapshots still import. |
| Audit rows included with correct schema | `test_export_audit_rows_match_sink` passes: rows are `AuditEvent` JSON, surface-agnostic, sink-ordered. |
| Round-trip no-loss/no-dup | `test_round_trip_audit_no_loss_no_duplication` passes; `test_sink_stays_append_only_after_restore` confirms the append-only guard survives restore. |
| Strict import validation | `test_import_v2_rejects_unknown_surface` / `_bad_actor_kind` / `_malformed_row` / `_event_id_conflict_writes_nothing` pass. |
| Redaction | `test_export_audit_redaction_system_verbatim` + `_user_masks_actor` pass. |
| CLI honest | `test_cli_export_include_audit` / `_no_sink_exit_2` / `test_cli_import_audit_snapshot` / `test_cli_import_v2_no_sink_exit_2` / `test_cli_audit_log_flag_wires_sink_for_writes` pass (exit codes 0/2, no silent empty audit). |
| Full CI parity | `uv run pytest -x`, `uv run ruff check .`, `uv run pyright` all clean — exactly what `.github/workflows/ci.yml` runs. **Never push a branch with red pyright** (2026-05-29 phase-7 incident). |

---

## §9 Exit criteria (done definition for the implementation task)

Per the roadmap item and child task `t_bb334626`:

1. `innerwork export --include-audit --audit-log <path> --database-url sqlite:///...` emits a `format_version: 2` envelope whose `audit` collection exactly matches the wired sink; without the flag the output is byte-identical to current `main`.
2. `innerwork import with_audit_v2.json --audit-log <path>` restores domain rows **and** audit rows into a fresh store + sink with no loss and no duplication; append-only triggers verified intact after restore.
3. Old-format (v1) snapshots still import unchanged; v1 payloads carrying an `audit` key are rejected loudly.
4. No compliance/legal claims; no default-export claims; all counts derived from the store; audit pipeline (`audit.py`) untouched.
5. `uv run pytest -x && uv run ruff check . && uv run pyright` all green before push.
6. PR opened against `main` on `feat/audit-export-flag`, **DO NOT MERGE** — end with `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")` per the child task's mandate.

---

## §10 Handoff checklist for the implementation worker (atlassianeng)

1. Branch from `main` at the current HEAD: `git checkout -b feat/audit-export-flag` (child task `t_bb334626` pins this branch name; worktree workspace at `/home/eml/atlassian/atlassian-innerwork`).
2. Write files in §1 order. The scoping doc (this file) is not modified.
3. Implement `portability.py` per §3/§4: additive `include_audit`/`audit_actor_kind` params; `PORTABILITY_FORMAT_VERSION_AUDIT = 2`; trailing `audit` collection (NOT in `_COLLECTION_ORDER`); export via `sink.query()` + per-row `redact_for`; import via strict `make_event` reconstruction + event_id conflict pre-check + `sink.record` restore pass; `_audit_portability` records the effective format_version.
4. Wire the CLI per §2: `--include-audit` on `export`; `--audit-log` on `export`/`import`; `INNERWORK_AUDIT_DB` env fallback; exit 2 with the exact stderr messages in §2 when the sink is missing.
5. Add the fixture pair and test file per §6, including the round-trip no-loss/no-dup gate and the append-only-after-restore test.
6. Add the migration-guide §6 section (renumbering current §6–§9 → §7–§10) and the CHANGELOG entry; optionally move the roadmap bullet (§1 row 8) and update threat-model §6.1 (§1 row 9).
7. Run the CI-parity gate exactly as GitHub Actions does: `uv run pytest -x`, `uv run ruff check .`, `uv run pyright`. **All three must be green before push.**
8. Run the §7 grep checks and quote results in the PR body.
9. Push via SSH remote (`git@github-personal:m0n3r0/atlassian-innerwork.git`), open PR titled e.g. `feat(portability): opt-in audit-log inclusion in export (--include-audit, format_version 2)` against `main`. **DO NOT MERGE.**
10. `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")`.
