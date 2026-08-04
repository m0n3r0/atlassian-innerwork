# Metrics Dashboard

Status: documentation of the metric surface exposed by `innerwork`
through Phase 10. This document describes what is observable today,
what is **not** observable, and how an operator can wire the available
data into their own dashboard.

`innerwork` does not ship a dashboard binary, a metrics server, or a
hosted analytics surface. It exposes a point-in-time JSON rollup that
operators can scrape from their own scheduler.

Companion documents:

- `docs/launch-plan.md`
- `docs/beta-program.md`
- `docs/migration-guide.md`
- `docs/roadmap.md`
- `docs/post-launch-iteration.md`

---

## 1. What is observable

The Phase-10 metric surface is the JSON document returned by
`innerwork.analytics.domain_rollup(store).to_dict()`. Phase 10 ships a
CLI wrapper that prints this document to stdout:

```sh
innerwork metrics --database-url sqlite:///path/to/store.sqlite3
```

The document shape is:

```json
{
  "project_count": 0,
  "space_count": 0,
  "work_item_count": 0,
  "page_count": 0,
  "work_items_by_state": { "todo": 0, "in_progress": 0, "done": 0 },
  "projects": [
    {
      "project_id": "...",
      "key": "...",
      "name": "...",
      "visibility": "...",
      "work_item_count": 0,
      "work_items_by_state": { "todo": 0, "in_progress": 0, "done": 0 },
      "comment_count": 0,
      "transition_count": 0
    }
  ],
  "spaces": [
    {
      "space_id": "...",
      "key": "...",
      "name": "...",
      "visibility": "...",
      "page_count": 0,
      "page_version_count": 0,
      "comment_count": 0
    }
  ]
}
```

Field meanings are documented in `src/innerwork/analytics.py`
(`DomainRollup`, `ProjectRollup`, `SpaceRollup`).

The `work_items_by_state` map is keyed by workflow state names from
`innerwork.workflow.WORKFLOW_STATES`; keys for unused states are
present with value `0` rather than omitted.

---

## 2. What is NOT observable

These are deliberate omissions, not gaps the maintainers intend to
quietly fill:

- **No time series.** `domain_rollup` returns counters as of the moment
  the call ran. For interval-based deltas, use the optional time-windowed
  mode instead (§4 below); for arbitrary point-in-time history, capture
  snapshots yourself (see §5 below).
- **No request-level telemetry.** `innerwork` does not record HTTP
  request counts, latencies, error rates, or any user-agent data.
- **No user identifiers in the rollup.** The rollup is intentionally
  populated with object counts and state distributions, not actor
  attribution.
- **No remote shipping.** Nothing in `innerwork` sends metrics to a
  third-party service. The data stays on the operator's machine until
  the operator chooses to move it.
- **No process / runtime metrics.** No CPU, memory, GC, or open-file
  counters. Operators who need those should use the standard tools
  for their runtime (e.g. `psutil`, systemd, Prometheus node exporter).
- **No audit-log surfacing in the rollup.** The append-only audit log
  is queryable directly through the domain store but is not summarised
  in `domain_rollup`. Surfacing it is on the
  `docs/roadmap.md` directional list, not committed.

---

## 3. Permissioned views

`domain_rollup(store, principal=<Principal>)` filters the per-project
and per-space lists to entries the principal can read. When called
without a principal (the default), every project and space is included.
The CLI wrapper calls without a principal — operators are expected to
restrict access to the database file itself rather than relying on
in-process filtering.

If an operator needs a per-principal rollup, they must call the Python
API directly; the Phase-10 CLI does not accept a principal argument.

---

## 4. Time-windowed mode

`innerwork metrics` accepts two optional flags that append an additive
top-level `"window"` object to the point-in-time rollup:

```sh
innerwork metrics --database-url sqlite:///path/to/store.sqlite3 \
  --window-start 2024-01-03T00:00:00Z --window-end 2024-01-05T00:00:00Z
```

Both flags are ISO-8601 timestamps and **must carry an explicit UTC
offset** (`Z` or `±HH:MM`); naive values are rejected. `--window-start`
is the inclusive lower bound, `--window-end` the exclusive upper bound
— the window is the half-open interval `[start, end)`: an event exactly
at `start` counts, an event exactly at `end` does not. Either flag alone
is unbounded on the other side, and the emitted `"window"` object echoes
the normalized bounds (`null` for an omitted bound). When neither flag
is given the output is byte-identical to the point-in-time rollup today:
no `"window"` key, no timestamp parsing.

The windowed aggregations are **activity over the window** (deltas), the
thing the point-in-time counters cannot express, and they respect the
same permission model as the rollup (§3):

- `state_counts` — transitions **into** each state during the window,
  with every workflow-state key present (0 for unused states).
- `cycle_time_per_project` — for transitions into `done` in the window,
  per readable project: `completed_count` plus `cycle_time_avg/min/max`
  in seconds (`null` when `completed_count` is 0). Every readable project
  is listed.
