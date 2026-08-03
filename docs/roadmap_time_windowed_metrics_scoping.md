# Roadmap item: time-windowed-metrics — optional time-windowed aggregations for `innerwork metrics` — PM scoping

**Status:** PM scoping (pre-implementation). Source: `docs/roadmap.md` → "Directional next" → Quality and operability (`slug=time-windowed-metrics`).
**Parent:** post-launch backlog item; no phase number. Implementation task `t_4faf0860` branches from `main` on `feat/time-windowed-metrics`.
**Audience:** the implementation worker (atlassianeng). Read this end-to-end before touching files.

---

## §0 Honest baseline (what the repo already has, today)

Verified against `main` at commit `302d9da` on 2026-08-04. The streaming-export feature (PR #41) is **already merged**; the metrics CLI surface is unchanged by it, so the windowed mode composes with the current `metrics` branch as it exists today.

| Asset | Present? | Path | Notes |
|---|---|---|---|
| Point-in-time rollup | ✅ | `src/innerwork/analytics.py` (258 lines) | `domain_rollup(store, *, principal=None)` → `DomainRollup` (dataclasses `ProjectRollup`, `SpaceRollup`, `DomainRollup`; `to_dict()` JSON-shaped). Counters are **as of the moment the call ran** — `project_count`, `space_count`, `work_item_count`, `page_count`, `work_items_by_state` (all `WORKFLOW_STATES` keys present, zeros for unused), plus per-project (`work_item_count`, `work_items_by_state`, `comment_count`, `transition_count`) and per-space (`page_count`, `page_version_count`, `comment_count`) entries. Deterministic: no clocks, no random IDs; projects/spaces sorted by key so snapshots are diff-friendly. |
| CLI wrapper | ✅ | `src/innerwork/cli.py:565-567` | `innerwork metrics [--database-url sqlite:///...] [--audit-log PATH]` prints `json.dumps(domain_rollup(store).to_dict(), indent=2, sort_keys=True)` to stdout. No timestamp flags exist today. |
| Timestamp sources in the store | ✅ | `src/innerwork/domain_store.py` | Every entity carries ISO-8601 timestamps, all settable on create via explicit overrides (used by the synthetic fixture): `projects.created_at`, `work_items.created_at` + `updated_at` (bumped on every transition), `work_item_transitions.occurred_at` (append-only log with `from_state`/`to_state`/`actor`), `spaces.created_at`, `pages.created_at` + `updated_at` (bumped on every update), `page_versions.created_at` (one row per write), `work_item_comments.created_at`, `page_comments.created_at`. `utc_now_iso()` emits `%Y-%m-%dT%H:%M:%SZ`; imported fixtures use `+00:00` offsets (e.g. `2024-01-03T09:00:00+00:00`). **Both forms — and any `±HH:MM` offset — must parse.** |
| Known-timestamp fixture | ✅ | `tests/fixtures/synthetic_migration.json` + `src/innerwork/migrators/synthetic_fixture.py` | Deterministic payload, all timestamps fixed in 2024-01, importable via `import_domain` (or `innerwork migrate --source synthetic`). Ideal oracle for hand-computed windowed values. |
| Analytics tests | ✅ | `tests/test_analytics.py` (238 lines, 12 tests) | Seeds a store via the `DomainStore` Python API (default wall-clock timestamps) and asserts counts, permission filtering (`principal=None` / `AnonymousPrincipal` / named principals), and JSON serializability. `tests/test_migration.py` additionally baselines the rollup shape against the synthetic fixture. **Both suites must stay green unchanged** — they are the backward-compatibility net. |
| Windowed aggregations | ❌ | n/a | No timestamp filtering anywhere in analytics; the roadmap bullet (`docs/roadmap.md:79-80`) is unimplemented: "Expand `innerwork metrics` output with optional time-windowed aggregations (currently the rollup is point-in-time only)." |

**Timestamp-format reality (important for the parser contract).** `utc_now_iso()` writes `...Z`; the synthetic fixture writes `...+00:00`; a caller may write anything non-empty. `datetime.fromisoformat` on Python 3.10 does **not** accept a trailing `Z` (it does on 3.11+), and the project supports `>=3.10` (`pyproject.toml`), so the parser **must normalize `Z` → `+00:00` before parsing** — stdlib only, no new dependency. Stored values may be naive (treated as UTC, documented) or offset-aware (compared in UTC).

**Implication.** A contained, additive slice with **no wire-format change and no change to the default output**: two new optional CLI flags (`--window-start`, `--window-end`) that, when present, append a top-level `"window"` object to the existing JSON rollup; when absent, the `metrics` branch is byte-for-byte the code path that runs today. New windowed rollup logic lives in `analytics.py` behind new functions; `domain_rollup` / `project_rollup` / `space_rollup` stay untouched.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `docs/roadmap_time_windowed_metrics_scoping.md` | (this file) | n/a | Exists at PM-scoping time. Implementation worker does not modify. |
| 2 | `src/innerwork/analytics.py` | **edit** | +~150 lines | The core change: `parse_window_bound` (or equivalent private helper), `DomainWindowMetrics` dataclass(es), `windowed_domain_rollup(store, *, window_start=None, window_end=None, principal=None)`, and private windowed-aggregation helpers (§3). `domain_rollup`, `project_rollup`, `space_rollup`, and the existing dataclasses stay **unchanged**. |
| 3 | `src/innerwork/cli.py` | **edit** | +~20/−5 lines | The `metrics` subcommand gains `--window-start` and `--window-end`; the `metrics` branch (`cli.py:565-567`) parses them and calls `windowed_domain_rollup` when either is given, else the existing `domain_rollup` call verbatim. `AnalyticsError` (invalid flag value, `end <= start`, unparseable stored timestamp) → stderr + exit 2. See §2. |
| 4 | `tests/test_analytics_windowed.py` | **new** | ~300 lines | Windowed-mode tests per §6: hand-computed oracle fixture, byte-identity of the default path, boundary/timezone semantics, zero-activity windows, permission filtering, flag validation, CLI help, synthetic-fixture smoke windows. |
| 5 | `docs/metrics-dashboard.md` | **edit** | +~35 lines | New section describing the windowed mode (shape, semantics, boundaries, permission note, the opt-in exception to the "no user identifiers in the rollup" doctrine); amend §2's "No time series" bullet to point at the windowed mode. While editing, correct the pre-existing `--db` → `--database-url` flag name in the section touched (the doc's examples use the wrong flag name; the real flag is `--database-url`). |
| 6 | `CHANGELOG.md` | **edit** | +~8 lines | Under `[Unreleased]`, a `### Added — Time-windowed metrics` subsection: new flags, additive `"window"` object, `[start, end)` semantics, zero-activity behavior, backward-compatibility guarantee, tests. No version bump, no new dependency. |
| 7 | `docs/roadmap.md` | **edit (optional, recommended)** | −2/+3 lines | After the implementation PR merges, move the "Expand `innerwork metrics` output with optional time-windowed aggregations…" bullet from "Directional next → Quality and operability" into the "Shipped through Phase 10" list as a post-phase-10 addition. Same PR, tiny diff. |

