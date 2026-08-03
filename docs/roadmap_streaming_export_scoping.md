# Roadmap item: streaming-export — streaming export for very large stores — PM scoping

**Status:** PM scoping (pre-implementation). Source: `docs/roadmap.md` → "Directional next" → Portability format (`slug=streaming-export`).
**Parent:** post-launch backlog item; no phase number. Implementation task `t_80d6c615` branches from `main` on `feat/streaming-export`.
**Audience:** the implementation worker (atlassianeng). Read this end-to-end before touching files.

---

## §0 Honest baseline (what the repo already has, today)

Verified against `main` at commit `5b1bc3d` on 2026-08-04. Test suite: **405 tests** (`uv run pytest --collect-only -q`).

| Asset | Present? | Path | Notes |
|---|---|---|---|
| Memory-resident export | ✅ | `src/innerwork/portability.py` (635 lines) | `PORTABILITY_FORMAT_VERSION = 1`; `PORTABILITY_FORMAT_VERSION_AUDIT = 2` (only when `include_audit=True`); `_COLLECTION_ORDER` = 9 domain collections; `export_domain(store, *, include_audit=False, audit_actor_kind="system")` fetches every row via `connection.execute(...).fetchall()` into a `dict` payload (O(store) memory), then `export_domain_json` runs `json.dumps(payload, indent=2, sort_keys=False)` (a second O(store) string). `_rows()` helper materializes each collection list. Import side: `import_domain` / `import_domain_json` with `_validate_envelope`, `_validate_fresh_target`, FK-safe insert order, sequence rebuild. `DomainImportError`. `_audit_portability` emits `portability_export` / `portability_import` into a wired sink. |
| CLI export | ✅ | `src/innerwork/cli.py` (540 lines) | `export` subcommand (`--database-url`, `--out PATH`, `--include-audit`, `--audit-log`) → `export_domain_json(store, indent=2, ...)` then `out_path.write_text(payload + "\n")` or `sys.stdout.write(payload + "\n")`. Errors: `DomainImportError` → `error: <msg>` + exit 2. `_domain_dispatch` builds `DomainStore(_resolve_database_url(args))` + `_wire_audit_sink`. No `--stream`, no progress, no streaming anywhere. |
| Audit pipeline | ✅ | `src/innerwork/audit.py` (443 lines) | `AuditSink` protocol (`record`, `query(...)` → `tuple[AuditEvent, ...]`); `SqliteAuditSink.query()` does `connection.execute(...).fetchall()` (memory-resident, `ORDER BY ts, rowid`); `MemoryAuditSink.query()` iterates `self._events`. **No incremental iterator exists** (`query()` always materializes a tuple). Redaction via `field_acl.redact_for(actor_kind, "AuditEvent", row)` (default `"system"` → verbatim). |
| Deterministic round-trip | ✅ | `tests/test_portability.py` (15 tests) + `tests/test_portability_audit.py` (32 tests) | `test_round_trip_re_export_is_byte_identical` is the canonical gate; `_seed` helper touches every collection; `tests/fixtures/synthetic_migration.json` + `tests/fixtures/audit_export/*` lock envelope shapes. Determinism comes from `ORDER BY` PK on every collection + fixed `_COLLECTION_ORDER` + `json.dumps(sort_keys=False)`. |
| Streaming export | ❌ | n/a | No flag, no function, no incremental writer. The roadmap bullet is unimplemented. |
| Bounded-memory tests | ❌ | n/a | No `tracemalloc`/RSS measurement anywhere in the suite; no incremental-sink probe. |
| `iter_events()` on sinks | ❌ | n/a | `query()` is the only read API. |

