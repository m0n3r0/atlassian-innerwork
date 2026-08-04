# Roadmap item: innerwork-doctor — `innerwork doctor` CLI to validate a database file — PM scoping

**Status:** PM scoping (pre-implementation). Source: `docs/roadmap.md` → "Directional next" → CLI ergonomics (`slug=innerwork-doctor`): "*`innerwork doctor` to validate a database file against the current schema and surface common operator misconfigurations*."
**Parent:** post-launch backlog item; no phase number. Implementation task `t_88234df1` branches from `main` on `feat/innerwork-doctor` and is **DO NOT MERGE** (QA gate first).
**Audience:** the implementation worker (atlassianeng). Read this end-to-end before touching files.

---

## §0 Honest baseline (what the repo has, today, verified)

Verified against `main` at commit `3284532` on 2026-08-04 by reading source **and** creating a fresh store to introspect `sqlite_master` (no guessed tables/columns anywhere in this doc).

| Asset | Present? | Path / facts |
|---|---|---|
| `innerwork doctor` | ❌ | `docs/operations-runbook.md:275` states "there is no `innerwork doctor` command (that is a roadmap future item)" — that line must be updated by this feature. No `doctor` symbol exists anywhere in `src/`. |
| CLI subcommand registry | ✅ | `src/innerwork/cli.py:42` `build_parser()` — 17 subcommands via `parser.add_subparsers(dest="command", required=True)`; domain commands dispatch through `_domain_dispatch` (`cli.py:449`) which constructs `DomainStore(_resolve_database_url(args))` **first**. |
| DB URL resolver | ✅ | `cli.py:378` `_resolve_database_url(args)`: `--database-url` → `INNERWORK_DATABASE_URL` env → stderr usage message + `SystemExit(2)` if neither, or if scheme ≠ `sqlite:///`. Exit-code 2 usage contract already established. |
| JSON printer | ✅ | `cli.py:637` `_print_json(payload)`: `json.dumps(payload, indent=2, sort_keys=True)` + newline to stdout — the house shape every CLI JSON payload uses. |
| Domain schema | ✅ | `src/innerwork/domain_store.py`: `DOMAIN_SCHEMA_VERSION = 4` (`:51`), persisted in the shared `meta` table as `domain_schema_version` (`:1233-1239`). `_initialize` (`:1027`) creates `meta` + **11 domain tables** + **8 indexes**, plus additive `_ensure_column` migrations for `visibility`/`members` on `projects`/`spaces` (v3→v4, `:1209-1232`). Verified fresh-store inventory: tables `projects, project_sequences, work_items, work_item_transitions, spaces, pages, page_versions, work_item_page_links, work_item_comments, page_comments, v1_idempotency_keys` (+`meta`); indexes `ix_work_items_project, ix_work_items_state, ix_pages_space, ux_work_item_page_links_triple, ix_links_work_item, ix_links_page, ix_work_item_comments_work_item, ix_page_comments_page`. |
| Broker (Phase 2) schema | ✅ | `src/innerwork/sql_state_store.py`: `SQLITE_SCHEMA_VERSION = 1` (`:11`), persisted in `meta` as `schema_version` (`:164-170`). Tables `services, operations, idempotency_keys`. **Note: `SqliteStateStore._initialize` UPSERTs `schema_version` on every open — construction mutates the file.** The CLI never constructs it (`EdgeBroker()` defaults `state_store=None`, `broker.py:19`; `render`/`validate` use the in-memory broker) — a domain-only file with no broker tables is legitimate. |
| Audit schema | ✅ | `src/innerwork/audit.py`: `AUDIT_SCHEMA_VERSION = 1` (`:50`) — **never persisted to any table** (verified: `ensure_audit_schema` `:204` only runs `_AUDIT_DDL`: `audit_log` table, 3 indexes `idx_audit_log_entity/surface/actor`, 2 append-only triggers `audit_log_no_update`/`audit_log_no_delete`). `SqliteAuditSink.__init__` (`:222-230`) runs that DDL on open — **construction writes**. |
| Read-only precedent | ✅ | `DomainStore._connect` (`domain_store.py:1022`) and `SqliteStateStore._connect` (`sql_state_store.py:115`) both plain `sqlite3.connect(path)` — **no existing read-only open helper to reuse**; doctor needs its own `mode=ro` URI connect. |
| Backup artifacts | ⚠️ | `scripts/backup.py` takes arbitrary `SOURCE DEST` (`backup(source, dest)`, no fixed naming/stamp convention) → **backup cadence is unknowable** from the store alone; freshness can only be an info-level hint. |
| Test conventions | ✅ | `tests/test_cli.py` + `tests/test_domain_cli.py` use a subprocess `_run_cli(*args, env_extra=...)` helper (`python -m innerwork.cli`, `PYTHONPATH=src`); `tests/test_domain_cli.py` accepts `env_extra` for env-driven cases. |
| CI parity | ✅ | `.github/workflows/ci.yml` runs `uv run ruff check .`, `uv run pyright`, `uv run pytest -q`; `pyproject.toml` line-length 100, target py310. |

