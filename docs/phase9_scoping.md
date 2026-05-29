# Phase 9 — Open-source governance, contributor experience, packaging, docs

**Status:** PM scoping (pre-implementation). Source: `data/production_oss_phases.json` (id=9).
**Parent:** phase 8 (deployment / ops / SLOs / observability / release engineering) merged via PR #16 (`1ee59c9`) on 2026-05-29.
**Audience:** the phase-9 implementation worker. Read this end-to-end before touching files.

---

## §0 Honest baseline (what the repo already has, today)

Verified against `main` at commit `1ee59c9` on 2026-05-29.

| Asset | Present? | Path | Notes |
|---|---|---|---|
| `LICENSE` | ✅ | `LICENSE` | MIT, © 2026 m0n3r0. 21 lines. No changes required. |
| `CONTRIBUTING.md` | ✅ (minimal) | `CONTRIBUTING.md` | 56 lines. Covers local setup, doc updates, TDD, grounding rules. **Does NOT** cover: governance, release flow, plug-in/extension model, PR review expectations, signoff/CLA stance, who maintainers are. Needs extension, not rewrite. |
| `CODE_OF_CONDUCT.md` | ❌ | n/a | Must be added. |
| `SECURITY.md` | ❌ | n/a | Must be added. Phase 7 produced `docs/threat-model.md` and `src/innerwork/audit.py` + `src/innerwork/field_acl.py`; SECURITY.md needs a reporting channel and a link to the threat model. |
| `GOVERNANCE.md` | ❌ | n/a | Must be added. Minimalist BDFL model honestly: `m0n3r0` is the sole maintainer. No other humans have opted in. **No foundation affiliation.** |
| `pyproject.toml` | ✅ | `pyproject.toml` | setuptools backend, `name = "atlassian-innerwork"`, `version = "0.1.0"`, `requires-python = ">=3.10"`. Already produces a wheel via `uv build` (exercised by release.yml). No build-system changes required for phase 9. Versioning policy is currently undeclared in writing. |
| `.github/workflows/release.yml` | ✅ | `.github/workflows/release.yml` | 63 lines. Tag-driven (`v*.*.*`), already builds wheel + sdist, generates `CHANGELOG_RELEASE.md` from git log, creates GitHub release with both artifacts attached, `fail_on_unmatched_files: true`. **Does not publish to PyPI.** Reuse as-is; phase 9 only documents it. |
| `.github/workflows/ci.yml` | ✅ | `.github/workflows/ci.yml` | 27 lines. Runs on PR + push to main: lint, type-check, OpenAPI contract validation, tests, wheel build. |
| `.github/PULL_REQUEST_TEMPLATE.md` | ❌ | n/a | Recommended (not blocking). |
| `.github/ISSUE_TEMPLATE/` | ❌ | n/a | Recommended (not blocking). |
| `docs/release.md` | ✅ | `docs/release.md` | 87 lines. Already documents pre-release checklist, tag procedure, what release.yml does, rollback. Phase 9 must cross-reference it from CONTRIBUTING and GOVERNANCE; no rewrite. |
| `docs/operations-runbook.md` | ✅ | `docs/operations-runbook.md` | 218 lines. Phase 8 deliverable. Cross-reference only. |
| `docs/threat-model.md` | ✅ | `docs/threat-model.md` | Phase 7 deliverable. SECURITY.md must link here. |
| Tagged release on git | ❌ | `git tag -l` returns empty | No `v*` tag yet exists. |
| Published on PyPI | ❌ | `https://pypi.org/pypi/atlassian-innerwork/json` → `{"message": "Not Found"}` | Package name `atlassian-innerwork` is NOT taken on PyPI as of 2026-05-29, but also NOT reserved by us. Phase 9 **does not publish**. |
| Docs site (sphinx/mkdocs/etc.) | ❌ | n/a | Repo has flat `docs/*.md`. No site generator configured. Phase 9 outlines one; does not stand it up. |

