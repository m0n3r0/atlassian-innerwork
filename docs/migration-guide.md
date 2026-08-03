# Migration Guide

Status: Phase 10 — synthetic-fixture round-trip plus the markdown-tree importer (`import-markdown`) and the CSV/TSV importer (`import-csv`).

This guide explains the migration surface that `innerwork` ships in
Phase 10. The goals are:

1. Document what `innerwork export-domain` and `innerwork import-domain`
   actually do.
2. Show operators how to run the round-trip safely against a fresh
   target.
3. Define the contract for the synthetic-fixture importer
   (`innerwork migrate --source synthetic`).

> Phase 10 deliberately ships **no** Jira or Confluence importer. Any
> mention of "migration" in this release refers either to the generic
> `export_domain` / `import_domain` portability surface or to the
> synthetic fixture used to exercise it. This boundary is explicit in
> the launch plan and the beta program documentation.

Companion documents:

- `docs/launch-plan.md` — cutover and rollback procedure.
- `docs/beta-program.md` — what beta operators can expect.
- `docs/operations-runbook.md` — day-2 ops, including DB lifecycle.
- `docs/roadmap.md` — directional future migrator candidates.

---

## 1. Portability surface

The exported surface is implemented by `innerwork.portability` and covers
exactly these collections, in this order:

1. `projects`
2. `work_items`
3. `transitions`
4. `spaces`
5. `pages`
6. `page_versions`
7. `links`
8. `work_item_comments`
9. `page_comments`

The export envelope carries two version fields:

- `format_version` — the portable wire format (`PORTABILITY_FORMAT_VERSION`).
- `schema_version` — the underlying domain schema (`DOMAIN_SCHEMA_VERSION`).

A re-export of an import produces byte-identical JSON when serialized with
`indent=2` and `sort_keys=False`. That property is enforced by tests and
is the definition of "round-trip" for this guide.

What is **not** in the portable surface (by design):

- Idempotency cache rows.
- Transient notification state.
- Audit log rows. The audit log is a record of operations performed
  against the store; it is intentionally **not** part of the default
  portable surface. The optional `export --include-audit` flag adds it
  explicitly (see §6) — audit rows never leave the store by default.
- Permissions configuration that lives outside the domain store (for
  example, environment variables consumed by the permissions module).
- Markdown frontmatter: `innerwork import-markdown` consumes a YAML
  frontmatter block at import time (see §4), but `export` emits only
  `title` / `body` / `author` / `created_at` per `PageVersion`. The
  frontmatter envelope is a one-way door — a re-export never re-emits
  it, so operators should not expect byte-identical `.md` files back.
- CSV column provenance: `innerwork import-csv` consumes column names
  and `type` values at import time (see §5), but `export` emits only
  the domain fields (`key`, `title`, `description`, `state`,
  `assignee`, timestamps). The original column names and `type` values
  are a one-way door — a re-export never re-emits them, so operators
  should not expect byte-identical `.csv` files back.

---

## 2. CLI surface

Phase 10 adds three subcommands to `innerwork` that wrap the existing
portability and analytics modules. These commands are thin and
side-effect-conservative: they never mutate an already-populated store.

> **Streaming + atomic `--out` (post-phase-10).** `innerwork export`
> writes the portability envelope incrementally (rows are fetched in
> bounded batches), so very large stores export with
> bounded memory instead of building the whole payload + JSON string in
> RAM. When `--out PATH` is given, the CLI streams to a temporary file
> (`PATH.tmp<pid>`) and `os.replace`s it into place only on success: an
> existing file at `PATH` is never clobbered by a failed export, and the
> temp file is removed on every failure path. Without `--out`, the
> envelope streams to stdout and the CLI appends a single trailing `\n`.
> The streamed artifact is byte-identical to the memory-resident export
> for the same store and settings — this is the load-bearing invariant.
> Caveat: a failed stdout export can leave a *partial* envelope on
> stdout (there is no atomicity for pipes); treat stdout as authoritative
> only when the exit code is 0.

### 2.1 `innerwork export-domain`

