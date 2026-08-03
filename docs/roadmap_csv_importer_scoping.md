# Roadmap item: CSV/TSV importer for work_items and projects — PM scoping

**Status:** PM scoping (pre-implementation). Source: `docs/roadmap.md` → "Directional next" → Migration (`slug=csv-importer`).
**Parent:** post-launch backlog item; no phase number. Implementation task `t_8609bbb9` branches from `main` on `feat/csv-importer`.
**Audience:** the implementation worker (atlassianeng). Read this end-to-end before touching files.

---

## §0 Honest baseline (what the repo already has, today)

Verified against `main` at commit `5eaf4ac` on 2026-08-03.

| Asset | Present? | Path | Notes |
|---|---|---|---|
| Work-graph domain model | ✅ | `src/innerwork/domain.py` | `Project` (key `^[A-Z][A-Z0-9]{1,9}$`, name, owner, created_at, visibility, members) and `WorkItem` (work_item_id, project_id, key `PROJ-N`, title ≤200, description ≤4000, state ∈ `{todo,in_progress,done}`, assignee, created_at, updated_at). **`WorkItem` has no `type` field** — this drives the `type`-column gap call in §4. |
| Domain store | ✅ | `src/innerwork/domain_store.py` (1294 lines) | `create_project` (raises `DuplicateProjectKeyError` on key reuse) and `create_work_item` — the latter **auto-allocates** `key` from `project_sequences` and always sets `state=INITIAL_STATE` ("todo"). There is **no store API to create a work item with an explicit key or state**. **This file is read-only for this task.** |
| Portability layer | ✅ | `src/innerwork/portability.py` (455 lines) | `export_domain` / `import_domain` preserve explicit keys and states, FK-safe insert order, byte-stable round-trip. `import_domain`'s `_validate_fresh_target` requires **all nine** collections empty and its sequence rebuild **wipes and re-seeds** every project — correct for a fresh target, wrong for `--allow-populated`. **This file is read-only for this task**; the CSV importer does NOT call `import_domain` (see §1 rationale). |
| Markdown-tree importer | ✅ | `src/innerwork/markdown_importer.py` (427 lines) | The direct precedent: writes **through** `DomainStore`, dry-run preview, fresh-target check that gates **only the three tables it touches** (`spaces`/`pages`/`page_versions`), `MarkdownImportError` → CLI exit 2, summary counts from `len()` of the scan. Documented in `docs/migration-guide.md` §4. |
| CLI scaffold | ✅ | `src/innerwork/cli.py` (421 lines) | `argparse` subcommands, `_add_db_arg` (`--database-url` + `INNERWORK_DATABASE_URL`), `_domain_dispatch`, JSON to stdout via `_print_json`, exit 2 + stderr on user errors. `import-markdown` (commit `5eaf4ac`) is the exact pattern to copy. |
| Migration guide | ✅ | `docs/migration-guide.md` (319 lines) | §4 documents `import-markdown`; §1 lists what is *not* in the portable surface. §7 explicitly says hosted-Jira/Confluence importers are **not** shipped. The CSV importer gets a new section here. |
| CSV parsing deps | ✅ | `pyproject.toml` | `requires-python = ">=3.10"`; stdlib `csv` module is fully sufficient (BOM via `utf-8-sig`, CRLF/quoting via `newline=""` + `csv.reader`, delimiter override). **No new dependency.** |
| Round-trip precedent | ✅ | `tests/test_markdown_importer.py` (18 tests) + `tests/test_migration.py` | `test_roundtrip_import_export_import_byte_identical` defines the round-trip gate: import → `export_domain_json` → `import_domain_json` into a fresh store → re-export → byte-identical. |
| CSV/TSV importer | ❌ | n/a | Nothing reads a `.csv`/`.tsv` file today. |

