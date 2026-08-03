# Consolidated Audit — 2026-08-03

Status: consolidation deliverable for task `t_b12c7442` (branch `feat/audit-review`).

This report merges the four domain audits into one deduplicated findings list
with a unified severity, grouped by subsystem, each finding carrying a
suggested fix and an effort estimate. It ends with a prioritized fix backlog
(P0–P3) that the orchestrator can spawn fix tasks from.

## Sources

| Audit | Report | PR | Findings |
|---|---|---|---|
| Code correctness | `docs/audit/2026-08-03-code.md` | #25 (`feat/audit-code`) | 0 HIGH / 3 MED / 7 LOW |
| Docs accuracy | `docs/audit/2026-08-03-docs.md` | #27 (`feat/audit-docs`) | 4 High / 7 Medium / 2 Low |
| Security & trust | `docs/audit/2026-08-03-security.md` | #28 (`feat/audit-sec`) | 0 HIGH / 2 MED / 8 LOW |
| QA / test coverage | `docs/audit/2026-08-03-qa.md` | #29 (`feat/audit-qa`) | 3 High / 5 Medium / 4 Low + §3.3 |

All four audits ran against `main @ 328561d` and independently recorded
**332/332 tests passing**. No code was changed by any audit; the suite is
untouched.

## Cross-audit reconciliation

### Contradictions: none found

The four reports agree on every shared fact they checked independently:
332 tests pass; no HIGH-severity correctness bug in `src/`; the
anti-hallucination guardrail passes with a narrow allowlist; no secrets in
tree or history; dependencies clean (`uv pip check`); the `.worktrees`
guardrail fix `2ea7180` is complete. The docs audit's P6 ("threat-model
claims verified true of code") and the sec audit's F5 (stale code comments
citing threat-model §3.4) are **complementary, not contradictory**: P6
verified the doc's claims, F5 found code-comment references to a subsection
that does not exist. Both stand.

### Overlaps (deduplicated into one consolidated finding each)

| Raw findings | Root cause | Consolidated |
|---|---|---|
| CODE M3 + DOCS H1 | migration-guide documents `export-domain`/`import-domain`/`--db` CLI that does not exist | **C21** |
| DOCS H2 + DOCS H3 | false "no metrics endpoint / no request-level telemetry" claims; `--db` flag wrong | **C22** |
| QA High 1 + QA High 2 | `ai_context.py` security-adjacent paths with zero coverage | **C32** |
| QA §1.1 + QA Med 7 | cli.py 0% coverage is a subprocess-measurement artifact; wiring branches untested in-process | **C34** |

### Complementary pairs (kept separate, cross-referenced)

- **SEC F1** (audit sink never wired) ↔ **QA Med 8** (portability audit
  emission untested): F1 is the wiring gap; the QA item is a test gap that
  only becomes meaningful once a sink is wireable. Fix F1 first.
- **CODE M1** (portability drops permission columns) ↔ **QA Med 8**: the
  round-trip byte-identical test passes only because its seed uses default
  visibility everywhere; the honest test is the one M1 asks for.
- **CODE L7** (import-wide `created_at` unvalidated) ↔ **QA Med 6**
  (frontmatter `created_at` validation untested): same module, different
  gaps (one code, one test).
- **CODE "guardrail verified complete"** ↔ **QA §3.3** (no regression test
  pins `2ea7180`): the fix is correct; the absence of a regression test is
  a separate, real gap.

## Unified severity scale

- **CRITICAL** — remotely exploitable, unrecoverable data loss, or secret
  exposure. *None found.*
- **HIGH** — real defect with user-visible harm: silent data/permission
  loss, false operational claims that mislead an operator, or a
  security-adjacent surface with zero test coverage.
- **MED** — genuine gap with bounded impact (silent failure, defeated
  documented control, missing regression test).
- **LOW** — hygiene, drift, diagnostics, or cosmetic.

Source severities are kept verbatim next to each consolidated finding so
reviewers can see the mapping.

---