```
innerwork export-domain --db <path/to/domain.db> [--indent N]
```

- Reads from an existing `DomainStore` at `--db`.
- Writes deterministic JSON to stdout.
- `--indent` defaults to 2; pass `--indent 0` for a compact one-line form
  (still deterministic, still round-trippable).
- Exit code is 0 on success, non-zero with a printed error on any
  database or serialization failure.

### 2.2 `innerwork import-domain`

```
innerwork import-domain --db <path/to/fresh.db> --input <export.json>
```

- Refuses to run against a non-fresh target. The store must be empty
  across every collection the payload contains. If any collection is
  populated, the CLI prints a `DomainImportError` and exits non-zero —
  no rows are inserted.
- Reads the JSON envelope, validates `format_version`/`schema_version`,
  and replays inserts in FK-safe order (projects → work_items →
  transitions → spaces → pages → page_versions → links → comments).
- Auto-assigned identifiers (`transition_id`, `version_id`,
  `comment_id`, `link_id`) are preserved exactly so a subsequent
  `export-domain` produces byte-identical JSON to the input.
- Prints a JSON summary `{collection: rows_inserted}` to stdout on
  success.

### 2.3 `innerwork migrate --source synthetic`

```
innerwork migrate --source synthetic --db <path/to/fresh.db>
```

- Loads the bundled synthetic fixture
  (`src/innerwork/migrators/synthetic_fixture.py` /
  `tests/fixtures/synthetic_migration.json`).
- Validates it as a portable payload.
- Imports it into the supplied fresh `--db`.
- This command exists to exercise the import code path without
  shipping a real third-party importer.

`--source synthetic` is the only supported value in Phase 10. Any
other value is rejected by the CLI with a clear error.

### 2.4 `innerwork metrics`

```
innerwork metrics --db <path/to/domain.db> [--principal <name>]
```

- Calls `innerwork.analytics.domain_rollup` and prints the resulting
  `DomainRollup.to_dict()` as JSON.
- `--principal` is optional; if omitted, the rollup runs over the full
  domain (back-compat with internal callers).
- The output schema is documented in `docs/metrics-dashboard.md`.

---

## 3. Recommended round-trip procedure

For operators who want to verify the migration path before launch:

```sh
# 1. Snapshot the source store.
innerwork export-domain --db ./prod-domain.db > /tmp/snapshot.json

# 2. Provision a fresh target (DomainStore creates the schema on first open).
rm -f /tmp/fresh-target.db

# 3. Replay the snapshot.
innerwork import-domain --db /tmp/fresh-target.db --input /tmp/snapshot.json

# 4. Re-export and diff for byte equality.
innerwork export-domain --db /tmp/fresh-target.db > /tmp/roundtrip.json
diff -u /tmp/snapshot.json /tmp/roundtrip.json
```

The expected outcome is an empty `diff`. Any divergence is a bug —
file it under the `bug` label per `docs/beta-program.md` §4.

---

## 4. Markdown-tree importer

`innerwork import-markdown` reads a directory tree of `.md` files and
writes it into the `spaces` / `pages` collections **directly through
the domain store** — it does not produce a portability envelope.
Input is purely local files; the command makes no network access.

### 4.1 Command

```
innerwork import-markdown <dir> --database-url sqlite:///path/to/fresh.db [--author NAME] [--dry-run]
```

- `<dir>` — root of the markdown tree. Must be an existing directory;
  otherwise the command prints an error and exits 2.
- `--author` — default author/owner for imported pages and spaces.
  Frontmatter `author` wins per page. Defaults to `importer`.
- `--dry-run` — scan and validate the tree without writing anything.
  The fresh-target check still runs, so the summary is an honest
  preview of a real import.
- Fresh-target requirement: the command refuses to run when `spaces`,
  `pages`, or `page_versions` already contain rows (exit 2, nothing
  written). It never overlays an existing knowledge graph.
- Success prints a JSON summary to stdout:
  `{"spaces": N, "pages": N, "warnings": [...], "dry_run": false}`.

### 4.2 Directory → space/page mapping

