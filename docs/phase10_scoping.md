# Phase 10 — Beta, migration, launch, and post-launch iteration

**Status:** PM scoping (pre-implementation). Source: `src/innerwork/data/production_oss_phases.json` (id=10).
**Parent:** phase 9 (governance / contributor experience / packaging / docs) merged via PR #17 (`26b0a17`) on 2026-05-29.
**Audience:** the phase-10 implementation worker. Read this end-to-end before touching files.

---

## §0 Honest baseline (what the repo already has, today)

Verified against `main` at commit `26b0a17` on 2026-05-29.

| Asset | Present? | Path | Notes |
|---|---|---|---|
| Portability layer | ✅ | `src/innerwork/portability.py` (455 lines) | `export_domain`, `export_domain_json`, `import_domain`, `import_domain_json`. Covers Phase A–F tables (projects, work_items, transitions, spaces, pages, page_versions, links, work_item_comments, page_comments). Deterministic key ordering, FK-safe insert order, byte-stable round-trip. Format version constant `PORTABILITY_FORMAT_VERSION = 1`. Audit emission on export/import. **No CLI wrapper.** **No external-format importer** (e.g. Jira/Confluence JSON exports). **No migration guide.** |
| Portability tests | ✅ | `tests/test_portability.py` | Existing round-trip coverage. Phase 10 will add a synthetic fixture flow, not replace these tests. |
| Analytics layer | ✅ | `src/innerwork/analytics.py` (258 lines) | `project_rollup`, `space_rollup`, `domain_rollup`, permission-filtered. Returns plain dicts/dataclasses. Suitable as the data source for a post-launch metrics view. |
| Audit log | ✅ | `src/innerwork/audit.py` | Phase 7 deliverable. Source of beta signal for "what users actually did". |
| Operations runbook | ✅ | `docs/operations-runbook.md` | Phase 8 deliverable. Beta onboarding/offboarding will cross-reference, not duplicate. |
| Release flow | ✅ | `docs/release.md` + `.github/workflows/release.yml` | Tag-driven. **No tag cut yet.** Phase 10 does NOT cut the tag; phase 10 produces the **launch plan** that points at the tag procedure. |
| Site outline | ✅ | `docs/site-outline.md` | Phase 9 deliverable; phase 10 launch plan references it. |
| CHANGELOG | ✅ | `CHANGELOG.md` | Single `[Unreleased]` section. Phase 10 appends a `[Phase 10]` block under `[Unreleased]`; **does not** cut `[0.1.0]`. |
| Governance / SECURITY / CoC / MAINTAINERS | ✅ | `GOVERNANCE.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `MAINTAINERS.md` | Phase 9. Beta onboarding doc cross-references them. |
| Public beta program | ❌ | n/a | Must be defined. No prior signup channel, no waitlist. |
| Migration tooling beyond round-trip | ❌ | n/a | `portability.py` only round-trips its own format. No importer for foreign JSON shapes. Phase 10 builds **one** synthetic-fixture importer, not a generic adapter. |
| Public roadmap | ❌ | n/a | No `ROADMAP.md` or pinned issue. Phase 10 adds `docs/roadmap.md` plus a roadmap pointer in README. |
| Post-launch metrics dashboard | ❌ | n/a | Phase 10 produces a **document describing** the dashboard surface (CLI command + computed-from-audit-log views), not a hosted dashboard. |
| Beta user counts | ❌ | n/a | None observed. Anti-hallucination: **do not invent numbers**. The launch plan documents the program; it does not claim usage. |
| Revenue / pricing / commercial relationships | ❌ | n/a | None. Anti-hallucination: **do not assert any**. Clean-room reference design, no monetization. |

**Implication.** Phase 10 is mostly *writing* (launch plan, beta runbook, migration guide, roadmap, post-launch iteration loop) plus **two small pieces of engineering**: (a) a CLI wrapper around the existing portability module (`innerwork export` / `innerwork import` subcommands) and (b) a synthetic foreign-format importer that exercises the import path end-to-end. Everything else is documentation, cross-referencing, and process.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep and should be deferred to a follow-up phase.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `docs/phase10_scoping.md` | (this file) | n/a | Exists at PM-scoping time. Implementation worker does not modify. |
| 2 | `docs/launch-plan.md` | **new** | ~220 lines | The headline phase-10 artifact. Sections: §1 launch posture (beta-only, no GA promise); §2 launch checklist (pre-tag, tag-cut, post-tag); §3 announce channels (GitHub Releases page, README banner — **no** Twitter/HN/Reddit claims unless explicitly executed); §4 rollback plan (tag deletion + revert PR, pointer to `docs/release.md`); §5 success criteria (documented beta window, ≥1 end-to-end migration on a synthetic fixture, iteration cadence operating); §6 explicit non-goals (no SLA, no support contract, no commercial offering, no claimed user count). |
| 3 | `docs/beta-program.md` | **new** | ~200 lines | The beta runbook. Sections: §1 program scope (what "beta" means here: 0.x versions, breaking changes permitted, no SLA); §2 onboarding (how a user joins — fork/clone instructions, GitHub Discussions sign-up template if Discussions enabled, otherwise a GitHub issue template `beta_signup`); §3 offboarding (how a user leaves — close their issues, stop pinging them, remove from any list); §4 feedback channels (bug reports → existing bug_report template; feature requests → existing feature_request template; security → SECURITY.md private vuln reporting); §5 dogfooding signal (project's own bug tracking happens in this instance once self-hosted; phase 10 documents the **plan**, does not require self-hosting). |
| 4 | `docs/migration-guide.md` | **new** | ~250 lines | The migration guide. Sections: §1 supported source formats (only the synthetic fixture format in this phase; explicitly **not** Jira REST exports, **not** Confluence Cloud exports — naming those is overreach without parser code); §2 the native portability format (point at `portability.py`, document `format_version=1` and the field-by-field shape); §3 step-by-step: foreign JSON → adapter → `import_domain_json`; §4 verification: round-trip the imported data and diff against the fixture; §5 known limits (idempotency cache and notification state are NOT portable; per `portability.py` module docstring). |
| 5 | `docs/roadmap.md` | **new** | ~180 lines | Public roadmap. Sections: §1 phases 0–10 status table (cross-link each to its merged PR/commit); §2 currently in progress (phase 10); §3 candidate post-launch tracks listed as **proposals, not commitments** (e.g. mkdocs site stand-up, foreign-format importers, optional integrations) — each with a paragraph and an "open question" bullet, **no dates**; §4 explicit non-roadmap items (no PyPI publish until BDFL decides, no hosted SaaS, no Atlassian-compatibility claim). |
| 6 | `docs/post-launch-iteration.md` | **new** | ~200 lines | Iteration loop. Sections: §1 cadence (recommend bi-weekly check-in via GitHub issue with label `iteration-review`; explicit: this is a recommendation, the BDFL may operate ad-hoc); §2 inputs to the loop (open issues, bug reports, audit-log-derived usage when self-hosted, beta participant feedback); §3 prioritization rubric (severity × reach × effort — define the buckets); §4 outputs (changelog entry per merged PR, roadmap delta documented in `docs/roadmap.md`); §5 metrics surface (the planned post-launch dashboard described in §7 of `docs/launch-plan.md`). |
| 7 | `docs/metrics-dashboard.md` | **new** | ~150 lines | Describes the **planned** dashboard. Sections: §1 data sources (audit log via `audit.py`, analytics rollups via `analytics.py`); §2 dashboard surface (a CLI subcommand `innerwork metrics` printing JSON / table — implement as a thin formatter over `domain_rollup`, no new datastore); §3 metrics shown (work-items by state, transitions/day, page versions/day, comment volume); §4 what is NOT shown (no per-user identifiers in aggregates, per Phase 7 field ACL stance; no external telemetry export). Phase 10 may implement the CLI subcommand (small, additive); if deferred, the doc explicitly says "implemented in follow-up." |
| 8 | `src/innerwork/cli.py` | **new** | ~250 lines | Minimal `argparse` CLI exposing four subcommands: `export` (calls `export_domain_json` and prints to stdout or `--out` file), `import` (calls `import_domain_json` from stdin or `--in` file into a target SQLite DB path), `migrate` (calls the synthetic-fixture adapter from §10 below), `metrics` (formats `domain_rollup` as JSON or pretty table). Entry point: `def main(argv: list[str] | None = None) -> int`. **Pure dispatch.** No business logic — all heavy lifting in existing modules. |
| 9 | `pyproject.toml` | **edit (small)** | +~3 lines | Add `[project.scripts]` block: `innerwork = "innerwork.cli:main"`. Do NOT bump version (still `0.1.0`, see §5). |
| 10 | `src/innerwork/migrators/__init__.py` | **new** | ~5 lines | Package marker + module docstring stating: "Adapters from foreign JSON shapes to the native portability format. Phase 10 ships one synthetic-fixture adapter; further importers are post-launch work." |
| 11 | `src/innerwork/migrators/synthetic_fixture.py` | **new** | ~180 lines | The single foreign-format adapter for phase 10. Shape: takes a "synthetic Jira-shaped" JSON (small fixture, no real Jira API mimicry — see §3 for what synthetic means here), maps it into the native portability dict, returns it. Pure function `synthetic_fixture_to_portable(payload: dict) -> dict`. Validates required fields, raises `MigrationError` (new exception class) on malformed input. No I/O; no DB writes. |
| 12 | `tests/fixtures/synthetic_migration.json` | **new** | ~120 lines | The synthetic fixture itself. Three projects, six work items across two states, two transitions per item, two spaces, three pages with two versions each, two comments per page, two comments per work item, two cross-links. Stable, deterministic. |
| 13 | `tests/test_cli.py` | **new** | ~200 lines | Unit tests for `cli.py`: each subcommand against a temp SQLite DB. Round-trip: import fixture → export → diff equals normalized fixture. `metrics` returns valid JSON whose `work_item_count` totals match the fixture. |
| 14 | `tests/test_migration.py` | **new** | ~180 lines | Tests the adapter: malformed input raises `MigrationError`; valid fixture produces a dict that `import_domain` accepts without error; resulting store passes `analytics.domain_rollup` cleanly. End-to-end test: load fixture → adapt → `import_domain_json` → re-export → diff matches a stored expected snapshot. |
| 15 | `README.md` | **edit (append "Roadmap" + "Beta" sections, do not rewrite)** | +~25 lines | Link to `docs/roadmap.md`, `docs/launch-plan.md`, `docs/beta-program.md`, `docs/migration-guide.md`. State explicitly: project is in beta, no SLA, breaking changes possible. |
| 16 | `CHANGELOG.md` | **edit** | +~25 lines | Under `[Unreleased]`, add a `### Phase 10` subsection enumerating the new CLI, the migration adapter, the docs, and the roadmap. Do NOT cut a `[0.1.0]` section — that happens at tag time, which is post-phase-10. |
| 17 | `.github/ISSUE_TEMPLATE/beta_signup.md` | **new** | ~20 lines | Lightweight signup template: name/handle (optional), use case (1 sentence), willingness to file bugs (yes/no). Label: `beta`. Body explicitly states: no SLA, no support promise, public issue (do not paste secrets). |

