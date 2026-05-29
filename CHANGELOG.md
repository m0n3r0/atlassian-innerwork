# Changelog

All notable changes to this project are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows [Semantic Versioning](https://semver.org/) per [`GOVERNANCE.md`](GOVERNANCE.md) §4.

> Versions correspond to git tags. **No tag exists yet**; the first release will be `v0.1.0`. Until then, every change accumulates under `[Unreleased]`.

## [Unreleased]

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
