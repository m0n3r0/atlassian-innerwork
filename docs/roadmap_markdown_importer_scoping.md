# Roadmap item: Markdown-tree importer — PM scoping

**Status:** PM scoping (pre-implementation). Source: `docs/roadmap.md` → "Directional next" → Migration (`slug=markdown-importer`).
**Parent:** post-launch backlog item; no phase number. Implementation task `t_dc473849` branches from `main` on `feat/markdown-importer`.
**Audience:** the implementation worker (atlassianeng). Read this end-to-end before touching files.

---

## §0 Honest baseline (what the repo already has, today)

Verified against `main` at commit `2ea7180` on 2026-08-03.

| Asset | Present? | Path | Notes |
|---|---|---|---|
| Portability layer | ✅ | `src/innerwork/portability.py` (455 lines) | `export_domain` / `export_domain_json` / `import_domain` / `import_domain_json`. Deterministic key ordering, FK-safe insert order, byte-stable round-trip. Fresh-target requirement enforced by `_validate_fresh_target`. **This file is read-only for this task.** |
| Domain store pages/spaces API | ✅ | `src/innerwork/domain_store.py` | `create_space(space_id, key, name, owner, created_at, visibility, members)` and `create_page(page_id, space_id, title, body, author, created_at)` both write through the store. `create_page` creates the page **and** its version-1 `PageVersion` in one transaction and emits an audit event (surface `confluence_page`); `create_space` emits a change hook. (`_emit_change` fires only for project/space creation — pages don't emit it today.) |
| Knowledge model | ✅ | `src/innerwork/knowledge.py` | `Space` (key regex `^[A-Z][A-Z0-9]{1,9}$`, 2–10 chars, uppercase), `Page` (page_id, space_id, current_version, created_at, updated_at — **no parent/hierarchy field**), `PageVersion` (title ≤200 chars non-empty, body ≤200_000 chars, author non-empty). |
| Synthetic-fixture migrator | ✅ | `src/innerwork/migrators/synthetic_fixture.py` | Precedent for an importer, but it adapts foreign **JSON → portability envelope**. The markdown importer is different: it writes **directly through DomainStore** and does NOT produce a portability envelope. Do not bolt it onto `migrators/`; see §1. |
| CLI scaffold | ✅ | `src/innerwork/cli.py` (382 lines) | `argparse` subcommands, `_add_db_arg` (`--database-url` + `INNERWORK_DATABASE_URL` env), `_domain_dispatch`, JSON to stdout via `_print_json`, exit 2 + stderr on user errors. Phase-10 commands (`export`, `import`, `migrate`, `metrics`) are the pattern to copy. |
| Migration guide | ✅ | `docs/migration-guide.md` (223 lines) | Documents portability surface, CLI, round-trip procedure, failure modes, synthetic-fixture contract. §6 explicitly says hosted-Jira/Confluence importers are **not** shipped. The markdown importer gets a new section here. |
| Markdown deps | ✅ | `pyproject.toml` | `pyyaml>=6.0.3` is already a declared runtime dependency (used by `cli.py` manifest loading). **No new dependency is needed** for frontmatter parsing. |
| Markdown-tree importer | ❌ | n/a | Nothing reads a directory of `.md` files today. |
| Page hierarchy / attachments / page→page links | ❌ | n/a | `Page` has no `parent_id`; there is no attachment table; `Link` only connects `work_item_id` ↔ `page_id`. These absences drive the gap calls in §4. |

**Implication.** This is a small, contained slice: one new module that scans a directory tree and writes through the existing `DomainStore` API, one CLI subcommand, one test file, one docs section, one changelog entry. Nothing in the domain core, portability, or schema changes.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `docs/roadmap_markdown_importer_scoping.md` | (this file) | n/a | Exists at PM-scoping time. Implementation worker does not modify. |
| 2 | `src/innerwork/markdown_importer.py` | **new** | ~230 lines | The importer module. Two public functions: `scan_markdown_tree(root, *, author, created_at) -> MarkdownTree` (pure: walk + parse + validate, no I/O beyond reading files, no DB) and `import_markdown_tree(store, root, *, author, created_at, dry_run=False) -> dict` (writes through `DomainStore.create_space` / `create_page`; returns `{"spaces": int, "pages": int, "warnings": [...], "dry_run": bool}`). New exception `MarkdownImportError(ValueError)` for all user-facing failures. Internal helpers: `_parse_frontmatter(text)`, `_space_key_from_dirname(name)`, `_validate_fresh_target(store)`. See §2, §3 for exact semantics. |
| 3 | `src/innerwork/cli.py` | **edit** | +~30 lines | Add subcommand `import-markdown` (positional `dir: Path`; `--database-url` via existing `_add_db_arg`; `--author` default `"importer"`; `--dry-run` flag). Add `"import-markdown"` to the `_domain_dispatch` set and a dispatch branch: call `import_markdown_tree`, print summary JSON, exit 0; `MarkdownImportError`/`OSError` → stderr + exit 2. No other changes to the file. |
| 4 | `tests/test_markdown_importer.py` | **new** | ~220 lines | API-level + CLI-level tests per §6. |
| 5 | `tests/fixtures/markdown_tree/` | **new** | ~7 files | Checked-in fixture tree: 2 spaces, one with a nested subdirectory, frontmatter variants, an empty `.md`, a non-`.md` file, and a wikilink sample. Used by the end-to-end round-trip test and as a manual demo tree. See §6 for layout. |
| 6 | `docs/migration-guide.md` | **edit** | +~50 lines | New section (after §3 "Recommended round-trip procedure", renumber later sections): the `import-markdown` command, directory→space/page mapping rules, frontmatter keys, round-trip posture, and the limits from §4. Update the §1 list of what is *not* in the portable surface with "markdown frontmatter is not re-emitted". |
| 7 | `CHANGELOG.md` | **edit** | +~6 lines | Under `[Unreleased]`, add `### Markdown-tree importer` subsection enumerating the new CLI subcommand and module. No version bump. |
| 8 | `docs/roadmap.md` | **edit (optional, recommended)** | −4/+6 lines | After the importer PR merges, move the "Build a Markdown-tree importer" bullet from "Directional next → Migration" into "Shipped through Phase 10" (renaming the section header to "Shipped through Phase 10 and markdown importer" or adding a one-line "Post-phase-10 additions" note). Same PR, tiny diff. |

**Files that LOOK like they should be touched but MUST NOT be touched.**

| Path | Why not |
|---|---|
| `src/innerwork/portability.py`, `src/innerwork/domain_store.py`, `src/innerwork/knowledge.py`, `src/innerwork/domain.py`, `src/innerwork/model.py` | Domain core + stable wire format. The importer is a **caller** of `DomainStore`, not a modifier of it. |
| `src/innerwork/migrators/*` | `migrators/` is scoped to "adapters from foreign JSON shapes to the native portability format" (its `__init__.py` docstring). The markdown importer writes through DomainStore directly and does not produce a portability envelope; it lives as a sibling module. If it were placed in `migrators/`, its output would have to be a portable payload first — that is a different, larger design. |
| `.github/workflows/*`, `pyproject.toml` (deps), `src/innerwork/app.py`, `src/innerwork/domain_api.py` | No HTTP surface, no CI change, no new dependency (`pyyaml` suffices). |
| `tests/test_migration.py`, `tests/test_portability.py`, `tests/fixtures/synthetic_migration.json` | Existing suites stay untouched; the new suite lives in `tests/test_markdown_importer.py` + `tests/fixtures/markdown_tree/`. |

---

## §2 Directory → space/page mapping rules (locked)

These are the exact, deterministic rules `scan_markdown_tree` implements. "Deterministic" means: for a given tree, the same scan produces the same spaces/pages/warnings regardless of filesystem enumeration order (all iteration is sorted).

1. **Root.** `<dir>` must be an existing directory, else `MarkdownImportError` (exit 2).
2. **Spaces.** Each **immediate subdirectory** of the root is one space. Root-level `.md` files are an **error** (`MarkdownImportError` naming the file) — they have no space to belong to. Symlinked directories are not followed; symlinked entries are skipped (see §4).
3. **Space key derivation.** `_space_key_from_dirname`: uppercase the directory name, drop every character outside `[A-Z0-9]`, then validate against `^[A-Z][A-Z0-9]{1,9}$` (2–10 chars, per `knowledge.validate_space_key`). Invalid result → `MarkdownImportError` telling the operator to rename the directory (e.g. `x/` → `X` is 1 char → error; `a-b/` → `AB` → valid). **No silent truncation** (truncation risks silent key collisions). Two directories sanitizing to the same key → `MarkdownImportError` listing both paths.
4. **Space fields.** `name` = the original directory name verbatim; `owner` = `--author` value; `visibility`/`members` = model defaults (`internal`, `()`). A space is created even if it ends up with zero pages (the tree says it exists; the acceptance gate is "consistent with the on-disk tree").
5. **Pages.** Every `*.md` file anywhere **below** a space directory (any depth) is one page. Non-`.md` files are ignored silently (documented in the guide). Hidden entries (dotfiles) are treated like any other entry — no special filtering.
6. **Page title.** Frontmatter `title` if present (after strip, ≤200 chars, non-empty — model enforces); otherwise the **relative path stem** with `/` preserved: `space_dir/guides/getting-started.md` → `guides/getting-started`. The model has no parent-page field, so nested paths are **flattened into the title**; the on-disk structure remains recoverable from titles. Duplicate titles are allowed (no uniqueness constraint).
7. **Page body.** File content with the frontmatter block (if any) removed, then leading and trailing blank lines stripped. A file that is empty after that → page with `body=""` (title still comes from stem/frontmatter).
8. **Page author / timestamp.** Author = frontmatter `author` if present, else `--author` (default `"importer"`). `created_at` = one import-wide UTC ISO timestamp (default `utc_now_iso()`; API parameter for deterministic tests). Every page becomes **version 1** via `create_page` — no version history is imported.
9. **Ordering.** Spaces processed in sorted directory-name order; pages within a space in sorted relative-path order; warnings in sorted order. ID generation: `space_id`/`page_id` via `uuid.uuid4()` (same pattern as the existing CLI `project-create`).
10. **Fresh-target requirement.** `_validate_fresh_target` refuses to run when `spaces`, `pages`, or `page_versions` tables are non-empty (`MarkdownImportError`, exit 2). This mirrors `import_domain`'s posture: the importer never overlays an existing knowledge graph. `projects`/`work_items`/links/comments may exist (they are untouched); only the three knowledge tables gate.

---

## §3 Frontmatter handling decision (locked)

- **Recognized.** An optional YAML frontmatter block: the file's first line must be exactly `---`; the block ends at the next line that is exactly `---`. Parsed with `yaml.safe_load` (`pyyaml` is a declared dependency — no new dep, no third-party markdown parser claim).
- **Keys.** `title` (str; overrides stem; model validates ≤200 chars non-empty), `author` (str; overrides `--author`), `created_at` (optional ISO-8601 str; validated with `datetime.fromisoformat`). Unknown keys are ignored **and** recorded as a per-file warning in the summary's `warnings` list (the model has nowhere to store them).
- **Malformed input.** Opening `---` with no closing delimiter, or YAML that fails `safe_load`, → `MarkdownImportError` naming the file (exit 2). Loud and deterministic beats guessing.
- **One-way door (documented).** Frontmatter is **not round-trippable**: `export_domain` emits only `title/body/author/created_at` per `PageVersion`; a re-export does not re-emit frontmatter. `import-markdown → export → import` preserves the *content* (title/body/author), not the frontmatter envelope. The migration guide must state this so operators don't expect byte-identical `.md` files back.

---

## §4 Honest gap calls (decide-and-document, locked for v1)

| Topic | Decision | Rationale |
|---|---|---|
| Wikilinks `[[...]]` | **Not resolved.** Left verbatim in the body. | The only link table is `work_item_page_links` (work_item ↔ page, requires a work-item id). There is no page→page link table and no slug-based page lookup, so `[[wikilink]]` has no target to resolve to. A future slice could add a mapping file + page→page links, but that requires a schema change — out of scope here. |
| Attachments / images | **Not imported.** Non-`.md` files are ignored (silently). | No attachment table exists. Documented in the guide. |
| Nested page versions / history | **Not imported.** Each file = exactly one page at version 1. | No per-file version convention is defined; `update_page` exists but importing history would require a version-directory convention nobody has. Documented. |
| Page hierarchy | **Not represented.** Nested dirs flatten into page titles (§2.6). | `Page` has no `parent_id`. If hierarchy lands later it is a schema change; this mapping can be revisited then, and titles keep the original structure recoverable in the meantime. |
| Symlinks | **Skipped** (both symlinked dirs and symlinked files), documented. | Avoids cycles and surprise duplicates; deterministic behavior without following links. |
| Space metadata (visibility/members) | Defaults only. | No CLI surface for them in v1; `--author` covers ownership. |
| Projects / work items / links / comments | **Never created** by this importer. | Scope is `pages`/`spaces` per the roadmap item. |
| Empty `.md` files | Imported as empty-body pages. | Lossless and deterministic; the tree is fully represented. |
| Root-level `.md` files | **Error** (exit 2). | No space to attach them to; silent skipping would hide operator error. |

---

## §5 Acceptance gates (must hold before opening PR)

| Gate | Verification |
|---|---|
| Importing a fixture directory produces pages/spaces consistent with the on-disk tree. | `pytest tests/test_markdown_importer.py -q` passes; `test_import_markdown_tree_populates_store` asserts the store's spaces/pages/page_versions exactly match the fixture tree (keys, titles, bodies, authors, nested-flattened titles). |
| Imported content round-trips through `innerwork export` without loss. | `test_roundtrip_import_export_import_byte_identical` passes: import fixture → `export_domain_json` → `import_domain_json` into a second fresh store → re-export → both exports byte-identical; body/title/author preserved. |
| No network access; purely local file input. | The importer imports nothing beyond stdlib + `pyyaml` + `DomainStore`; grep check in §7. |
| Fresh-target rule enforced. | `test_fresh_target_required` passes (non-empty `spaces` → `MarkdownImportError`, exit 2, nothing written). |
| CLI is wired and honest. | `innerwork import-markdown --help` lists `dir`, `--database-url`, `--author`, `--dry-run`; CLI test asserts summary JSON and exit codes (0 / 2). |
| Full CI parity. | `uv run pytest -x`, `uv run ruff check .`, `uv run pyright` all clean — this is exactly what `.github/workflows/ci.yml` runs (ruff, pyright, pytest). **Never push a branch with red pyright.** |

---

## §6 Test plan

Fixture tree (`tests/fixtures/markdown_tree/`):

```
markdown_tree/
├── docs/                        # space key DOCS
│   ├── index.md                 # frontmatter {title: "Docs Home", author: alice@example.test}
│   └── guides/
│       └── getting-started.md   # no frontmatter → title "guides/getting-started"
├── eng/                         # space key ENG
│   ├── runbook.md               # unknown frontmatter key → warning
│   ├── empty.md                 # empty body
│   └── diagram.png              # ignored (non-md)
└── root.md                      # root-level → error case (used by one test; excluded from round-trip tests)
```

| Test | Asserts |
|---|---|
| `test_scan_tree_maps_directories_to_spaces` | `scan_markdown_tree` returns 2 spaces (DOCS, ENG) and 4 pages; titles/bodies/space_keys match §2 rules. |
| `test_import_markdown_tree_populates_store` | API import into tmp DB → `list_spaces`/`list_pages`/`get_page_version` reflect the tree (keys, titles, flattened nested title, empty body page, author override, non-md ignored). |
| `test_frontmatter_title_and_author` | `title`/`author` from frontmatter win over stem/`--author` default. |
| `test_unknown_frontmatter_keys_warned` | `warnings` contains the file path; unknown key value not stored anywhere. |
| `test_malformed_frontmatter_raises` | Unclosed `---` block and invalid YAML both raise `MarkdownImportError` naming the file. |
| `test_nested_dirs_flatten_into_titles` | `guides/getting-started.md` → title `guides/getting-started`. |
| `test_invalid_space_key_rejected` / `test_space_key_collision_rejected` | Dir `x/` → error; dirs `a-b/` and `a_b/` (both → AB) → error listing both. |
| `test_root_level_md_rejected` | Root `.md` → `MarkdownImportError`. |
| `test_empty_file_imports_empty_body` | `empty.md` → page with `body == ""`. |
| `test_body_over_limit_rejected` | 200_001-char body → `MarkdownImportError` (model's `PageVersion` cap). |
| `test_fresh_target_required` | Store with one pre-existing space → error, no rows added. |
| `test_roundtrip_import_export_import_byte_identical` | Import fixture (minus root.md) → export → import into fresh store → export; two exports byte-identical. |
| `test_cli_import_markdown_summary` | `main([...])` or subprocess `python -m innerwork.cli import-markdown <fixture> --database-url sqlite:///tmp.db` → exit 0, stdout JSON `{"spaces": 2, "pages": 4, "warnings": [...], "dry_run": false}`. |
| `test_cli_dry_run_no_write` | `--dry-run` → same summary, `dry_run: true`, DB file has zero knowledge rows (or no DB created). |
| `test_cli_missing_dir_exit_2` / `test_cli_root_md_exit_2` | Exit code 2 + stderr message. |

---

## §7 Anti-hallucination checklist

Implementation worker MUST run each check and quote the (empty / verified) output in the PR description.

| Check | Command |
|---|---|
| No hosted-importer claim | `grep -RInE "Jira.*(importer|import)|Confluence.*(importer|import)|hosted.*import" docs/migration-guide.md src/innerwork/markdown_importer.py CHANGELOG.md` returns nothing beyond the existing "not shipped" sentences. |
| No third-party markdown-parser claim | `grep -RInE "markdown.*(parser|library)|mistune|markdown-it|commonmark" src/innerwork/ docs/migration-guide.md CHANGELOG.md` returns nothing. The importer uses only `pathlib`/`yaml`/`datetime`/`uuid`/`DomainStore`. |
| No fabricated counts/benchmarks | `grep -RInE "[0-9]+ (pages|files|spaces) (imported|per second|in [0-9]+ms)" src/innerwork/markdown_importer.py` returns nothing; summary counts come from the scan itself, never hard-coded. |
| No network surface | `grep -RInE "httpx|requests|urllib|socket|http://|https://" src/innerwork/markdown_importer.py` returns nothing. |
| Files-touched boundary | `git diff --stat main` shows exactly: `src/innerwork/markdown_importer.py`, `src/innerwork/cli.py`, `tests/test_markdown_importer.py`, `tests/fixtures/markdown_tree/*`, `docs/migration-guide.md`, `CHANGELOG.md`, optional `docs/roadmap.md`. Nothing else. |

---

## §8 Exit criteria (done definition for the implementation task)

Per the roadmap item and child task `t_dc473849`:

1. `innerwork import-markdown <dir> --database-url sqlite:///...` works on `tests/fixtures/markdown_tree/` (and any tmp tree) — spaces/pages created consistent with §2.
2. Portability round-trip test passes with imported content (`test_roundtrip_import_export_import_byte_identical`).
3. Purely local file input; no network access in the new code (grep-clean).
4. `uv run pytest -x && uv run ruff check . && uv run pyright` all green before push.
5. PR opened against `main` on `feat/markdown-importer`, **DO NOT MERGE** — end with `kanban_block(reason="review-required: ...")` per the child task's mandate.

---

## §9 Handoff checklist for the implementation worker (atlassianeng)

1. Branch from `main` at the current HEAD: `git checkout -b feat/markdown-importer`. (Child task `t_dc473849` already pins this branch name.)
2. Write files in §1 order. The scoping doc (this file) is not modified.
3. Implement `src/innerwork/markdown_importer.py` exactly per §2/§3/§4. Keep it a thin caller of `DomainStore` — no raw SQL, no portability-envelope generation, no new dependencies.
4. Wire the CLI subcommand per §1 row 3. Follow the existing error convention: `MarkdownImportError`/`OSError` → stderr + exit 2; success → summary JSON + exit 0.
5. Add the checked-in fixture tree and the test file per §6. Include the round-trip byte-identity test — it is the acceptance gate.
6. Add the migration-guide section and CHANGELOG entry; optionally move the roadmap bullet (§1 row 8).
7. Run the CI-parity gate exactly as GitHub Actions does: `uv run pytest -x`, `uv run ruff check .`, `uv run pyright`. **All three must be green before push.** Do not repeat the 2026-05-29 phase-7 incident (green pytest, red pyright).
8. Run the §7 grep checks and quote results in the PR body.
9. Push via SSH remote (`git@github-personal:m0n3r0/atlassian-innerwork.git`), open PR titled e.g. `feat(markdown-importer): markdown-tree importer for spaces/pages` against `main`. **DO NOT MERGE.**
10. `kanban_block(reason="review-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")`.