## Consolidated findings by subsystem

### Portability & import (export / import / migrate)

**C1 — HIGH** *(source: CODE M1, MED)* — Export/import silently drops
`visibility`/`members` from projects and spaces.

- `src/innerwork/portability.py:92-95, 128-133` (SELECT), `:247-248,
  :275-276` (INSERT). Import falls back to defaults (`'internal'`, `'[]'`).
- Verified by execution: `public` project + `restricted` space both
  round-trip to `internal`/`()`. **`restricted` widens to `internal`
  (access broadens)**; member lists vanish. The byte-identical round-trip
  test passes only because its seed uses defaults.
- Fix: add `visibility, members` to the projects/spaces SELECT and INSERT
  (export `members` as the decoded tuple); extend the round-trip test to
  seed a non-default visibility.
- Effort: **S** (0.5–1d).

**C2 — MED** *(source: SEC F10, LOW)* — JSON import has no input size cap;
deep-nesting `RecursionError` and non-UTF-8 input are not mapped to
`DomainImportError`.

- `src/innerwork/cli.py:363,369`; `portability.py` import path. A multi-GB
  envelope is parsed fully; a 2000-deep array raises an uncaught
  `RecursionError` (runtime-verified).
- Fix: cap input size (e.g. 50 MB) in the CLI/`import_domain_json`; wrap
  `json.loads` to map `RecursionError`/`ValueError` to `DomainImportError`.
- Effort: **S**.

**C3 — LOW** *(source: CODE L3)* — Synthetic fixture uses int ids for
TEXT-PK tables, so its payload is not byte-stable under
export→import→export.

- `src/innerwork/migrators/synthetic_fixture.py:181,191,199,208` vs
  TEXT-PK columns (`domain_store.py:1139,1166,1182`).
- Fix: use string ids (`"link-001"`, …) and regenerate
  `tests/fixtures/synthetic_migration.json`.
- Effort: **XS**.

**C4 — LOW** *(source: QA Med 8)* — Portability audit emission
(`portability_export`/`portability_import`) has no test.

- `src/innerwork/portability.py:204-205`; zero tests construct a store with
  an audit sink and export/import.
- Fix: test that export/import emit one `portability_*` event each. Do this
  after C5 (sink wiring) so the test exercises a real path.
- Effort: **S**.

### Audit & trust

**C5 — MED** *(source: SEC F1, MED)* — The audit sink is never wired by any
shipped surface; there is no mechanism to enable it.

- `domain_store.py:110,133-134`; `cli.py:289`; `app.py:98`. Runtime-verified:
  a store built exactly as the CLI builds it emits **zero** audit rows and
  creates no `audit.db`. The threat model §6.1 calls wiring an operator
  responsibility, but the shipped CLI offers no way to perform it.
- Fix: add `--audit-log <path>` + `INNERWORK_AUDIT_DB` env var; wire
  `SqliteAuditSink` in `_domain_dispatch` and `AppState`; update
  `docs/threat-model.md` §6.1.
- Effort: **M** (1–2d).

**C6 — LOW** *(source: SEC F2)* — `actor_kind` is hardcoded `"system"`; the
documented spoofing mitigation is not wireable.

- `domain_store.py:139,111`; `notify.py:463`. A transition by `bob` records
  `actor_kind=system` (runtime-verified).
- Fix: accept `actor_kind` per call in `_audit` (default `"system"`);
  forward caller kind from the mutation APIs.
- Effort: **M**.

**C7 — LOW** *(source: SEC F3)* — Several mutation surfaces are un-audited
even with a wired sink, and the exclusions are undocumented.

- `src/innerwork/audit.py:53-62` (`AUDIT_SURFACES` closed enum). Project /
  space / work-item / comment / link / `import-markdown` writes emit
  nothing; the threat model lists only the included surfaces.
- Fix: extend `AUDIT_SURFACES` (work_item/comment/link/markdown_import) or
  explicitly enumerate exclusions in `docs/threat-model.md` §4/§5.
- Effort: **S**.