**Implication.** A contained, additive slice: `portability.py` gains a streaming writer that reproduces the exact bytes of the memory-resident export while fetching rows in bounded batches; `audit.py` gains one additive incremental iterator (the only allowed change there); `cli.py` gains `--stream` + `--progress` on `export`; one new test file proves byte-identity, determinism, round-trip, incremental flushing, and a measured memory differential. Envelope format, import, fixtures, and default export behavior are untouched — **the default `innerwork export` stays byte-identical, and the streamed artifact IS the same envelope**.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `docs/roadmap_streaming_export_scoping.md` | (this file) | n/a | Exists at PM-scoping time. Implementation worker does not modify. |
| 2 | `src/innerwork/portability.py` | **edit** | +~140 lines | The core change: `export_domain_stream` + batch iterator + per-row serializer + progress plumbing (§3). All existing functions/constants unchanged. |
| 3 | `src/innerwork/audit.py` | **edit (additive only)** | +~30 lines | `iter_events(...)` generator on `SqliteAuditSink` and `MemoryAuditSink`, plus the optional method on the `AuditSink` protocol. `query()` and `record()` untouched — this is the ONLY audit.py change and it is purely additive. See §4. |
| 4 | `src/innerwork/cli.py` | **edit** | +~45 lines | `export` gains `--stream` and `--progress`; the export branch opens the sink and calls `export_domain_stream` when `--stream` is set, with `OSError` → `error: <msg>` + exit 2 (§2). |
| 5 | `tests/test_portability_stream.py` | **new** | ~300 lines | ~28 tests per §6. No new checked-in fixture file needed — see §6 for why. |
| 6 | `docs/migration-guide.md` | **edit** | +~70 lines | New §7 "Streaming export (`export --stream`)" after current §6 (audit-bearing export); renumber current §7–§10 → §8–§11. Document flag, memory characteristics (target + measured), partial-file semantics, determinism. |
| 7 | `docs/operations-runbook.md` | **edit (optional, recommended)** | +~10 lines | Short "Very large stores" paragraph under an existing ops section: `export --stream` for stores beyond comfortable RAM, memory posture, partial-file recovery. |
| 8 | `CHANGELOG.md` | **edit** | +~8 lines | Under `[Unreleased]`, `### Added — Streaming export` after the audit-bearing export subsection: flag, bounded-memory claim (target + measured), byte-identity invariant, tests, docs. No version bump. |
| 9 | `docs/roadmap.md` | **edit (optional, recommended)** | −1/+3 lines | After the PR merges, move the "Consider streaming export for very large stores…" bullet from "Directional next → Portability format" into the "Shipped through Phase 10" list as a post-phase-10 addition. Same PR, tiny diff. |

**Files that LOOK like they should be touched but MUST NOT be touched.**

| Path | Why not |
|---|---|
| `src/innerwork/domain_store.py`, `src/innerwork/domain.py`, `src/innerwork/domain_api.py`, `src/innerwork/app.py` | Domain core + HTTP surface unchanged. `export_domain_stream` reads through the existing `store._connect()` context manager exactly like `export_domain` does. |
| `src/innerwork/field_acl.py` | Redaction logic exists; the streaming path becomes a caller (same `redact_for` call as the memory-resident audit export). Read-only. |
| `tests/test_portability.py`, `tests/test_portability_audit.py`, `tests/fixtures/*` | Existing suites stay untouched and green; new suite lives in `tests/test_portability_stream.py`. No existing fixture is modified. |
| `pyproject.toml`, `.github/workflows/*` | No new dependency (stdlib `json`, `io`, `sqlite3` + existing modules suffice), no CI change. `tracemalloc` is stdlib. |
| `scripts/backup.py`, `scripts/check_anti_hallucination.py` | Unrelated; backup already streams JSONL via the sink. The guardrail is untouched (and must keep passing — see §7). |
| `src/innerwork/migrators/*` | Adapters from foreign JSON shapes; unrelated. |

---

## §2 CLI surface (locked)

### 2.1 `innerwork export`

```
innerwork export [--database-url sqlite:///...] [--out PATH] [--include-audit] [--audit-log PATH] [--stream] [--progress]
```