**Files that LOOK like they should be touched but MUST NOT be touched.**

| Path | Why not |
|---|---|
| `src/innerwork/domain_store.py` | The windowed helpers read via `store._connect()` with parameterized SQL (same private cursor API the streaming writer used). **No new `DomainStore` public API**, no schema change, no migration. The store's existing `create_*` methods already accept explicit `created_at`/`occurred_at` overrides, so the test fixture needs no store changes. |
| `src/innerwork/domain.py`, `comments.py`, `permissions.py`, `audit.py`, `portability.py` | Unchanged. Windowed mode is analytics-only; the permission model is *consumed* (same `can_read` / principal gating as `domain_rollup`), not modified. |
| `tests/test_analytics.py`, `tests/test_migration.py`, `tests/fixtures/*` | Existing suites and fixtures stay untouched and must stay green — they are the backward-compatibility net (default output must be byte-identical). New suite lives in `tests/test_analytics_windowed.py`. The synthetic fixture is **read** (imported) by the new suite as an oracle, never modified. |
| `pyproject.toml`, `.github/workflows/*` | No new dependency (stdlib `datetime` suffices; `fromisoformat` + `timedelta` are all that is needed), no CI change. |
| `src/innerwork/portability.py` | The portability envelope is unchanged; windowed metrics are a read-only CLI/analytics surface and must not leak into export format decisions. |

---

## §2 CLI surface (locked)