**C8 — LOW** *(source: SEC F4)* — Direct read endpoints bypass `can_read`;
visibility is enforced only on search/analytics/ai_context.

- `permissions.py:18-20` vs `domain_api.py:828-962`. `GET /v1/projects`,
  `/v1/work_items`, `/v1/spaces`, `/v1/pages`, `/v1/*/comments`,
  `/v1/links` return full content regardless of `visibility`/`members`.
- Fix: apply `parse_principal_header` + `can_read` on direct reads, or
  document the direct surface as operator-only. (LOW given the documented
  single-tenant posture, but a real conformance gap.)
- Effort: **M**.

**C9 — LOW** *(source: SEC F5)* — Doc drift: `field_acl.py` cites
threat-model §3.4 (does not exist); `audit.py` says `JsonlAuditSink` is
used by `scripts/backup.py` (it is not); threat-model scope omits the
markdown importer; archived threat-model is not allowlisted.

- Fix: correct the two stale code references; add import surfaces to the
  threat-model scope; delete or allowlist `docs/archive/threat-model.md`.
- Effort: **S**.

**C10 — MED** *(source: QA Med 5)* — Audit-sink read-back query filters are
untested.

- `src/innerwork/audit.py:280-287` (`SqliteAuditSink.query`), `:390-414`
  (`MemoryAuditSink.query`): `surface`/`entity_kind`/`entity_id`/`actor`
  filters and `limit` have zero tests.
- Fix: filter/limit tests for both sinks (single, combined, limit, empty).
- Effort: **S**.

### Input safety

**C11 — MED** *(source: SEC F8, MED)* — Markdown importer reads the full
file before the size check; no pre-read cap.

- `markdown_importer.py:168` (`read_text`) runs before `:170-173`
  (`_PAGE_BODY_MAX` check). Runtime-verified: a 40 MB file is read fully
  (0.13 s) and only then rejected; a multi-GB file exhausts memory first.
  Frontmatter block is likewise unbounded before `yaml.safe_load`.
- Fix: check `path.stat().st_size` against a cap (2–5 MB) before
  `read_text`; cap the frontmatter block (16 KB); both in
  `scan_markdown_tree` so `--dry-run` is gated too.
- Effort: **S**.

**C12 — LOW** *(source: SEC F9)* — `UnicodeDecodeError` / `RecursionError`
escape as tracebacks from the importer.

- `markdown_importer.py:168` + `cli.py:401` (`except (MarkdownImportError,
  OSError)` misses `ValueError`/`RecursionError`). Runtime-verified with a
  non-UTF-8 file and a 3000-level YAML nesting.
- Fix: catch both in `_scan_pages`, map to `MarkdownImportError` (clean
  per-file error + exit 2).
- Effort: **XS**.

**C13 — LOW** *(source: CODE L7)* — Import-wide `created_at` is not
ISO-validated (only frontmatter `created_at` is).

- `markdown_importer.py:118-119, 386` vs `:271-285`. Not exposed by the
  CLI today (library callers only).
- Fix: run `_validate_iso_timestamp` on the import-wide `created_at`.
- Effort: **XS**.

**C14 — LOW** *(source: QA Med 6)* — Malformed frontmatter `created_at`
(non-string / unparseable ISO) has no test.

- `markdown_importer.py:272-282`; `test_malformed_frontmatter_raises`
  covers YAML errors only.
- Fix: tests with `created_at: not-a-date` and `created_at: 123`.
- Effort: **XS**.

### Notifications

**C15 — MED** *(source: CODE M2, MED)* — Mixed-case mention handles never
resolve — silent notification loss.

- `notify.py:110` (validation accepts any case), `:133-139` (register keeps
  verbatim key), `:63,144-160` (lookup lowercases). `User(handle="Alice")`
  resolves neither `@alice` nor `@Alice` (verified).
- Fix: normalize handles to lowercase at registration (or reject
  non-lowercase in `User.__post_init__`).
- Effort: **XS**.

### API / HTTP surface