**Implication.** A contained, additive slice: a new `src/innerwork/doctor.py` module (pure read-only diagnostics, raw `sqlite3` only — **must never construct `DomainStore`/`SqliteStateStore`/`SqliteAuditSink`**, all three `__init__`s write), one new CLI subcommand wired in `cli.py` with its own dispatch branch **before** `_domain_dispatch` (which would create tables), one new test suite, and doc/CHANGELOG updates. No schema source file changes: the expected-schema tables in `doctor.py` are a **mirror** of the DDL in `domain_store.py`/`sql_state_store.py`/`audit.py`, and a drift-guard test (§8) keeps the mirror honest.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `docs/roadmap_innerwork_doctor_scoping.md` | (this file) | n/a | Exists at PM-scoping time. Implementation worker does not modify. |
| 2 | `src/innerwork/doctor.py` | **new** | ~380 lines | The core module per §3–§6: finding/report dataclasses, `EXPECTED_*` schema mirrors, `run_doctor(path, *, integrity_check=False, audit_path=None)`, read-only open helper, human-report renderer. Stdlib only (`sqlite3, os, stat, hashlib, shutil, json, dataclasses, pathlib, typing`). |
| 3 | `src/innerwork/cli.py` | **edit** | +~35/−0 | Register `doctor` subcommand in `build_parser()` (with epilog examples, §2) and add `_doctor_dispatch(args)` + a `if args.command == "doctor": return _doctor_dispatch(args)` branch in `main()` **before** the domain-dispatch set. No changes to any existing branch. |
| 4 | `tests/test_doctor.py` | **new** | ~380 lines | Full suite per §8, reusing the `_run_cli` subprocess pattern from `tests/test_domain_cli.py`. |
| 5 | `docs/migration-guide.md` | **edit** | +~18 lines | New subsection `2.5 innerwork doctor` (or next free `2.x`): command shape, exit-code contract §5, `--json` report contract §4, read-only guarantee §6, one example. |
| 6 | `docs/operations-runbook.md` | **edit** | ±3 lines | Replace the `:275` sentence "there is no `innerwork doctor` command (that is a roadmap future item)" with a pointer to the new command; add `innerwork doctor <db>` to the Restore-verification recipe (step 5 area) as an additional verification step. |
| 7 | `CHANGELOG.md` | **edit** | +~6 lines | Under `[Unreleased]`, a `### Added — innerwork doctor` subsection: new subcommand, check catalog summary, exit codes 0/1/2, read-only guarantee, `--json` flag, tests. No version bump, no new dependency. |
| 8 | `docs/roadmap.md` | **edit (optional, recommended)** | −1/+3 lines | After the implementation PR merges, move the "`innerwork doctor` …" bullet from "Directional next → CLI ergonomics" into the shipped list as a post-phase-10 addition. Same PR, tiny diff. |

**Files that LOOK like they should be touched but MUST NOT be touched.**

