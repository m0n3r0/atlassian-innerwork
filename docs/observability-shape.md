# Observability Shape: Prometheus and Log Scraping

> **Status: Recommendation, not a shipped feature.** This document
> defines a *recommended* Prometheus / log-scraping shape for operators
> who want to wire `innerwork` into their existing observability stack.
> It was written from roadmap item `observability-shape`
> (`docs/roadmap.md` → "Directional next" → Quality and operability).
> **No exporter ships.** The repository ships in-process observability
> primitives (see `docs/observability.md`) and a `GET /metrics` endpoint
> that renders them; it does **not** ship a Prometheus exporter, a
> scraping agent, a pushgateway integration, an OpenTelemetry collector,
> an APM agent, or an alerting rule set. Everything an operator does with
> the shapes below happens on the operator's side of the stack.
>
> **Truthfulness contract.** Every endpoint, command, flag, metric name,
> label, and field named in this document exists in the codebase today
> (verified against `src/innerwork/app.py`,
> `src/innerwork/observability.py`, and `innerwork --help`). Anything
> that is a *recommendation for future work* is explicitly labeled as
> such; nothing here claims a capability that does not ship.

## Companion documents

- `docs/observability.md` — design + emission semantics of the
  stdlib-only registry, formatter, and `trace_span()`.
- `docs/operations-runbook.md` — how to boot, probe, and operate the
  service; the runbook's "Observability surfaces" section is the
  operational view of this shape.
- `docs/slos.md` — latency / error-rate / business targets. The shapes
  here are what an operator would aggregate to *measure* those targets;
  the SLOs themselves remain review targets, not measurements.
- `docs/metrics-dashboard.md` — the `innerwork metrics` CLI rollup
  (point-in-time + windowed) and the operator-side collection patterns
  around it.

---

## 1. The HTTP service surface (exists today)

### 1.1 `GET /metrics`

The FastAPI app serves an in-process Prometheus text exposition on the
same port as the API (`src/innerwork/app.py`, route
`src/innerwork/app.py:172`):

| Property | Value |
|---|---|
| Method / path | `GET /metrics` |
| Content type | `text/plain; version=0.0.4; charset=utf-8` |
| Served on | the same port as the API (default 8000; `innerwork serve --port`) |
| OpenAPI | excluded (`include_in_schema=False`) |
| Auth | **none** — the runbook directs operators to terminate it behind a reverse proxy with IP allow-listing if it would be publicly reachable |
| Recommended scrape interval | 15 s (per `docs/operations-runbook.md`) |

This is an **in-process registry render**, not an exporter: there is no
separate exporter process, no `prometheus_client` dependency, and no
push/crawl machinery. An operator points their Prometheus (or any
OpenMetrics-compatible scraper) at it directly.

### 1.2 Metric catalog as shipped

Pre-declared in the module-level registry at import time
(`src/innerwork/observability.py`):

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `http_requests_total` | counter | `endpoint`, `method`, `status` | Every HTTP response. |
| `http_request_errors_total` | counter | `endpoint`, `reason` | 5xx responses + raised exceptions. |
| `http_request_duration_ms` | histogram | `endpoint`, `method` | Wall-clock duration, milliseconds. |
| `domain_writes_total` | counter | (as needed by call site) | Domain mutation count (work-graph + knowledge-graph). |
| `domain_write_conflicts_total` | counter | (as needed by call site) | Domain mutation rejections by reason. |
| `span_duration_ms` | histogram | `span` | Duration of an in-process `trace_span()`. |

Histogram buckets (ms): `5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000`.

Label semantics:

- `endpoint` is the **route template**, not the raw URL path
  (`src/innerwork/app.py`, `_route_label`): parameterized routes render
  as `/v1/projects/{project_id}` regardless of how many ids exist, so
  label cardinality stays bounded. Unmatched routes (404) fall back to
  the raw path.
- `status` is the stringified HTTP status code (`"200"`, `"409"`, ...).
- `reason` on `http_request_errors_total` is either `"exception"` (a
  raised exception) or `status_<code>` (e.g. `status_500`, a 5xx
  response without an exception).
- `span` on `span_duration_ms` is the `trace_span(name)` name, e.g.
  `"create_work_item"`.

### 1.3 What is *not* on `/metrics` today

- No process / runtime metrics (CPU, memory, GC, file descriptors).
  Operators who need those use standard tools (`psutil`, systemd,
  Prometheus node exporter).
- No gauges. The registry implements counters and histograms only.
- No business/domain time series yet: `domain_writes_total` and
  `domain_write_conflicts_total` are **declared but not incremented** —
  call sites can opt in incrementally. The domain analytics rollup lives
  in the CLI surface (§4), not on `/metrics`.
- No per-tenant or per-user series, and no request ids in labels.

## 2. Metric naming and label convention (recommendation)

The roadmap item asks for a recommended naming scheme for the domain
store + workflow engine. This section is a **recommendation** for future
metrics; the names in §1.2 are already shipped and should be treated as
stable (renaming them would break existing scrapers for no benefit).