- `--stream` (store_true, new): write the portability envelope **incrementally** to the output sink (`--out PATH` or stdout) with bounded memory instead of building the full payload + JSON string in memory. **Output bytes are identical to the non-streamed export for the same store at the same `--include-audit` setting** (§3.2) — this is the load-bearing invariant, not a "close enough" format.
- `--progress` (store_true, new): print progress lines to **stderr** at a documented cadence so operators see the export is alive on huge stores. Without the flag, stderr stays silent on success (script-friendly). Cadence: one line at each collection start, then every **10 000 rows** within a collection, then one line at each collection completion and at the end. Line shape: `export: work_items 10000 rows...` / `export: work_items done (N rows)` / `export: done (N rows across 10 collections)`. **Progress lines contain only the constant collection name and integers — never row content, never audit fields, never paths** (SEC gate; see §7).
- Composition rules:
  - `--stream --out PATH` → writes directly to `PATH` (creates parent dirs, same as today). A failed/interrupted export **leaves the partial file in place** and exits 2; the operator reruns to a fresh path. Documented in migration guide §7 — deliberate (see §5 gap call on atomicity).
  - `--stream` without `--out` → writes to stdout; progress still goes to stderr, so the JSON stream and progress never interleave.
  - `--stream --include-audit` → streams the trailing `audit` collection (format_version 2) with the exact same per-row redaction as the memory-resident path (§4). The existing "requires a wired sink" error (`exit 2`) is unchanged.
- **Error contract:** any `OSError` during the incremental write (disk full, broken pipe, permission, interrupted) → stderr `error: <msg>` + **exit 2**, no traceback. `--stream` adds no new exit-code space: 0 success, 2 any error, matching the existing export/import convention.
- `--help` output must document `--stream` and `--progress` (criterion 5). Existing flags unchanged.

### 2.2 `innerwork import`

**No change.** The streamed artifact is the same JSON envelope, so `import <input.json>` accepts it exactly as today. Import stays memory-resident (this roadmap item is export-only — see §5 gap call).

---

## §3 Streaming export semantics (locked)

### 3.1 API surface

New function in `src/innerwork/portability.py` (added to `__all__`):

```python
def export_domain_stream(
    store: DomainStore,
    sink: TextIOBase,  # io.TextIOBase-like: requires .write(str) and .flush()
    *,
    include_audit: bool = False,
    audit_actor_kind: str = "system",
    batch_size: int = 500,
    progress: Callable[[str, int], None] | None = None,
) -> dict[str, int]:
    """Write the portability envelope to ``sink`` incrementally.

    Byte-identical to ``export_domain_json(store, indent=2, ...)`` + "\\n"
    for the same store / include_audit / audit_actor_kind. Returns a count
    summary {collection: rows_written} (audit included when include_audit).
    """
```

- `sink` is owned by the caller: `export_domain_stream` calls `sink.write(str)` and `sink.flush()` per batch but never closes it. The CLI opens/closes the file (try/finally) for `--out`; tests pass `io.StringIO` / probe sinks.
- `batch_size` is the `fetchmany` batch size; must be `>= 1` (`ValueError` otherwise). Default 500. This is the documented bounded buffer.
- `progress(collection, cumulative_rows)` is invoked at collection start (0), after **every** batch, and once more with the final count. The CLI throttles these calls into the §2.1 cadence; the function itself calls per batch so API callers get precise pacing.
- Returns `{collection: rows_written}` — same shape as `import_domain`'s return, so a streamed export can be logged/audited with real counts (never fabricated; see §7).
- The output is always written with the `indent=2` grammar (the only grammar the CLI uses). There is deliberately **no `indent` parameter** — a compact-`indent=None` streaming counterpart is out of scope (§5 gap call).

### 3.2 Byte-identity invariant (the referee is a test, not prose)

The streamed artifact MUST equal `export_domain_json(store, indent=2) + "\n"` byte-for-byte for the same store at the same settings. This is achievable because the memory-resident output is a fully deterministic JSON document, and the streaming writer reproduces its grammar section by section:

1. Header: `{\n  "format_version": N,\n  "schema_version": 4,` (N = 1 or 2 per §3.4).
2. For each key in `_COLLECTION_ORDER` (plus trailing `"audit"` when `include_audit`, exactly as the memory-resident v2 envelope):
   - Empty collection → `\n  "name": []` (verified: `json.dumps({"a": []}, indent=2)` renders `[]` on one line).
   - Non-empty → `\n  "name": [` then, per row: each line of `json.dumps(row, indent=2)` re-indented by 4 spaces (row `{` at 4, fields at 6; nested audit dicts at 8/10 — verified against `json.dumps(payload, indent=2)` output), `,` after every row except the last, then `\n  ]`.