**C16 — MED** *(source: QA High 3, MED-unified)* — `/v2/products` and
`/v2/production-oss-phases` HTTP endpoints (and the `products`/`phases`
CLI branches) have no test at all.

- `app.py:200,204`; `cli.py:186-191`. Module functions are unit-tested; the
  public endpoints and CLI dispatch branches are not (`grep /v2/products
  tests/` → no hits).
- Fix: `TestClient` tests asserting 200 + stable key shape; in-process
  `main(argv)` tests for the two CLI branches.
- Effort: **S**.

**C17 — LOW** *(source: CODE L6)* — `x-request-id` header missing on
exception-path responses.

- `app.py:132-142`: header set only on the success path; `call_next`
  raising yields a 500 without a request id.
- Fix: set the header on the exception path (or an exception handler that
  echoes the bound id).
- Effort: **XS**.

**C18 — LOW** *(source: CODE L1)* — UNIQUE-violation handler mislabels any
unique-constraint conflict as key reuse.

- `domain_store.py:244-247, 531-534`: a PRIMARY-KEY duplicate contains
  "UNIQUE" in SQLite's message and is misreported as "key already exists".
- Fix: match the specific constraint name (`projects.key`/`spaces.key`)
  before the generic UNIQUE branch.
- Effort: **XS**.

**C19 — LOW** *(source: CODE L5)* — Broker idempotency: validation-failure
path does not bind the idempotency key.

- `broker.py:47-50` vs `:73-75`. A retried invalid payload gets a fresh
  failure operation id each time instead of a stable replay.
- Fix: save the idempotency record in the validation-failure branch.
- Effort: **S**.

**C20 — LOW** *(source: CODE L2)* — `truncated` flag in the AI-context
budget loop is sticky.

- `ai_context.py:532-534`: set on the first skipped candidate, never
  cleared when a later, smaller candidate fits.
- Fix: set it only when a candidate is skipped and no later one is
  admitted (or rename semantics to "any skipped").
- Effort: **XS**.

### Documentation accuracy

**C21 — HIGH** *(source: DOCS H1 + CODE M3)* — `docs/migration-guide.md`
documents a CLI surface that does not exist.

- §1, §2.1–2.4, §3, §5, §7 show `innerwork export-domain` /
  `import-domain` with `--db`, `--indent`, `--input`, `--principal`, and an
  `upgrade` subcommand. The shipped CLI has `export` / `import` with
  `--database-url` and a positional input (`cli.py:114-134, 273-285`).
  Verified: `uv run innerwork export-domain` → argparse `invalid choice`.
- Fix: rewrite the examples to `innerwork export --database-url
  sqlite:///path.db --out snapshot.json` / `innerwork import
  --database-url sqlite:///fresh.db snapshot.json` (ideally regenerate from
  `--help`). §4 (markdown importer) is accurate and stays.
- Effort: **S**.

**C22 — HIGH** *(source: DOCS H2 + H3)* — False claims about metrics and
telemetry; wrong `--db` flag.

- `docs/metrics-dashboard.md` §1/§2/§4/§6: flag is `--database-url`, not
  `--db`; "No request-level telemetry" is false (observability middleware
  records `http_requests_total`/`http_request_errors_total`/
  `http_request_duration_ms`, `app.py:121-158`); "deliberately does not run
  a metrics endpoint" is false (`GET /metrics` at `app.py:172-182`).
- `CHANGELOG.md` [Unreleased]: "no metrics endpoint exposed by the FastAPI
  app" is false and contradicts `docs/operations-runbook.md`.
- Fix: scope the telemetry-negative claims to the *analytics rollup*,
  reword the endpoint claim, swap `--db` → `--database-url` everywhere.
- Effort: **S**.

**C23 — MED** *(source: DOCS H4, docs-High)* — README has five broken
"Design docs" links.

- `README.md`: `docs/production-oss-grand-design.md` (×2),
  `docs/autonomous-kanban-playbook.md` (×2), `docs/grand-design.md`,
  `docs/production-readiness-checklist.md`, `docs/architecture.html` all
  moved to `docs/archive/`.