1. **Prefix scheme.** Keep the shipped `http_*`, `domain_*`, and
   `span_*` names as-is. Adopt an `innerwork_` prefix for **new**
   domain/workflow metrics so they group cleanly in queries and dashboards:
   e.g. `innerwork_work_items_total`, `innerwork_transitions_total`,
   `innerwork_page_versions_total`.
2. **Counter names end in `_total`** (`innerwork_transitions_total`,
   `domain_writes_total`). Prometheus adds `_total` to the exposed name;
   the registry's rendered name already carries it.
3. **Histograms carry an explicit unit suffix.** The registry is
   millisecond-based (`_HIST_BUCKETS_MS`), so shipped duration
   histograms end in `_ms` (`http_request_duration_ms`,
   `span_duration_ms`). New duration histograms should follow the same
   `_ms` suffix for consistency — do not mix units under one name.
4. **Snake_case, ASCII, no dots.** Metric names use `[a-z0-9_]` only,
   matching what the Prometheus text format accepts without escaping.
5. **Label discipline (the cardinality rule).** Labels are for *bounded*
   dimensions only:
   - workflow state names (`WORKFLOW_STATES`: `todo`, `in_progress`,
     `done`) — bounded by the workflow definition;
   - error classes / rejection reasons (`version_conflict`,
     `invalid_state`) — bounded by the domain's conflict vocabulary;
   - route templates — bounded by the OpenAPI surface.
   Never use raw object ids (`project_id`, `work_item_id`), request ids,
   actors, or timestamps as labels: each distinct value adds a series.
   Worked example for a future metric:
   `innerwork_transitions_total{from_state="todo",to_state="in_progress"}`
   — bounded by the 3×3 state transition matrix.
6. **Help text.** Every metric carries a one-line `# HELP` string
   (already the registry's behaviour); keep it to the metric's meaning,
   not its value.

## 3. Log shape

### 3.1 What ships today

Every log line is a single JSON object on stdout
(`JsonLogFormatter` in `src/innerwork/observability.py`). Example from
`docs/observability.md`:

```json
{"ts":"2026-05-29T19:31:21+0900","level":"INFO","logger":"innerwork.domain","msg":"created work item","request_id":"9bf244edfac34f3ab0ed86eab861e7dd","spans":["create_work_item"],"project_id":"p_abc","work_item_key":"ENG-42"}
```

| Field | Always present | Meaning |
|---|---|---|
| `ts` | yes | `%Y-%m-%dT%H:%M:%S%z` local time with offset |
| `level` | yes | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `logger` | yes | logger name, e.g. `innerwork.domain` |
| `msg` | yes | human-readable message |
| `request_id` | when bound | uuid4 hex (minted from `x-request-id` or generated) |
| `spans` | when a `trace_span(...)` is active | list of active span names |
| `exc` | on exception records | formatted traceback |
| *any other key* | when passed via `logger.info(..., extra={...})` | caller-attached payload; non-serializable values are `repr()`-replaced |

Correlation: the middleware reads or mints `x-request-id` (max 128
chars), binds it to the context, echoes it as a response header, and the
formatter attaches it to every log line emitted inside that request.

### 3.2 Recommended scrape-friendly contract (recommendation)

The current format is already scrape-friendly — newline-delimited JSON
("JSON lines"). The recommendation is to keep it and consume it with a
shipper-side JSON parser rather than a line-based regex:

1. **Parse, don't split.** Use a JSON parser in the log shipper (e.g.
   Fluent Bit's `parser` / `json` filter, Vector's `json` codec,
   journald's structured fields, or `jq -c` for ad-hoc pipelines).
   Every line is one complete object; a partial line only occurs if the
   process dies mid-write.
2. **Route on `level`.** Keep `level` as a first-class field and filter
   `WARNING`+ to the error pipeline. The formatter writes `level` from
   the `LogRecord` level name, so no transformation is needed.
3. **Correlate on `request_id`.** Treat `request_id` as the join key
   across lines (and, via `spans`, across in-process spans). It is
   stable end-to-end when an upstream gateway propagates `x-request-id`.
4. **Don't add fields the app does not emit.** The formatter will happily
   serialize whatever `extra={...}` the call site passes; enrichment
   (service name, environment, version) belongs on the shipper side so
   the app's output stays identical across deployments.
5. **Keep PII out of logs.** The existing policy (per
   `docs/observability.md`) is that domain code logs non-PII payloads at
   INFO; payload review happens in code review. A redaction layer is
   deliberately not shipped — operators who log user content should run
   their own redaction at the shipper.

## 4. Prometheus collection guidance (no exporter ships)

Two shapes are available to an operator today. Both are **operator-side
patterns**; the repository ships neither.

### Option A — pull-based scraping of the existing `GET /metrics` (recommended for service telemetry)

The endpoint in §1.1 is real and scrape-ready. An operator running
Prometheus points a scrape job at it:

```yaml
scrape_configs:
  - job_name: innerwork
    metrics_path: /metrics
    scrape_interval: 15s
    static_configs:
      - targets: ["127.0.0.1:8000"]
```

- What you get: `http_requests_total{endpoint,method,status}`,
  `http_request_errors_total{endpoint,reason}`,
  `http_request_duration_ms{endpoint,method}` (with `_bucket`/`_sum`/
  `_count` series), and `span_duration_ms{span}` once spans execute.
- What you do not get: domain business metrics (declared counters are
  not incremented yet) and process/runtime metrics.
- Caveats: no authentication on `/metrics` — put it behind a reverse
  proxy with IP allow-listing if it would be reachable beyond the
  operator's network; the endpoint restarts empty (process-local
  registry), so counters are per-process and should be used with
  `rate()`/`increase()`, never absolute thresholds.