Two new optional flags on the existing `metrics` subcommand; the command line is otherwise identical to today:

```
innerwork metrics [--database-url sqlite:///...] [--audit-log PATH] [--window-start ISO-8601] [--window-end ISO-8601]
```

1. **`--window-start`** — ISO-8601 timestamp with an explicit UTC offset (`Z` or `±HH:MM`, e.g. `2024-01-03T00:00:00Z` or `2024-01-03T09:00:00+09:00`). Inclusive lower bound. **Naive timestamps (no offset) are rejected** with an `AnalyticsError` → stderr + exit 2 — silently assuming a zone for a user-supplied bound would be a footgun, and the repo's own timestamps are always UTC-aware (`Z` or `+00:00`).
2. **`--window-end`** — same format. Exclusive upper bound. Naive timestamps rejected for the same reason.
3. **Defaults.** Neither flag given → the `metrics` branch calls `domain_rollup(store).to_dict()` exactly as today: **byte-identical output**, no `"window"` key. `--window-start` alone → window is `[start, +∞)`. `--window-end` alone → window is `(−∞, end)`. Both given → `[start, end)`.
4. **Flag validation (SEC gate).** `end <= start` (after parsing and UTC normalization) → `AnalyticsError` → stderr + exit 2, nothing printed. Unparseable flag value → `AnalyticsError` → stderr + exit 2, nothing printed, no traceback in normal operation. There is **no duration-style flag** (no `--window-hours`, no relative windows) — the roadmap names time-windowed aggregations over absolute bounds, and absolute bounds are the honest, deterministic choice for a tool whose fixtures are fixed-in-time.
5. **Output shape.** With window flags, output is the current point-in-time rollup **plus** a new top-level `"window"` object (shape in §3.1). Additive by design: `jq '.project_count'`-style consumers keep working in both modes, and windowed consumers read `.window`. The point-in-time rollup in the same document is **not** recomputed over the window — it stays "as of now", exactly as today. (The windowed aggregations live in `.window` with their own names; see §3.)
6. **Errors.** `AnalyticsError` from the windowed path (invalid flag, `end <= start`, unparseable **stored** timestamp — §3.4) → `error: <message>` on stderr, exit 2, empty stdout. This matches the `DomainImportError` → exit 2 convention used by `export`/`import`/`import-csv`/`import-markdown`. The windowed path must never emit partial JSON: the rollup is computed fully before `_print_json` is called.
7. **Interaction with `--audit-log`.** Unchanged — `--audit-log`/`INNERWORK_AUDIT_DB` wires the audit sink for write-side events; `metrics` is read-only and does not consult the audit sink. No interaction.

`--help` output for `metrics` documents both new flags (acceptance criterion).

---

## §3 Rollup contract (locked)

### 3.1 Window bounds semantics (the closed/open definition)

