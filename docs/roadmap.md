# Roadmap

Status: directional, non-binding. Updated alongside each Phase release.

This roadmap exists to give beta participants and contributors a shared
view of where the maintainers think `innerwork` is going. It is **not** a
contract. No item below carries a delivery date, a commitment, or an
implied service level. Items can be removed, reordered, or scoped down
at any time, and that is on purpose.

If you are an operator depending on a specific behaviour, depend on the
documented surfaces (`docs/migration-guide.md`, `docs/operations-runbook.md`,
the CLI help text, the CHANGELOG) — not on this document.

Companion documents:

- `docs/launch-plan.md`
- `docs/beta-program.md`
- `docs/migration-guide.md`
- `docs/post-launch-iteration.md`
- `docs/metrics-dashboard.md`
- `docs/governance.md`

---

## Shipped through Phase 10

These capabilities are in the codebase today and covered by the test
suite. They form the stable surface that the beta program exercises.

- Catalog + workflow definitions (`innerwork catalog`, `innerwork workflow`).
- Domain store with projects, work items, transitions, spaces, pages,
  page versions, links, and comments on work items and pages.
- Analytics rollup (`innerwork.analytics.domain_rollup`) exposed via the
  Phase-10 `innerwork metrics` CLI.
- Append-only audit log (opt-in via `store.audit_sink`).
- Portability surface: `export_domain` / `import_domain` with explicit
  `format_version` and `schema_version`, byte-deterministic round-trip,
  fresh-target requirement, FK-safe insert order.
- Phase-10 CLI wrappers: `export`, `import`,
  `migrate --source synthetic`, `metrics`.
- Synthetic-fixture importer and round-trip test
  (`tests/test_migration.py`).
- Markdown-tree importer (`innerwork import-markdown`) — reads a local
  directory tree of `.md` files into `spaces` / `pages` via
  `src/innerwork/markdown_importer.py`; documented in
  `docs/migration-guide.md` §4. Post-phase-10 addition.
- CSV/TSV importer (`innerwork import-csv`) — reads a local CSV/TSV
  file of work-item rows into `projects` / `work_items` via
  `src/innerwork/csv_importer.py`; documented in
  `docs/migration-guide.md` §5. Post-phase-10 addition.
- Audit-bearing portability export (`innerwork export --include-audit`)
  — opt-in inclusion of the store's audit log in the portability
  payload behind an explicit flag and `format_version` 2; default
  exports stay byte-identical. Implemented in `src/innerwork/portability.py`
  / `src/innerwork/cli.py`; documented in `docs/migration-guide.md` §6.
  Post-phase-10 addition.
- Streaming export (`export_domain_json_stream` + atomic `--out`) —
  `innerwork export` writes the envelope incrementally in bounded
  batches (byte-identical to the memory-resident export), and `--out`
  targets are written atomically via a temp file + `os.replace`.
  Implemented in `src/innerwork/portability.py` / `src/innerwork/cli.py`;
  documented in `docs/migration-guide.md` §2/§6. Post-phase-10 addition.
- Time-windowed metrics (`innerwork metrics --window-start/--window-end`)
  — optional activity-over-window aggregations (`state_counts`,
  `cycle_time_per_project`, `page_writes`, `contributors`) appended as an
  additive top-level `"window"` object, computed over half-open `[start, end)`
  UTC windows; no flags → byte-identical point-in-time output. Implemented
  in `src/innerwork/analytics.py` / `src/innerwork/cli.py`; documented in
  `docs/metrics-dashboard.md` §4. Post-phase-10 addition.
- Operations runbook backup / restore / upgrade procedures — the
  operations runbook now documents the shipped `scripts/backup.py` /
  `scripts/restore.py` / `scripts/rollback_drill.py` surface with
  copy-paste Backup / Restore / Upgrade sections, the portability
  envelope as the only data-migration path, and honest gap calls (no
  production-store restore drill recorded; audit sink is CLI-gated;
  retention is operator guidance). Docs-only: no new scripts or code.
  Post-phase-10 addition.