**Files that LOOK like they should be touched but MUST NOT be touched in phase 10.**

| Path | Why not |
|---|---|
| `src/innerwork/portability.py` | Phase 5/6 artifact; stable wire format. Phase 10 builds **around** it (CLI + adapter), not on top of it. |
| `src/innerwork/audit.py`, `src/innerwork/field_acl.py` | Phase 7. Read-only references from new docs. |
| `src/innerwork/domain_store.py`, `src/innerwork/domain.py` | Domain core. Out of scope. |
| `.github/workflows/release.yml`, `.github/workflows/ci.yml` | Phase 8/9 artifact. Phase 10 references the release flow; it does NOT modify it. |
| `pyproject.toml` `version` field | **No version bump in phase 10.** The first version bump and `v0.1.0` tag are a deliberate post-phase-10 act gated by the BDFL. |
| `GOVERNANCE.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `MAINTAINERS.md` | Phase 9 artifacts. Cross-link only. |
| `docs/site-outline.md` | Phase 9 outline. The site itself remains deferred. Phase 10 does NOT stand up mkdocs. |

---

## §2 Acceptance gates (must hold before opening PR)

| Gate | Verification |
|---|---|
| Beta program has documented onboarding and offboarding. | `docs/beta-program.md` exists with explicit §2 (onboarding) and §3 (offboarding) headings, each with a numbered procedure a third party can follow. |
| Migration path is tested with ≥1 synthetic fixture. | `tests/test_migration.py` includes an end-to-end test that loads `tests/fixtures/synthetic_migration.json` through `synthetic_fixture_to_portable` → `import_domain` and asserts the result is non-empty + round-trippable. Test passes under `pytest`. |
| Post-launch iteration loop is documented and operating. | `docs/post-launch-iteration.md` exists with §1 cadence, §2 inputs, §3 prioritization, §4 outputs, §5 metrics. "Operating" here means **documented and ready to run**; the loop does not require a live cycle to have completed at phase-10 PR time. |
| CLI ships and is wired. | `innerwork --help` succeeds after `uv pip install -e .` (covered by `tests/test_cli.py`). Each subcommand has its own `--help`. |
| All tests pass. | `pytest -q` exits 0. `ruff check`, `pyright` clean for new files. |
| OpenAPI contract validation unchanged. | Phase 10 adds no HTTP surface; the existing `validate_openapi_contract.py` continues to pass. |
| README cross-links land. | README's new "Roadmap" and "Beta" sections link to the four new docs and they all resolve. |

---

## §3 What "synthetic fixture" means here (anti-overreach)

The phase brief says "migration guide for importing from common JSON exports." We deliberately ship **one synthetic adapter**, not a Jira or Confluence importer, because:

1. The repo has no Jira/Confluence client, no real export samples, and no permission to redistribute real exports.
2. Naming "Jira REST export" or "Confluence Cloud export" without parsing the real shape is dishonest.
3. The acceptance gate says "≥1 synthetic fixture" — singular, synthetic. That is what we build.

The synthetic fixture is shaped *loosely like* a generic issue-tracker/wiki export (project → work items → comments; space → pages → versions → comments) but is invented by us, lives in `tests/fixtures/`, and is documented as a *template* future adapters can model. The migration guide (§4 above) lists Jira/Confluence as **post-launch candidates**, not phase-10 deliverables.

---

## §4 Beta posture (what we promise, what we don't)

**We promise.**
- Public issue tracker for bug reports.
- Best-effort response to security reports per `SECURITY.md`.
- Changelog entry for every merged PR.
- Documented breaking-change policy (per `GOVERNANCE.md` §breaking-changes).

**We do NOT promise.**
- A specific response time, uptime, or release cadence.
- Any commercial relationship, paid support, or service contract.
- Backwards compatibility for `0.x` versions; breaking changes are explicitly permitted per `GOVERNANCE.md`.
- That feedback will be acted on; only that it will be acknowledged (issue close or comment) where reasonable.
- Any specific user count, adoption metric, or testimonial — phase 10 documentation **must not** quote numbers it cannot cite.

---

## §5 Versioning, tagging, packaging — explicitly deferred

Phase 10 does NOT:
- Bump `pyproject.toml` `version` (stays `0.1.0`).
- Cut a `v*` git tag.
- Publish to PyPI.
- Stand up a docs site.

Each of these is a deliberate BDFL act gated **after** phase 10's PR is merged and at least one external migration has been demonstrated. The phase-10 PR description must explicitly note this so a reviewer doesn't accidentally tag.

---

## §6 Public roadmap layout (`docs/roadmap.md`)

Phases 0–10 table cross-linking each phase to its commit + PR.

```
| Phase | Title                                                                 | Status   | PR  | Commit  |
|------:|-----------------------------------------------------------------------|----------|-----|---------|
|     0 | PM product selection & production OSS phase specification             | shipped  | #N  | <sha>   |
|     1 | …                                                                     | shipped  | #N  | <sha>   |
| …     | …                                                                     | …        | …   | …       |
|     9 | Open-source governance, contributor experience, packaging, docs       | shipped  | #17 | 26b0a17 |
|    10 | Beta, migration, launch, and post-launch iteration                    | active   | TBD | TBD     |
```

Implementation worker fills in the actual PR numbers / SHAs by running `git log` and `gh pr list --state merged --json number,mergeCommit,title --limit 30` at write-time. **Do not invent PR numbers** — query the repo.

---

## §7 Cross-product integration (Jira + Confluence inspiration)

The Jira/Confluence-inspired requirements call for "public beta surfaces work-item lifecycles" and "page editing and version history; release notes written in the system itself." These map to phase 10 as **documented intent**, not new code:

- **Work-item lifecycles in public beta** → the existing work-item state machine (Phase A) is already exercised by `tests/`. The beta program doc states that the project will **self-host this very system** once a deployment is stood up to track its own bugs. Phase 10 does NOT stand up that deployment; phase 10 documents the intent so it is visible to beta participants.
- **Page editing + version history** → the existing page versioning (Phase D) is functional. Same posture: documented intent to dogfood, no deployment commitment.
- **Release notes written in the system** → aspirational; for phase 10 the release notes for the (future) `v0.1.0` tag live in `CHANGELOG.md` and the GitHub Release body generated by `release.yml`. The doc explicitly says this is the bootstrap mode and that once self-hosting exists, release notes will move to in-system pages.

This is honest: it acknowledges the source of the requirement without claiming work we haven't done.

---

## §8 Module/file boundary checklist

Before opening PR, the implementation worker MUST confirm:
- No file under `src/innerwork/` except the new `cli.py`, `migrators/__init__.py`, `migrators/synthetic_fixture.py` is modified.
- `portability.py` is read-only.
- `release.yml` and `ci.yml` are untouched.
- New CLI lives behind `[project.scripts]` and works after editable install.
- All new code has type hints, docstrings, and 100% test coverage of new lines (matching repo precedent).

---

## §9 Anti-hallucination checklist

Before opening PR, the implementation worker MUST verify each of the following with grep / git / pytest commands and quote the output in the PR description:

| Check | Command |
|---|---|
| No beta user counts asserted | `grep -RInE "\\b[0-9]+\\s+(users|beta testers|customers)\\b" docs/launch-plan.md docs/beta-program.md docs/roadmap.md` returns nothing. |
| No revenue / pricing language | `grep -RInE "\\b(price|pricing|revenue|\\$|USD|EUR|subscription|paid|free tier|enterprise plan)\\b" docs/` returns nothing in the new files (existing files may be unaffected). |
| No commercial relationship claim | `grep -RInE "\\b(partner|partnership|enterprise customer|client|contract)\\b" docs/launch-plan.md docs/beta-program.md docs/migration-guide.md docs/roadmap.md docs/post-launch-iteration.md docs/metrics-dashboard.md` returns nothing. |
| No Atlassian-compatibility claim | `grep -RInE "\\b(compatible with Jira|compatible with Confluence|Jira-compatible|Confluence-compatible|Atlassian-compatible|drop-in replacement)\\b" docs/` returns nothing. The migration guide explicitly says "synthetic fixture, not Jira/Confluence." |
| Roadmap PR/SHA references are real | Each phase row in `docs/roadmap.md` cross-links to an actual merged PR; verify with `gh pr view <N>` or `git show <sha>`. |
| Acceptance gates verifiable | Each acceptance-gate row in §2 maps to a concrete command a reviewer can run. |

---

## §10 Test plan

| Test | Location | Asserts |
|---|---|---|
| CLI `export` round-trip | `tests/test_cli.py::test_export_roundtrip` | Stored fixture → import → export → byte-identical. |
| CLI `import` from stdin | `tests/test_cli.py::test_import_stdin` | stdin JSON imported into temp DB; row counts match. |
| CLI `metrics` JSON shape | `tests/test_cli.py::test_metrics_json` | Output parses as JSON; top-level keys match `domain_rollup` contract. |
| CLI `migrate` | `tests/test_cli.py::test_migrate_synthetic` | `innerwork migrate --in fixtures/synthetic_migration.json --out /tmp/out.db` exits 0; `/tmp/out.db` contains the expected row counts. |
| Adapter happy path | `tests/test_migration.py::test_synthetic_fixture_adapter_happy` | Fixture → adapter → portable dict shape valid. |
| Adapter error path | `tests/test_migration.py::test_synthetic_fixture_adapter_missing_field` | Missing required field raises `MigrationError` with informative message. |
| End-to-end migration | `tests/test_migration.py::test_end_to_end_synthetic_migration` | Fixture → adapter → `import_domain_json` → `analytics.domain_rollup` non-empty + matches expected snapshot. |

---

## §11 Exit criteria (phase-10 done definition)

Per JSON spec id=10, phase 10 is "done" when:
1. Beta has run for a documented window. **For PR-merge purposes**, "documented" means the program doc exists, declares a window, and the program is open. The window itself spans post-merge time; no PR-time activity is required.
2. At least one external migration has been completed end-to-end. **For PR-merge purposes**, the synthetic-fixture test exercising adapter → import → analytics counts as the demonstration. "External" here means "from a non-native JSON shape," which the synthetic fixture is.
3. Post-launch iteration cadence is in place. **For PR-merge purposes**, the iteration loop doc exists with concrete cadence, inputs, prioritization, outputs.

These are documentation-bounded; phase 10 does not require live beta users at merge time. The launch plan explicitly separates "phase-10 merge" from "tag cut" from "beta active" so the boundaries are honest.

---

## §12 Handoff for implementation worker

Pattern for the implementation task (`t_b4f48eb1` per task children):

1. Branch from `main` at `26b0a17`: `git checkout -b feat/phase-10-beta-launch`.
2. Write files in §1 order. Tests and docs land in the same PR.
3. Run `pytest -q && ruff check . && pyright src tests` before committing.
4. Update CHANGELOG and README (§1 rows 15, 16).
5. Open PR with title `Phase 10: beta, migration, launch, and post-launch iteration` and a body that quotes the §9 anti-hallucination check commands + their (empty / verified) outputs.
6. End with `kanban_block(reason="review-required: phase 10 beta/migration/launch scoping implementation — see PR")`. Reviewer = BDFL `m0n3r0`.
7. After merge, sync local `main` (`git fetch --all --prune && git checkout main && git pull --ff-only`) and report final SHA. **Do NOT cut a `v*` tag** — that is a deliberate post-phase-10 act.