- Each **immediate subdirectory** of `<dir>` is one space. A space is
  created even if it ends up with zero pages — the tree says it exists.
- Space key: the directory name is uppercased, every character outside
  `[A-Z0-9]` is dropped, and the result must match `^[A-Z][A-Z0-9]{1,9}$`
  (2–10 characters, uppercase). Invalid results are an **error** telling
  the operator to rename the directory — keys are never silently
  truncated. Two directories mapping to the same key are an error
  listing both paths.
- Every `*.md` file anywhere below a space directory is one page.
  Non-`.md` files are ignored silently. Symlinks (files and
  directories) are skipped.
- Page title: frontmatter `title` if present; otherwise the relative
  path stem with `/` preserved (`space_dir/guides/getting-started.md`
  → `guides/getting-started`). The model has no parent-page field, so
  nested directories flatten into the title and the on-disk structure
  remains recoverable from titles.
- Page body: file content with the frontmatter block (if any) removed,
  then leading/trailing blank lines stripped. An empty file imports as
  an empty-body page.
- Every page becomes **version 1**; no version history is imported.
- Root-level `.md` files (directly under `<dir>`) are an **error** —
  they have no space to belong to.

### 4.3 Frontmatter

An optional YAML block is recognized when the file's first line is
exactly `---`; the block ends at the next line that is exactly `---`.
Parsed with `yaml.safe_load` (PyYAML is a declared dependency).

- `title` — overrides the path-stem title (must be a non-blank string
  ≤ 200 characters).
- `author` — overrides `--author` (must be a non-blank string).
- `created_at` — recognized and validated as an ISO-8601 timestamp;
  the page timestamp is the import-wide `created_at` and this key is
  not applied per file.
- Unknown keys are ignored and recorded as a per-file warning in the
  summary's `warnings` list (the model has nowhere to store them).
- Malformed input — an unclosed `---` block or YAML that fails
  `safe_load` — aborts the import with an error naming the file
  (exit 2). Loud and deterministic beats guessing.

### 4.4 Round-trip posture

`import-markdown → export → import` preserves the imported *content*:
titles, bodies, and authors round-trip through the portability
envelope without loss. Frontmatter itself is a **one-way door** — it
is consumed at import time and never re-emitted by `export`, so the
round-trip returns page content, not byte-identical `.md` files.

### 4.5 Limits (v1)

- `[[wikilinks]]` are left verbatim in the body; there is no page→page
  link table to resolve them against.
- Attachments and images are not imported (non-`.md` files are
  ignored).
- No version history: one file = one page at version 1.
- No page hierarchy: nested directories flatten into page titles.
- The importer creates only `spaces` / `pages` / `page_versions`; it
  never creates projects, work items, links, or comments.

---

## 5. CSV/TSV importer

`innerwork import-csv` reads a local CSV or TSV file of **work-item
rows** and writes it into the `projects` / `work_items` collections
**directly through the domain store** — it does not produce a
portability envelope and never calls `import-domain`. The `projects`
collection is derived from the distinct `project` column values; there
are no separate project rows. Input is purely local files; the command
makes no network access.

### 5.1 Command

```
innerwork import-csv <file> --database-url sqlite:///path/to/fresh.db [--owner NAME] [--delimiter auto|comma|tab] [--dry-run] [--allow-populated]
```

- `<file>` — the CSV/TSV file to import. Must be an existing file;
  otherwise the command prints an error and exits 2.
- `--owner` — owner identifier for imported projects. Defaults to
  `importer`.
- `--delimiter` — `auto` (default), `comma`, or `tab`. `auto` picks the
  delimiter by extension: `.tsv` → tab, anything else → comma. There is
  no heuristic sniffing; the resolved delimiter is echoed in the
  summary JSON.
- `--dry-run` — parse, validate, and run the fresh-target and conflict
  checks without writing anything, so the summary is an honest preview
  of a real import.
- `--allow-populated` — skip the fresh-target check and import into a
  store that already has projects / work items. Existing rows are never
  modified; conflicting rows still error (see §5.4).
