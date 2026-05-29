# Contributor Guide

A deeper how-to for working in `atlassian-innerwork`. Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) first for the short version. This guide goes into the module layout, the dev loop, test conventions, extension seams, and the docs-update map.

## §1 Repo tour — what each module owns

Source lives under `src/innerwork/`. Public surface is what the FastAPI app, the CLI, and the test suite import.

| Module                          | Owns                                                                                          |
|---------------------------------|-----------------------------------------------------------------------------------------------|
| `model.py`                      | Service-intent model + fail-closed validation rules (edge-broker side).                       |
| `broker.py`                     | OSB-inspired provisioning broker, idempotent operation tracking.                              |
| `control_plane.py`              | Deterministic xDS-style snapshot renderer.                                                    |
| `app.py`                        | FastAPI live application, route wiring, middleware.                                           |
| `cli.py`                        | Local contributor CLI (`innerwork ...`).                                                      |
| `state_store.py`                | Optional JSON state store for restart-safe demos.                                             |
| `sql_state_store.py`            | Local SQLite store for durable services / operations / idempotency keys.                      |
| `domain.py`                     | Work-graph domain: projects, work items, workflow constants, transitions. **No registry.**   |
| `domain_store.py`               | Domain persistence (SQLite). Work-item / project / comment CRUD, transitions.                |
| `domain_api.py`                 | FastAPI pydantic models for the work-graph surface (`WorkItemCreate`, etc.).                  |
| `knowledge.py`                  | Knowledge-graph domain: spaces, pages, page versions, link kinds. **No macro system.**       |
| `ai_context.py`                 | AI-context bundle assembly across both graphs. Defines `ContextEntry` / `ContextBundle`.      |
| `search.py`                     | Cross-graph search; kind-filtered hits, snippet builder, scoring.                             |
| `audit.py`                      | Append-only audit log (phase 7).                                                              |
| `field_acl.py`                  | Field-level ACL enforcement (phase 7).                                                        |
| `observability.py`              | Prometheus-text metrics renderer + structured logging helpers.                                |
| `data/`                         | Bundled JSON catalogs (`product_catalog.json`, `production_oss_phases.json`).                 |

Tests live in `tests/` and mirror the module layout. Fixtures (FastAPI client, temp SQLite path, sample catalogs) are in `tests/conftest.py`.

## §2 Dev loop

The supported toolchain is `uv` (Astral). Falling back to plain `pip` is supported by CI but not preferred locally.

```bash
# one-time
uv sync --dev

# every change
uv run pytest -q
uv run ruff check .
uv run pyright
uv run python scripts/validate_openapi_contract.py

# run the live app
uv run uvicorn innerwork.app:app --reload

# CI-compatible pip fallback (no uv)
python -m pip install -e . pytest ruff
python -m pytest -q
python -m ruff check .
```

Before opening a PR: all four checks above must be green locally. CI (`.github/workflows/ci.yml`) runs the same set, plus a wheel build, on every PR and push to main.

## §3 Testing conventions

The repo follows test-driven development for behavior changes:

1. add a failing test that describes the new behavior or asserts the bug,
2. run it and confirm it fails for the right reason,
3. implement the smallest change that makes it pass,
4. run the full suite,
5. update the relevant doc (see §5).

**What a "behavior test" looks like here.** Tests assert observable behavior of public surfaces (FastAPI route response shapes, CLI output, persisted state, snapshot determinism). They do not assert private function call sequences. A good test names the contract it protects in its `test_` function name (e.g. `test_create_work_item_rejects_unknown_state`).

**Fixtures.** Prefer the existing fixtures in `tests/conftest.py`. Don't introduce a new temp-directory pattern when `tmp_path` is already wired into the test fixtures.

**Snapshot-style assertions.** When asserting a rendered snapshot, compare the full structure rather than a single field. The control-plane snapshot renderer is intentionally deterministic; a flake there usually means an actual non-determinism bug.

## §4 Extension points (the honest version)

> **Read first.** `atlassian-innerwork` does **not** ship plug-in registries for work-item types or page macros yet. Both extension surfaces are intentionally deferred until product requirements force the abstraction. Until then, "adding a new work-item type" or "adding a new page macro" is a core change made through a normal PR against the modules listed below. This section names the exact module seams a future plug-in registry would live behind, so a contributor can size the change honestly instead of looking for an entry-point that does not exist.

### 4.1 Adding a new work-item type (Jira-inspired)

Today there is **one work-item type**: an item belongs to a project and moves through the fixed default workflow (`todo -> in_progress -> done`). The workflow constants and transition table are in code, not data. There is no `WorkItemType` registry. There is no `[project.entry-points."innerwork.work_item_types"]` entry in `pyproject.toml`. There is no abstract base class a third party can implement.

To introduce a new type today, the change touches these seams in order:

1. **`src/innerwork/domain.py`** — extend or generalize the workflow constants (`STATE_*`) and the transition table. The state name list and transition table are the source of truth. A real registry would replace these constants with a lookup keyed on `WorkItem.kind`.
2. **`src/innerwork/domain_store.py`** — extend validation for the new type in `create_work_item` (around lines 293–356) and the SQLite schema if the type carries new fields. The store currently writes any `WorkItem` row whose fields validate; adding a per-type field set means extending the schema, the dataclass, and the migration.
3. **`src/innerwork/domain_api.py`** — `WorkItemCreate` (line ~82) is the API surface. New types need new fields and corresponding response models.
4. **`src/innerwork/ai_context.py`** — `_entry_for_work_item` (line ~117) shapes the AI-context payload per item. New types need their own entry shape if the payload should differ.
5. **`src/innerwork/search.py`** — search currently treats work items as one kind; per-type filtering goes in `_validate_kinds` (line ~127) and the hit builder.