- Fix: point all five at `docs/archive/...` (or drop stale entries).
- Effort: **XS**.

**C24 — MED** *(source: DOCS M1)* — `docs/roadmap.md`: wrong CLI names
(`export-domain`/`import-domain`) and three references to nonexistent
`docs/governance.md` (actual: root `GOVERNANCE.md`).

- Effort: **XS**.

**C25 — MED** *(source: DOCS M2)* — `docs/beta-program.md` and
`docs/post-launch-iteration.md` both reference nonexistent
`docs/governance.md` (companion docs + §8).

- Effort: **XS**.

**C26 — MED** *(source: DOCS M3/M4/M5)* — `docs/overview.md`,
`docs/live-application.md`, `docs/docker-poc.md` describe a
pre-Phase-6/7/10 world (phases "planned", CLI surface incomplete,
work-graph/knowledge-graph APIs "planned next").

- Fix: update each to the current shipped state (comments, Phase-6 read
  surface, Phase-10 portability/metrics/import-markdown).
- Effort: **M**.

**C27 — MED** *(source: DOCS M6/M7)* — Envelope/schema-version examples
stale: `schema_version: 3` in `docs/collaboration.md` and "bumps to 3" in
`docs/comments-and-idempotency.md`; actual `DOMAIN_SCHEMA_VERSION = 4`
(`domain_store.py:51`).

- Effort: **XS**.

**C28 — LOW** *(source: DOCS L1)* — `docs/operations-runbook.md`:
`PORT`/`UVICORN_LOG_LEVEL` env vars are not read by code;
`INNERWORK_STATE_PATH` default description wrong (unset → no state store);
"Structured logs | stdout" is actually stderr; "SLite" typo.

- Effort: **XS**.

**C29 — LOW** *(source: DOCS L2)* — `docs/README.md` archive note says
archived docs will be rewritten "once Phase D (identity/permission/audit)
lands" — audit landed in Phase 7; phrasing is stale (harmless).

- Effort: **XS**.

**C30 — LOW** *(source: CODE L4)* — `src/innerwork/search.py:13-15`
module docstring says permissions are a later phase; the code filters by
`principal` (lines 256-292).

- Effort: **XS**.

### Test coverage & infrastructure

**C31 — MED** *(source: QA §3.3)* — No regression test pins the `2ea7180`
`.worktrees` guardrail fix.

- `test_anti_hallucination_script_passes` runs against `REPO_ROOT` where
  `.worktrees/` is a parent sibling (or absent in CI), so the `SKIP_DIRS`
  entry is never exercised.
- Fix: build a `tmp_path` tree with a forbidden token *under* a
  `.worktrees/` subdir, assert exit 0; control case already exists.
- Effort: **S**.

**C32 — HIGH** *(source: QA High 1 + 2)* — `ai_context.py` security-adjacent
paths have zero coverage.

- `:407-423` per-kind permission filter (comment/transition/link
  redaction) and `:511-522` page-comment candidate collection: 0 tests hit
  either branch.
- Fix: tests asserting a restricted parent hides its comments/transitions/
  links from an unprivileged principal's bundle; a query matching a page
  comment lands in the bundle.
- Effort: **S**.

**C33 — MED** *(source: QA Med 4)* — `domain_api.py` per-endpoint 404/400
error branches (~76 lines) untested.

- e.g. `GET /pages/{id}` 404 (509-512), page-comment 404 (540-546),
  ai_context anchor-collapse 400 (896-901). The only page-404 test covers a
  different endpoint.
- Fix: table-driven error-path tests per endpoint family (page, comment,
  link, ai_context, analytics).
- Effort: **M**.

**C34 — MED** *(source: QA §1.1 + Med 7)* — CLI coverage is invisible to
the coverage gate and several wiring branches are untested.