**Implication.** A contained slice mirroring the markdown importer: one new module (parse + map + validate + a scoped insert path), one CLI subcommand, one test file, one fixture dir, one migration-guide section, one changelog entry. The domain core, portability, and schema are untouched.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `docs/roadmap_csv_importer_scoping.md` | (this file) | n/a | Exists at PM-scoping time. Implementation worker does not modify. |
| 2 | `src/innerwork/csv_importer.py` | **new** | ~380 lines | The importer module. Public surface: `CsvImportError(ValueError)`; `scan_csv_file(path, *, owner, delimiter="auto", created_at=None) -> CsvImportPlan` (pure: parse + map + validate + resolve keys + within-file conflict pre-checks; filesystem reads only, no DB); `import_csv_file(store, path, *, owner="importer", delimiter="auto", created_at=None, dry_run=False, allow_populated=False) -> dict` (fresh-target check, DB-level conflict checks, scoped insert; returns `{"projects": int, "work_items": int, "warnings": [...], "dry_run": bool, "delimiter": "comma"\|"tab"}`). Dataclasses `CsvProject`, `CsvWorkItem`, `CsvImportPlan`. Internal helpers: `_detect_delimiter`, `_read_table`, `_sanitize_project_key`, `_map_state`, `_resolve_keys`, `_validate_fresh_target`, `_write_plan`, `_bump_sequences`. See §2, §3 for exact semantics. |
| 3 | `src/innerwork/cli.py` | **edit** | +~30 lines | Add subcommand `import-csv` (positional `file: Path`; `--database-url` via existing `_add_db_arg`; `--owner` default `"importer"`; `--delimiter` choices `auto|comma|tab` default `auto`; `--dry-run` flag; `--allow-populated` flag). Add `"import-csv"` to the `_domain_dispatch` set and a dispatch branch: call `import_csv_file`, print summary JSON, exit 0; `CsvImportError`/`OSError` → stderr + exit 2. No other changes to the file. |
| 4 | `tests/test_csv_importer.py` | **new** | ~280 lines | API-level + CLI-level tests per §6. |
| 5 | `tests/fixtures/csv_import/` | **new** | 3 files | Checked-in fixtures: `work_items.csv` (comma), `work_items.tsv` (tab), `edge_cases.csv` (BOM, CRLF, quoted comma/tab, blank line, unknown column, `type` column). Error-case inputs (missing header, invalid status, duplicate natural key, bad key format, header-only) are written as tmp files inside the tests — they are 2–4 lines each and don't deserve checked-in fixtures. See §6. |
| 6 | `docs/migration-guide.md` | **edit** | +~70 lines | New section after §4 "Markdown-tree importer" (renumber §5→§6, §6→§7, §7→§8, §8→§9): the `import-csv` command, delimiter rules, the column mapping table, the status vocabulary, key allocation, fresh-target + `--allow-populated` semantics, conflict behavior, round-trip posture, and the limits from §4. Update the §1 "not in the portable surface" list with "CSV column provenance (column names, `type` values) is not re-emitted by `export`". |
| 7 | `CHANGELOG.md` | **edit** | +~8 lines | Under `[Unreleased]`, add `### Added — CSV/TSV importer` subsection (after the markdown-tree importer subsection) enumerating the new module, subcommand, tests, and docs. No version bump. |
| 8 | `docs/roadmap.md` | **edit (optional, recommended)** | −1/+4 lines | After the importer PR merges, move the "Investigate a CSV / TSV importer for `work_items` and `projects`" bullet from "Directional next → Migration" into the "Shipped through Phase 10" list as a one-line "Post-phase-10 additions" note. Same PR, tiny diff. |

**Files that LOOK like they should be touched but MUST NOT be touched.**

| Path | Why not |
|---|---|
| `src/innerwork/portability.py`, `src/innerwork/domain_store.py`, `src/innerwork/domain.py`, `src/innerwork/knowledge.py`, `src/innerwork/model.py` | Domain core + stable wire format. The importer is a **caller**, not a modifier. |
| `src/innerwork/migrators/*` | `migrators/` is scoped to "adapters from foreign JSON shapes to the native portability format" (its `__init__.py` docstring). The CSV importer writes rows directly, not a portability envelope; it lives as a sibling module exactly like `markdown_importer.py`. |
| `import_domain` / `portability.py` reuse as the write path | `import_domain` requires **all nine** collections empty and wipes+re-seeds every project sequence. That cannot express criterion 4's `--allow-populated` (import into a populated store) and would wrongly block import when a knowledge graph coexists. The importer therefore has its own ~40-line scoped insert path (projects, work_items, `project_sequences`) mirroring portability's SQL against the same tables — `DOMAIN_SCHEMA_VERSION` is stable and the §5 round-trip gate pins the two paths to each other. |
| `src/innerwork/cli.py` `import` subcommand | `import` is the portability-envelope command with strict all-collections-fresh semantics. `import-csv` is a **new sibling** subcommand, not an extension of `import` — same relationship as `import-markdown` to `import`. |
| `.github/workflows/*`, `pyproject.toml` (deps), `src/innerwork/app.py`, `src/innerwork/domain_api.py` | No HTTP surface, no CI change, no new dependency (stdlib `csv` suffices). |
| `tests/test_migration.py`, `tests/test_portability.py`, `tests/test_markdown_importer.py`, `tests/fixtures/markdown_tree/`, `tests/fixtures/synthetic_migration.json` | Existing suites stay untouched; the new suite lives in `tests/test_csv_importer.py` + `tests/fixtures/csv_import/`. |