- A window is a half-open interval **`[start, end)`**: a timestamp `t` is inside iff `start <= t < end`.
- `start` is inclusive; `end` is exclusive. Locked and tested at both edges (event exactly at `start` counts; event exactly at `end` does not).
- When a bound is omitted it is **unbounded** on that side: `--window-start` alone → `[start, ∞)`; `--window-end` alone → `(−∞, end)`.
- All comparisons happen in **UTC** after normalization. A stored naive timestamp is interpreted as UTC (documented; the repo's writers always emit UTC-aware values, so this only affects hand-crafted data). Fractional seconds compare exactly (an event at `...00:00:00.500Z` is inside a window starting `...00:00:00Z`).
- The emitted `"window"` object echoes the **normalized** bounds (`null` for an omitted bound) so every snapshot is self-describing and diff-friendly: `"start": "2024-01-03T00:00:00Z"`, `"end": "2024-01-05T00:00:00Z"`.

### 3.2 Windowed aggregations (exactly the four the roadmap names)

All four are **activity-over-window** (deltas), which is precisely what the point-in-time rollup cannot express. Each aggregation is computed only over rows whose event timestamp is inside the window, restricted to readable projects/spaces per §4.

1. **`state_counts`** — transitions **into** each state during the window. For every `work_item_transitions` row with `occurred_at` in the window, increment `state_counts[to_state]`. All `WORKFLOW_STATES` keys are always present (0 for unused states), mirroring the existing `work_items_by_state` convention. Activity semantics: an item moving `todo → in_progress → done` inside the window contributes 1 to `in_progress` and 1 to `done` — this counts workflow **motion**, not board occupancy, and it is what the transition log can answer exactly. Reopened items re-entering a state count again on each entry (it is activity, not unique items).
2. **`cycle_time_per_project`** — for every transition **into `done`** with `occurred_at` in the window, per item: `cycle_time = (occurred_at − work_items.created_at).total_seconds()` (float seconds). Per readable project: `completed_count` (number of such transitions), `cycle_time_avg_seconds` (`sum/count`; `null` when count 0), `cycle_time_min_seconds` / `cycle_time_max_seconds` (`null` when count 0). One entry **per readable project**, sorted by project key (consistent with the existing `projects` list). Negative cycle times are mathematically possible only when a fixture/import places a `done` transition before `created_at`; they are **surfaced as-is, never clamped and never silently dropped** — clamping or dropping would be invented data.
3. **`page_writes`** — page-write activity and recency within the window, from `page_versions.created_at` (one row per page write, append-only): `total_versions` (all versions created in window), `pages_touched` (distinct `page_id` with ≥ 1 version in the window — "how many pages were written"), `by_space` (per readable space key: versions created in window; **every** readable space key present with 0 when idle).
4. **`contributors`** — distinct authors of activity in the window, across the four activity sources that carry an actor: `work_item_comments.author`, `page_comments.author`, `page_versions.author`, `work_item_transitions.actor`. `distinct` = number of distinct actors; `by_actor` = `{actor: event_count}` (an event is one comment, one page version, or one transition; a single page version is one event, not one event per page). Sorted by actor name for diff-friendly output. Only events attached to **readable** projects/spaces count (§4).

### 3.3 `"window"` object shape (locked)

```json
{
  ...existing point-in-time rollup keys, unchanged...,
  "window": {
    "start": "2024-01-03T00:00:00Z",
    "end": "2024-01-05T00:00:00Z",
    "state_counts": { "todo": 0, "in_progress": 1, "done": 2 },
    "cycle_time_per_project": [
      {
        "project_id": "pp",
        "key": "PROJ",
        "completed_count": 2,
        "cycle_time_avg_seconds": 86400.0,
        "cycle_time_min_seconds": 43200.0,
        "cycle_time_max_seconds": 129600.0
      }
    ],
    "page_writes": {
      "total_versions": 3,
      "pages_touched": 2,
      "by_space": { "SPACE": 3 }
    },
    "contributors": {
      "distinct": 2,
      "by_actor": { "alice@example.test": 3, "bob@example.test": 2 }
    }
  }
}
```

Key insertion order within `"window"`: `start`, `end`, `state_counts`, `cycle_time_per_project`, `page_writes`, `contributors` (fixed, so serialization is stable). Top-level keys keep today's order (`_print_json` uses `sort_keys=True` anyway). Cycles-times are JSON floats; `avg/min/max` are `null` when `completed_count == 0`.

**Zero-activity windows produce explicit empty/zero results, never errors and never invented data:** `state_counts` all zeros; every readable project listed with `completed_count: 0` and null stats; `page_writes` all zeros with every readable space key at 0; `contributors` `{distinct: 0, by_actor: {}}`.

### 3.4 Data access and parse contract (implementation guidance)

- New private helpers in `analytics.py` read via `store._connect()` with **parameterized** SQL (`?` binds). Window bounds are parsed to `datetime` objects **before** any query; the parsed values are the only things ever bound. No string interpolation of flag input anywhere (SEC gate: no injection surface).
- Time parsing helper (stdlib only): normalize a trailing `Z` to `+00:00`, then `datetime.fromisoformat` (handles `±HH:MM` offsets and fractional seconds). Reject naive **flag** values (require an offset). Store **values** that fail to parse → `AnalyticsError` naming the table and the offending value, e.g. `error: unparseable created_at in work_items: '2024-13-99T00:00:00Z'` → exit 2. Loud over silent: silently skipping an unparseable row would undercount and produce invented-looking numbers, which the anti-hallucination rule forbids. The default (non-windowed) path never parses timestamps and is unaffected by store data quirks.
- Queries needed (reference tables): `work_item_transitions` (`occurred_at`, `to_state`, `actor`, `work_item_id`), joined to `work_items` (`project_id`, `created_at`) for cycle time and project scoping; `page_versions` (`created_at`, `author`, `page_id`) joined to `pages` (`space_id`) for page writes and space scoping; `work_item_comments` / `page_comments` (`created_at`, `author`) for contributor events. Permissions filter the same way `domain_rollup` does today: a project/space the principal cannot read contributes **nothing** to any windowed counter (see §4).
- `windowed_domain_rollup(store, *, window_start=None, window_end=None, principal=None)` returns a dataclass whose `to_dict()` produces the `"window"` object. Add it (and the helper dataclasses) to `__all__`.

---

## §4 Permission model (locked)

Windowed mode reuses the existing permission model verbatim — no new rules, no new exposure:

- `windowed_domain_rollup(..., principal=<Principal>)` applies the same `can_read(principal, visibility=..., members=...)` gate as `domain_rollup`. A restricted project/space a principal cannot read contributes nothing: its transitions are absent from `state_counts` and `contributors`, its completed items are absent from `cycle_time_per_project`, its page versions are absent from `page_writes`. The CLI calls without a principal (exactly as today — operators restrict access to the database file itself).
- **`by_space` includes every readable space and `cycle_time_per_project` includes every readable project** even when their windowed values are zero — the same "all keys present" convention as `work_items_by_state`, so a zero is distinguishable from an elided row. Unreadable ones are absent entirely, same as today's `projects`/`spaces` lists.
- **Doctrine change, documented (§5 and metrics-dashboard.md):** the existing rollup deliberately carries **no user identifiers** ("No user identifiers in the rollup", `docs/metrics-dashboard.md` §2). The windowed `contributors.by_actor` necessarily surfaces actor names. This is an **opt-in** exception: it only appears when a window flag is passed, and the actors are the same identifiers already stored in the domain and already present in portability exports. The default output keeps the doctrine intact.

---

## §5 Honest gap calls (decide-and-document, locked for v1)

| Topic | Decision | Rationale |
|---|---|---|
| Window bounds | Half-open `[start, end)`, UTC-normalized, bounds echoed normalized in the output. | The anti-hallucination rule demands a precisely defined and tested closed/open definition; half-open intervals compose (`[a,b) ∪ [b,c)`) and make boundary tests deterministic. |
| "State counts over window" meaning | **Transitions into each state** during the window (activity), not board occupancy at window end. | The transition log answers activity exactly; a "state at window end" is itself a point-in-time snapshot at a different clock, which is a different feature (time-travel rollup) and is **not** in this slice. |
| Point-in-time rollup in windowed output | **Unchanged and always present**; windowed values live in `.window` with their own names. | Additive output keeps every existing consumer (`jq '.project_count'`, dashboard recipes) working in both modes; replacing the top-level counters would change the meaning of stable keys. |
| Relative windows / duration flags | **No** `--since`, `--window-hours`, etc. Absolute ISO bounds only. | The repo's fixtures are fixed-in-time; absolute bounds are deterministic and unambiguous. A relative-window flag is a trivial future addition if beta feedback asks for it. |
| Unparseable **stored** timestamps | `AnalyticsError` naming table + value → exit 2, empty stdout. | Silent skipping undercounts (invented-looking data); crashing is worse. Loud failure on the windowed path is the honest middle; the default path never parses timestamps and is unaffected. |
| Naive **flag** timestamps | Rejected (must carry `Z` or `±HH:MM`). | Assuming a timezone for a user-supplied bound is a footgun; every repo writer emits UTC-aware values, so requiring offsets is consistent and cheap. |
| Negative cycle times | Surfaced as-is, never clamped/dropped. | Clamping or dropping would be invented data. Negative values can only arise from inconsistent fixture timestamps and should be visible to the operator. |
| Contributor actor names | Included in `contributors.by_actor`, opt-in only, permission-gated; doctrine change documented in metrics-dashboard.md. | The roadmap names "contributor counts"; a count without attribution is much less useful. Security gate is about not bypassing the permission model — which we do not. |
| Time-travel snapshots ("state at window end") | **Not in this slice.** Documented as a possible follow-up. | Roadmap names four deltas; a full historical-state reconstruction needs transition-log replay logic and its own tests. Scope discipline. |
| `created`-in-window counters (projects/spaces/work items/pages created during window) | **Not in this slice.** | The four named rollups are all computable from the transition/version/comment logs without new counters; adding more inflates the surface. Follow-up if beta feedback asks. |
| Docs fix | Correct the pre-existing `--db` → `--database-url` flag name in the metrics-dashboard section touched. | The doc's examples have used the wrong flag name since before this slice; fixing it in the section we edit is a two-word honest correction, not scope creep. |

---

## §6 Test plan

Primary oracle: a **new minimal fixture** seeded inside the test file via the existing `DomainStore` API with **explicit timestamps on every object** (all `create_*` methods accept `created_at`/`occurred_at` overrides — verified for projects, work items, transitions, spaces, pages, page versions, and both comment types; no store changes needed). The expected values are hand-computed from those timestamps and written as literals with the arithmetic in a comment. Secondary oracle: the existing synthetic fixture (all timestamps fixed in 2024-01), imported via `build_synthetic_fixture()` + `import_domain`, with expected values derived by counting rows in `tests/fixtures/synthetic_migration.json` at implementation time (a deterministic fixture — the counts are countable by hand from the JSON).

| Test | Asserts |
|---|---|
| `test_default_output_byte_identical` | Store seeded → `_run_cli("metrics", "--database-url", url)` (or `domain_rollup(store).to_dict()`) has **no** `"window"` key and equals today's output exactly. Plus: `tests/test_analytics.py` and `tests/test_migration.py` pass **unmodified** — the regression net. |
| `test_windowed_state_counts_hand_computed` | Minimal fixture with known transitions (e.g. 2 transitions into `done`, 1 into `in_progress`, 0 into `todo` inside `[2024-01-03T00:00:00Z, 2024-01-05T00:00:00Z)`) → `state_counts` matches literals; all three keys present. |
| `test_windowed_cycle_time_hand_computed` | Items completed in the window with known `created_at`/done-`occurred_at` gaps (e.g. 2 items: 86400 s and 43200 s) → `cycle_time_avg_seconds == 64800.0`, min/max match; a project with no completions has `completed_count 0` and null stats. |
| `test_windowed_page_writes_hand_computed` | Known page versions in the window across 2 spaces → `total_versions`, `pages_touched`, `by_space` match literals; every readable space key present (0 when idle). |
| `test_windowed_contributors_hand_computed` | Known comment/page-version/transition authors in the window → `distinct` and `by_actor` match literals; events outside the window and events in unreadable projects/spaces excluded. |
| `test_synthetic_fixture_full_window` | Import synthetic fixture → window `[2024-01-01T00:00:00+00:00, 2024-02-01T00:00:00+00:00)` → `state_counts` equals the countable transitions-by-`to_state` in the fixture JSON; cycle-time avg equals the hand-computed mean over the fixture's done-transitions. End-to-end oracle on the repo's canonical fixture. |
| `test_zero_activity_window` | Window over a period with no events → all zeros / empty dicts / null stats; **no error**; `exit 0`. |
| `test_boundary_start_inclusive_end_exclusive` | Event exactly at `start` counted; event exactly at `end` **not** counted (two events placed exactly on the bounds). |
| `test_partial_windows` | `--window-start` alone includes everything at/after it; `--window-end` alone includes everything before it; echoed `start`/`end` show `null` for the omitted bound. |
| `test_timezone_equivalence` | A window given as `2024-01-03T09:00:00+09:00` selects the same events as `2024-01-03T00:00:00Z`; stored `Z`-suffixed and `+00:00` timestamps are treated identically. |
| `test_naive_stored_timestamp_treated_as_utc` | A stored naive `2024-01-03T00:00:00` is inside a window starting `2024-01-03T00:00:00Z`. |
| `test_flag_validation_errors` | `end <= start` → exit 2, `error:` on stderr, empty stdout; malformed date (`not-a-date`, `2024-13-99T00:00:00Z`, naive `2024-01-03T00:00:00`) → exit 2 each, no traceback in normal operation, no partial JSON. |
| `test_unparseable_stored_timestamp_loud` | Store a work item with `created_at="garbage"` → windowed query raises `AnalyticsError` naming the table/value (CLI: exit 2, empty stdout); **default** metrics query still succeeds (no timestamp parsing on the default path). |
| `test_permission_filtering` | Restricted project/space with in-window activity → `windowed_domain_rollup(store, principal=AnonymousPrincipal)` excludes it from `state_counts`, `cycle_time_per_project`, `page_writes.by_space`, and `contributors`; named member principal sees it. |
| `test_cli_help_documents_flags` | `innerwork metrics --help` contains `--window-start` and `--window-end` with descriptions. |
| `test_deterministic_two_runs` | Two windowed rollups on the same store → identical JSON (stable ordering, no clocks). |
| `test_no_new_dependencies` | `grep -RInE "import (dateutil|pandas|numpy|pendulum|arrow)" src/innerwork/analytics.py` returns nothing (stdlib `datetime` only). |

---

## §7 Anti-hallucination checklist

Implementation worker MUST run each check and quote the (empty / verified) output in the PR description.

| Check | Command |
|---|---|
| No compliance/measurement claims | `uv run python scripts/check_anti_hallucination.py` exits 0. |
| No fabricated numbers in docs/tests | `grep -RInE "[0-9]+\.[0-9]+\s*(s|sec|ms)|avg.*=.*[0-9]" docs/metrics-dashboard.md CHANGELOG.md` returns nothing but the hand-computed literals inside `tests/test_analytics_windowed.py` (every literal there must carry the arithmetic in a comment). |
| No new dependency / no network | `grep -RInE "httpx|requests|urllib|socket|http://|https://" src/innerwork/analytics.py` returns nothing; imports stay stdlib (`datetime`, `collections`) + local modules. |
| No string-interpolated SQL | `grep -nE "f['\"].*SELECT|%\\s*\\(|\.format\(" src/innerwork/analytics.py` returns nothing; all window bounds bound as `?` parameters. |
| Default path untouched | `git diff main -- src/innerwork/analytics.py` shows no change to `domain_rollup`/`project_rollup`/`space_rollup` bodies; `git diff main -- src/innerwork/cli.py` shows the `metrics` branch still calls `domain_rollup(store).to_dict()` when no window flags are present. |
| Store/portability untouched | `git diff main -- src/innerwork/domain_store.py src/innerwork/domain.py src/innerwork/comments.py src/innerwork/permissions.py src/innerwork/portability.py` is empty. |
| Files-touched boundary | `git diff --stat main` shows exactly: `src/innerwork/analytics.py`, `src/innerwork/cli.py`, `tests/test_analytics_windowed.py`, `docs/metrics-dashboard.md`, `CHANGELOG.md`, optional `docs/roadmap.md`. Nothing else. |
| Existing suites green unchanged | `git diff main -- tests/test_analytics.py tests/test_migration.py tests/fixtures/synthetic_migration.json` is empty and both suites pass. |

---

## §8 Acceptance gates (must hold before opening PR)

| Gate | Verification |
|---|---|
| Backward compatibility | `test_default_output_byte_identical` passes; `tests/test_analytics.py` + `tests/test_migration.py` pass **unmodified** — `innerwork metrics` with no window flags is byte-identical to current behavior. |
| Correct windowed aggregations | `test_windowed_*_hand_computed` and `test_synthetic_fixture_full_window` pass — windowed values match hand-computed arithmetic on fixtures with known timestamps. |
| Zero-activity windows | `test_zero_activity_window` passes: explicit zeros/empty/null, exit 0, no errors, no invented data. |
| Boundary semantics | `test_boundary_start_inclusive_end_exclusive` passes — `[start, end)` locked and proven at both edges. |
| Timezone handling | `test_timezone_equivalence` + `test_naive_stored_timestamp_treated_as_utc` pass — UTC normalization, `Z`/`+00:00` equivalence, naive-flag rejection. |
| Flag validation (SEC) | `test_flag_validation_errors` + `test_unparseable_stored_timestamp_loud` pass — negative/inverted windows and malformed dates exit 2 with no crash, no traceback in normal operation, no partial JSON, no injection surface (parameterized SQL only). |
| Permission model | `test_permission_filtering` passes — windowed queries respect the existing permission model; no new data exposure beyond the documented opt-in contributor names. |
| CLI help | `test_cli_help_documents_flags` passes — `--window-start`/`--window-end` documented in `innerwork metrics --help`. |
| Docs | `docs/metrics-dashboard.md` describes the windowed mode and the doctrine exception; CHANGELOG `[Unreleased]` gains the `### Added — Time-windowed metrics` entry; no compliance claims. |
| Full CI parity | `uv run pytest -x`, `uv run ruff check .`, `uv run pyright` all clean — exactly what `.github/workflows/ci.yml` runs. **Never push a branch with red pyright** (2026-05-29 phase-7 incident). |

---

## §9 Exit criteria (done definition for the implementation task)

Per the roadmap item and child task `t_4faf0860`:

1. `innerwork metrics` with **no** window flags produces byte-identical output to today (existing suites green unchanged; new byte-identity test).
2. `--window-start` / `--window-end` (ISO-8601, offset-required) produce correct, hand-computed aggregations over a fixture with known timestamps: `state_counts` (transitions into each state in `[start, end)`), `cycle_time_per_project` (done-transition cycle times), `page_writes` (versions/touched/by_space), `contributors` (distinct/by_actor) — all permission-gated.
3. Zero-activity windows return explicit zeros/empty/null with exit 0 — never an error and never invented data.
4. Window bounds are precisely `[start, end)` (start inclusive, end exclusive), UTC-normalized, echoed normalized in the output, and proven by boundary tests; partial windows (one flag) work and echo `null` for the omitted bound.
5. Flag validation is safe: inverted (`end <= start`) and malformed/naive dates exit 2 with a clear stderr message, empty stdout, no crash, no partial JSON; windowed queries use parameterized SQL only; no new dependencies.
6. Windowed queries respect the existing permission model (same `can_read` gating as `domain_rollup`); the opt-in contributor-actor-names exception is documented in `docs/metrics-dashboard.md`.
7. `innerwork metrics --help` documents both flags.
8. `docs/metrics-dashboard.md` updated with the windowed mode; CHANGELOG `[Unreleased]` gains `### Added — Time-windowed metrics`; no compliance claims, no fabricated numbers.
9. `uv run pytest -x && uv run ruff check . && uv run pyright` all green before push.
10. PR opened against `main` on `feat/time-windowed-metrics`, **DO NOT MERGE** — end with `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")` per the child task's mandate.

---

## §10 Handoff checklist for the implementation worker (atlassianeng)

1. Branch from `main` at the current HEAD: `git checkout -b feat/time-windowed-metrics` (child task `t_4faf0860` pins this branch name; worktree workspace at `/home/eml/atlassian/atlassian-innerwork`).
2. Write files in §1 order. The scoping doc (this file) is not modified.
3. Implement in `analytics.py`: time-parsing helper (`Z` → `+00:00` normalization, naive-flag rejection, `AnalyticsError` on unparseable stored values), `DomainWindowMetrics` dataclass(es) with `to_dict()` per §3.3, `windowed_domain_rollup(store, *, window_start=None, window_end=None, principal=None)`, private windowed helpers reading via `store._connect()` parameterized SQL (§3.4). Add to `__all__`. Do **not** touch `domain_rollup` / `project_rollup` / `space_rollup`.
4. Refactor the CLI `metrics` branch per §2: add `--window-start`/`--window-end` to `metrics_cmd` with the §2 help text; when either is given, parse → `windowed_domain_rollup` → print the point-in-time rollup dict **with** the `"window"` object appended; `AnalyticsError` → `error: <msg>` stderr + exit 2, empty stdout; no flags → existing `domain_rollup(store).to_dict()` call unchanged.
5. Add `tests/test_analytics_windowed.py` per §6, including the hand-computed literal fixture (with the arithmetic in comments), the byte-identity test, the synthetic-fixture full-window oracle, zero-activity, boundary, timezone, validation, permission, help, determinism, and no-new-dependency tests.
6. Update `docs/metrics-dashboard.md` (windowed mode section + §2 "No time series" amendment + `--db` → `--database-url` fix in the section touched) and add the CHANGELOG entry; optionally move the roadmap bullet (§1 row 7).
7. Run the CI-parity gate exactly as GitHub Actions does: `uv run pytest -x`, `uv run ruff check .`, `uv run pyright`. **All three must be green before push.**
8. Run the §7 grep checks and quote results in the PR body.
9. Push via SSH remote (`git@github-personal:m0n3r0/atlassian-innerwork.git`), open PR titled `feat(analytics): optional time-windowed aggregations for innerwork metrics (--window-start/--window-end)` against `main`. **DO NOT MERGE.**
10. `kanban_block(reason="qa-required: PR #<num> (<title>) opened; local pytest+ruff+pyright all green")`.