### Option B — pushgateway or textfile for the `innerwork metrics` CLI rollup

The domain analytics rollup is a **CLI surface**, not an HTTP endpoint:
`innerwork metrics` prints a JSON document
(`docs/metrics-dashboard.md` §1; windowed mode §4). To turn that JSON
into Prometheus series, the operator transforms it themselves — the
repository ships no transform script (metrics-dashboard.md §5, Pattern B
calls this out as the open recommendation this document now closes).

Recommended mapping for the point-in-time rollup (textfile-collector
shape, one line per series):

| Rollup JSON path | Recommended metric | Type | Labels |
|---|---|---|---|
| `project_count` | `innerwork_rollup_project_count` | gauge | — |
| `space_count` | `innerwork_rollup_space_count` | gauge | — |
| `work_item_count` | `innerwork_rollup_work_item_count` | gauge | — |
| `page_count` | `innerwork_rollup_page_count` | gauge | — |
| `work_items_by_state.<state>` | `innerwork_rollup_work_items_by_state` | gauge | `state` (`todo`/`in_progress`/`done`) |

Windowed mode adds `state_counts`, `cycle_time_per_project`
(`cycle_time_*_seconds` — the rollup reports **seconds**), `page_writes`
(`total_versions`, `pages_touched`, `by_space`), and `contributors`
(`distinct`, `by_actor`). `by_space` / `by_actor` are the only
potentially unbounded label dimensions in the rollup; an operator
transforming them should cap or omit them until cardinality is a
deliberate decision.

Collection shapes (both already documented in `docs/metrics-dashboard.md`
§5):

```sh
# Pattern B — Prometheus node exporter textfile collector
innerwork metrics --database-url sqlite:///var/lib/innerwork/store.sqlite3 \
  | <operator-supplied transform script> \
  > /var/lib/node_exporter/textfile/innerwork.prom
```

```sh
# Pattern C — log aggregation as NDJSON
innerwork metrics --database-url sqlite:///var/lib/innerwork/store.sqlite3 \
  | jq -c '. + {"ts": now | todate, "source": "innerwork"}' \
  >> /var/log/innerwork/metrics.ndjson
```

Pushgateway is possible but discouraged here: the rollup is a snapshot,
so a push-based flow must manage staleness (orphaned series after a
failed cron run) and loses the scrape-time semantics Prometheus assumes.
Prefer the textfile collector (same machinery, file-based, no orphan
problem) or a plain cron that writes the JSON/NDJSON files and lets the
collector do the scraping.

### Option A vs Option B — honest tradeoff

| | Option A: pull `/metrics` | Option B: textfile / push |
|---|---|---|
| What it covers | HTTP + span telemetry (counters/histograms) | domain rollup snapshots (gauges) |
| Machinery | endpoint ships; Prometheus pulls | operator-side transform script + node exporter textfile |
| Freshness | continuous per scrape interval | cron-driven (snapshot cadence) |
| Effort | scrape config only | transform script to write + maintain |
| Risk | none shipped; endpoint is unauthenticated | stale series if the cron dies; label cardinality is the operator's job |

**Verdict.** Run Option A for service health (request rate, error rate,
latency histograms — the inputs `docs/slos.md`'s targets are defined
over), and Option B with the textfile collector for domain rollup
snapshots on a cron. Both are recommendations; neither is shipped.

## 5. What is deliberately out of scope here

- No exporter, collector, agent, or shipper ships — and none is claimed.
- No alerting rules. `docs/slos.md` defines targets; composing alerting
  against them is the operator's responsibility.
- No OpenTelemetry / Datadog / Honeycomb bridge ships. The registry is
  intentionally introspectable (`docs/observability.md` §"Bridging to a
  managed backend") for an operator who wants to write one.
- No sampling. Every request is instrumented today; sampling belongs at
  the bridge layer if high-cardinality endpoints ever appear.
- No PII redaction in logs, and no authentication on `/metrics` (both
  are operator-side decisions documented in §3.2 and §1.1).

## 6. Keeping this document accurate

This document mirrors three code-owned surfaces:

- `src/innerwork/observability.py` — the metric catalog (§1.2) and the
  JSON field set (§3.1);
- `src/innerwork/app.py` — the `/metrics` route and label semantics;
- `src/innerwork/cli.py` — the `innerwork metrics` surface (§4).

Any change to those files that alters a metric name, label set, bucket,
field, or CLI flag must be mirrored here, in `docs/observability.md`,
and in `docs/operations-runbook.md` in the same PR. The SLO targets in
`docs/slos.md` are deliberately not restated here; keep this document
about shape, and `docs/slos.md` about targets.
