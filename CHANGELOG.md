# Changelog

All notable changes to this project are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows [Semantic Versioning](https://semver.org/) per [`GOVERNANCE.md`](GOVERNANCE.md) §4.

> Versions correspond to git tags. **No tag exists yet**; the first release will be `v0.1.0`. Until then, every change accumulates under `[Unreleased]`.

## [Unreleased]

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
