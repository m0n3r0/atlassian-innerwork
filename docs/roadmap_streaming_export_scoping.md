# Roadmap item: streaming-export — streaming export for very large stores — PM scoping

**Status:** PM scoping (pre-implementation). Source: `docs/roadmap.md` → "Directional next" → Portability format (`slug=streaming-export`).
**Parent:** post-launch backlog item; no phase number. Implementation task `t_streaming_export_impl` branches from `main` on `feat/streaming-export`.
**Audience:** the implementation worker (atlassianeng). Read this end-to-end before touching files.

---

## §0 Honest baseline (what the repo already has, today)

Verified against `main` at commit `5b1bc3d` on 2026-08-04. The audit-export-flag feature (PR #36) is **already merged**, so the streaming writer must compose with it from day one — the audit collection exists and is a first-class part of the envelope.

| Asset | Present? | Path | Notes |
|---|---|---|---|
| In-memory export | ✅ | `src/innerwork/portability.py` (635 lines) | `export_domain(store, *, include_audit=False, audit_actor_kind="system")` → deterministic dict; `export_domain_json(store, *, indent=2, include_audit=False, audit_actor_kind="system")` → `json.dumps(payload, indent=indent, sort_keys=False)`. `_COLLECTION_ORDER` = 9 collections; `PORTABILITY_FORMAT_VERSION = 1`; `PORTABILITY_FORMAT_VERSION_AUDIT = 2` (emitted when `include_audit=True`, trailing `audit` collection **not** in `_COLLECTION_ORDER`). |
| Memory-resident fetch | ⚠️ | `portability.py:291` (`_rows`) | `connection.execute(query).fetchall()` per collection; **every** row of **every** collection is materialized into the `payload` dict simultaneously. Peak memory = O(total store size). `export_domain_json` then builds the **entire** serialized string (`json.dumps`), so peak is roughly 2× store size plus the encoder's intermediate buffers. |
| Audit collection export | ✅ | `portability.py:207` (`_export_audit_rows`) | `sink.query()` → `[redact_for(actor_kind, "AuditEvent", event.as_jsonable()) ...]` — also fully materialized in memory. Raises `DomainImportError` when `include_audit=True` and no sink is wired (loud-before-silent-empty contract, exit 2). |
| Portability audit event | ✅ | `portability.py:262` (`_audit_portability`) | Fires after payload build (`export_domain_json`) and after import; records `counts` + effective `format_version` in metadata; no-op without a wired sink. |
| CLI export | ⚠️ | `src/innerwork/cli.py:447` | `innerwork export [--database-url] [--out PATH] [--include-audit] [--audit-log PATH]`. Builds the full string via `export_domain_json(store, indent=2, include_audit=...)`, then `out_path.write_text(payload + "\n")` or `sys.stdout.write(payload + "\n")`. `DomainImportError` → stderr + exit 2. **No streaming anywhere.** |
| CLI import | ✅ | `cli.py:465` | `innerwork import <input.json>` reads the whole file (`read_text`) and `json.loads` it — memory-resident by design. **Out of scope for this slice** (see §4). |
| Round-trip gates | ✅ | `tests/test_portability.py` (15 tests), `tests/test_portability_audit.py` (28 tests), `tests/test_migration.py` (7 tests, CLI via `_run_cli` subprocess) | `test_round_trip_re_export_is_byte_identical` is the canonical gate; `test_portability_audit.py` covers the v2/audit paths incl. `test_round_trip_audit_no_loss_no_duplication`. These suites must stay green **unchanged** — the streaming writer must produce byte-identical output so every existing round-trip assertion holds for streamed files too. |
| Streaming primitives | ❌ | n/a | No iterating writer, no `fetchmany` usage, no chunked export anywhere in the repo. The roadmap bullet (`docs/roadmap.md:86`) is unimplemented: "Consider streaming export for very large stores (the current shape is memory-resident; this has been acceptable through Phase 10)." |

**Implication.** A contained, additive slice with **no wire-format change**: a new `export_domain_json_stream(store, out, ...)` writer that emits byte-identical JSON to today's `export_domain_json(...)` while bounding peak memory to O(batch_size × row size) instead of O(store size), plus a small CLI refactor of the `export` branch (`--out` becomes atomic temp+rename; stdout streams). The import side, the in-memory `export_domain`/`export_domain_json` API, the audit pipeline, and every existing test stay untouched.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `docs/roadmap_streaming_export_scoping.md` | (this file) | n/a | Exists at PM-scoping time. Implementation worker does not modify. |
| 2 | `src/innerwork/portability.py` | **edit** | +~90 lines | The core change: `export_domain_json_stream` + private batch-fetch/write helpers per §3. `export_domain`/`export_domain_json`/`_rows` stay **unchanged** (the in-memory path remains the byte-identity reference and serves API callers). |
| 3 | `src/innerwork/cli.py` | **edit** | +~15/−10 lines | The `export` branch (currently `cli.py:447-464`) switches to the stream writer. `--out`: stream to a temp file in the same directory then `os.replace` (atomic); stdout: stream directly. No new flags. See §2. |
| 4 | `tests/test_portability_stream.py` | **new** | ~300 lines | API-level + CLI-level tests per §6. Reuses the canonical `_seed` (import from `test_portability`, or a local copy if import mode blocks it). |
| 5 | `docs/migration-guide.md` | **edit (optional, recommended)** | +~10 lines | §2 "CLI surface": one paragraph — `export` now writes incrementally (bounded memory), `--out` is atomic (temp file + rename, a failed export never clobbers an existing file), stdout may hold partial JSON if the store errors mid-stream. §6 "Failure modes": one row for the partial-stdout case. No format or procedure change — existing round-trip recipes are unaffected. |
| 6 | `CHANGELOG.md` | **edit** | +~7 lines | Under `[Unreleased]`, a `### Changed — Streaming export` subsection (after the audit/portability entries): new `export_domain_json_stream` API, CLI `export` streams with atomic `--out`, byte-identical output guarantee, memory profile change, tests. No version bump, no new dependency. |
| 7 | `docs/roadmap.md` | **edit (optional, recommended)** | −1/+3 lines | After the implementation PR merges, move the "Consider streaming export for very large stores…" bullet from "Directional next → Portability format" into the "Shipped through Phase 10" list as a post-phase-10 addition. Same PR, tiny diff. |

**Files that LOOK like they should be touched but MUST NOT be touched.**

| Path | Why not |
|---|---|
| `src/innerwork/portability.py` import section (`import_domain`, `import_domain_json`, `_validate_envelope`, `_validate_audit_rows`, `_validate_audit_sink`, `_validate_fresh_target`, `_insert_many`, `_rebuild_project_sequences`, `_bump_autoincrement`) | Streaming import is explicitly out of scope (§4). Streamed files are ordinary format-1/2 envelopes and import through the existing path unchanged. |
| `_rows` / `export_domain` / `export_domain_json` | The in-memory path is the byte-identity reference. `export_domain_json` stays for API callers (e.g. `tests/test_portability.py`). |
| `src/innerwork/audit.py`, `src/innerwork/field_acl.py` | The stream writer **calls** the existing `_export_audit_rows` logic (sink check + `redact_for`); nothing in the pipeline changes. |
| `src/innerwork/domain_store.py`, `domain.py`, `domain_api.py`, `app.py` | Domain core untouched; the writer consumes the same `store._connect()` cursor API as today. |
| `tests/test_portability.py`, `tests/test_portability_audit.py`, `tests/test_migration.py`, `tests/fixtures/*` | Existing suites and fixtures stay untouched and must stay green — they are the regression net for byte-identity. New suite lives in `tests/test_portability_stream.py`; no new fixtures (no wire-format change, so no fixture pair is needed). |
| `pyproject.toml`, `.github/workflows/*` | No new dependency (stdlib `json` + existing `sqlite3` iteration suffice), no CI change. |
| `scripts/backup.py`, `scripts/restore.py` | Already call the portability API; they benefit from the CLI change automatically and need no edits. |

---

## §2 CLI surface (locked)

No new flags. The command line is **identical** to today:

```
innerwork export [--database-url sqlite:///...] [--out PATH] [--include-audit] [--audit-log PATH]
```

What changes is the mechanism and two observable behaviors:

1. **Streaming.** The `export` branch calls `export_domain_json_stream(store, out, indent=2, include_audit=...)` instead of building `export_domain_json(...)` first. Output bytes are identical to today (`export_domain_json(store, indent=2, include_audit=...) + "\n"`); only the memory profile and write timing change.
2. **Atomic `--out`.** With `--out PATH`: write to `PATH.parent / (PATH.name + f".tmp{os.getpid()}")` (parent dirs created as today), then `os.replace(tmp, PATH)` on success. On **any** failure the temp file is removed and the existing `PATH` (if any) is left untouched — a failed export never clobbers a previous good snapshot and never leaves a partial file at the target. Success/failure contract unchanged: exit 0 silent on success; `DomainImportError` (e.g. `--include-audit` without a sink) → stderr + exit 2, nothing written; other exceptions propagate exactly as they do today.
3. **stdout.** Without `--out`, the writer streams directly to `sys.stdout`; the CLI appends the trailing `"\n"` after the call returns. Honest caveat, documented in §5: a mid-stream failure leaves **partial JSON on stdout** plus the error on stderr and a non-zero exit — stdout cannot be atomic. File exports are atomic; pipe exports are not. (An `include_audit`-without-sink error is detected **before** the first byte is written, so that specific failure still produces empty stdout, matching today.)

`--audit-log` / `INNERWORK_AUDIT_DB` wiring (`_wire_audit_sink`, `cli.py:368`) is unchanged. `_audit_portability` fires once, after the stream completes, with counts returned by the stream writer and the effective `format_version` — the same event shape and timing semantics as today (the event is emitted after the data is read either way).

---

## §3 Writer contract (locked)

### 3.1 API

```python
def export_domain_json_stream(
    store: DomainStore,
    out: TextIO,
    *,
    indent: int | None = 2,
    batch_size: int = 500,
    include_audit: bool = False,
    audit_actor_kind: str = "system",
) -> dict[str, int]:
```

- `out` is a text stream (`io.StringIO`, an open file, `sys.stdout`). The function writes the envelope and **nothing else** — no trailing newline (the CLI appends `"\n"` exactly as it does today after `export_domain_json`).
- Returns `{collection: rows_written}` for the 9 `_COLLECTION_ORDER` collections (plus `"audit"` when `include_audit=True`) — same shape as `import_domain`'s return. Used internally for `_audit_portability` counts and available to API callers.
- Added to `__all__`.
- Keyword-only params mirror `export_domain_json` exactly (`indent`, `include_audit`, `audit_actor_kind`) plus `batch_size`.

### 3.2 The byte-identity invariant (THE gate)

For any store snapshot, any `indent ∈ {2, None}`, any `include_audit`/`audit_actor_kind` combination:

```
export_domain_json_stream(store, out, ...)  ⟹  out.getvalue() == export_domain_json(store, ...)
```

- Same `format_version` / `schema_version` header, same collection order (`_COLLECTION_ORDER`, `audit` last when included), same row order (the existing `ORDER BY <pk>` queries), same indentation, same `ensure_ascii=True` escaping (`json.dumps` default — non-ASCII renders as `\uXXXX`), `sort_keys=False` preserved (row dicts keep column insertion order).
- This is what keeps every existing round-trip test meaningful for streamed files: a streamed export **is** an ordinary envelope; import behaves identically.

### 3.3 Memory bound (the other gate)

- Rows are fetched per collection with a **bounded cursor**: `cursor.fetchmany(batch_size)` (default 500) in a loop, never `fetchall()`. Peak memory is O(batch_size × largest-row-size) plus the envelope header, **not** O(store size).
- `_rows` (the `fetchall` helper) is **not** used by the stream path.
- The `audit` collection is streamed in the same batch-wise manner over `sink.query()`'s rows (chunking the returned list). `SqliteAuditSink.query()` materializes today — that is pre-existing behavior and out of scope; if audit logs themselves ever grow huge, a chunked `query_iter(batch_size)` on the sink is a documented follow-up (§5), not part of this slice.
- No fabricated memory figures anywhere: the doc/CHANGELOG claims "bounded by `batch_size`, not store size" and never an MB/GB number.

### 3.4 Writer algorithm sketch (implementation guidance)

`json.dumps(payload, indent=N, sort_keys=False)` has a uniform, composable layout that a streaming writer can reproduce exactly:

- Pretty (`indent=2`) — the shape to emit:
  ```
  {
    "format_version": 1,
    "schema_version": 4,
    "projects": [
      {
        "project_id": "p1",
        ...
      },
      ...
    ],
    ...
    "audit": [ ... ]        # only when include_audit=True
  }
  ```
  Row objects at array-item level are exactly `json.dumps(row, indent=2)` with every line indented by 4 additional spaces. So per collection: write `  "key": [`, then for each row `\n` + re-indented `json.dumps(row, indent=2)` (separator `,\n` between rows — first row has no leading comma), then `\n  ]` (plus `,` if another key follows). Empty collection → `  "key": [],` with no interior newlines. Header keys `format_version`/`schema_version` at indent 2. Nested dicts inside rows (e.g. audit `before`/`after`/`metadata`) are handled automatically by `json.dumps(row, indent=2)` and the uniform re-indent.
- Compact (`indent=None`): `json.dumps(payload, sort_keys=False)` separators (`, `, `: `), no newlines. Emit `{` then `"key": [` + `json.dumps(row)` joined by `, ` + `]` with `, ` between keys, closing `}`.
- `ensure_ascii=True` on every `json.dumps` call (the default) — required for byte identity.
- The byte-identity tests (§6) are the arbiter; if a micro-detail of the layout disagrees, fix the writer, not the test.

### 3.5 Audit composition (both features already on main)

- `include_audit=True` → header `format_version: 2`, and after `page_comments` the trailing `audit` collection is streamed: the same rows `export_domain_json` would emit (via the existing `_export_audit_rows` logic: `sink.query()` → `redact_for(audit_actor_kind, "AuditEvent", event.as_jsonable())`, sink-missing → `DomainImportError`).
- **Fail-before-write:** the sink check happens before the first byte is written to `out` — `export_domain_json_stream(store, out, include_audit=True)` with no wired sink raises `DomainImportError` and `out` is left empty. The stream writer must not discover the missing sink mid-write.
- `_audit_portability(store, action="export", counts=<returned dict>, format_version=2-or-1)` fires after the stream completes — same event as today (existing `test_portability_audit.py` expectations for event shape/metadata hold).

### 3.6 Determinism

Two streamed exports of the same store produce identical bytes (same ORDER BY, same row-dict column order, no wall-clock or random data in the envelope). Existing `test_export_is_deterministic` semantics extend to the stream path.

---

## §4 Import side (locked: out of scope)

The roadmap bullet names **export**. Import stays exactly as-is:

- `innerwork import <input.json>` continues to `read_text()` + `json.loads()` (memory-resident) and replays through `import_domain` unchanged.
- Streamed exports are ordinary format-1/2 envelopes; **no import change is needed** for them to round-trip.
- Streaming import (incremental parse of a very large snapshot without materializing the full tree) is a **separate future roadmap item**; it is deliberately not bundled here so this slice stays a contained, verifiable behavior change to one command's memory profile. If beta feedback shows import is the bottleneck, it gets its own scoping doc.

---

## §5 Honest gap calls (decide-and-document, locked for v1)

| Topic | Decision | Rationale |
|---|---|---|
| Wire format | **Unchanged.** Streamed output is byte-identical to today's envelope; `format_version` 1/2 semantics untouched. | Criterion for the slice: operators' existing snapshots and recipes keep working; round-trip gates hold. |
| Streaming import | **Not in this slice.** Documented as a separate roadmap item (§4). | Roadmap names export; bundling import would double the surface and the risk for no stated need. |
| stdout partial output on mid-stream error | **Accepted and documented** (migration-guide §2/§6, CHANGELOG). File exports are atomic; pipe exports cannot be. The `include_audit`-without-sink error still fails before the first byte (empty stdout). | Atomicity is only implementable for seekable files; lying about stdout atomicity would be dishonest. |
| `--out` atomicity | **Temp file + `os.replace`**, temp cleaned up on every failure path. | A failed export must never clobber the last good snapshot — cheap, testable, matches operator expectations for backup tooling. |
| Memory claims | Only structural claims ("bounded by `batch_size`, not store size"); **no MB/GB figures** anywhere. | Anti-hallucination rule: real numbers depend on hardware/row size; the invariant is the bounded fetch. |
| Audit collection chunking | Streamed over `sink.query()`'s list; no sink API change. If audit logs grow huge, a chunked `SqliteAuditSink.query_iter(batch_size)` is a follow-up. | The sink's materializing `query()` is pre-existing; changing it expands this slice into the audit pipeline. |
| In-memory API (`export_domain` / `export_domain_json`) | **Stays**, unchanged, as the reference and for API callers. | Removing it would break callers and the byte-identity tests' oracle; both paths must agree, enforced by tests. |
| `batch_size` default | 500, API-level only; **no `--batch-size` CLI flag**. | Keeps the CLI surface minimal; operators don't need to tune it. |
| New flags | **None.** Streaming is the mechanism, not a mode. | The roadmap item is about removing the memory ceiling, not adding opt-in complexity. |
| Non-`DomainImportError` failures | Propagate as today (traceback); `--out` temp is cleaned up first. | Matches current uncaught-exception behavior; only the partial-file risk is new and it is mitigated by atomicity. |

---

## §6 Test plan

No new fixtures (no wire-format change). The suite reuses the canonical `_seed` from `tests/test_portability.py` (prefer `from test_portability import _seed`; pytest's default import mode puts `tests/` on `sys.path` — if that fails, copy the seed into the new file verbatim and note the drift risk).

| Test | Asserts |
|---|---|
| `test_stream_byte_identical_to_memory_export` | Seeded store → `export_domain_json_stream(store, StringIO(), indent=2)` == `export_domain_json(store)` byte-for-byte; same with `indent=None`. This is the master gate. |
| `test_stream_byte_identical_unicode_and_special_chars` | Store rows containing emoji, CJK, quotes, `\n`/`\t`, backslashes, `{}`, `$`, control chars (`\u0001`) in titles/bodies/actors → byte-identical (covers `ensure_ascii=True` escaping). |
| `test_stream_empty_store` | Empty store → streamed bytes == `export_domain_json(store)` (all collections `[]`). |
| `test_stream_multi_batch_fetchmany` | Store with > `batch_size` rows in one collection (e.g. 1,250 comments, `batch_size=500` → 3 batches) → byte-identical; returned counts == 9 keys with correct totals. |
| `test_stream_never_calls_fetchall` | Monkeypatch `sqlite3.Cursor.fetchall` to raise `AssertionError`; `export_domain_json_stream(store, out)` (no `include_audit`) completes byte-identically — proving the domain path is fetchmany/iteration-only. |
| `test_stream_counts_match_export_domain` | Returned counts == `{k: len(v) for k, v in export_domain(store).items() if isinstance(v, list)}`. |
| `test_stream_include_audit_byte_identical` | Store + `MemoryAuditSink` with events → `include_audit=True` stream == `export_domain_json(store, include_audit=True)` (format_version 2, trailing `audit`). |
| `test_stream_include_audit_no_sink_fails_before_write` | `include_audit=True`, no sink → `DomainImportError`; the StringIO is **empty** (fail-before-write). |
| `test_stream_include_audit_redaction_user` | `audit_actor_kind="user"` → audit rows carry `"[redacted-actor]"`; byte-identical to the memory path with the same argument. |
| `test_stream_audit_event_emitted_after_success` | Wired sink; after a stream export the sink holds exactly one new `portability_export` event whose `metadata["counts"]` == returned counts and `metadata["format_version"]` is the effective version. |
| `test_stream_round_trip_import_byte_identical` | Stream to a file → `import_domain_json(fresh_store, file_text)` → `export_domain_json(fresh_store)` == streamed bytes. (Round-trip through a streamed file, reusing the canonical gate shape.) |
| `test_stream_deterministic_two_runs` | Two streamed exports of the same store → identical bytes. |
| `test_cli_export_out_byte_identical` | `_run_cli("export", "--database-url", url, "--out", path)` → exit 0; file bytes == `export_domain_json(store, indent=2) + "\n"`. |
| `test_cli_export_out_include_audit` | `--audit-log <sink> --include-audit --out path` → file bytes == `export_domain_json(store, include_audit=True, indent=2) + "\n"`. |
| `test_cli_export_stdout_byte_identical` | `_run_cli("export", "--database-url", url)` → exit 0; stdout == `export_domain_json(store, indent=2) + "\n"`. |
| `test_cli_export_out_atomic_on_error` | Pre-create `PATH` with sentinel content; monkeypatch the row iterator to raise mid-stream (e.g. patch `fetchmany` to raise on the 2nd call) → exit non-zero, `PATH` still holds the sentinel bytes, **no** `*.tmp*` files remain in the directory. |
| `test_cli_export_include_audit_no_sink_stdout_empty` | `--include-audit` without sink → exit 2, stderr names `--audit-log`/`INNERWORK_AUDIT_DB`, stdout empty (fail-before-write preserved). |
| `test_existing_suites_stay_green` | `tests/test_portability.py`, `tests/test_portability_audit.py`, `tests/test_migration.py` pass **unmodified** — the regression net for byte identity and audit composition. |

---

## §7 Anti-hallucination checklist

Implementation worker MUST run each check and quote the (empty / verified) output in the PR description.

| Check | Command |
|---|---|
| No compliance claims | `uv run python scripts/check_anti_hallucination.py` exits 0. |
| No fabricated memory figures | `grep -RInE "[0-9]+ ?(MB|GB|MiB|GiB)" src/innerwork/portability.py tests/test_portability_stream.py docs/migration-guide.md CHANGELOG.md` returns nothing; only structural claims ("bounded by `batch_size`"). |
| No streaming-import claims | `grep -RInE "stream.*import|import.*stream" src/innerwork/portability.py docs/migration-guide.md CHANGELOG.md` returns nothing asserting streaming import; the doc's §4 out-of-scope statement is the only mention and lives in the scoping doc. |
| No format-change claims | `grep -RInE "format_version.?[0-9]|wire format" CHANGELOG.md docs/migration-guide.md` shows no claim that the wire format changed (it did not). |
| No new dependency / no network | `grep -RInE "httpx|requests|urllib|socket|http://|https://" src/innerwork/portability.py` returns nothing; imports stay stdlib + local modules. |
| `fetchall` confined to the memory path | `grep -n "fetchall" src/innerwork/portability.py` shows `fetchall` only inside `_rows` (the in-memory reference) — the stream path uses `fetchmany`/iteration. |
| Files-touched boundary | `git diff --stat main` shows exactly: `src/innerwork/portability.py`, `src/innerwork/cli.py`, `tests/test_portability_stream.py`, `docs/migration-guide.md`, `CHANGELOG.md`, optional `docs/roadmap.md`. Nothing else. |
| Audit pipeline untouched | `git diff main -- src/innerwork/audit.py src/innerwork/field_acl.py src/innerwork/domain_store.py src/innerwork/domain.py` is empty. |

---

## §8 Acceptance gates (must hold before opening PR)

| Gate | Verification |
|---|---|
| Byte-identity | `test_stream_byte_identical_to_memory_export` (+ unicode variant, empty store, multi-batch) pass; `tests/test_portability.py`, `tests/test_portability_audit.py`, `tests/test_migration.py` untouched and green — every existing round-trip assertion holds for streamed files. |
| Bounded memory | `test_stream_never_calls_fetchall` passes; the stream path uses `fetchmany(batch_size)` only. |
| Atomic `--out` | `test_cli_export_out_atomic_on_error` passes (sentinel preserved, no temp litter, non-zero exit). |
| Audit composition | `test_stream_include_audit_byte_identical` / `_no_sink_fails_before_write` / `_redaction_user` / `test_stream_audit_event_emitted_after_success` pass — v2 trailing `audit` streams correctly, fail-before-write preserved, redaction honored, portability event shape unchanged. |
| CLI honest | `test_cli_export_out_byte_identical` / `_include_audit` / `test_cli_export_stdout_byte_identical` / `_include_audit_no_sink_stdout_empty` pass (exit codes 0/2, no silent empty audit, no clobbered files). |
| Full CI parity | `uv run pytest -x`, `uv run ruff check .`, `uv run pyright` all clean — exactly what `.github/workflows/ci.yml` runs. **Never push a branch with red pyright** (2026-05-29 phase-7 incident). |

---

## §9 Exit criteria (done definition for the implementation task)

Per the roadmap item and child task `t_streaming_export_impl`:

1. `export_domain_json_stream(store, out, ...)` produces output **byte-identical** to `export_domain_json(store, ...)` for every tested shape (indent 2/None, empty/full stores, unicode, include_audit on/off), while fetching rows in `batch_size` batches (never `fetchall`).
2. `innerwork export --out PATH` streams to an atomic temp+rename target; `innerwork export` streams to stdout; exit codes and the `--include-audit`/`--audit-log` contract are unchanged; `--include-audit` without a sink still fails before any output with exit 2.
3. No wire-format change: streamed files are ordinary format-1/2 envelopes and import unchanged; the existing portability/audit/migration suites pass unmodified.
4. `docs/migration-guide.md` §2/§6 note the streaming behavior + partial-stdout caveat; CHANGELOG `[Unreleased]` gains the `### Changed — Streaming export` entry; no compliance claims, no fabricated memory figures.
5. `uv run pytest -x && uv run ruff check . && uv run pyright` all green before push.
6. PR opened against `main` on `feat/streaming-export`, **DO NOT MERGE** — end with `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")` per the child task's mandate.

---

## §10 Handoff checklist for the implementation worker (atlassianeng)

1. Branch from `main` at the current HEAD: `git checkout -b feat/streaming-export` (child task `t_streaming_export_impl` pins this branch name; worktree workspace at `/home/eml/atlassian/atlassian-innerwork`).
2. Write files in §1 order. The scoping doc (this file) is not modified.
3. Implement `export_domain_json_stream` per §3: batch-fetch via `fetchmany(batch_size)`; byte-identical composer per §3.4; `include_audit`/`audit_actor_kind` mirrored from `export_domain_json` with fail-before-write sink check; `_audit_portability` after success with the returned counts; add to `__all__`.
4. Refactor the CLI `export` branch per §2: stream to temp+`os.replace` for `--out` (temp cleaned on every failure path), stream to `sys.stdout` otherwise, append the trailing `"\n"` after the call; keep the `DomainImportError` → stderr + exit 2 contract.
5. Add `tests/test_portability_stream.py` per §6, including the master byte-identity gate, the `fetchall`-ban test, the atomicity test, and the audit-composition tests.
6. Add the migration-guide §2/§6 notes and the CHANGELOG `### Changed — Streaming export` entry; optionally move the roadmap bullet (§1 row 7).
7. Run the CI-parity gate exactly as GitHub Actions does: `uv run pytest -x`, `uv run ruff check .`, `uv run pyright`. **All three must be green before push.**
8. Run the §7 grep checks and quote results in the PR body.
9. Push via SSH remote (`git@github-personal:m0n3r0/atlassian-innerwork.git`), open PR titled `feat(portability): streaming export for very large stores (export_domain_json_stream, atomic --out)` against `main`. **DO NOT MERGE.**
10. `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")`.