- Success prints a JSON summary to stdout:
  `{"projects": N, "work_items": N, "warnings": [...], "dry_run": false, "delimiter": "comma"}`.

### 5.2 Column mapping

Header cells are matched case-insensitively and whitespace-trimmed
(`"Project"` and `" project "` both map to `project`). Two headers
normalizing to the same name are an error listing both. Unknown columns
do **not** abort the import — they produce one warning listing the
unknown column names (sorted) and are otherwise ignored.

| Canonical column | Accepted aliases | Required | Target field | Rules |
|---|---|---|---|---|
| `project` | `project_key`, `project key` | required | `Project.key` | Sanitized per §5.3; determines project membership/creation. |
| `project_name` | `project name` | optional | `Project.name` | Used only when the project is **newly created**; ignored (with a warning) when the project already exists under `--allow-populated`. |
| `title` | `summary` | required | `WorkItem.title` | Stripped; non-blank; ≤ 200 characters. |
| `status` | `state` | optional | `WorkItem.state` | Default `todo`; vocabulary mapping below. Unknown value → error naming the row, the value, and the allowed set. |
| `type` | `work_item_type`, `issue type` | optional | — (no field) | **Recognized but unmappable**: the domain model has no work-item type field. Dropped, with one warning total. |
| `description` | `desc` | optional | `WorkItem.description` | ≤ 4000 characters; blank → `""`. |
| `assignee` | — | optional | `WorkItem.assignee` | Blank → `""`; non-blank stored verbatim. |
| `key` | `work_item_key` | optional | `WorkItem.key` | Explicit key; must match `^[A-Z][A-Z0-9]{1,9}-\d+$` and its prefix must equal the sanitized project key. |

The `status` cell is normalized (strip + lowercase + collapse internal
whitespace) and mapped:

| Normalized value | Maps to |
|---|---|
| `todo`, `backlog`, `open`, `to do`, `to-do` | `todo` |
| `in_progress`, `in progress`, `wip`, `doing`, `inprogress` | `in_progress` |
| `done`, `closed`, `complete`, `completed`, `resolved` | `done` |

### 5.3 Keys and project derivation

- **Project keys** are sanitized from the `project` cell: uppercase,
  drop every character outside `[A-Z0-9]`, then require the result to
  match `^[A-Z][A-Z0-9]{1,9}$` (2–10 uppercase characters starting with
  a letter). Invalid results are an **error** naming the value — keys
  are never silently truncated. Two distinct values sanitizing to the
  same key are an error listing both. The project name is the first
  non-blank `project_name` cell for that project (file order), else the
  verbatim `project` cell of the project's first row.
- **Work-item keys** are explicit (from the `key` column) or
  auto-allocated. Explicit keys are used verbatim and validated (format
  + prefix). Auto keys are `{PROJ}-{n}` in the importer's deterministic
  file order, where `n` starts at the project's current
  `next_sequence` (1 on a fresh store) and advances past every used
  suffix — an auto row before an explicit `ENG-5` row gets `ENG-1` and
  the explicit row keeps `ENG-5`.
- After the import, `project_sequences` is bumped incrementally for the
  projects in the file (`next_sequence = max(current, max_used) + 1`),
  so a later `work-item-create` never collides and projects not in the
  file are left untouched.

### 5.4 Fresh-target, conflicts, and `--allow-populated`

- **Fresh-target requirement.** The command refuses to run when the
  `projects` or `work_items` tables already contain rows (exit 2,
  nothing written) — unless `--allow-populated` is passed. Only the two
  collections the importer touches gate; spaces / pages / links /
  comments may exist and are untouched. The check runs in `--dry-run`
  too, so the preview is honest.
- **Conflicts always error** (nothing is written; there is no silent
  skip):
  - An explicit `key` that already exists in `work_items` → error
    naming the key and the row.
  - A row without an explicit key whose natural key `(project, title)`
    already exists → error naming the row, the title, and the existing
    work item's key. Re-importing the same CSV into the same store
    therefore always fails loudly instead of silently duplicating rows.
  - Two rows in one file with the same explicit key → error naming both
    rows.