---

## §2 File → project/work-item mapping rules (locked)

These are the exact, deterministic rules `scan_csv_file` implements. "Deterministic" means: for a given file, the same scan produces the same projects/work-items/warnings regardless of anything (all iteration is sorted, header matching is normalized, row order is preserved as the tiebreaker).

1. **Input.** `<file>` must be an existing file, else `CsvImportError` (exit 2). One file only: it contains **work-item rows**; the `projects` collection is **derived** from the distinct `project` column values. There are no separate project rows.
2. **Encoding and newlines.** Read with `encoding="utf-8-sig"` (a leading BOM is stripped) and `newline=""` (the csv-module requirement; CRLF and LF both parse). Rows are parsed with `csv.reader`.
3. **Header row required.** The first row is the header. An empty file (no rows at all, or only blank lines) or a file with no data rows after the header → `CsvImportError`. Header cells are matched **case-insensitively and whitespace-trimmed** (`"Project"` and `" project "` both map to `project`). Two headers normalizing to the same name → `CsvImportError` listing both.
4. **Row shape.** Every data row must have exactly as many cells as the header. A row with **more** cells → `CsvImportError` naming the row. A row with **fewer** cells → `CsvImportError` naming the row as well — use `dict(zip(header, row, strict=True))` so a short row is a loud error, never a silent pad. Blank lines are skipped by `csv.reader` (documented, not an error).
5. **Projects.** Distinct sanitized `project` column values, **sorted by sanitized key**. `_sanitize_project_key`: uppercase, drop every character outside `[A-Z0-9]`, then validate against `^[A-Z][A-Z0-9]{1,9}$` (mirrors `markdown_importer._space_key_from_dirname`). Invalid → `CsvImportError` naming the value; **no silent truncation**. Two distinct values sanitizing to the same key → `CsvImportError` listing both. `name` = the first non-blank `project_name` cell for that project in sorted work-item order, else the verbatim `project` cell of the first row. `owner` = the `--owner` value; `visibility`/`members` = model defaults (`internal`, `()`).
6. **Work items.** One per data row. `title` (required, strip, non-blank, ≤200), `description` (optional, ≤4000, blank → `""`), `assignee` (optional, blank → `""`), `state` (from `status` column per §3 vocabulary, default `todo`).
7. **Keys.** `key` column optional (see §3). When absent, keys are **auto-allocated** per project in the importer's deterministic row order: `{PROJ}-{n}` where `n` starts at the project's current `next_sequence` (1 on a fresh store) and increments. When present, the explicit key is validated (`^[A-Z][A-Z0-9]{1,9}-\d+$` and its prefix must equal the sanitized project key) and used verbatim. See §3 for allocation and conflict rules.
8. **Ordering.** Rows are processed in **file order** (row 2 = first data row) for allocation and error messages. Projects are created in sorted-key order; work items are inserted in file order grouped by project (sorted-key project order, file order within). Warnings are sorted. IDs: `project_id`/`work_item_id` via `uuid.uuid4()` (same pattern as the markdown importer and `project-create`).
9. **Timestamps.** `created_at`/`updated_at` = one import-wide UTC ISO timestamp (default `utc_now_iso()`; API parameter `created_at` for deterministic tests — no CLI flag, same as the markdown importer). No transition history is synthesized: `state` is taken verbatim from the file (§4).
10. **Fresh-target requirement.** `_validate_fresh_target` refuses to run when `projects` or `work_items` tables are non-empty (`CsvImportError`, exit 2) — **unless** `--allow-populated` is passed (criterion 4). Only the two touched collections gate; spaces/pages/links/comments may exist and are untouched (mirrors the markdown importer's scoping). The check runs in dry-run mode too, so the preview is honest.

---

## §3 Column mapping, status vocabulary, and key handling (locked)

### 3.1 Column mapping table (documented verbatim in the migration guide)

Header matching is case-insensitive and whitespace-trimmed. Unknown columns do **not** abort the import — they produce one warning listing the unknown column names (sorted), and are otherwise ignored.

| Canonical column | Accepted aliases | Required | Target field | Rules |
|---|---|---|---|---|
| `project` | `project_key`, `project key` | **required** | `Project.key` | Sanitized per §2.5 (`eng` → `ENG`, `a-b` → `AB`, `x` → error). Determines project membership/creation. |
| `project_name` | `project name` | optional | `Project.name` | Used only when the project is **newly created**; ignored (with a warning) when the project already exists under `--allow-populated`. |
| `title` | `summary` | **required** | `WorkItem.title` | Strip; non-blank; ≤200. Missing/blank → `CsvImportError` naming the row and column. |
| `status` | `state` | optional | `WorkItem.state` | Default `todo`; vocabulary mapping in §3.2. Unknown value → `CsvImportError` naming the row, the value, and the allowed set. |
| `type` | `work_item_type`, `issue type` | optional | — (no field) | **Recognized but unmappable**: the domain model has no work-item type field. Dropped, with **one** warning total (not per row): `type column dropped: the domain model has no work-item type field`. |
| `description` | `desc` | optional | `WorkItem.description` | ≤4000; blank → `""`. |
| `assignee` | — | optional | `WorkItem.assignee` | Blank → `""`; non-blank stored verbatim. |
| `key` | `work_item_key` | optional | `WorkItem.key` | Explicit key; must match `^[A-Z][A-Z0-9]{1,9}-\d+$` **and** its prefix must equal the sanitized project key. Enables lossless round-trip and disambiguates duplicate titles (§3.3). |

Any other column (e.g. `priority`, `labels`, `due_date`) → unknown-column warning, ignored.

### 3.2 Status vocabulary (locked)

The `status` cell is normalized (strip + lowercase + collapse internal whitespace) and mapped:

| Normalized value | Maps to |
|---|---|
| `todo`, `backlog`, `open`, `to do`, `to-do` | `todo` |
| `in_progress`, `in progress`, `wip`, `doing`, `inprogress` | `in_progress` |
| `done`, `closed`, `complete`, `completed`, `resolved` | `done` |

Anything else → `CsvImportError` naming the row, the offending value, and the three canonical states. The mapping table is a module-level constant (`_STATUS_ALIASES`) so the migration guide and the code cannot drift.

### 3.3 Key allocation and conflict rules (locked)

Within one file (per project, in file order):

- Maintain a per-project `used` set of suffixes and a `next_auto` counter (starts at the store's current `next_sequence`, or 1).
- Explicit-key row: validate format + prefix; if the key is already in `used` (another row in the same file) → `CsvImportError` naming both rows. Allocate it (add its suffix to `used`).
- Auto row: `key = f"{PROJ}-{next_auto}"`, advancing `next_auto` past every used suffix. Because explicit and auto allocation interleave in file order, an auto row that sorts before an explicit `ENG-5` row gets `ENG-1` and the explicit row keeps `ENG-5` — deterministic, no renumbering of explicit keys.

Across the store (`import_csv_file`, runs in dry-run too so the preview is honest):

- Explicit key already exists in `work_items` → `CsvImportError` naming the key and the row (**explicit conflict error**, criterion 6).
- No explicit key → the import natural key is `(project_key, title)`. If a work item with that project and title already exists → `CsvImportError` naming the row, the title, and the existing work item's key. This makes re-importing the same CSV into the same store always fail loudly instead of silently duplicating rows (criterion 6: "idempotent re-import **or** explicit conflict error" — this implements the explicit-conflict arm).
- An explicit `key` column disambiguates legitimate duplicate titles: with explicit keys, title duplication is allowed (keys are unique), so only key conflicts error.

After the write, `project_sequences` is **bumped incrementally** for the projects in the file: `next_sequence = max(current, max_used_suffix) + 1` (INSERT-or-UPDATE). This deliberately diverges from `portability._rebuild_project_sequences` (which wipes and re-seeds every project) because `--allow-populated` must not disturb projects that are not in the file.

---

## §4 Honest gap calls (decide-and-document, locked for v1)

| Topic | Decision | Rationale |
|---|---|---|
| Work-item `type` | **Dropped with a warning.** | The model has no type field and v1 adds no schema change. Operators with type data must encode it in `title`/`description` or wait for a model change. |
| Transition history | **Not synthesized.** `state` is taken verbatim. | A CSV row is a snapshot, not an event log; fabricating `todo → done` transitions would invent history (and `created_at`/`updated_at` would diverge). The portability envelope round-trips the state exactly. |
| Project `visibility`/`members` | Defaults only (`internal`, `()`). | No CSV columns in v1 (mirrors the markdown importer's space-metadata decision). |
| Links / comments / spaces / pages | **Never created.** | Roadmap scope is `work_items` and `projects` only. |
| `--allow-populated` semantics | Skips the fresh-target check; **never modifies existing rows**; conflicting rows error (no silent skip). | Criterion 4 requires an explicit-allow escape hatch. Existing rows are treated as immutable; the conflict rules of §3.3 still apply so an allow-populated import cannot silently duplicate. |
| Delimiter auto-detection | **Extension-based, no `csv.Sniffer`.** `auto` = `.tsv` → tab, anything else → comma; `--delimiter` overrides. | `Sniffer` heuristics are not stable enough to lock into a spec; extension + explicit override is deterministic and boring. The resolved delimiter is echoed in the summary JSON. |
| `project_name` on an existing project | Ignored, **with a warning**. | Existing rows are never modified; the warning makes the non-application visible. |
| Header-only file / empty file | **Error** (exit 2). | An import that writes nothing is almost certainly an operator mistake; loud beats guessing. |
| Row with more cells than the header | **Error** naming the row. | Malformed input; silent truncation hides data loss. |
| CSV column provenance | **Not round-trippable.** `export` emits the domain fields (`key`, `title`, `description`, `state`, `assignee`, timestamps) — not the original column names or `type` values. | Same one-way-door posture as markdown frontmatter; documented in the migration guide so operators don't expect byte-identical CSVs back. |

---

## §5 Acceptance gates (must hold before opening PR)

| Gate | Verification |
|---|---|
| Importing a fixture file produces projects/work_items consistent with the file. | `pytest tests/test_csv_importer.py -q` passes; `test_import_csv_populates_store` asserts the store's projects/work_items exactly match the fixture (keys, titles, states, descriptions, assignees, project names, explicit keys, auto keys in file order). |
| Imported content round-trips through `innerwork export` without loss. | `test_roundtrip_import_export_import_byte_identical` passes: import fixture → `export_domain_json` → `import_domain_json` into a second fresh store → re-export → both exports byte-identical; keys/states/titles preserved. This gate also pins the importer's insert SQL to the portability schema. |
| No network access; purely local file input. | The importer imports nothing beyond stdlib (`csv`, `pathlib`, `uuid`, `datetime`, `dataclasses`, `typing`) + local modules (`domain_store`, `domain`); grep check in §7. |
| Fresh-target rule enforced; `--allow-populated` honored. | `test_fresh_target_required` passes (non-empty `projects` → `CsvImportError`, exit 2, nothing written) and `test_allow_populated_imports` passes (populated store + flag → imports non-conflicting rows; conflicting rows still error). |
| Conflict semantics (criterion 6) enforced. | `test_natural_key_conflict_rejected`, `test_explicit_key_conflict_rejected`, `test_dup_key_in_file_rejected`, `test_bad_key_prefix_rejected` pass: re-importing the same file into the same store errors with the existing key named; nothing is written. |
| CLI is wired and honest. | `innerwork import-csv --help` lists `file`, `--database-url`, `--owner`, `--delimiter`, `--dry-run`, `--allow-populated`; CLI tests assert summary JSON and exit codes (0 / 2). |
| Full CI parity. | `uv run pytest -x`, `uv run ruff check .`, `uv run pyright` all clean — exactly what `.github/workflows/ci.yml` runs. **Never push a branch with red pyright.** |

---

## §6 Test plan

Fixtures (`tests/fixtures/csv_import/`):

| File | Contents |
|---|---|
| `work_items.csv` | Comma-delimited, LF. 2 projects, 4 work items: explicit keys (`ENG-1`, `ENG-3`), auto keys, statuses `todo`/`in_progress`/`done`, a `description` with an embedded comma, an `assignee`, `project_name` on one project. Happy path for parse + import + round-trip. |
| `work_items.tsv` | Tab-delimited variant of the same shape (different titles/keys so count assertions can't be confused with the CSV fixture). |
| `edge_cases.csv` | Comma-delimited with a **UTF-8 BOM**, **CRLF line endings**, a title containing a **quoted comma** (`"Fix parser, v2"`), a description containing a **quoted tab**, a **blank line** mid-file, an unknown column `priority`, and a `type` column. Used by parse tests, warning tests, and the CLI dry-run test. |

Error-case inputs (missing header / empty file, header-only, invalid status, duplicate natural key, bad key prefix, short row, duplicate normalized header) are written as 2–4 line tmp files inside the tests.

| Test | Asserts |
|---|---|
| `test_parse_comma_file` / `test_parse_tab_file` | `scan_csv_file` returns the expected plan: delimiter resolved (`comma`/`tab`), projects derived+sorted, work items mapped, warnings empty. Counts derive from the file (2 projects, 4 items — the fixture's real length). |
| `test_delimiter_override_wins` | `.csv` file parsed as tab with `delimiter="tab"` and vice versa; `plan.delimiter` echoes the override. |
| `test_bom_crlf_quoted_and_blank_lines` | `edge_cases.csv` parses: BOM stripped, CRLF rows read, quoted comma preserved in title, quoted tab preserved in description, blank line skipped; summary `work_items` == number of real data rows (assert against `len(plan.work_items)`, not a magic constant). |
| `test_unknown_columns_warned` | `edge_cases.csv` warnings contain exactly one entry naming `priority` (unknown) and one naming `type` (dropped); import still succeeds. |
| `test_missing_required_column_rejected` | File without `title` → `CsvImportError` naming the column. File without `project` → same. |
| `test_missing_header_rejected` / `test_header_only_rejected` | Empty file and header-only file → `CsvImportError`. |
| `test_duplicate_normalized_header_rejected` | `title` + `Title` → `CsvImportError`. |
| `test_short_row_rejected` / `test_long_row_rejected` | Row with fewer / more cells than the header → `CsvImportError` naming the row. |
| `test_project_key_sanitized` | `eng` → project key `ENG`; `a-b` → `AB`. |
| `test_invalid_project_key_rejected` | `x` (sanitizes to 1 char) → error; `a-b` and `a_b` in one file (both → `AB`) → error listing both. |
| `test_status_mapping` | All §3.2 aliases map to the canonical states. |
| `test_invalid_status_rejected` | `Blocked` → `CsvImportError` naming the row and the allowed set. |
| `test_explicit_keys_used` | Explicit `key` cells land verbatim in `work_items.key`; auto rows get `{PROJ}-{n}` in file order; sequences re-seeded so a later `create_work_item` does not collide. |
| `test_bad_key_prefix_rejected` | `key=ENG-1` under `project=OTHER` → error. `key=1` → error. |
| `test_dup_key_in_file_rejected` | Two rows with `ENG-1` → error naming both rows. |
| `test_natural_key_conflict_rejected` | Import fixture → import same file again → `CsvImportError` naming the title and existing key; second import wrote nothing. |
| `test_explicit_key_conflict_rejected` | `--allow-populated` store with existing `ENG-1`; CSV row keyed `ENG-1` → error. |
| `test_fresh_target_required` | Store with one pre-existing project → error, no rows added (without `--allow-populated`). |
| `test_allow_populated_imports` | Populated store + `--allow-populated` + non-conflicting CSV → rows added, existing rows untouched, `project_name`-on-existing warning present. |
| `test_dry_run_writes_nothing` | `--dry-run` → identical summary with `dry_run: true`; DB has zero new rows (or no DB created); fresh-target check still runs. |
| `test_import_csv_populates_store` | API import into tmp DB → `list_projects`/`list_work_items` reflect the file (keys, states, titles, descriptions, assignees, project names). |
| `test_roundtrip_import_export_import_byte_identical` | Import fixture → export → import into fresh store → export; two exports byte-identical. |
| `test_cli_import_csv_summary` | `main([...])` or subprocess `python -m innerwork.cli import-csv <fixture> --database-url sqlite:///tmp.db` → exit 0, stdout JSON `{"projects": N, "work_items": N, "warnings": [...], "dry_run": false, "delimiter": "comma"}`. |
| `test_cli_dry_run_no_write` | `--dry-run` → same summary, `dry_run: true`, zero rows in DB. |
| `test_cli_missing_file_exit_2` / `test_cli_fresh_target_exit_2` / `test_cli_invalid_status_exit_2` | Exit code 2 + stderr message; nothing written. |

---

## §7 Anti-hallucination checklist

Implementation worker MUST run each check and quote the (empty / verified) output in the PR description.

| Check | Command |
|---|---|
| No hosted-importer claim | `grep -RInE "Jira.*(importer|import)|Confluence.*(importer|import)|hosted.*import" docs/migration-guide.md src/innerwork/csv_importer.py CHANGELOG.md` returns nothing beyond the existing "not shipped" sentences. |
| No third-party CSV-library claim | `grep -RInE "pandas|polars|openpyxl|csvkit|delimiter.*(library|parser)" src/innerwork/ docs/migration-guide.md CHANGELOG.md` returns nothing. The importer uses only `csv`/`pathlib`/`uuid`/`datetime`/`dataclasses`/`typing`/local modules. |
| No fabricated counts/benchmarks | `grep -RInE "[0-9]+ (projects|work items|rows) (imported|per second|in [0-9]+ms)" src/innerwork/csv_importer.py` returns nothing; summary counts come from `len(plan...)`, never hard-coded. |
| No network surface | `grep -RInE "httpx|requests|urllib|socket|http://|https://" src/innerwork/csv_importer.py` returns nothing. |
| Files-touched boundary | `git diff --stat main` shows exactly: `src/innerwork/csv_importer.py`, `src/innerwork/cli.py`, `tests/test_csv_importer.py`, `tests/fixtures/csv_import/*`, `docs/migration-guide.md`, `CHANGELOG.md`, optional `docs/roadmap.md`. Nothing else. |

---

## §8 Exit criteria (done definition for the implementation task)

Per the roadmap item and child task `t_8609bbb9`:

1. `innerwork import-csv <file> --database-url sqlite:///...` works on `tests/fixtures/csv_import/work_items.csv` and `work_items.tsv` — projects/work_items created consistent with §2/§3.
2. Portability round-trip test passes with imported content (`test_roundtrip_import_export_import_byte_identical`).
3. Purely local file input; no network access in the new code (grep-clean).
4. `uv run pytest -x && uv run ruff check . && uv run pyright` all green before push.
5. PR opened against `main` on `feat/csv-importer`, **DO NOT MERGE** — end with `kanban_block(reason="review-required: ...")` per the child task's mandate.

---

## §9 Handoff checklist for the implementation worker (atlassianeng)

1. Branch from `main` at the current HEAD: `git checkout -b feat/csv-importer`. (Child task `t_8609bbb9` already pins this branch name.)
2. Write files in §1 order. The scoping doc (this file) is not modified.
3. Implement `src/innerwork/csv_importer.py` exactly per §2/§3/§4. Pure scan → validated plan → scoped insert. No raw SQL beyond the projects/work_items/`project_sequences` statements mirroring portability's, no portability-envelope generation, no new dependencies, no network.
4. Wire the CLI subcommand per §1 row 3. Follow the existing error convention: `CsvImportError`/`OSError` → stderr + exit 2; success → summary JSON + exit 0.
5. Add the checked-in fixtures and the test file per §6. Include the round-trip byte-identity test — it is the acceptance gate.
6. Add the migration-guide section (renumbering §5–§8 → §6–§9) and the CHANGELOG entry; optionally move the roadmap bullet (§1 row 8).
7. Run the CI-parity gate exactly as GitHub Actions does: `uv run pytest -x`, `uv run ruff check .`, `uv run pyright`. **All three must be green before push.** Do not repeat the 2026-05-29 phase-7 incident (green pytest, red pyright).
8. Run the §7 grep checks and quote results in the PR body.
9. Push via SSH remote (`git@github-personal:m0n3r0/atlassian-innerwork.git`), open PR titled e.g. `feat(csv-importer): CSV/TSV importer for projects and work items` against `main`. **DO NOT MERGE.**
10. `kanban_block(reason="review-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")`.