3. Trailer: `\n}` then a single `\n` (the CLI's trailing-newline behavior).
4. Escaping MUST match `json.dumps` defaults: `ensure_ascii=True` (non-ASCII → `\uXXXX`), `sort_keys=False`, indent separators `,` / `: `. Floats use Python's repr (identical to `json.dumps`).

Implementation hint: serialize each row with `json.dumps(row, indent=2)` and re-indent its lines by 4 — this composes correctly for both scalar rows (domain collections) and nested-dict rows (audit), and inherits the exact escaping rules. The byte-identity tests in §6 (`test_streaming_bytes_equal_memory_resident` on a store seeded with unicode, control characters, empty collections, and nested audit dicts) are the referee: if any edge case diverges, the writer is wrong, not the test.

### 3.3 Memory bound (target + measured, never asserted as an absolute without the measurement)

- **Target (documented):** peak *additional* memory is `O(batch_size × largest-row-bytes) + O(1) envelope` — a bounded buffer independent of store size. The two O(store) terms of today's export (payload dict of every row, then the full JSON string) disappear. This is the "documented bounded buffer" form of the roadmap's `O(1) w.r.t. store size` phrasing — the honest version, because a fixed `batch_size` means memory does not grow with the store.
- **Measured (reproducible):** `tests/test_portability_stream.py` runs a `tracemalloc` differential on a programmatically seeded store (no checked-in fixture): N = 20 000 work items + 20 000 page versions with ~200-char bodies (≥ 8 MiB memory-resident peak — the test asserts this floor so it cannot pass trivially on a tiny store). Assertions: (1) memory-resident peak ≥ 8 MiB (the test is meaningful); (2) streaming peak < memory-resident peak / 4. This is an honest, deterministic, CI-stable claim (Python allocations only; no RSS flakiness) and is the number the docs quote: **"measured: streaming peak ≤ 25% of the memory-resident peak on a 40k-row workload; target: O(batch_size) additional memory"**.
- The incremental-flush test (§6) additionally proves the writer does not buffer the envelope: every `sink.write()` chunk is bounded by `O(batch_size × row)` and multiple flushes occur before the export completes.

### 3.4 Envelope semantics (unchanged by design)

- `format_version` semantics are **preserved exactly**: 1 for default, 2 only with `--include-audit`. No format change, no new version, no new collection key. `_COLLECTION_ORDER` is not modified (streaming iterates it; adding keys there would change default export bytes).
- `schema_version` stays `DOMAIN_SCHEMA_VERSION` (= 4).
- Determinism: identical ordering guarantees as today — each collection read with the existing `ORDER BY <pk>` SQL, collections emitted in `_COLLECTION_ORDER`, serialization deterministic. Two streamed exports of the same store → identical bytes; a streamed export of a re-imported store → identical bytes to the first export (full round-trip, §6).
- The store must be quiescent during export (single read connection, same posture as today's memory-resident export — no new locking claims, no concurrency promises).
- `_audit_portability(action="export", ...)` fires **only after the envelope has been fully written to the sink successfully**, with `counts` = the actual per-collection counts returned by the function and the effective `format_version`. Divergence from `export_domain_json` (which emits the event before serialization): on a failed/interrupted streamed export no `portability_export` event is recorded, because the export never materialized. This is the honest ordering and is deliberate (§5).
- Empty store: valid envelope, every collection `[]`, byte-identical to the memory-resident empty export; progress reports `0 rows`.

---

## §4 Audit integration in streaming (locked)

1. **Incremental audit iteration.** `store.audit_sink.query()` materializes a tuple — fine for the memory-resident path, wrong for bounded memory. `audit.py` gains one additive method on `SqliteAuditSink` and `MemoryAuditSink` (and the `AuditSink` protocol):

   ```python
   def iter_events(self, *, surface=None, entity_kind=None, entity_id=None, actor=None) -> Iterator[AuditEvent]:
       """Same filters + ordering as query(), but yields incrementally in bounded batches."""
   ```

   `SqliteAuditSink.iter_events` iterates `SELECT ... FROM audit_log <same where> ORDER BY ts, rowid` with `fetchmany` batching on its own short-lived connection; `MemoryAuditSink.iter_events` is a generator over `self._events` with the same filter logic as `query()`. `query()` is re-implementable as `tuple(self.iter_events(...))` but MUST keep identical output (tests lock both paths). Protocol method is additive — existing sinks that don't declare it remain protocol-compatible for `query`-only callers.
2. **Export.** `export_domain_stream(..., include_audit=True)` emits the trailing `audit` collection from `sink.iter_events()` in sink order, passing every row through `field_acl.redact_for(audit_actor_kind, "AuditEvent", row)` exactly like the memory-resident path (default `"system"` → verbatim; `"user"` → `[redacted-actor]`). Byte-identity with the memory-resident v2 export is asserted by test. The "requires a wired sink" `DomainImportError` behavior for `--include-audit` without a sink is unchanged.
3. **Import.** No change — a streamed v2 artifact imports through the existing strict validation (closed enums via `make_event` reconstruction, all-or-nothing `event_id` conflict pre-check, restore pass). The SEC posture is inherited, not weakened.
4. **Progress never touches audit content** — only the collection name `audit` and a row count.

---

## §5 Honest gap calls (decide-and-document, locked for v1)

| Topic | Decision | Rationale |
|---|---|---|
| Import stays memory-resident | **Yes — this slice is export-only.** `import <input>` continues to `json.loads` the artifact. | The roadmap item is "streaming export"; import is a later, separate roadmap candidate. Documented in migration guide §7 as a known boundary. A streamed export of a huge store can still be imported on a machine with enough RAM for one copy. |
| Byte-identity vs schema-compatible | **Byte-identical** — the streamed artifact equals the memory-resident artifact byte-for-byte, enforced by referee tests. | Criterion 1's strongest form. The indent=2 grammar is deterministic and reproducible (§3.2); "schema-compatible with documented diffs" is the fallback only if the referee test uncovers an unreproducible edge — and in that case the writer is fixed, not the target. |
| Direct-to-target writes (no atomic temp+rename) | **Direct write; partial file on failure, documented, exit 2.** | Temp+rename would hide progress from operators live-tailing a huge export and costs nothing for memory. The failure mode (partial file) is loud and documented. |
| `_audit_portability` timing | **Emitted after successful full write only.** | A failed export that still records "I exported" would be a lie. Deliberate divergence from `export_domain_json`'s before-serialization timing; the event payload (counts, format_version) is identical otherwise. |
| No `indent` parameter on `export_domain_stream` | **Always indent=2.** | The CLI (the only caller surface) always uses indent=2; a compact streaming grammar has no consumer. Keeps the byte-identity matrix small. |
| No absolute RSS number in docs | **Docs quote the measured differential (≤ 25% of memory-resident peak on the 40k-row tracemalloc workload) + the O(batch_size) target.** | Anti-hallucination: absolute RSS depends on machine/Python build; the differential is deterministic in CI. Any doc sentence containing a byte/MiB figure is marked "measured" or "target" explicitly. |
| Progress is opt-in (`--progress`) | **No auto-progress on TTY.** | Deterministic, script-friendly, matches the existing quiet-stdout posture. |
| No new dependency | **stdlib only (`json`, `io`, `sqlite3`, `tracemalloc` in tests).** | Criterion verified by grep (§7). No `orjson`/`ijson`/`polars` — the envelope grammar is simple enough to reproduce exactly with `json.dumps` per row. |
| Concurrency | **No new locking claims.** | Streaming uses one read connection like today's export; quiescent-store requirement documented, no new promises. |

---

## §6 Test plan

No new checked-in fixture file: the memory-resident export is already the locked reference (existing round-trip + `synthetic_migration.json` + `audit_export/*` fixtures lock its bytes), so the streaming tests compare against `export_domain_json(store, indent=2)` output at runtime on stores seeded with adversarial content. A separate expected-bytes fixture would duplicate hundreds of lines of JSON that drift on every schema change for no additional honesty.

`tests/test_portability_stream.py` (~28 tests). Seeding helpers: reuse the `_seed`-style pattern from `tests/test_portability.py` locally (copy, don't import across test modules), plus a `_seed_streaming_store(store, n=...)` helper that programmatically creates N work items + N page versions with ~200-char bodies (used by the memory test; deterministic content, fast).

| Test | Asserts |
|---|---|
| `test_streaming_bytes_equal_memory_resident` | Seeded store (unicode names/bodies, control chars, empty `page_comments`, `\u`-escapable content) → `export_domain_stream` into `io.StringIO` == `export_domain_json(store, indent=2) + "\n"` byte-for-byte. **The referee.** |
| `test_streaming_bytes_equal_memory_resident_include_audit` | Same, with `include_audit=True` + wired `MemoryAuditSink` with nested-dict before/after/metadata rows → streamed v2 artifact == memory-resident v2 artifact byte-for-byte. |
| `test_streaming_redaction_user_masks_actor` | `export_domain_stream(..., include_audit=True, audit_actor_kind="user")` → every audit row `actor == "[redacted-actor]"`, identical to the memory-resident path's output. |
| `test_streaming_is_deterministic` | Two `export_domain_stream` runs on the same store → identical bytes. |
| `test_streaming_empty_store` | Empty store → valid envelope, all collections `[]`, byte-identical to `export_domain_json` of the empty store. |
| `test_streaming_returns_real_counts` | Returned `{collection: n}` equals `len(payload[collection])` from the memory-resident export, for all 9 collections (and `audit` when included) — derived, never hard-coded. |
| `test_streaming_flushes_incrementally` | Probe sink records every `write()` chunk size + counts flushes: (1) every chunk ≤ `O(batch_size × row)` bound (e.g. ≤ 256 KiB with batch_size=500 and small rows); (2) ≥ 2 flushes occurred before completion. Proves no envelope buffering. |
| `test_streaming_batch_size_validation` | `batch_size=0` / negative → `ValueError`. |
| `test_streaming_interrupted_sink_writes_nothing_audit` | Sink raises `OSError` mid-write → error propagates; **no `portability_export` event** in the sink afterwards (the failed export never materialized). |
| `test_streaming_peak_memory_bounded_vs_memory_resident` | 40k-row store (20k work items + 20k page versions, ~200-char bodies); `tracemalloc`: memory-resident peak ≥ 8 MiB (floor guard — the test is not trivially satisfied); streaming peak < memory-resident peak / 4. Marked `measured` in the test docstring. |
| `test_streaming_progress_callback_cadence` | `progress` callback: called at collection start (0), after batches, and with final counts; never with row content (all args are `str` collection names + `int` counts). |
| `test_streaming_audit_requires_sink` | `include_audit=True` with `store.audit_sink is None` → `DomainImportError` (same message/behavior as memory-resident). |
| `test_sink_iter_events_sqlite_matches_query` | Seeded `SqliteAuditSink` (tmp file): `tuple(sink.iter_events())` == `sink.query()` for same filters/order; `iter_events` yields in bounded batches (monkeypatched `fetchmany` count or chunk-size probe). |
| `test_sink_iter_events_memory_matches_query` | Same for `MemoryAuditSink`. |
| `test_cli_export_stream_stdout_matches_default` | Seeded store → `main([... "export" ...])` with `--stream` stdout == stdout without `--stream`, byte-for-byte. |
| `test_cli_export_stream_out_file` | `--stream --out path` → file bytes == non-streamed `--out` file bytes; import of the file into a fresh store round-trips (counts match, re-export byte-identical). |
| `test_cli_export_stream_include_audit` | `--stream --include-audit --audit-log <path>` → format_version 2, streamed bytes == memory-resident `--include-audit` bytes. |
| `test_cli_export_stream_no_sink_exit_2` | `--stream --include-audit` with no sink → exit 2, stderr names `--audit-log`/`INNERWORK_AUDIT_DB`. |
| `test_cli_export_stream_progress_stderr` | `--stream --progress` on a store with ≥ 1 collection > 0 rows → stderr contains `export:` lines with collection names + counts, **no row content**; stdout/stderr never interleave (stdout parses as JSON). |
| `test_cli_export_stream_quiet_without_progress` | `--stream` without `--progress` → stderr empty on success. |
| `test_cli_export_stream_write_error_exit_2` | `--stream --out` into an unwritable path (e.g. a path whose parent is a file) → exit 2, stderr `error: ...`, no traceback. |
| `test_cli_export_help_documents_stream` | `--help` output contains `--stream` and `--progress`. |
| `test_cli_export_default_unchanged` | `export` without `--stream` behaves exactly as before (existing suite already locks this; this test is a smoke guard that the flag's absence changes nothing — output parses, exit 0). |
| `test_round_trip_streamed_export_import_reexport` | Seed store A → streamed export (P1) → import into fresh store B → streamed re-export (P2) → P2 == P1 byte-for-byte (full round-trip through the streaming path). |
| `test_streamed_artifact_imports_like_memory_artifact` | The streamed artifact imports through `import_domain_json` with identical counts to the memory-resident artifact's import. |
| `test_streaming_large_single_collection_progress` | One collection with > 10k rows → `--progress` emits ≥ 1 mid-collection line (heartbeat works on a single huge collection). |
| `test_streaming_batch_size_1` | `batch_size=1` still produces byte-identical output (stress the comma/indent logic; every row is its own batch). |

---

## §7 Anti-hallucination checklist

Implementation worker MUST run each check and quote the (empty / verified) output in the PR description.

| Check | Command |
|---|---|
| No new dependency / no network | `grep -RInE "httpx\|requests\|urllib\|socket\|http://\|https://" src/innerwork/portability.py src/innerwork/audit.py src/innerwork/cli.py` returns nothing new; imports stay stdlib + local modules. |
| No absolute memory claim without measurement | `grep -RInE "MiB\|MB\|RSS\|peak" docs/migration-guide.md docs/operations-runbook.md CHANGELOG.md tests/test_portability_stream.py` — every occurrence is either the O(batch_size) **target** or the **measured** tracemalloc differential; nothing states an absolute machine-independent number. |
| No fabricated counts | `grep -RInE "export.*[0-9]+ (rows|items)|[0-9]+ rows.*export" src/innerwork/ tests/test_portability_stream.py` returns nothing; every count is `len(...)` / the returned counts dict / a derived fixture count. |
| Default export untouched | `git diff main -- src/innerwork/portability.py` shows `_COLLECTION_ORDER`, `export_domain`, `export_domain_json`, `import_domain*` byte-identical (only additive additions); `git diff main -- tests/test_portability.py tests/test_portability_audit.py` is empty. |
| Audit.py additive-only | `git diff main -- src/innerwork/audit.py` shows only the new `iter_events` method (both sinks + protocol) and its imports; `query()`/`record()`/triggers untouched. |
| Files-touched boundary | `git diff --stat main` shows exactly: `src/innerwork/portability.py`, `src/innerwork/audit.py`, `src/innerwork/cli.py`, `tests/test_portability_stream.py`, `docs/migration-guide.md`, `CHANGELOG.md`, optional `docs/operations-runbook.md`, optional `docs/roadmap.md`. Nothing else. |
| No secrets in progress | `grep -RInE "progress" src/innerwork/portability.py src/innerwork/cli.py` shows progress payloads are `(collection_name: str, count: int)` only; the CLI prints only those + constant text. |

---

## §8 Acceptance gates (must hold before opening PR)

| Gate | Verification |
|---|---|
| Byte-identity | `test_streaming_bytes_equal_memory_resident` (+ `_include_audit` variant) pass: streamed output == memory-resident output byte-for-byte, including unicode escaping and empty collections. |
| Bounded memory | `test_streaming_peak_memory_bounded_vs_memory_resident` passes with the 8 MiB floor guard (not trivially satisfied) and the < 25% differential; `test_streaming_flushes_incrementally` proves chunked writes. |
| Round-trip | `test_round_trip_streamed_export_import_reexport` + `test_streamed_artifact_imports_like_memory_artifact` pass: streamed → import → streamed is lossless and byte-identical. |
| Determinism | `test_streaming_is_deterministic` passes. |
| CLI surface | `test_cli_export_help_documents_stream`, `_stdout_matches_default`, `_out_file`, `_include_audit`, `_progress_stderr`, `_write_error_exit_2` pass. |
| Default unchanged | `test_cli_export_default_unchanged` + the existing 405-test suite green (no existing test modified). |
| Audit/redaction parity | `test_streaming_bytes_equal_memory_resident_include_audit` + `test_streaming_redaction_user_masks_actor` + `test_sink_iter_events_*` pass; `--include-audit` without sink still exit 2. |
| Full CI parity | `uv run pytest -x`, `uv run ruff check .`, `uv run pyright` all clean — exactly what `.github/workflows/ci.yml` runs. **Never push a branch with red pyright** (2026-05-29 phase-7 incident). |
| Security | Redaction identical to memory-resident export (tested); no new path handling (`--out` behavior unchanged — operator-controlled, existing surface); progress carries no row content (tested); streamed artifacts import through the unchanged strict validation (no event injection / closed enums / all-or-nothing conflict checks). |

---

## §9 Exit criteria (done definition for the implementation task)

Per the roadmap item and child task `t_80d6c615`:

1. `innerwork export --stream` produces an artifact byte-identical to `innerwork export` for small stores (fixture-locked referee test), and `--stream --include-audit` is byte-identical to `--include-audit`.
2. Large-store export completes with bounded memory: target O(batch_size) additional memory; measured ≤ 25% of the memory-resident peak on the 40k-row tracemalloc workload (both stated as target/measured, never as an absolute machine-independent number).
3. Import of the streamed artifact round-trips losslessly (streamed → import → streamed re-export byte-identical).
4. Determinism: two streamed exports of the same store produce identical bytes.
5. `innerwork export --help` documents `--stream` and `--progress`; `--progress` emits stderr lines for long runs with no row content.
6. `uv run pytest -x && uv run ruff check . && uv run pyright` all green before push (405 existing tests + ~28 new, none modified).
7. PR opened against `main` on `feat/streaming-export`, **DO NOT MERGE** — end with `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")` per the child task's mandate.

---

## §10 Handoff checklist for the implementation worker (atlassianeng)

1. Branch from `main` at the current HEAD: `git checkout -b feat/streaming-export` (child task `t_80d6c615` pins this branch name; worktree workspace at `/home/eml/atlassian/atlassian-innerwork`).
2. Read this doc end-to-end; also read `docs/roadmap_audit_export_flag_scoping.md` §2–§4 for the v2/audit semantics this feature composes with (already merged, `main@5b1bc3d`).
3. Write files in §1 order. The scoping doc (this file) is not modified.
4. Implement `export_domain_stream` per §3: header → per-collection `fetchmany` batches (existing ORDER BY SQL) → per-row `json.dumps(row, indent=2)` re-indented 4 spaces → trailing `]`/`]` rules → trailer + `\n`; `progress` callback per batch; counts dict returned; `_audit_portability` only after full successful write; audit collection streamed via the new `sink.iter_events()` with per-row `redact_for` (§4).
5. Add `iter_events()` to `SqliteAuditSink` (bounded `fetchmany` on a short-lived connection, same WHERE/ORDER as `query()`) and `MemoryAuditSink` (generator, same filters), plus the additive protocol method. Nothing else in `audit.py`.
6. Wire the CLI per §2: `--stream`, `--progress` on `export`; open `--out` file (try/finally), call `export_domain_stream`, catch `OSError` → `error: <msg>` + exit 2; throttle progress to the §2.1 cadence (10 000-row heartbeat, collection boundaries, final line) on stderr.
7. Write `tests/test_portability_stream.py` per §6 (~28 tests), including the byte-identity referee, the 8 MiB-floor tracemalloc differential, the incremental-flush probe, the interrupted-sink no-audit-event test, and the CLI smoke/error paths.
8. Add migration-guide §7 (renumber §7–§10 → §8–§11), the optional runbook paragraph, and the CHANGELOG entry; optionally move the roadmap bullet (§1 row 9).
9. Run the CI-parity gate exactly as GitHub Actions does: `uv run pytest -x`, `uv run ruff check .`, `uv run pyright`. **All three must be green before push.**
10. Run the §7 grep checks and quote results in the PR body.
11. Push via SSH remote (`git@github-personal:m0n3r0/atlassian-innerwork.git`), open PR titled e.g. `feat(portability): streaming export for very large stores (--stream, bounded memory)` against `main`. **DO NOT MERGE.**
12. `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")`.
