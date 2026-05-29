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
- Phase-10 CLI wrappers: `export-domain`, `import-domain`,
  `migrate --source synthetic`, `metrics`.
- Synthetic-fixture importer and round-trip test
  (`tests/test_migration.py`).
- Beta program docs, launch plan, operations runbook, governance,
  security policy, post-launch iteration cadence.

---

## Directional next (no commitment)

The items below are candidates for future work. They are listed in
rough priority order as the maintainers see it today; that order is
fluid and may change as beta feedback arrives.

### Quality and operability

- Tighten the operations runbook with explicit backup / restore /
  upgrade procedures.
- Expand `innerwork metrics` output with optional time-windowed
  aggregations (currently the rollup is point-in-time only).
- Document a recommended Prometheus / log-scraping shape for operators
  who want to wire `innerwork` into existing observability stacks.
  No exporter ships in Phase 10.

### Migration

- Build a Markdown-tree importer (read a directory of `.md` files into
  the `pages` / `spaces` collections). Lower-risk than third-party
  importers because the input is local files only.
- Investigate a CSV / TSV importer for `work_items` and `projects`.
- Hosted-Jira and hosted-Confluence importers are **not** committed
  and not in active design. They are mentioned only to say: when /
  if those land, they will go through a dedicated scoping document
  and a separate phase. They will not be added quietly.

### Portability format

- Consider adding optional, opt-in inclusion of audit log rows in the
  portability payload, behind an explicit `--include-audit` flag and
  a bumped `format_version`. The default would remain "audit not
  exported" so existing snapshots round-trip unchanged.
- Consider streaming export for very large stores (the current shape
  is memory-resident; this has been acceptable through Phase 10).

### CLI ergonomics

- `innerwork doctor` to validate a database file against the current
  schema and surface common operator misconfigurations.
- Friendlier `--help` examples on the migration commands.
- Optional shell completion (bash, zsh, fish) emitted by a hidden
  CLI subcommand.

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