A real plug-in story would introduce a `WorkItemTypeRegistry` in a new module (e.g. `src/innerwork/types.py`) plus a `[project.entry-points."innerwork.work_item_types"]` table in `pyproject.toml`. **This project does not yet do that.** A follow-up phase will, once a second concrete type is needed. Until then, "adding a type" is a normal core PR.

### 4.2 Adding a new page macro / renderer (Confluence-inspired)

Today `PageVersion.body` (in `src/innerwork/knowledge.py`, around line 151) is a plain string with a size cap. There is no macro syntax, no renderer pipeline, no macro-context object. The substring `macro` and the function `render_page` do not appear anywhere relevant in `src/innerwork/`.

To introduce a macro system, the change touches these seams in order:

1. **Decide a macro syntax.** None is implied by the current code; you'll need to make a call (Confluence storage format? Markdown-with-shortcodes? Mustache? Something else?). Discuss in an issue first.
2. **`src/innerwork/knowledge.py`** — `PageVersion` (~line 151) gains a `body_format: str` field. A real registry would key macro lookup on this field plus inline macro tokens in the body.
3. **A new module** (e.g. `src/innerwork/page_renderer.py`) would own the registry. A real `[project.entry-points."innerwork.page_macros"]` table in `pyproject.toml` would let third parties register a callable.
4. **`src/innerwork/ai_context.py`** — `_entry_for_page` (~line 140) currently returns the raw body in the context payload. A renderer must decide whether to expand or strip macros before context export.
5. **`src/innerwork/search.py`** — search indexes the raw body today. A macro system must decide whether to index pre- or post-render text. Wrong default here leaks macro source into search results.

**This project does not yet ship a macro system.** Pretending otherwise burns contributor trust, so the maintainers prefer to call this out plainly rather than imply an extensibility story that does not exist.

### 4.3 Why not just ship the registries?

Two reasons. First, neither registry has a second concrete consumer today; introducing the abstraction would be speculative. Second, designing a wrong registry and shipping it is harder to walk back than not having one. The maintainers would rather merge a second concrete type or macro first, observe what is actually shared, and extract the abstraction afterward.

## §5 Docs conventions — what to update for which change

| Kind of change                                                                  | Update                                                          |
|---------------------------------------------------------------------------------|-----------------------------------------------------------------|
| Architecture or grand-design shift                                              | `docs/grand-design.md` and/or `docs/production-oss-grand-design.md` |
| New module, renamed module, or removed module under `src/innerwork/`            | This guide §1 (the table) and `docs/overview.md`                |
| Work-graph behavior (workflow, transitions, projects, work items)               | `docs/work-graph-domain.md`                                     |
| Knowledge-graph behavior (spaces, pages, links)                                 | `docs/knowledge-graph-domain.md`                                |
| Cross-graph link kinds (`LINK_KINDS` in `knowledge.py`)                         | `docs/work-graph-domain.md` + `docs/knowledge-graph-domain.md` + `GOVERNANCE.md` §4.3 |
| AI context surface (`ContextEntry` / `ContextBundle`)                           | `docs/collaboration.md` + `GOVERNANCE.md` §4.3                  |
| Idempotency / comments contract                                                 | `docs/comments-and-idempotency.md`                              |
| Threat model, audit log, field ACLs                                             | `docs/threat-model.md` + `SECURITY.md` if reporting surface changes |
| Operational behavior (SLOs, metrics, runbooks)                                  | `docs/operations-runbook.md`, `docs/slos.md`, `docs/observability.md` |
| Release flow                                                                    | `docs/release.md` + this guide §2                               |
| Governance, maintainers, code of conduct                                        | `GOVERNANCE.md` / `MAINTAINERS.md` / `CODE_OF_CONDUCT.md`       |
| Public API contract (OpenAPI)                                                   | `spec/openapi.yaml` + run `scripts/validate_openapi_contract.py` |
| User-facing CHANGELOG                                                           | `CHANGELOG.md` under `[Unreleased]`                             |

## §6 PR workflow

1. **Branch from `main`.** Branch names are not enforced; descriptive names help (e.g. `fix/snapshot-determinism-when-two-routes-tie`).
2. **Conventional-commit subjects are preferred but not enforced.** A subject like `feat(domain): add bug as a work-item type` is easier to changelog than `update domain.py`.
3. **Open the PR early.** Mark it draft if it isn't ready for review. CI will run on every push.
4. **Fill in the PR template.** Especially the "Docs updated" row — point at the file you touched.
5. **Lazy consensus, squash merge.** A single maintainer LGTM after CI is green is sufficient (24h objection window for non-trivial changes, see [`GOVERNANCE.md`](../GOVERNANCE.md) §3). Squash merge is the default; the squashed subject becomes the changelog line.
6. **No force-push after review has started.** Add fixup commits; the maintainer will squash on merge.
7. **Sign-off (`git commit -s`).** This project uses the [Developer Certificate of Origin](https://developercertificate.org/). There is **no CLA**.

If you're new to the repo, a good first PR is a docs fix, a missing test, or a small refactor that has a clear before/after.