- Under `--allow-populated`, existing rows are immutable: a non-blank
  `project_name` for an existing project is ignored with a warning.

### 5.5 Round-trip posture

`import-csv → export → import` preserves the imported *content*: keys,
titles, descriptions, states, assignees, and project names round-trip
through the portability envelope without loss (the round-trip gate
asserts byte-identical re-exports). CSV column provenance itself is a
**one-way door** — the original column names and `type` values are
consumed at import time and never re-emitted by `export`, so the
round-trip returns domain content, not byte-identical `.csv` files.

### 5.6 Limits (v1)

- No transition history is synthesized: `state` is taken verbatim from
  the file (a CSV row is a snapshot, not an event log).
- Work-item `type` is dropped with a warning (the domain model has no
  type field); operators with type data must encode it in
  `title`/`description` or wait for a model change.
- Project `visibility` / `members` default to `internal` / `()` — there
  are no CSV columns for them in v1.
- Links, comments, spaces, and pages are never created.
- The importer creates only `projects` / `work_items` (plus the
  `project_sequences` bookkeeping rows); it never creates spaces,
  pages, links, or comments.

---

## 6. Audit-bearing export (`export --include-audit`)

Audit log rows are **not** part of the default portable surface. When an
operator wants to move the audit trail along with the domain data, the
`export` command gains an explicit, opt-in flag:

### 6.1 Command

```
innerwork export [--database-url sqlite:///...] [--out PATH] [--include-audit] [--audit-log PATH]
innerwork import <input.json> [--database-url sqlite:///...] [--audit-log PATH]
```

- `--include-audit`: include the store's audit log rows in the envelope
  and bump `format_version` to 2. **Without the flag, the output is
  byte-identical to today** (`format_version` 1, 9 domain collections,
  no `audit` key).
- `--audit-log <path>`: path to the SQLite audit DB to wire as the
  store's audit sink (`INNERWORK_AUDIT_DB` env fallback). Wiring the
  sink also makes CLI writes (`project-create`, `work-item-create`,
  `work-item-transition`, page writes via the importers) emit audit rows
  — the CLI previously never wired a sink, so shipped writes produced
  zero audit rows (audit finding F1).
- **Error contract:** `export --include-audit` with no sink configured
  exits 2: `error: --include-audit requires an audit sink; pass
  --audit-log or set INNERWORK_AUDIT_DB`. Importing a v2 payload with
  audit rows but no sink also exits 2 — silently dropping restored rows
  would violate "without duplication or loss".
- **Streaming + atomic `--out` (post-phase-10).** The audit-bearing
  export streams through the same incremental writer as the default
  export (`export_domain_json_stream`), so `--include-audit` on a large
  store stays bounded-memory. The sink-missing check above happens
  BEFORE the first byte is written: on a missing sink the command exits
  2 with stdout empty and an existing `--out` file left untouched (the
  temp file is removed, never renamed over the target).

### 6.2 Format version and envelope