- cli.py reports 0% because all CLI tests run out-of-process
  (`subprocess.run`), which pytest-cov does not instrument. Untested
  branches: `products`/`phases` dispatch, `render` failure exit 1,
  `_resolve_database_url` non-sqlite rejection, `import` unreadable file,
  parser/no-args/unknown-command paths.
- Fix: in-process `build_parser()` + `main(argv)` tests; optionally
  `COVERAGE_PROCESS_START` + `parallel=true` for subprocess measurement.
- Effort: **M**.

**C35 — LOW** *(source: QA Low 9/10)* — Validator edge cases untested:
`model.py:100-106,141-143` (IDNA failure, >253 chars, RouteRule) and
`domain.py:98-113` (transition-validation edges).

- Effort: **S**.

**C36 — LOW** *(source: QA Low 11/12)* — `catalog.py:21-26,36` wheel
resource fallback only exercised by the (unmeasured) packaging probe;
`state_store_base.py:25-38` Protocol default stubs untested.

- Effort: **XS**.

### Dependencies & hygiene

**C37 — LOW** *(source: SEC F6)* — Floor-only `>=` pins; routine drift
behind latest (fastapi 0.136.1→0.141.1, starlette 1.0.0→1.3.1, etc.). No
known critical advisories; `uv.lock` committed so builds are reproducible.

- Fix: scheduled `uv lock --upgrade` + dependabot, or `==` pins for direct
  runtime deps.
- Effort: **S**.

**C38 — LOW** *(source: SEC F7)* — `.gitignore` lacks `.env` / `.env.*`
(no secret has ever been committed — hygiene only).

- Effort: **XS**.

---

## Prioritized fix backlog

Priority definitions: **P0** = fix now (real defect, small blast radius,
blocks nothing else) · **P1** = this sprint · **P2** = next sprint ·
**P3** = deferred with reason.

### P0 — fix now

| ID | Finding | Effort |
|---|---|---|
| C1 | Portability drops `visibility`/`members` — silent permission-state loss, `restricted` widens to `internal` | S |
| C15 | Mixed-case mention handles never resolve — silent notification loss | XS |

Both are small, self-contained correctness fixes with silent-failure
character; neither blocks any other work.

### P1 — this sprint

| ID | Finding | Effort |
|---|---|---|
| C21 | migration-guide CLI examples do not exist (rewrite to `export`/`import`/`--database-url`) | S |
| C22 | metrics-dashboard.md + CHANGELOG false metrics/telemetry claims | S |
| C32 | ai_context permission-filter + page-comment paths untested (security-adjacent) | S |
| C16 | `/v2/products` + `/v2/production-oss-phases` endpoints/CLI branches untested | S |
| C5 | Audit sink never wireable — add `--audit-log`/`INNERWORK_AUDIT_DB` | M |
| C11 | Markdown importer full-file read before size cap | S |
| C2 | JSON import no size cap; uncaught `RecursionError`/decode errors | S |
| C31 | No regression test for the `.worktrees` guardrail fix | S |
| C10 | Audit-sink query filter/limit tests | S |
| C13 + C14 | md importer import-wide `created_at` validation + frontmatter test | XS |
| C12 | Importer traceback errors mapped to `MarkdownImportError` | XS |
| C38 | `.gitignore` `.env` entry | XS |
| C23 | README broken archive links | XS |

### P2 — next sprint

| ID | Finding | Effort |
|---|---|---|
| C24 + C25 | roadmap/beta/post-launch `docs/governance.md` → `GOVERNANCE.md`; roadmap CLI names | XS |
| C27 | schema_version examples 3 → 4 (collaboration, comments-and-idempotency) | XS |
| C26 | Stale-state docs: overview, live-application, docker-poc | M |
| C33 | domain_api per-endpoint 404/400 table-driven tests | M |
| C34 | In-process CLI tests (products/phases/render-failure/parser) | M |
| C8 | Direct `/v1` reads bypass `can_read` — enforce or document | M |
| C6 | Per-call `actor_kind` in `_audit` | M |
| C7 | Extend `AUDIT_SURFACES` or document exclusions in threat model | S |
| C9 | Stale code refs (field_acl §3.4, JsonlAuditSink/backup.py, threat-model scope) | S |
| C4 | Portability audit-emission test (after C5) | S |
| C3 | String ids in synthetic fixture + regenerate JSON | XS |
| C19 | Broker idempotency validation-failure binds key | S |
| C17 | `x-request-id` on exception path | XS |
| C18 | UNIQUE-violation constraint-name matching | XS |