**Implication.** Phase 9 is mostly *writing* (docs, governance, security policy, code of conduct) plus a *dry-run* packaging exercise. It introduces no new runtime code paths. The single piece of real engineering work is the **extension-point honesty pass** (§3 below) — and that work is deliberately small because the registries the brief implies do not yet exist.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep and should be deferred to a follow-up phase.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `LICENSE` | confirm | unchanged | No change. Reference as-is. |
| 2 | `CODE_OF_CONDUCT.md` | **new** | ~80 lines | Contributor Covenant 2.1 verbatim, with the enforcement contact line filled in as a GitHub issue label (`code-of-conduct`) on this repo, not a personal email. Do NOT invent a private email address. |
| 3 | `SECURITY.md` | **new** | ~60 lines | Supported versions table (only `0.x` until first stable tag, no SLA promised), reporting channel = **GitHub private vulnerability reporting** (`Security > Report a vulnerability` on the repo). Cross-link `docs/threat-model.md`. State explicitly: no bug bounty, no PGP key, no embargo policy beyond "we will coordinate disclosure on best effort". |
| 4 | `GOVERNANCE.md` | **new** | ~120 lines | BDFL model. Sections: roles (Maintainer, Contributor), decision-making (lazy consensus on PRs; BDFL tiebreak), how to become a maintainer (one named human + one merged non-trivial PR + opt-in PR adding self to MAINTAINERS.md), breaking-change policy (semver; cross-graph contract breaks require a 1-minor-version deprecation window documented in CHANGELOG), conflict resolution. Section "Current maintainers" lists `m0n3r0` only and explicitly says no one else has opted in. State: **no foundation affiliation; not an Atlassian project; clean-room reference design**. |
| 5 | `MAINTAINERS.md` | **new** | ~15 lines | One row: `m0n3r0`, GitHub handle, scope = "all". Header line says "Add yourself via PR after the criteria in GOVERNANCE.md are met. Do not add anyone who has not personally opened the PR." |
| 6 | `CONTRIBUTING.md` | **edit (append, do not rewrite)** | +~140 lines | Append sections: "How decisions are made" (1-line pointer to GOVERNANCE.md), "How to report a security issue" (1-line pointer to SECURITY.md), "Release flow" (1-line pointer to `docs/release.md`), "Extension model: adding a new work-item type or page macro" (pointer to `docs/contributor-guide.md` §4), "Code review expectations" (lazy consensus, 1 maintainer LGTM, CI green, no force-push after review starts), "Sign-off" (use `git commit -s`; DCO; no CLA), "Project layout" (1-paragraph map of `src/innerwork/` modules and what each owns). |
| 7 | `docs/contributor-guide.md` | **new** | ~300 lines | The deeper how-to. Sections: §1 repo tour (module map, what each file in `src/innerwork/` owns); §2 dev loop (`uv sync --dev`, `pytest`, `ruff`, `pyright`, `validate_openapi_contract.py`); §3 testing conventions (TDD, what a "behavior test" looks like, fixtures in `tests/`); §4 **extension points** (see §3 of this scoping doc for the exact, honest version); §5 docs conventions (which doc to update for which change, cross-reference table); §6 PR workflow (branch from main, squash merge, conventional commit subject preferred but not enforced). |
| 8 | `docs/phase9_scoping.md` | (this file) | n/a | Already exists at PM-scoping time. Implementation worker does not modify. |
| 9 | `pyproject.toml` | **edit (small)** | +~10 lines | Add `[project.urls]` block: `Homepage`, `Source`, `Documentation = "https://github.com/m0n3r0/atlassian-innerwork#readme"` (until a docs site exists; do not point at a URL that 404s), `Issues`, `Changelog`. Add `keywords` and `classifiers` (License :: OSI Approved :: MIT License; Programming Language :: Python :: 3.10/3.11/3.12; Development Status :: 3 - Alpha; Topic :: Software Development). Do NOT bump version (still `0.1.0` — see §5). |
| 10 | `.github/PULL_REQUEST_TEMPLATE.md` | **new** | ~30 lines | Sections: "What this changes", "Why", "Tests", "Docs updated (which file?)", "Breaking change? (if yes, link GOVERNANCE.md §breaking-changes)". |
| 11 | `.github/ISSUE_TEMPLATE/bug_report.md` | **new** | ~25 lines | Standard. |
| 12 | `.github/ISSUE_TEMPLATE/feature_request.md` | **new** | ~25 lines | Standard. |
| 13 | `.github/ISSUE_TEMPLATE/config.yml` | **new** | ~10 lines | `blank_issues_enabled: false`, link to SECURITY.md private vuln reporting and to GitHub Discussions if enabled (otherwise omit). |
| 14 | `README.md` | **edit (append "Community" section, do not rewrite)** | +~30 lines | Linkrow to: `LICENSE` (already linked indirectly), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `GOVERNANCE.md`, `MAINTAINERS.md`, `docs/contributor-guide.md`, `docs/release.md`. This satisfies the acceptance gate "linked from README." |
| 15 | `docs/site-outline.md` | **new** | ~80 lines | The docs-site **outline**, not the site itself. Section "Recommended tooling: mkdocs-material" (rationale: existing `docs/*.md` are already markdown; mkdocs-material reuses them with minimal config). Section "Proposed `mkdocs.yml`" with a YAML stub (not committed as `mkdocs.yml`; just shown inline). Section "Site IA" (information architecture) grouping the existing docs into: Getting Started / Architecture / Operations / Security / Contributing / Reference. Section "Deferred" stating why phase 9 does **not** stand the site up: no hosting decision made, no maintainer time committed, mkdocs adds a build dep we don't want pinned without consensus. |
| 16 | `CHANGELOG.md` | **new** | ~30 lines (initial) | Keep-a-changelog format. Single `[Unreleased]` section listing phase 9 additions. Note in header: "Versions correspond to git tags. No tag exists yet; the first release will be `v0.1.0`." |