`format_version` stays 1 for default exports. Only `--include-audit`
emits `format_version` 2, which is the v1 envelope plus one trailing
`audit` collection (the sink's rows, in sink order). `schema_version`
is unchanged. Import accepts both 1 and 2; a v1 payload carrying an
`audit` key and a v2 payload missing it are both rejected loudly.

### 6.3 Audit row schema

Each element of `audit` is exactly the JSON form of one `AuditEvent`:

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
  "metadata": {"transition_id": 1}
}
```

Eligibility is **whatever the sink holds** — all surfaces, no
allowlist, no synthesis. The envelope carries the `surface` field
verbatim; surfaces that are reserved-but-unwired today (e.g.
`permission_change`) produce no rows and none are fabricated.

### 6.4 Redaction

Every exported row passes through `field_acl.redact_for` with the
operator actor kind (default `"system"` → rows verbatim; the operator
already owns the audit DB file). Non-system actor kinds (future
API/HTTP callers) get the existing policy applied — e.g. `"user"` masks
the `actor` field.

### 6.5 Import semantics

Strict, all-or-nothing:

1. Every audit row is reconstructed through `make_event` **before any
   write** — `surface` and `actor_kind` are closed enums, so no event
   injection is possible.
2. `event_id` conflicts with the existing sink abort the whole import
   (domain rows included), before any INSERT.
3. Audit rows restore into the wired sink via `sink.record` in payload
   order after the 9 domain collections; the sink's append-only
   triggers stay intact.
4. A v2 payload with rows and no sink errors; `"audit": []` is valid
   without a sink.

### 6.6 Round-trip honesty

- Default v1 exports round-trip byte-identical, unchanged.
- Audit-bearing exports are **no-loss / no-duplication** (every payload
  `event_id` lands in the sink exactly once), **not** byte-stable
  across cycles: the append-only sink grows by exactly one
  `portability_export` / `portability_import` event per export/import.
  This is correct append-only behavior, documented here so it is never
  mistaken for a defect.

> This is an opt-in **operational convenience** for moving a self-hosted
> store between hosts — **not** a compliance/legal export; no
> certifications are claimed or implied.

---

## 7. Failure modes and recovery

| Failure | Cause | Recovery |
|---|---|---|
| `DomainImportError: target store not empty` | Operator pointed `--db` at a populated database | Run against a freshly-initialised database. The portability module deliberately refuses partial overlays. |
| `DomainImportError: unsupported format_version` | Snapshot produced by a different `innerwork` version | Re-export the source with the same `innerwork` version as the target, or follow the upgrade path in CHANGELOG. |
| `DomainImportError: unsupported schema_version` | Domain schema migrated between source and target | Re-export the source from a build that matches the target's `DOMAIN_SCHEMA_VERSION`, or rebuild the source against the newer schema before re-exporting. |
| `sqlite3.IntegrityError` mid-import | FK or unique constraint violated | The portability code is FK-ordered, so this should not happen; if it does, treat it as a bug and capture the input JSON for triage. The target database is in an inconsistent state — discard it. |

The portability code uses a single SQLite connection per import. On any
exception inside `import_domain`, the connection is closed without an
explicit `COMMIT`, so the database file should be safe to discard. There
is no automatic rollback to a known-good state because the contract is
"target must be fresh"; if the import fails, the target was meant to be
disposable.

---

## 8. Synthetic fixture contract

The synthetic fixture lives at `tests/fixtures/synthetic_migration.json`
and is loaded both by:

- `tests/test_migration.py` — round-trip equivalence test.
- `src/innerwork/migrators/synthetic_fixture.py` — runtime loader used
  by `innerwork migrate --source synthetic`.

Fixture contents are intentionally small but cover every collection
(`projects`, `work_items`, `transitions`, `spaces`, `pages`,
`page_versions`, `links`, `work_item_comments`, `page_comments`) so the
round-trip exercises every insert path.

Fixture rules:

- All identifiers are stable strings or integers — no clocks, no random
  IDs.
- `created_at` / `updated_at` use fixed ISO-8601 strings.
- The fixture is checked in and must be regenerated only by editing
  the JSON directly or by re-running an export that has been reviewed
  by a maintainer.

---

## 9. What this guide is NOT

- It is **not** a guide for migrating from hosted Jira or Confluence.
  Phase 10 ships no such importer. The roadmap document lists this as a
  directional future item; no commitment is implied.
- It is **not** a backup strategy. SQLite backup is operationally
  separate (file copy with proper locking, or `VACUUM INTO`). See
  `docs/operations-runbook.md`.
- It is **not** an upgrade guide. Schema upgrades happen through
  `innerwork upgrade`; portability snapshots are tagged with the
  schema version they were taken under and refuse to load against a
  newer schema.

---

## 10. Cross-references

- `docs/launch-plan.md`
- `docs/beta-program.md`
- `docs/operations-runbook.md`
- `docs/roadmap.md`
- `docs/metrics-dashboard.md`
- `CHANGELOG.md` (entries under `[Phase 10]` and the `[Unreleased]`
  markdown-tree importer section).
