# Changelog

All notable changes to this project are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows [Semantic Versioning](https://semver.org/) per [`GOVERNANCE.md`](GOVERNANCE.md) §4.

> Versions correspond to git tags. **No tag exists yet**; the first release will be `v0.1.0`. Until then, every change accumulates under `[Unreleased]`.

## [Unreleased]

### Added — Markdown-tree importer

- `src/innerwork/markdown_importer.py` — `scan_markdown_tree()` / `import_markdown_tree()` / `MarkdownImportError`. Walks a directory of `.md` files and writes spaces/pages directly through `DomainStore` (no portability envelope, no new dependency — frontmatter parsed with the already-declared `pyyaml`). Directory → space/page mapping: each immediate subdirectory is a space (key = sanitized uppercase dirname, `^[A-Z][A-Z0-9]{1,9}$`, collisions and invalid keys error), every `.md` file below a space is a page (nested paths flatten into titles), optional YAML frontmatter (`title`/`author`/`created_at`), unknown keys warned, fresh-target requirement enforced, root-level `.md` files rejected.
- `src/innerwork/cli.py` — new `import-markdown <dir>` subcommand with `--database-url`, `--author` (default `importer`), and `--dry-run`; success prints `{"spaces", "pages", "warnings", "dry_run"}` JSON, `MarkdownImportError`/`OSError` exit 2.
- `tests/test_markdown_importer.py` + `tests/fixtures/markdown_tree/` — 18 tests covering scan mapping, frontmatter handling, fresh-target enforcement, CLI exit codes, and the portability round-trip (import → export → import → export byte-identical).
- `docs/migration-guide.md` — new §4 documenting `import-markdown` semantics and v1 limits; §1 notes frontmatter is a one-way door (not re-emitted by `export`).

### Added — CSV/TSV importer

- `src/innerwork/csv_importer.py` — `scan_csv_file()` / `import_csv_file()` / `CsvImportError` plus `CsvProject` / `CsvWorkItem` / `CsvImportPlan`. Reads a local CSV/TSV file of work-item rows (stdlib `csv` only, no new dependency, no network) and writes projects/work items directly through `DomainStore` via its own scoped insert path (projects, work_items, `project_sequences` — never `import_domain`). Extension-based delimiter auto-detect with `--delimiter` override (no `csv.Sniffer`), `utf-8-sig` BOM + `newline=""` parsing, locked column aliases and status vocabulary, explicit or auto-allocated keys (`{PROJ}-{n}` starting at the store's `next_sequence`), fresh-target gate on `projects`/`work_items` with `--allow-populated` escape hatch, conflicts always error, dry-run preview that still runs the fresh-target + conflict checks.
- `src/innerwork/cli.py` — new `import-csv <file>` subcommand with `--database-url`, `--owner` (default `importer`), `--delimiter` (auto/comma/tab), `--dry-run`, and `--allow-populated`; success prints `{"projects", "work_items", "warnings", "dry_run", "delimiter"}` JSON, `CsvImportError`/`OSError` exit 2.
- `tests/test_csv_importer.py` + `tests/fixtures/csv_import/` — 41 tests covering delimiter detection/override, BOM/CRLF/quoting/blank-line handling, column mapping and status vocabulary, key allocation, within-file and store-level conflict errors, fresh-target enforcement, `--allow-populated`, CLI exit codes, validation error paths (missing file, blank owner/created_at, unknown delimiter, non-UTF-8 input, blank/over-length title and description), and the portability round-trip (import → export → import → export byte-identical).
- `docs/migration-guide.md` — new §5 documenting `import-csv` semantics and v1 limits; §1 notes CSV column provenance (`type` values) is a one-way door (not re-emitted by `export`).

### Added — Audit-bearing portability export

- `src/innerwork/portability.py` — additive `include_audit` / `audit_actor_kind` keyword params on `export_domain` / `export_domain_json`; new `PORTABILITY_FORMAT_VERSION_AUDIT = 2` emitted only when `--include-audit` is used (default exports stay `format_version` 1, byte-identical). The v2 envelope is the v1 envelope plus a trailing `audit` collection (not in `_COLLECTION_ORDER`), exported from the wired sink's `query()` in sink order with every row passed through `field_acl.redact_for` (default `"system"` → verbatim). Import accepts `format_version` 1 and 2, rejects v1-with-audit-key and v2-without-audit loudly, validates every audit row by strict `make_event` reconstruction (closed `surface`/`actor_kind` enums — no event injection), enforces an all-or-nothing `event_id` conflict pre-check, and restores rows via `sink.record` after the 9 domain collections with append-only triggers intact.
- `src/innerwork/cli.py` — `export` gains `--include-audit` and `--audit-log`; `import` gains `--audit-log`; all domain subcommands gain `--audit-log` + `INNERWORK_AUDIT_DB` env fallback via `_wire_audit_sink`, which wires `store.audit_sink = SqliteAuditSink(...)` before any domain work (fixes audit finding F1 — CLI writes now emit audit rows). Exit 2 when `export --include-audit` has no sink, and when importing a v2 payload with audit rows but no sink.
- `tests/test_portability_audit.py` + `tests/fixtures/audit_export/` — 32 tests covering the default-off invariant (byte-identical vs the legacy v1 fixture), version markers, sink-matched audit export, redaction (`system` verbatim / `user` masks actor), strict import validation, all-or-nothing conflict handling, no-loss/no-dup round-trip, append-only survival after restore, and the CLI surface (exit 0/2, no silent empty audit).
- `docs/migration-guide.md` — new §6 documenting `export --include-audit` semantics, the audit-row schema, redaction, import validation, and the honest round-trip guarantee; §1 now states audit rows are **not** part of the default portable surface. Docs state clearly: opt-in operational convenience — **not** a compliance/legal export; no certifications are claimed or implied.

### Changed — Streaming export

- `src/innerwork/portability.py` — new `export_domain_json_stream(store, out, *, indent=2, batch_size=500, include_audit=False, audit_actor_kind="system", progress=None)` writes the portability envelope incrementally to a caller-owned `TextIO`. Rows are fetched in `fetchmany(batch_size)` batches (never `fetchall`), so peak additional memory is bounded by one batch rather than by store size. The streamed artifact is **byte-identical** to `json.dumps(export_domain(...), indent=..., sort_keys=False)` for the same store and settings — the referee gate, locked by the new test suite. `include_audit=True` emits the trailing `audit` collection (format_version 2) via the existing `_export_audit_rows` logic, with the sink-missing check before the first byte (fail-before-write); `_audit_portability` fires only after a fully successful write, with the real per-collection counts and the effective format_version. `export_domain`, `export_domain_json`, `import_domain*`, and `_COLLECTION_ORDER` are byte-identical to before. Memory is documented as **target** O(batch_size) additional memory, **measured** by a tracemalloc differential test: streamed peak ≤ 25% of the memory-resident peak on the 40k-row workload (with a ≥ 8 MiB floor guard so the workload cannot be trivially small).
- `src/innerwork/cli.py` — `innerwork export` now always streams through the new function. `--out PATH` is atomic: the CLI streams to `PATH.tmp<pid>` next to the target and `os.replace`s it into place only on success; the temp file is removed on every failure path and an existing `PATH` is never clobbered. Without `--out`, the envelope streams to stdout and the CLI appends the trailing `\\n` after the call. `DomainImportError` (including `--include-audit` with no sink) → stderr + exit 2 with stdout empty; `OSError` → stderr + exit 2. One new flag: `--progress` (stderr progress lines at collection boundaries, every 100,000 rows within a collection, and a final summary — collection names and counts only, never row content; stderr silent on success without the flag).
- `tests/test_portability_stream.py` — 29 tests: the byte-identity referee (unicode/control chars, empty store, multi-batch >batch_size, batch_size=1, compact `indent=None`), `fetchall` ban (wrapped-connection proxy), counts parity with `export_domain`, audit composition (v2 byte-identity, redaction, no-sink fail-before-write), portability-event-after-success, interrupted-sink records no event, round-trip import/reexport, progress-callback cadence (API, incl. audit multi-batch) + `--progress` stderr (CLI, no row content, silent without the flag) + `--help` documents it, the tracemalloc memory differential (streamed < 25% of memory-resident peak, ≥ 8 MiB floor), unreadable import input, and CLI atomicity (`test_cli_export_out_atomic_on_error` — sentinel preserved, no temp litter).
- `docs/migration-guide.md` — §2 note (streaming + atomic `--out` + partial-stdout caveat), §2 note on `--progress`, and §6 note (audit-bearing streaming, fail-before-write). No version bump.

### Fixed

- `scripts/check_anti_hallucination.py` — skip `.worktrees/` when scanning. Git worktree checkouts of the repo were being scanned as part of the tree, causing the guardrail to false-positive on the allowlisted `docs/threat-model.md` (and the script/test files) under their worktree paths. CI was unaffected (fresh checkouts have no worktrees); local runs with linked worktrees now pass.

### Added — Phase 10 (beta, migration, launch, post-launch iteration)

- `docs/launch-plan.md` — public-beta launch plan: scope, sequencing, communications channels (GitHub issues + private vulnerability reporting only), success signals tied to issue/PR throughput rather than user counts, and explicit non-goals (no PyPI publish, no `v*` tag, no commercial commitments).
- `docs/beta-program.md` — beta intake, expectations, and exit criteria. Calls out that the maintainers do not publish participant counts and that the beta carries no SLA, no pricing, and no support contract.
- `docs/migration-guide.md` — Phase-10 migration scope: the generic portability envelope (`export` / `import`) plus the bundled `--source synthetic` fixture. Explicitly states no Jira/Confluence importer exists; only the synthetic fixture is shipped.
- `docs/roadmap.md` — directional, non-binding roadmap covering near-term iteration ticks and longer-arc themes. Explicitly non-binding.
- `docs/post-launch-iteration.md` — two-week iteration cadence, structured iteration notes under `docs/iteration-notes/YYYY-MM-DD.md`, and the feedback loop between beta signups, issues, and PRs.
- `docs/metrics-dashboard.md` — documents the analytics rollup (`domain_rollup` → `DomainRollup.to_dict()`) and how Phase 10 surfaces it via `innerwork metrics`. No external dashboard, no telemetry collection.
- `src/innerwork/migrators/__init__.py` and `src/innerwork/migrators/synthetic_fixture.py` — `build_synthetic_fixture()` / `load_synthetic_fixture()` / `SYNTHETIC_FIXTURE_PATH`. Builds a deterministic portability envelope at the current `PORTABILITY_FORMAT_VERSION` / `DOMAIN_SCHEMA_VERSION`. The on-disk fixture is the byte-for-byte equivalent of the in-memory build and is the only `--source` accepted by `innerwork migrate` in Phase 10.
- `tests/fixtures/synthetic_migration.json` — on-disk synthetic fixture (2 projects, 3 work items, 3 transitions, 1 space, 1 page, 2 page versions, 1 link, 2 work-item comments, 1 page comment). Deliberately reads as obviously synthetic.
- `src/innerwork/cli.py` — four new work-graph subcommands: `export`, `import`, `migrate`, `metrics`. `export` writes the portability envelope to stdout or `--out PATH`. `import` reads a JSON envelope and writes into a fresh store; non-empty target fails with exit code 2. `migrate --source synthetic` prefers the on-disk fixture, falls back to `build_synthetic_fixture()`. `metrics` prints `domain_rollup(store).to_dict()`.
- `tests/test_migration.py` — module invariants for `build_synthetic_fixture` (envelope versions match portability constants, all nine collections present, on-disk fixture matches builder, fresh-store import succeeds) and end-to-end CLI tests covering `migrate` → `export` → `import` round-trip, stdout export, non-empty-import failure, and `metrics`.
- `.github/ISSUE_TEMPLATE/beta_signup.md` — beta-signup issue template. Captures handle/org, primary use case, surfaces in use, deployment shape, feedback preferences. Includes hard reminders against pasting secrets/customer data and against commercial expectations.
- `README.md` — added doc links for the six Phase-10 docs, a Beta section linking to the signup template and `docs/beta-program.md`, and a CLI quick-reference for the four new subcommands. No claims about beta user counts, revenue, pricing, or a Jira/Confluence importer.

### Not changed

- `pyproject.toml` version pinned at `0.1.0` — Phase 10 ships no version bump and cuts no `v*` tag.
- No PyPI publish; no changes to `release.yml`.
- No telemetry, no metrics endpoint exposed by the FastAPI app; the analytics rollup is read on-demand via `innerwork metrics`.
- Existing CLI subcommands (`catalog`, `validate`, `serve`, the Phase-B work-graph slice, etc.) untouched.

### Added — Phase 9 (open-source governance, contributor experience, packaging, docs)

- `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1, with the enforcement contact line wired to a GitHub issue label (`code-of-conduct`) and to GitHub private vulnerability reporting for sensitive matters. No invented private email.
- `SECURITY.md` — supported versions table (only `0.x` until the first stable tag, no SLA), reporting channel via GitHub private vulnerability reporting, cross-link to `docs/threat-model.md`. Explicit: no bug bounty, no PGP key, no formal embargo policy.
- `GOVERNANCE.md` — minimalist BDFL model. Roles (Contributor, Maintainer, BDFL), decision-making (lazy consensus + BDFL tiebreak), becoming a maintainer (self-nomination via PR adding own name to `MAINTAINERS.md`), breaking-change policy with explicit cross-graph contract list (`LINK_KINDS` in `knowledge.py`, `ContextEntry`/`ContextBundle` in `ai_context.py`, workflow constants in `domain.py`, `PageVersion` shape in `knowledge.py`). No foundation affiliation, not an Atlassian project.
- `MAINTAINERS.md` — one row: `m0n3r0`, scope `all`, since 2026-05-29. Header line enforces the self-nomination rule and forbids non-human handles.
- `CONTRIBUTING.md` — appended sections (decision-making pointer, security-reporting pointer, Code of Conduct pointer, release-flow pointer, extension-model pointer, code-review expectations, DCO sign-off / no CLA, project layout map). The existing content was preserved.
- `docs/contributor-guide.md` — deeper how-to: repo tour with per-module ownership table, dev loop, testing conventions, extension-points §4 (the honest version that names real module seams and explicitly states that no plug-in registry exists yet for work-item types or page macros), docs-update map, PR workflow.
- `docs/site-outline.md` — outline of a future docs site (mkdocs-material recommended; `mkdocs.yml` stub provided inline; IA grouping). Explicitly does not stand the site up.
- `pyproject.toml` — `[project.urls]` (Homepage / Source / Documentation / Issues / Changelog), `keywords`, and `classifiers` populated. Version unchanged at `0.1.0`. No build-system change.
- `.github/PULL_REQUEST_TEMPLATE.md` — what / why / tests / docs-updated / breaking-change / sign-off.
- `.github/ISSUE_TEMPLATE/bug_report.md`, `feature_request.md`, `config.yml` — standard issue templates with blank issues disabled and a contact link to GitHub private vulnerability reporting.

### Documented

- That `atlassian-innerwork` is **not** published to PyPI and has **no tag yet**. Phase 9 only validated that `uv build` produces a clean wheel + sdist; it did not publish, did not tag, did not modify `release.yml`.
- That plug-in registries for work-item types and page macros are **future work**, not current capabilities. Contributors needing to extend either surface today are editing core modules through a normal PR.

### Not changed

- `release.yml`, `ci.yml`, and any source under `src/innerwork/` were intentionally not touched in phase 9.
- `LICENSE` (MIT, © 2026 m0n3r0) unchanged.