**Files that LOOK like they should be touched but MUST NOT be touched in phase 9.**

- `.github/workflows/release.yml`: works as-is. Phase 9 documents it; does not modify it.
- `.github/workflows/ci.yml`: works as-is.
- Any file under `src/innerwork/`: phase 9 is governance + docs + packaging metadata. **No runtime code changes.** If the contributor guide reveals a true API friction, file a follow-up issue; do not slip a code change into this phase.
- Existing `docs/*.md` other than `README.md` and the new files above: do not edit. They were validated in their own phases.

---

## §2 Acceptance gates (must hold before block-with-review)

Verify each before calling `kanban_block(reason="review-required: phase 9 scoping doc complete")`:

1. `LICENSE`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CONTRIBUTING.md`, `GOVERNANCE.md`, `MAINTAINERS.md` all exist at repo root and are linked from `README.md` "Community" section.
2. `docs/contributor-guide.md` exists and §4 ("Extension points") matches §3 of this scoping doc verbatim in substance — does not invent registries.
3. `pyproject.toml` `[project.urls]`, `keywords`, `classifiers` populated; `version` still `0.1.0`.
4. `uv build` produces both `dist/*.whl` and `dist/*.tar.gz` cleanly in a sandbox (`uv build --out-dir /tmp/phase9-build`). **Do not commit `dist/`.** Capture the output as a log line in the implementation task's `kanban_complete` metadata: `{"uv_build_dry_run": "ok", "wheel": "<filename>", "sdist": "<filename>"}`.
5. `git tag -l` is unchanged (still empty). Phase 9 **does not cut a tag.** Tagging is a separate human-driven action by the BDFL.
6. PyPI is **not** touched. `pypi-publish` action is not added to release.yml. CHANGELOG.md says "no tag yet."
7. `pytest -q`, `ruff check .`, `pyright`, `python scripts/validate_openapi_contract.py` all pass on a clean main + phase-9 branch checkout. None of phase 9's edits should regress these.
8. `MAINTAINERS.md` lists exactly one human (`m0n3r0`). No other names. No foundations. No "advisor" rows.

---

## §3 Extension points — the honest version

This is the most important section. The phase-9 brief asks the contributor guide to describe "how to add a new work-item type without forking core" (Jira-inspired) and "how to add a new page macro/renderer plug-in without forking core" (Confluence-inspired).

**Verified state of the code on `main` at `1ee59c9` (do not deviate from this in the contributor guide):**

- `src/innerwork/domain.py` defines a **closed-vocabulary** workflow: constants for state names, a hardcoded transition table, and `default_workflow() -> WorkflowDefinition`. There is no `WorkItemType` registry; there is no plug-in entry-point declared in `pyproject.toml`; there is no abstract base class a third party can implement.
- `src/innerwork/knowledge.py` defines `Page` and `PageVersion`. `PageVersion.body` is `str`. **There is no macro/renderer system.** `body` is opaque text. The codebase contains zero occurrences of `macro` or `render_page` outside of an unrelated `observability.py` Prometheus-text-renderer reference.

**Therefore the contributor guide MUST say (in §4 of `docs/contributor-guide.md`):**

> Innerwork does **not** ship plug-in registries for work-item types or page macros yet. Both extension surfaces are intentionally deferred until product requirements force the abstraction. Until then, "adding a new work-item type" or "adding a new page macro" is a core change made through a normal PR against the modules listed below. This section names the exact module seams a future plug-in registry would live behind, so a contributor can size the change honestly instead of looking for an entry-point that does not exist.

Then enumerate the **real seams** — module + line-of-responsibility — without inventing registries:

**Work-item types (Jira-inspired).** Today there is one work-item *type* (an item belongs to a project and moves through a fixed workflow). To introduce a new type:

1. `src/innerwork/domain.py` — extend or generalize the workflow constants. The state name list and the transition table are the source of truth. A real registry would replace these constants with a lookup keyed on `WorkItem.kind`.
2. `src/innerwork/domain_store.py` — add validation for the new type in the `create_work_item` path (lines around 302–356). The store currently writes any `WorkItem` row whose fields validate; adding a per-type field set means extending the SQLite schema and the dataclass.
3. `src/innerwork/domain_api.py` — `WorkItemCreate` (line ~82) is the API surface. New types need new fields here and corresponding response models.
4. `src/innerwork/ai_context.py` — `_entry_for_work_item` (line ~117) shapes the AI context payload per item. New types need their own entry shape if the payload should differ.
5. `src/innerwork/search.py` — search currently treats work items as one kind; per-type filtering would go in `_validate_kinds` (line ~127) and the hit-builder.

A real plug-in story would introduce a `WorkItemTypeRegistry` in a new module (e.g. `src/innerwork/types.py`) plus a `[project.entry-points."innerwork.work_item_types"]` table in `pyproject.toml`. **Phase 9 does not introduce this.** A follow-up phase (call it phase 10 or later) should, once a second concrete type is needed.

**Page macros / renderers (Confluence-inspired).** Today `PageVersion.body` is a plain string with a size cap. There is no macro syntax, no renderer pipeline, no macro context object. To introduce a macro system:

1. Decide a macro syntax. None is implied by the current code.
2. `src/innerwork/knowledge.py` — `PageVersion` (line ~151) gains a `body_format: str` field. A real registry would key macro lookup on this field plus inline macro tokens in the body.
3. A new module (e.g. `src/innerwork/page_renderer.py`) would own the registry. A real entry-point table in `pyproject.toml` (`[project.entry-points."innerwork.page_macros"]`) would let third parties register a callable.
4. `src/innerwork/ai_context.py` — `_entry_for_page` (line ~140) currently returns the raw body in the context payload. A renderer would need to decide whether to expand or strip macros before context export.
5. `src/innerwork/search.py` — search indexes the raw body today. A macro system needs to decide whether to index pre- or post-render text. Wrong default here leaks macro source into search results.

**Phase 9 does not introduce a macro system.** The contributor guide must say this plainly. "Plug-in without forking core" is a future promise, not a current capability. Pretending otherwise burns contributor trust.

---

## §4 Packaging — documented shape (no behavior change)

`pyproject.toml` already builds a wheel via `setuptools` and is exercised by `release.yml`. Phase 9's packaging deliverable is **documentation + metadata polish**, not a build-system change.

| Concern | Current state | Phase 9 action |
|---|---|---|
| Build backend | `setuptools` | unchanged |
| Source layout | `src/innerwork/` with explicit `packages = ["innerwork", "innerwork.data"]` | unchanged |
| Package data | `innerwork/data/*.json` included | unchanged |
| Console script | `innerwork = "innerwork.cli:main"` | unchanged |
| Python support | `>=3.10` | declare classifiers for 3.10/3.11/3.12 |
| `[project.urls]` | absent | add Homepage / Source / Issues / Changelog (and Documentation pointing at README for now) |
| `keywords` / `classifiers` | absent | add (see §1 row 9) |
| Wheel + sdist build | works (`uv build`) | documented in `docs/release.md`; phase 9 runs as dry-run only |
| PyPI publication | not done; name not reserved | **not in scope for phase 9** |
| Version | `0.1.0` | unchanged. First tag will be `v0.1.0`. |
| Versioning policy | undocumented | document semver in `GOVERNANCE.md` §breaking-changes |
| Tag flow | already tag-driven in `release.yml` | document in `CONTRIBUTING.md` + `GOVERNANCE.md`, cross-link existing `docs/release.md` |

**Dry-run packaging check the implementation worker MUST run** (not the PM scoping worker):

```sh
cd <repo>
rm -rf /tmp/phase9-build
uv build --out-dir /tmp/phase9-build
ls /tmp/phase9-build
# expect: atlassian_innerwork-0.1.0-py3-none-any.whl AND atlassian_innerwork-0.1.0.tar.gz
```

Capture filenames in the implementation task's `kanban_complete` metadata. Do **not** commit `/tmp/phase9-build` or any `dist/` directory.

---

## §5 Versioning policy (to be encoded in GOVERNANCE.md)

- Semver. `MAJOR.MINOR.PATCH`.
- Pre-1.0 (where we live now): minor bumps may include breaking changes; patches are strictly bug fixes.
- Post-1.0 (whenever the BDFL declares it): breaking changes require a minor-version deprecation window. Deprecation must be announced in `CHANGELOG.md` under the minor before removal under the next minor.
- Cross-graph contract changes (work-graph ↔ knowledge-graph link kinds in `knowledge.py::LINK_KINDS`, or the cross-graph fields in `ai_context.py`) are explicitly enumerated as breaking surfaces in `GOVERNANCE.md`.
- Tag format: `vMAJOR.MINOR.PATCH`. Signed tags (`git tag -s`) per `docs/release.md`.
- No alpha/beta/rc tag conventions until needed. Do not pre-declare a release-candidate flow that no one has used.

---

## §6 Governance — minimalist BDFL model (to be encoded in GOVERNANCE.md)

**Anti-hallucination guardrails the implementation worker must enforce:**

- Maintainers list contains **only humans who have personally opened the PR adding their own name to `MAINTAINERS.md`**. Today: `m0n3r0` only.
- Do not list `@dependabot`, `@github-actions`, `@github-copilot`, AI agents, or any non-human handle as a maintainer.
- Do not name any human who has not opted in via PR. If in doubt, omit.
- Do not claim affiliation with Atlassian, the Linux Foundation, Apache Software Foundation, OpenJS, CNCF, or any other foundation. The project has no such affiliation.
- Do not name a corporate sponsor.
- Do not invent a private security email. Use GitHub private vulnerability reporting and a label on this repo. Phase 9 does **not** stand up a `security@` address.

**Decision-making.** Lazy consensus on PRs (24h to object on a non-trivial change). BDFL tiebreak on disagreement. BDFL is `m0n3r0` until a second maintainer is added by the procedure above, at which point GOVERNANCE.md is amended.

**Breaking changes.** See §5. The breaking-change section of GOVERNANCE.md must explicitly call out the two cross-graph surfaces:

- `LINK_KINDS` and `validate_link_kind` in `src/innerwork/knowledge.py` — adding or removing a kind is breaking.
- The `ContextEntry` / `ContextBundle` shape in `src/innerwork/ai_context.py` — fields are part of the AI-context contract and changing them breaks downstream consumers.

---

## §7 Docs-site outline (`docs/site-outline.md`)

Phase 9 produces the **outline** of a future docs site, not the site. The outline must:

- Name **mkdocs-material** as the recommended generator, with a one-sentence rationale (reuses existing `docs/*.md` flat markdown; minimal config; no JS toolchain).
- Provide an inline `mkdocs.yml` YAML stub (not committed as a real file) showing nav structure.
- Group existing docs into IA buckets: Getting Started (`README.md`, `docs/docker-poc.md`), Architecture (`docs/overview.md`, `docs/work-graph-domain.md`, `docs/knowledge-graph-domain.md`, `docs/collaboration.md`, `docs/comments-and-idempotency.md`, `docs/product-scope.md`, `docs/phase-6.md`), Operations (`docs/operations-runbook.md`, `docs/slos.md`, `docs/observability.md`, `docs/release.md`), Security (`docs/threat-model.md`, `SECURITY.md`), Contributing (`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `GOVERNANCE.md`, `MAINTAINERS.md`, `docs/contributor-guide.md`), Reference (`docs/production-grade-roadmap.md`, `docs/live-application.md`).
- State clearly: "Phase 9 does not commit `mkdocs.yml`, does not add `mkdocs-material` to `pyproject.toml`, and does not deploy a site. A future phase will, once the maintainer commits the build/deploy time." This is an honest deferral, not a missed deliverable.

---

## §8 Exit criteria mapped to deliverables

The phase brief's exit criteria:

| Brief exit criterion | How phase-9 implementation satisfies it |
|---|---|
| External contributor can land a non-trivial PR using only documented workflow | `CONTRIBUTING.md` + `docs/contributor-guide.md` + `GOVERNANCE.md` together describe: setup, dev loop, test conventions, PR flow, review expectations, decision model, breaking-change handling, and where to ask. CI is documented (`.github/workflows/ci.yml` is the contract). |
| A tagged release is installable from PyPI or equivalent | **Honest deviation.** Phase 9 does not publish to PyPI and does not cut a tag. It proves the wheel + sdist build cleanly (`uv build` dry-run) and that `release.yml` is wired to do the publish when a maintainer tags. CHANGELOG.md, GOVERNANCE.md, and `docs/release.md` together describe how the first tag will produce an installable artifact via the existing GitHub Release attachment. PyPI publication is a follow-up decision for the BDFL, not a phase-9 task. |

The phase-9 implementation `kanban_complete` summary must call this deviation out explicitly: *"No PyPI publication, no git tag cut. `uv build` dry-run produced wheel + sdist cleanly. First tag is reserved for a separate human-driven release action."*

---

## §9 Anti-hallucination checklist (implementation worker re-reads before completing)

- [ ] `MAINTAINERS.md` contains only humans who personally opened the PR. (Today: `m0n3r0` alone.)
- [ ] No mention of foundation affiliation anywhere.
- [ ] No mention of corporate sponsorship.
- [ ] `SECURITY.md` reporting channel = GitHub private vulnerability reporting; no invented email.
- [ ] `docs/contributor-guide.md` §4 (extension points) does not claim a plug-in registry exists. It names real module seams.
- [ ] No new file under `src/innerwork/` (phase 9 is docs + metadata only).
- [ ] `pyproject.toml` `version` unchanged at `0.1.0`.
- [ ] `git tag -l` unchanged (no tag created in this phase).
- [ ] No `dist/` committed.
- [ ] `release.yml` and `ci.yml` unchanged.
- [ ] CHANGELOG.md explicitly notes no tag exists yet.

---

## §10 Out of scope (deferred to later phases)

- Building an actual `WorkItemTypeRegistry`.
- Building an actual page macro/renderer registry.
- Standing up the docs site (committing `mkdocs.yml`, adding `mkdocs-material` dep, GitHub Pages workflow).
- Publishing to PyPI / Test PyPI.
- Cutting `v0.1.0`.
- Bug bounty, CLA, DCO bot enforcement, signed-commit enforcement.
- Translations / i18n of governance docs.
- Adopting a foundation governance model.

If any of these surface as needs during phase-9 implementation, **file a follow-up issue and proceed without them.** Do not scope-creep.

---

## §11 Implementation task handoff (what the orchestrator should dispatch next)

After this scoping doc lands and is approved (review-required block), the orchestrator should create the implementation task with:

- **Title:** `phase 9: Open-source governance, contributor experience, packaging, docs - implementation`
- **Assignee:** the appropriate implementation profile (same one that landed phase 7 + phase 8 implementation tasks)
- **Body must include:** the file list from §1, the gates from §2, the anti-hallucination checklist from §9, the dry-run build command from §4, and an explicit reminder that `release.yml`, `ci.yml`, and `src/innerwork/` are off-limits.
- **Workspace:** `dir:/home/eml/repos/atlassian-innerwork` (same repo the prior phase tasks used; branch from main as `feat/phase-9-governance-docs`).
- **Block at end with:** `review-required: phase 9 implementation ready for PR`. The orchestrator opens the PR; the BDFL merges.
