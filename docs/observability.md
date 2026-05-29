# Observability

The Phase 8 observability module (`src/innerwork/observability.py`)
ships three stdlib-only primitives wired into the FastAPI app:

| Primitive | Purpose | Surface |
|---|---|---|
| `MetricsRegistry` | counters + histograms | `/metrics` (Prometheus text) |
| `JsonLogFormatter` | structured logs | stdout (one JSON object per line) |
| `trace_span()` | in-process spans + correlation | logs' `spans` field, `span_duration_ms` histogram |

The module is intentionally dependency-free: no OpenTelemetry, no
`prometheus_client`, no `ddtrace`. The rationale is that
`atlassian-innerwork` is a reference application; pulling in a heavy
observability stack would (a) force operators to pick a backend up front
and (b) couple the reference design to one vendor's mental model. By
shipping the primitives, an operator who wants OpenTelemetry can install
the SDK and write a 30-line adapter that forwards from this registry.

## Wiring inside `create_app`

The app installs:

1. `configure_json_logging()` — replaces root logger handlers with a
   single `StreamHandler` whose formatter is `JsonLogFormatter`.
   Idempotent.
2. A FastAPI middleware that:
   - Reads or mints an `x-request-id` (max 128 chars; mints a uuid4 hex
     otherwise), binds it to a contextvar, and echoes it back as a
     response header.
   - Times the request, increments `http_requests_total{endpoint,method,status}`,
     observes `http_request_duration_ms{endpoint,method}`, and increments
     `http_request_errors_total{endpoint,reason}` for 5xx / raised
     exceptions.
   - Uses the *route template* (e.g. `/v1/projects/{project_id}`) as the
     `endpoint` label rather than the raw URL path, so label cardinality
     stays bounded regardless of how many ids exist.
3. A `GET /metrics` endpoint that renders the registry as Prometheus
   text exposition (version 0.0.4). Served on the same port as the API;
   intended for an internal scraper or a sidecar that exposes it more
   selectively.
4. A `GET /v1/system/request-id` endpoint that echoes the current
   request id back to the caller — useful for smoke-testing that an
   upstream-provided header is being honored end-to-end.

## Log shape

Every emitted log line is a single JSON object. Example:

```json
{
  "ts": "2026-05-29T19:31:21+0900",
  "level": "INFO",
  "logger": "innerwork.domain",
  "msg": "created work item",
  "request_id": "9bf244edfac34f3ab0ed86eab861e7dd",
  "spans": ["create_work_item"],
  "project_id": "p_abc",
  "work_item_key": "ENG-42"
}
```

Anything passed via `logger.info("...", extra={"key": value})` becomes a
top-level key in the payload (after a `json.dumps` round-trip check; if
the value is not serializable it is replaced with `repr(value)`).

## Metrics catalog

Pre-declared in the registry at import time:

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `http_requests_total` | counter | endpoint, method, status | Every HTTP response. |
| `http_request_errors_total` | counter | endpoint, reason | 5xx responses + raised exceptions. |
| `http_request_duration_ms` | histogram | endpoint, method | Wall-clock duration. |
| `domain_writes_total` | counter | (label as needed by call site) | Domain mutation count. |
| `domain_write_conflicts_total` | counter | (label as needed) | Domain mutation rejections. |
| `span_duration_ms` | histogram | span | Duration of a `trace_span()`. |

Default histogram buckets (ms): 5, 10, 25, 50, 100, 250, 500, 1000,
2500, 5000.

The `domain_writes_total` / `domain_write_conflicts_total` counters are
declared but call sites can opt in incrementally; Phase 8 only declares
them so downstream code can `registry.inc(...)` without first calling
`registry.counter(...)`.

## Bridging to a managed backend

If an operator wants OpenTelemetry / Datadog / Honeycomb, the bridge is
a small adapter that walks `registry._counters` / `registry._histograms`
and forwards samples. The registry is intentionally introspectable; the
private attribute access is acknowledged as the bridge surface. A future
ticket may expose an iter API once the shape of the first real bridge
is known.

For logs, configure the SDK to consume stdout JSON; every line is
already a structured event with `ts`, `level`, `logger`, `msg`, plus the
correlation fields.

For traces, replace `trace_span()` with an OTel-backed context manager
of the same name; logs and metrics will continue to work because they
only depend on the contextvar stack.

## What's deliberately not here

- No sampling. Every request is instrumented. If high-cardinality
  endpoints exist (they do not today), add sampling at the bridge layer.
- No `LogRecord` filtering by level beyond the root logger's level. If
  you need per-logger thresholds, configure them after
  `configure_json_logging()` (the formatter is idempotent and won't fight
  you).
- No PII redaction. Domain code is expected to log at INFO with non-PII
  payloads; payload review happens in code review.
- No alerting. See `docs/operations-runbook.md` and `docs/slos.md` for
  what targets exist; alerting is the operator's responsibility.