| Path | Why not |
|---|---|
| `src/innerwork/domain_store.py`, `sql_state_store.py`, `audit.py` | These are the **schema authorities**. The doctor mirrors their DDL in `EXPECTED_*` constants; the drift-guard test (§8) enforces the mirror stays current. Refactoring the DDL into a shared module is a separate change and out of scope. |
| `src/innerwork/state_store.py` (JSON state file, `STATE_SCHEMA_VERSION = 1`) | JSON-state, not a SQLite DB; the roadmap bullet is about a database file. Out of scope. |
| `src/innerwork/app.py`, `domain_api.py`, `portability.py`, `model.py`, `serialization.py` | The doctor reads raw SQLite; it consumes none of these. |
| `scripts/backup.py`, `scripts/restore.py`, `scripts/rollback_drill.py` | Backup naming is arbitrary (`SOURCE DEST`), so no freshness logic can key off it (§7). The runbook edit (#6) is the only touch. |
| `tests/test_cli.py`, `tests/test_domain_cli.py`, `tests/fixtures/*`, all other suites | Existing suites stay untouched and must stay green — they are the regression net. New suite lives in `tests/test_doctor.py`; no new fixtures (all doctor scenarios are generated in-test via `tmp_path`). |
| `pyproject.toml`, `.github/workflows/*` | No new dependency (stdlib suffices), no CI change. |

---

## §2 CLI surface (locked)

```
innerwork doctor [DB_PATH] [--database-url sqlite:///...] [--audit-log PATH] [--json] [--integrity-check]
```

Registration in `build_parser()`:

- `doctor = subcommands.add_parser("doctor", help="Validate a database file against the current schema", description=..., epilog=<examples>)`.
- **Positional `db_path`** (`type=Path`, `nargs="?"`, `metavar="DB_PATH"`): the database file to validate. Help: "Database file to validate (default: the configured store from --database-url / INNERWORK_DATABASE_URL)".
- **`--database-url`**: added via the existing `_add_db_arg(p)` helper (same text as every other domain command).
- **`--audit-log`**: added via the existing `_add_audit_log_arg(p)` helper — when resolved (`--audit-log` or `INNERWORK_AUDIT_DB`), the audit database is validated too (checks A1–A5, §3). Absent → audit checks are skipped entirely and the report says so with a single `INFO` line (`schema.audit_skipped`).
- **`--json`** (`store_true`): machine-readable report (§4) instead of the human report (§3.3).
- **`--integrity-check`** (`store_true`): run `PRAGMA integrity_check` (check T6, §3). **Off by default** — it scans every page and is slow on large stores. Without the flag the report never claims integrity was verified (§7).

**Target resolution precedence** (locked): `DB_PATH` positional → `--database-url` → `INNERWORK_DATABASE_URL`. If none of the three yields a value, or `--database-url` has an unsupported scheme, fail exactly like `_resolve_database_url` does today: message to stderr, **exit 2, stdout empty** (even with `--json` — matches the `export`/`import` convention of stderr-only usage failures). Implementation note: `_doctor_dispatch` calls `_resolve_database_url(args)` only when `args.db_path is None` — `_resolve_database_url` reads `args.database_url` + env, so **no signature change** to it.

**Help text MUST contain at least one example** (acceptance criterion). Locked epilog (no `%` chars — argparse `%`-escaping footgun):

```
examples:
  innerwork doctor                          validate the configured store (INNERWORK_DATABASE_URL)
  innerwork doctor data/innerwork.db        validate a specific database file
  innerwork doctor data/innerwork.db --json
  innerwork doctor data/innerwork.db --integrity-check --audit-log data/audit.db
```

Human report goes to **stdout** (findings + summary); usage errors go to **stderr**; nothing else is ever written to stderr on success (script-friendly, matching the rest of the CLI).

---

## §3 Check catalog (locked)

Every check id maps to a real schema object verified in §0. Severity semantics: `error` = the store is not healthy/usable; `warning` = functional but flagged (perf, permissions, disk); `info` = advisory, never affects exit code. Checks run in the exact order below; findings are emitted in this order (stable, §4).

### Group T — target & file (run for every invocation)

| id | sev | What it verifies | Grounding |
|---|---|---|---|
| T2 `target.exists` | error | `path.stat()` succeeds; if the path is a directory, fires with message "path is a directory, not a database file" | `os.stat` / `Path.stat` |
| T3 `target.readable` | error | `os.access(path, R_OK)` and a probe open succeeds (no `PermissionError`) | POSIX access bits; root caveat documented in §6 test |
| T4 `target.sqlite_header` | error | first 16 bytes == `b"SQLite format 3\x00"` (wrong format = not a SQLite DB) | SQLite file header magic |
| T5 `target.openable` | error | `sqlite3.connect("file:{path}?mode=ro", uri=True)` succeeds (catches truncation/corrupt header-valid files, locked DBs → `sqlite3.DatabaseError` / `OperationalError`) | §6 read-only open |
| T6 `target.integrity` | error | **only when `--integrity-check`**: `PRAGMA integrity_check` result is exactly `"ok"`; **absent from the report otherwise** (never claim it ran) | real `PRAGMA integrity_check` (read-only page scan) |
| T7 `target.writable` | warning | `os.access(path, W_OK)` — reads fine, but `serve`/writes will fail on a read-only file | POSIX access bits; root caveat documented |
| T8 `target.disk_space` | warning | `shutil.disk_usage(path).free < max(64 MiB, 2 × size_bytes)` — heuristic, documented in message | `shutil.disk_usage` |
| T9 `target.age` | info | DB mtime age in days + hint text pointing at `docs/operations-runbook.md` backup guidance. **Never** warning/error — backup cadence is unknowable (scripts/backup.py takes arbitrary dest, §7) | `stat().st_mtime` |

If T2–T5 fail, the schema group (S) is skipped — the file cannot be meaningfully schema-checked — and the report ends with the T findings plus a summary line noting the skip. T7–T9 still run (they are independent of schema health).

### Group S — schema (run when T2–T5 all pass)

| id | sev | What it verifies | Grounding |
|---|---|---|---|
| S1 `schema.domain_version` | error | `meta` table exists **and** `meta['domain_schema_version'] == str(DOMAIN_SCHEMA_VERSION)` (`"4"`); missing meta/key or mismatch → error naming expected vs found ("stale schema version vs code") | `domain_store.py:51`, `:1233-1239` |
| S2 `schema.table.<name>` | error | each of the **11 domain tables** exists in `sqlite_master` (`type='table'`): `projects, project_sequences, work_items, work_item_transitions, spaces, pages, page_versions, work_item_page_links, work_item_comments, page_comments, v1_idempotency_keys` | verified fresh-store inventory (§0) |
| S3 `schema.columns.<name>` | error | expected column set (below) ⊆ `PRAGMA table_info(<name>)` names; **missing column → error**; **extra column → info** (forward-compatible, never error) | per-table DDL in `domain_store.py:1037-1205`; exact sets captured from a fresh store |
| S4 `schema.index.<name>` | warning | each of the **8 domain indexes** exists in `sqlite_master` (`type='index'`); present-but-wrong-shape (different table/columns) → warning | `domain_store.py:1090-1193` |
| S5 `schema.broker_scope` | info | `services`/`operations`/`idempotency_keys` absent → info "domain-only file (no edge-broker tables) — fine if you only use domain commands"; when present, S6/S7 run | `broker.py:19` default `state_store=None`; CLI never wires `SqliteStateStore` |
| S6 `schema.broker_columns.<name>` | warning | broker tables present but column drift vs `sql_state_store.py:130-163` DDL (`services: service_id,payload_json,updated_at`; `operations: operation_id,service_id,state,description,payload_json,created_at`; `idempotency_keys: key,request_hash,operation_id,created_at`) | `sql_state_store.py` DDL |
| S7 `schema.broker_version` | warning | broker tables present but `meta['schema_version'] != str(SQLITE_SCHEMA_VERSION)` (`"1"`) or the key is missing | `sql_state_store.py:11`, `:164-170` |

Expected column sets for S3 (verified from a fresh store — copy these exactly into `EXPECTED_DOMAIN_TABLES`):

```
projects:               project_id, key, name, owner, created_at, visibility, members
project_sequences:      project_id, next_sequence
work_items:             work_item_id, project_id, key, title, description, state, assignee, created_at, updated_at
work_item_transitions:  transition_id, work_item_id, from_state, to_state, actor, occurred_at, reason
spaces:                 space_id, key, name, owner, created_at, visibility, members
pages:                  page_id, space_id, current_version, created_at, updated_at
page_versions:          version_id, page_id, version_number, title, body, author, created_at
work_item_page_links:   link_id, work_item_id, page_id, kind, created_by, created_at
work_item_comments:     comment_id, work_item_id, author, body, created_at
page_comments:          comment_id, page_id, author, body, created_at
v1_idempotency_keys:    scope, key, request_hash, response_body, created_at
```

Expected index names for S4: `ix_work_items_project, ix_work_items_state, ix_pages_space, ux_work_item_page_links_triple, ix_links_work_item, ix_links_page, ix_work_item_comments_work_item, ix_page_comments_page`.

### Group A — audit database (only when `--audit-log`/`INNERWORK_AUDIT_DB` resolves)

The audit DB is a **separate file** opened read-only (never via `SqliteAuditSink`, whose constructor writes DDL). If the audit path resolves but the file fails T2/T4/T5-style checks, one error fires: `schema.audit_target` ("audit database not found/not a SQLite database at <path>").

| id | sev | What it verifies | Grounding |
|---|---|---|---|
| A2 `schema.audit_log_table` | error | `audit_log` table exists | `audit.py` `_AUDIT_DDL` |
| A3 `schema.audit_columns` | error | column set ⊆ `PRAGMA table_info(audit_log)`: `event_id, ts, actor, actor_kind, surface, entity_kind, entity_id, action, before_json, after_json, metadata_json` | `_AUDIT_DDL` |
| A4 `schema.audit_triggers` | error | triggers `audit_log_no_update` and `audit_log_no_delete` exist in `sqlite_master` (`type='trigger'`) — the append-only guard is a phase-7 security property; losing it is an integrity/security issue, not a perf hint | `_AUDIT_DDL` |
| A5 `schema.audit_indexes` | warning | indexes `idx_audit_log_entity, idx_audit_log_surface, idx_audit_log_actor` exist | `_AUDIT_DDL` |

**No audit version-drift check exists or may be invented:** `AUDIT_SCHEMA_VERSION = 1` (`audit.py:50`) is never persisted to the DB, so there is no stored value to compare (anti-hallucination, §9).

### 3.3 Human report format (locked)

Findings as `SEVERITY  [check.id] message` lines — severity left-padded to 5 chars (`ERROR`/`WARN `…), plus `INFO `, then a final summary line. Healthy → single `OK` line:

```
$ innerwork doctor data/innerwork.db --audit-log data/audit.db
WARN   [schema.index.ix_work_items_project] index 'ix_work_items_project' is missing (performance)
INFO   [schema.audit_skipped] no audit database configured (set --audit-log or INNERWORK_AUDIT_DB)
INFO   [target.age] database file is 12.3 days old; confirm backups are fresh (docs/operations-runbook.md)
1 warning, 0 errors, 2 info
```

```
$ innerwork doctor data/innerwork.db
OK: database is healthy (0 warnings, 0 errors)
```

---

## §4 JSON output contract (locked)

`--json` prints exactly one object via the existing `_print_json` (`sort_keys=True, indent=2` — byte-stable and identical to every other CLI JSON). Documented stable shape:

```json
{
  "ok": true,
  "exit_code": 0,
  "target": {
    "path": "/abs/data/innerwork.db",
    "exists": true,
    "size_bytes": 40960,
    "mtime": "2026-08-04T10:00:00Z",
    "age_days": 12.3
  },
  "schema_versions": {
    "domain": {"expected": 4, "found": "4", "ok": true},
    "broker": {"expected": 1, "found": null, "ok": true}
  },
  "checks": [
    {"id": "schema.index.ix_work_items_project", "severity": "warning", "ok": false, "message": "index 'ix_work_items_project' is missing (performance)"}
  ],
  "counts": {"error": 0, "warning": 1, "info": 2},
  "summary": "1 warning, 0 errors, 2 info"
}
```

Contract rules (each one testable):

1. **`checks`** is an array in the §3 definition order (T → S → A), each entry `{"id", "severity", "ok", "message"}`; `severity ∈ {"error","warning","info"}`; `ok` is `false` exactly for error/warning findings, `true` for info entries and passed checks. `schema.audit_skipped` (info) is always present when no audit path resolves.
2. **`counts`** = `{"error": N, "warning": N, "info": N}`; `summary` is the same sentence the human report prints last.
3. **`ok`** = `counts.error == 0`. **`exit_code`** mirrors the process exit code (0 or 1 — see rule 5).
4. **`target`** keys are always present; `size_bytes`/`mtime`/`age_days` are `null` when the path does not exist. `path` is the resolved absolute path.
5. **Exit 2 produces no JSON**: usage failures (no target resolvable, unsupported scheme) write the message to stderr and exit 2 with stdout empty — identical to `export`/`import` today. Automation MUST treat a missing JSON payload + exit 2 as "could not run", never as "healthy".
6. The JSON shape is documented in `docs/migration-guide.md` §2.5 (no separate JSON Schema file — a written contract with a shape test is the repo convention, matching the envelope docs).

---

## §5 Exit code contract (locked)

| Code | Meaning | When |
|---|---|---|
| **0** | healthy | zero findings at error **and** warning severity (info allowed) |
| **1** | findings | ≥ 1 error or ≥ 1 warning (report/JSON distinguish severity) |
| **2** | usage / cannot run | no target resolvable (no `DB_PATH`, no `--database-url`, no `INNERWORK_DATABASE_URL`), unsupported URL scheme, or argparse error — stderr message + empty stdout, matching the `_resolve_database_url` contract |

Design decision, documented so it is not "fixed" later: **warnings DO affect the exit code** (exit 1). The roadmap text is explicit — "0 = healthy, non-zero = issues found" — and a DB with a missing index or a read-only file *has* issues found. Automation that tolerates warnings uses `--json` and tests `counts.error == 0` (documented pattern in migration-guide). Exit 2 is reserved strictly for "the tool could not run", consistent with every other CLI command.

---

## §6 Read-only guarantee (locked)

The doctor **must not modify the database, ever** — acceptance criterion, enforced three ways:

1. **`mode=ro` URI open.** Every connection is `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` (helper `_connect_ro(path)` in `doctor.py`). SQLite enforces read-only at the VFS layer; any write attempt raises `OperationalError`. Never plain `sqlite3.connect(path)`.
2. **Never construct the write-capable classes.** `DomainStore.__init__` (`domain_store.py:113`) runs `_initialize` (CREATE TABLEs); `SqliteStateStore.__init__` (`sql_state_store.py:25`) runs `_initialize` (CREATE TABLEs **+ UPSERT of `schema_version`**, `:164-170`); `SqliteAuditSink.__init__` (`audit.py:222-230`) runs `ensure_audit_schema` DDL. `doctor.py` uses raw `sqlite3` only — this is why the CLI dispatch is a dedicated `_doctor_dispatch` branch **before** `_domain_dispatch` (which constructs `DomainStore`).
3. **No write-adjacent PRAGMAs.** No `journal_mode`, `wal_checkpoint`, `vacuum`, `reindex` — only `PRAGMA foreign_keys = OFF`-free plain reads, `PRAGMA table_info`, `PRAGMA index_list`/`sqlite_master` selects, and (opt-in) `PRAGMA integrity_check` (a read-only page scan, safe under `mode=ro`).

Sidecar guarantee: opening a non-WAL store with `mode=ro` creates no `-wal`/`-shm`/`-journal` files. Honest edge (documented in migration-guide): a store left in WAL mode with its `-wal`/`-shm` files deleted will fail T5 with a clear message — that is a real operator misconfiguration the doctor surfaces, not a bug.

Enforcement tests: byte hash + mtime + size of the target unchanged before/after a run; directory listing before == after (no new files); see §8 (`test_read_only_guarantee`).

---

## §7 Honest gap calls (decide-and-document, locked for v1)

| Topic | Decision | Rationale |
|---|---|---|
| Warnings affect exit code | **Yes — warnings → exit 1** | Roadmap text is explicit ("0 = healthy, non-zero = issues found"); JSON `counts` let tolerant automation distinguish. Alternative (warnings→0, git-fsck style) considered and rejected: the spec sentence wins, and the contract is tested either way. |
| `PRAGMA integrity_check` | **Opt-in (`--integrity-check`), off by default** | It scans every page — slow on large stores; header + open checks are the default corruption net. Without the flag the report never claims integrity was verified (anti-hallucination: no fake check that didn't run). |
| Corruption beyond header | Detected only when open fails or `--integrity-check` runs | SQLite reads pages lazily; mid-file bitrot can be invisible to a read of the header. Stated honestly in migration-guide; not claimed otherwise. |
| Audit version drift | **Not checked** | `AUDIT_SCHEMA_VERSION = 1` is never persisted (`audit.py:50`); there is no stored value to compare. Only shape checks A2–A5. |
| Backup freshness | **info-only hint (mtime age)** | `scripts/backup.py` takes arbitrary `SOURCE DEST` — no fixed artifact naming, so cadence is unknowable. Inventing a threshold would be a fabricated check. |
| Disk-space threshold | `free < max(64 MiB, 2 × db size)` → warning | Documented heuristic, warning-only, no flag. Not a "measured" claim — the formula is the contract. |
| Broker tables absent | **info, not warning** | The CLI never creates them (`broker.py:19` default; `render`/`validate` use the in-memory broker). A domain-only file is legitimate; warning on it would be a false positive that breaks exit 0. |
| Extra columns | **info** | Forward-compatible (future schema versions add columns — the `_ensure_column` pattern, `domain_store.py:1209-1232`). Never error. |
| Repair / auto-fix | **Out of scope** | Doctor is diagnostic-only; remediation paths already exist (`migrate`, `import`, backup/restore per runbook). No `--fix`/`--repair`/`--vacuum` flags. |
| New dependencies | **None** | `sqlite3, os, stat, hashlib, shutil, json, dataclasses, pathlib, typing` — all stdlib. No network access. |

---

## §8 Test plan

`tests/test_doctor.py` (new). Reuse the `_run_cli` subprocess pattern from `tests/test_domain_cli.py` (with `env_extra` for env-driven cases). All scenarios generate their own DBs in `tmp_path` — no new fixtures. Root caveat: permission-based tests (`T3`, `T7`) must `pytest.skip` when `os.geteuid() == 0` (root bypasses access bits).

| Test | Asserts |
|---|---|
| `test_help_lists_doctor_with_example` | `innerwork doctor --help` exit 0; stdout contains `examples:` block, `--json`, `--integrity-check`, `--audit-log`; `innerwork --help` lists `doctor` among subcommands. |
| `test_healthy_fresh_db_exit_0` | Fresh `DomainStore`-created DB → exit 0; human report is the single `OK:` line; no error/warning findings. |
| `test_missing_index_warning_exit_1` | `DROP INDEX ix_work_items_project` → warning `schema.index.ix_work_items_project`, exit 1 (warnings fail, §5), `ok=true` in JSON (errors==0). |
| `test_missing_table_exit_1` | `DROP TABLE projects` → error `schema.table.projects`, exit 1. |
| `test_missing_column_exit_1` | Build an old-schema DB by hand (v3 DDL: `projects` without `visibility`/`members`) → error `schema.columns.projects`, exit 1. |
| `test_schema_version_drift_exit_1` | `UPDATE meta SET value='3' WHERE key='domain_schema_version'` → error `schema.domain_version` naming expected 4 / found 3, exit 1. |
| `test_missing_meta_table_exit_1` | `DROP TABLE meta` → error `schema.domain_version`, exit 1. |
| `test_path_does_not_exist_exit_1` | Nonexistent path → error `target.exists`, exit 1; schema group skipped (no `schema.*` checks in report). |
| `test_path_is_directory_exit_1` | Path = a directory → error `target.exists` with the directory message, exit 1. |
| `test_not_a_sqlite_db_exit_1` | File with text content → error `target.sqlite_header`, exit 1; schema group skipped. |
| `test_corrupt_file_open_error_exit_1` | Truncated valid DB (valid header, cut pages) → error `target.openable`, exit 1. |
| `test_integrity_check_opt_in` | Flip a mid-file byte of a valid DB: without `--integrity-check` → exit 0 (documented: header+open is the default net — the file still opens); with `--integrity-check` → error `target.integrity`, exit 1. Both runs assert the flag-only presence of the check id. |
| `test_unreadable_file_exit_1` (skip if root) | `chmod 000` → error `target.readable`, exit 1. |
| `test_not_writable_warning_exit_1` (skip if root) | `chmod 444` → warning `target.writable`, exit 1 (warnings fail). |
| `test_disk_space_warning` | `monkeypatch` `shutil.disk_usage` → tiny `free` → warning `target.disk_space`, exit 1. |
| `test_backup_age_info_never_fails` | `INFO target.age` present with `age_days`; severity is `info`; exit 0 on an otherwise healthy DB. |
| `test_broker_tables_absent_info` | DomainStore-only DB → `INFO schema.broker_scope`, no `schema.broker_*` errors/warnings, exit 0. |
| `test_broker_drift_warning` | Fresh DB + broker init, then `ALTER TABLE operations DROP COLUMN description` (or hand-built drifted schema) → warning `schema.broker_columns.operations`, exit 1. |
| `test_audit_checks_pass` | `--audit-log` → `SqliteAuditSink`-created audit DB → all A-checks pass, exit 0. |
| `test_audit_trigger_missing_is_error` | `DROP TRIGGER audit_log_no_update` → error `schema.audit_triggers`, exit 1. |
| `test_audit_index_missing_is_warning` | `DROP INDEX idx_audit_log_entity` → warning `schema.audit_indexes`, exit 1. |
| `test_audit_path_missing_is_error` | `--audit-log` nonexistent path → error `schema.audit_target`, exit 1. |
| `test_no_url_no_path_exit_2` | No positional, no flag, `INNERWORK_DATABASE_URL` cleared from env → exit 2; stderr names `--database-url`/`INNERWORK_DATABASE_URL`; stdout empty (also with `--json`). |
| `test_unsupported_scheme_exit_2` | `--database-url postgres://…` → exit 2, stderr, stdout empty. |
| `test_positional_wins_over_flag` | Valid positional path + conflicting `--database-url` → validates the positional file (exit 0 on a healthy file). |
| `test_json_shape_stable` | Healthy DB with `--json`: stdout parses; top-level keys exactly `{ok, exit_code, target, schema_versions, checks, counts, summary}`; check ids/order follow §3; severities ∈ {error, warning, info}; `exit_code` == process rc. Run twice → byte-identical stdout (stability). |
| `test_json_matches_human_report` | Same DB: `--json` `counts`/`summary` agree with the human report's summary line; finding set identical. |
| `test_read_only_guarantee` | sha256 + mtime + size of the DB before == after a doctor run (including `--integrity-check` and `--audit-log` runs); directory listing before == after (no `-wal`/`-shm`/`-journal` created). |
| `test_drift_guard_expected_schema_matches_store` | Fresh `DomainStore`: every `EXPECTED_DOMAIN_TABLES` table exists with every expected column; every `EXPECTED_DOMAIN_INDEXES` index exists. Fresh broker store: `EXPECTED_BROKER_TABLES` match. `SqliteAuditSink` DB: `EXPECTED_AUDIT_*` match. (The anti-drift net — if a future schema change breaks the mirror, this test fails first.) |
| `test_existing_suites_stay_green` | `tests/test_cli.py`, `tests/test_domain_cli.py`, `tests/test_migration.py` pass **unmodified**. |

---

## §9 Anti-hallucination checklist

Implementation worker MUST run each check and quote the (empty / verified) output in the PR description.

| Check | Command |
|---|---|
| No DDL/DML in doctor | `grep -RInE "CREATE TABLE|CREATE INDEX|ALTER TABLE|INSERT INTO|UPDATE |DELETE FROM|DROP |VACUUM|journal_mode|wal_checkpoint" src/innerwork/doctor.py` returns nothing. |
| Read-only open everywhere | `grep -n "mode=ro" src/innerwork/doctor.py` shows the single connect helper; `grep -n "sqlite3.connect" src/innerwork/doctor.py` shows **only** `file:...?mode=ro` URI opens. |
| Integrity check is real and opt-in | `grep -n "integrity_check" src/innerwork/doctor.py src/innerwork/cli.py` — occurrences live only inside the `--integrity-check` branch; no report text claims integrity ran without the flag. |
| No audit version-drift claim | `grep -RInE "audit.*version|AUDIT_SCHEMA_VERSION" src/innerwork/doctor.py` returns nothing (audit has no persisted version — §7). |
| No write-capable construction | `grep -RInE "DomainStore|SqliteStateStore|SqliteAuditSink" src/innerwork/doctor.py` returns nothing (raw `sqlite3` only). |
| Expected schema mirror is current | `test_drift_guard_expected_schema_matches_store` passes (fresh-store introspection vs `EXPECTED_*`). |
| Stdlib only | `grep -RInE "^(import|from) " src/innerwork/doctor.py` shows only stdlib modules. |
| Files-touched boundary | `git diff --stat main` shows exactly the §1 files. |
| Schema authorities untouched | `git diff main -- src/innerwork/domain_store.py src/innerwork/sql_state_store.py src/innerwork/audit.py` is empty. |
| Compliance | `uv run python scripts/check_anti_hallucination.py` exits 0. |

---

## §10 Acceptance gates (must hold before opening PR)

| Gate | Verification |
|---|---|
| Exit-code contract | §8 matrix passes: healthy → 0, any error or warning → 1, unresolvable target/unsupported scheme → 2 with empty stdout. |
| Read-only | `test_read_only_guarantee` passes (hash/mtime/size/dir unchanged, including `--integrity-check` runs); §9 grep shows `mode=ro` only. |
| JSON stable | `test_json_shape_stable` passes (exact keys, fixed check order, deterministic bytes across runs); shape documented in migration-guide §2.5. |
| Help example | `test_help_lists_doctor_with_example` passes (epilog examples block present). |
| No hallucinated checks | Every §3 check id is either tested or explicitly opt-in; drift-guard test green; §9 grep outputs quoted in the PR. |
| CI parity | `uv run pytest -x`, `uv run ruff check .`, `uv run pyright` all green — exactly what `.github/workflows/ci.yml` runs. **Never push a branch with red pyright** (2026-05-29 phase-7 incident). |

---

## §11 Exit criteria (done definition for the implementation task)

Per the roadmap item and child task `t_88234df1`:

1. `innerwork doctor [DB_PATH] [--database-url ...] [--audit-log ...] [--json] [--integrity-check]` implemented; help text carries the §2 example block; `doctor` appears in `innerwork --help`.
2. Every §3 check id maps to a real schema object (drift-guard test enforces); no invented tables/columns/checks; `PRAGMA integrity_check` only ever runs under `--integrity-check`.
3. Exit-code contract §5 (0 healthy / 1 findings / 2 usage) implemented, documented in migration-guide, and covered by the §8 matrix.
4. `--json` output follows §4 exactly — stable keys, fixed order, deterministic bytes — and is documented in migration-guide §2.5.
5. Read-only guarantee §6 enforced (mode=ro opens only, no store/audit-sink construction, no DDL/DML) and proven by `test_read_only_guarantee`.
6. `docs/operations-runbook.md:275` no-longer claims the command doesn't exist; runbook restore-verification recipe mentions `innerwork doctor`; CHANGELOG `[Unreleased]` gains `### Added — innerwork doctor`; roadmap bullet moved to shipped (optional, same PR).
7. `uv run pytest -x && uv run ruff check . && uv run pyright` all green before push.
8. PR opened against `main` on `feat/innerwork-doctor`, **DO NOT MERGE** — end with `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")` per the child task's mandate.

---

## §12 Handoff checklist for the implementation worker (atlassianeng)

1. Branch from `main` at the current HEAD: `git checkout -b feat/innerwork-doctor` (child task `t_88234df1` pins this branch name; worktree workspace at `/home/eml/atlassian/atlassian-innerwork`).
2. Write files in §1 order. The scoping doc (this file) is not modified.
3. Implement `src/innerwork/doctor.py` per §3–§6: dataclasses `Finding`/`DoctorReport` (with `to_dict()`), `EXPECTED_DOMAIN_TABLES`/`EXPECTED_DOMAIN_INDEXES`/`EXPECTED_BROKER_TABLES`/`EXPECTED_AUDIT_*` mirrors, `_connect_ro(path)` (`file:...?mode=ro` URI), `run_doctor(path, *, integrity_check=False, audit_path=None)` running checks in §3 order, human renderer per §3.3, `DoctorReport.to_dict()` per §4. Export the public names via module `__all__` or direct import (flat module next to `cli.py`, matching `analytics.py`/`portability.py`).
4. Wire `cli.py`: register `doctor` in `build_parser()` (positional `db_path`, `--database-url` via `_add_db_arg`, `--audit-log` via `_add_audit_log_arg`, `--json`, `--integrity-check`, epilog examples); add `_doctor_dispatch(args)` (resolve target per §2 precedence — call `_resolve_database_url(args)` only when `args.db_path is None`; resolve audit path from `--audit-log`/`INNERWORK_AUDIT_DB`; print via `_print_json` for `--json` else human renderer; return 2 on the resolver's `SystemExit`, else 1 if `report.counts.error > 0` else 0) and the `main()` branch **before** the domain-dispatch set.
5. Add `tests/test_doctor.py` per §8 (all rows), including the read-only hash test, the JSON-shape/stability tests, the exit-code matrix, the opt-in integrity tests, and the drift-guard test.
6. Add migration-guide §2.5 (command, exit codes, JSON contract, read-only guarantee, example), runbook `:275` replacement + restore-recipe line, CHANGELOG `### Added — innerwork doctor` entry; optionally move the roadmap bullet (§1 row 8).
7. Run the CI-parity gate exactly as GitHub Actions does: `uv run pytest -x`, `uv run ruff check .`, `uv run pyright`. **All three must be green before push.**
8. Run the §9 grep checks and quote results in the PR body.
9. Push via SSH remote (`git@github-personal:m0n3r0/atlassian-innerwork.git`), open PR titled `feat(cli): innerwork doctor — read-only database validation (schema, version drift, operator misconfigurations)` against `main`. **DO NOT MERGE.**
10. `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")`.