- `page_writes` — from `page_versions`: `total_versions` created in the
  window, `pages_touched` (distinct pages), and `by_space` with every
  readable space key present (0 when idle).
- `contributors` — distinct actors across comments, page versions, and
  transitions: `distinct` plus `by_actor` (sorted by actor name).

A window with no activity returns explicit zeros / empty objects / null
stats — never an error and never invented data. Invalid windows
(`end <= start`), malformed or naive bounds, and unparseable **stored**
timestamps (the windowed path parses every timestamp it reads) fail
loudly: `error: <message>` on stderr and exit 2, with empty stdout and
no partial JSON.

**Opt-in exception to the no-user-identifiers doctrine.** The point-in-time
rollup deliberately carries no user identifiers. `contributors.by_actor`
necessarily surfaces actor names — the same identifiers already stored in
the domain and exported by `export`. This exception applies **only** when
a window flag is passed (the default output keeps the doctrine intact),
and only for activity on projects/spaces the caller can read.

Example `"window"` object:

```json
{
  "window": {
    "start": "2024-01-03T00:00:00Z",
    "end": "2024-01-05T00:00:00Z",
    "state_counts": { "todo": 0, "in_progress": 1, "done": 2 },
    "cycle_time_per_project": [
      {
        "project_id": "pp",
        "key": "PROJ",
        "completed_count": 2,
        "cycle_time_avg_seconds": 203400.0,
        "cycle_time_min_seconds": 201600.0,
        "cycle_time_max_seconds": 205200.0
      }
    ],
    "page_writes": { "total_versions": 3, "pages_touched": 2, "by_space": { "SPACE": 3 } },
    "contributors": { "distinct": 2, "by_actor": { "alice@example.test": 4, "bob@example.test": 3 } }
  }
}
```

---

## 5. Wiring into an external dashboard

`innerwork` deliberately does not run a metrics endpoint. The
recommended pattern is to scrape the JSON from a scheduler the
operator already runs.

### Pattern A — cron + JSON file

```sh
# Every 5 minutes, capture a snapshot to a timestamped file.
*/5 * * * * innerwork metrics --database-url sqlite:///var/lib/innerwork/store.sqlite3 \
  > /var/log/innerwork/metrics-$(date -u +\%Y\%m\%dT\%H\%M).json
```

The JSON files are append-only and can be replayed offline. This is
the lowest-coupling pattern and the one the maintainers test against.

### Pattern B — Prometheus textfile collector

If the operator runs the Prometheus node exporter with the textfile
collector enabled, they can shape the JSON into Prometheus exposition
format with a short script of their own:

```sh
innerwork metrics --database-url sqlite:///var/lib/innerwork/store.sqlite3 \
  | <operator-supplied transform script> \
  > /var/lib/node_exporter/textfile/innerwork.prom
```

No transform script ships with `innerwork`. Documenting a
recommended shape is on the `docs/roadmap.md` "Quality and operability"
list.

### Pattern C — log aggregation

For operators who already ingest structured logs:

```sh
innerwork metrics --database-url sqlite:///var/lib/innerwork/store.sqlite3 \
  | jq -c '. + {"ts": now | todate, "source": "innerwork"}' \
  >> /var/log/innerwork/metrics.ndjson
```

The result is newline-delimited JSON suitable for the operator's
existing pipeline.

---

## 6. Validating the metric surface

The rollup is covered by the existing analytics tests
(`tests/test_analytics.py`) and indirectly exercised by the Phase-10
migration round-trip test (`tests/test_migration.py`), which imports
a synthetic fixture and asserts the resulting `domain_rollup`
matches the recorded baseline. The time-windowed mode is covered by
`tests/test_analytics_windowed.py` (hand-computed literals, boundary
and timezone semantics, zero-activity windows, permission filtering,
and the synthetic-fixture full-window oracle).

Operators who depend on rollup field stability should pin the
`schema_version` reported in the portability envelope and read
the CHANGELOG before upgrading. Field additions are not considered
breaking; field removals or renames will be called out explicitly.

---

## 7. What appears on the dashboard at launch

Per `docs/launch-plan.md`, the project itself does not run a public
dashboard. Phase-10 beta participants are expected to wire their own.
The maintainers' internal smoke check for the rollup is:

```sh
innerwork metrics --database-url sqlite:///<ephemeral-test-db> | jq '.project_count, .work_item_count, .page_count'
```

The expected output on a freshly-imported synthetic fixture is the
values recorded in `tests/test_migration.py`.

---

## 8. Cross-references

- `docs/launch-plan.md`
- `docs/beta-program.md`
- `docs/migration-guide.md`
- `docs/roadmap.md`
- `docs/post-launch-iteration.md`
- `src/innerwork/analytics.py`
- `tests/test_analytics.py`
- `tests/test_migration.py`