- Observability shape (`docs/observability-shape.md`) — a recommended
  Prometheus / log-scraping shape for operators wiring `innerwork` into
  existing stacks: the shipped `GET /metrics` Prometheus 0.0.4 text
  surface (metric catalog, label semantics, histogram buckets), the
  JSON-lines log shape (field contract, `request_id` correlation), a
  recommended `innerwork_*` naming/label convention for future domain
  metrics, and collection guidance (pull-based scrape of `/metrics`
  for service telemetry; textfile collector for the `innerwork metrics`
  rollup) with an honest tradeoff table. No exporter ships — the shapes
  are operator-side recommendations, labeled as such. Docs-only: no new
  code. Post-phase-10 addition.
- `innerwork doctor` (`innerwork doctor [DB_PATH] [--database-url ...]
  [--audit-log ...] [--json] [--integrity-check]`) — read-only
  validation of a database file against the current schema plus common
  operator misconfigurations (schema version drift, missing
  tables/columns/indexes, read-only files, disk space, backup age,
  audit-database shape). Implemented in `src/innerwork/doctor.py` /
  `src/innerwork/cli.py`; documented in `docs/migration-guide.md` §2.5.
  Post-phase-10 addition.
- CLI ergonomics — the five migration commands (`export`, `import`,
  `migrate`, `import-markdown`, `import-csv`) ship parse-validated
  `--help` examples (real flags and paths only; verified against the
  real argument parser), `doctor`/migration help renders examples on
  separate lines (raw-description formatter), and a hidden
  `innerwork completion bash|zsh|fish` subcommand emits static,
  best-effort shell-completion scripts with word lists derived from
  `build_parser()` at emission time. Implemented in
  `src/innerwork/completion.py` / `src/innerwork/cli.py`; documented in
  `docs/migration-guide.md` §2.6. Post-phase-10 addition.
- Beta program docs, launch plan, operations runbook, governance,
  security policy, post-launch iteration cadence.

---

## Directional next (no commitment)

The items below are candidates for future work. They are listed in
rough priority order as the maintainers see it today; that order is
fluid and may change as beta feedback arrives.

### Migration

- Hosted-Jira and hosted-Confluence importers are **not** committed
  and not in active design. They are mentioned only to say: when /
  if those land, they will go through a dedicated scoping document
  and a separate phase. They will not be added quietly.

### Portability format

- Consider compact (indent=None) streaming export plumbing for
  pipe-oriented consumers, if demand appears.

### Documentation

- A short architectural overview document (`docs/architecture.md`)
  that explains the relationship between catalog, workflow, domain
  store, analytics, audit, and portability — primarily for new
  contributors.
- A "common operator recipes" cookbook to live alongside the
  operations runbook.

---

## Explicitly out of scope (Phase 10 and the directional window)

These items are **not** on the roadmap and the maintainers do not
intend to add them in the foreseeable future. They are listed here
so beta participants do not have to guess.

- **No managed hosting / SaaS.** `innerwork` is and remains a
  self-hosted, source-available project.
- **No telemetry.** The project does not collect usage data, crash
  reports, or operator metadata.
- **No commercial tier, no paid features, no pricing.** Any feature
  in the codebase is available to every operator who can run it.
- **No proprietary extensions.** Anything that ships in `innerwork`
  ships under the repository's license; there are no out-of-tree
  closed-source plugins endorsed by the project.
- **No service-level agreements.** Triage windows
  (`docs/post-launch-iteration.md`) are best-effort.
- **No automated upgrade path for breaking schema changes** beyond
  what the portability surface provides. Operators are expected to
  read CHANGELOG and follow `docs/migration-guide.md`.

---

## How the roadmap changes

Roadmap edits go through PRs against this file. A maintainer will:

1. Open a PR with the proposed change and a short rationale.
2. Wait at least the triage window
   (`docs/post-launch-iteration.md`) for community comment.
3. Merge after review per `docs/governance.md`.

Removing an item from the roadmap requires the same process as adding
one. The roadmap is a public artifact; silently dropping items would
undermine the contract that nothing here is hidden from contributors.

---

## Cross-references

- `docs/launch-plan.md` — what shipped at launch.
- `docs/beta-program.md` — how beta feedback enters the project.
- `docs/migration-guide.md` — what migration means in Phase 10.
- `docs/post-launch-iteration.md` — release cadence and triage.
- `docs/governance.md` — decision-making process.
- `CHANGELOG.md` — the authoritative record of behaviour changes.