### P3 — deferred (with reason)

| ID | Finding | Reason |
|---|---|---|
| C20 | `truncated` flag sticky in ai_context | Cosmetic; greedy priority order is already correct, only the flag's meaning is loose. Decide semantics during C32 work. |
| C28 | runbook env-var table, stdout/stderr, typo | Cosmetic; no behavior change. Fold into a docs sweep. |
| C29 | docs/README archive note | Harmless historical framing by definition. |
| C30 | search.py docstring | Comment-only; fix alongside any search work. |
| C35 | model/domain validator edge tests | Modules already at 88-90% coverage; low leverage. |
| C36 | catalog wheel fallback + state_store_base stubs | One is covered behaviorally, the other is a default stub. |
| C37 | Floor-only pins / dependency drift | No known advisories; committed lockfile guarantees reproducibility. Schedule `uv lock --upgrade` as maintenance, not a fix. |

---

## Honesty verification (step 4 of the task)

The four audit PRs were spot-checked against the code — 5 findings across
the code/docs/qa/sec reports, including every source-HIGH in scope:

1. **C21 / DOCS H1 / CODE M3** — confirmed: `src/innerwork/cli.py:46-154`
   defines `catalog/products/phases/validate/render/serve/workflow/projects/
   project-create/work-items/.../export/import/migrate/metrics/
   import-markdown`; there is **no** `export-domain`/`import-domain`
   parser, and `docs/migration-guide.md:76-92` documents them with `--db`.
2. **C22 / DOCS H2+H3** — confirmed: `app.py:121-158` middleware records
   `http_requests_total`/`http_request_errors_total`/
   `http_request_duration_ms`; `app.py:172-182` serves `GET /metrics`;
   `CHANGELOG.md:39` says "no metrics endpoint exposed by the FastAPI
   app" — false.
3. **C1 / CODE M1** — confirmed: `portability.py:92-95` selects only
   `project_id, key, name, owner, created_at` (no `visibility`/`members`),
   and `:247-248` inserts the same 5 columns; `domain_store.py` defaults
   (`DEFAULT_VISIBILITY`) confirm the fallback.
4. **C15 / CODE M2** — confirmed: `notify.py:137` stores the handle
   verbatim as the dict key while `:63` (parse) and `:147,158` (lookup)
   lowercase.
5. **C11 / SEC F8** — confirmed: `markdown_importer.py:168` calls
   `path.read_text(...)` *before* the `_PAGE_BODY_MAX` check at `:170-173`.
6. **C32 / QA High 1+2** — confirmed: `ai_context.py:405-423` (per-kind
   permission filter) and `:509-522` (page-comment candidate collection)
   exist; `grep /v2/products tests/` and the QA coverage table show zero
   hits for those branches.
7. **C16 / QA High 3** — confirmed: `app.py:200,204` define
   `/v2/products` and `/v2/production-oss-phases`; `grep -rn "v2/products"
   tests/` → no hits.

No invented findings were found. Where a finding was "verified by
execution" in a source report, the code-level evidence was re-checked and
is consistent (e.g. the round-trip permission drop, the 40 MB read-before-
check, the 2000-deep JSON `RecursionError`, the uncaught `UnicodeDecodeError`).

**Baseline for fix tasks:** `uv run pytest -q` → **332 passed** (34.5 s,
re-run at consolidation time); `ruff` clean; `pyright` 0 errors. The four
audit reports (PRs #25, #27, #28, #29) are unchanged and open for review;
the consolidated report is the single source of truth for the fix backlog.
