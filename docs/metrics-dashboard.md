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
innerwork metrics --db path/to/store.sqlite3
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
  the call ran. If an operator wants a time series, they must capture
  snapshots themselves (see §4 below).
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

## 4. Wiring into an external dashboard

`innerwork` deliberately does not run a metrics endpoint. The
recommended pattern is to scrape the JSON from a scheduler the
operator already runs.

### Pattern A — cron + JSON file

```sh
# Every 5 minutes, capture a snapshot to a timestamped file.
*/5 * * * * innerwork metrics --db /var/lib/innerwork/store.sqlite3 \
  > /var/log/innerwork/metrics-$(date -u +\%Y\%m\%dT\%H\%M).json
```

The JSON files are append-only and can be replayed offline. This is
the lowest-coupling pattern and the one the maintainers test against.

### Pattern B — Prometheus textfile collector

If the operator runs the Prometheus node exporter with the textfile
collector enabled, they can shape the JSON into Prometheus exposition
format with a short script of their own:

```sh
innerwork metrics --db /var/lib/innerwork/store.sqlite3 \
  | <operator-supplied transform script> \
  > /var/lib/node_exporter/textfile/innerwork.prom
```

No transform script ships with `innerwork`. Documenting a
recommended shape is on the `docs/roadmap.md` "Quality and operability"
list.

### Pattern C — log aggregation

For operators who already ingest structured logs:

```sh
innerwork metrics --db /var/lib/innerwork/store.sqlite3 \
  | jq -c '. + {"ts": now | todate, "source": "innerwork"}' \
  >> /var/log/innerwork/metrics.ndjson
```

The result is newline-delimited JSON suitable for the operator's
existing pipeline.

---

## 5. Validating the metric surface

The rollup is covered by the existing analytics tests
(`tests/test_analytics.py`) and indirectly exercised by the Phase-10
migration round-trip test (`tests/test_migration.py`), which imports
a synthetic fixture and asserts the resulting `domain_rollup`
matches the recorded baseline.

Operators who depend on rollup field stability should pin the
`schema_version` reported in the portability envelope and read
the CHANGELOG before upgrading. Field additions are not considered
breaking; field removals or renames will be called out explicitly.

---

## 6. What appears on the dashboard at launch

Per `docs/launch-plan.md`, the project itself does not run a public
dashboard. Phase-10 beta participants are expected to wire their own.
The maintainers' internal smoke check for the rollup is:

```sh
innerwork metrics --db <ephemeral-test-db> | jq '.project_count, .work_item_count, .page_count'
```

The expected output on a freshly-imported synthetic fixture is the
values recorded in `tests/test_migration.py`.

---

## 7. Cross-references

- `docs/launch-plan.md`
- `docs/beta-program.md`
- `docs/migration-guide.md`
- `docs/roadmap.md`
- `docs/post-launch-iteration.md`
- `src/innerwork/analytics.py`
- `tests/test_analytics.py`
- `tests/test_migration.py`
