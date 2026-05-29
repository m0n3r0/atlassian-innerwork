# Service Level Objectives (SLOs)

> **Status: Targets, not measurements.** The numbers in this document are
> *targets* for the production-grade reference design. No live deployment
> currently emits the metrics required to compute compliance. The
> observability module shipped in Phase 8 (`src/innerwork/observability.py`)
> exposes the counter / latency primitives a future operator would aggregate
> to measure these targets against a real workload.

## Scope

Phase 8 documents SLOs for the two domain graphs exposed by the FastAPI app:

1. **Work-graph (Jira-inspired):** projects, work items, transitions, links,
   comments, analytics.
2. **Knowledge-graph (Confluence-inspired):** spaces, pages, page versions,
   page comments, search, AI context.

System endpoints (`/healthz`, `/`, broker control-plane) are tracked but
deliberately given more permissive targets because they are not on the
critical user-write path.

## Critical-endpoint targets

| Endpoint | Method | Class | Latency p99 target | Error-rate ceiling |
|---|---|---|---|---|
| `/healthz` | GET | system | 50 ms | 0.1% |
| `/v1/projects` | POST | work-graph write | 300 ms | 1.0% |
| `/v1/projects` | GET | work-graph read | 150 ms | 0.5% |
| `/v1/work_items` | POST | work-graph write | 350 ms | 1.0% |
| `/v1/work_items/{id}/transitions` | POST | work-graph state-change | 350 ms | 1.0% |
| `/v1/work_items/{id}/comments` | POST | work-graph write | 350 ms | 1.0% |
| `/v1/spaces` | POST | knowledge-graph write | 300 ms | 1.0% |
| `/v1/pages` | POST | knowledge-graph write | 400 ms | 1.5% |
| `/v1/pages/{id}` | PUT | knowledge-graph version write | 400 ms | 1.5% |
| `/v1/pages/{id}/comments` | POST | knowledge-graph write | 350 ms | 1.0% |
| `/v1/search` | GET | knowledge-graph read | 250 ms | 1.0% |
| `/v1/ai_context` | POST | knowledge-graph read | 500 ms | 1.5% |
| `/v1/analytics/domain` | GET | analytics read | 500 ms | 1.0% |

## Business / domain targets

These are derived metrics computed by aggregating the per-endpoint counters
the observability module emits.

| Metric | Target | How it is derived |
|---|---|---|
| Work-item write success | ≥ 99.0% over 30 days | `1 - (failed work-item writes / total work-item writes)` |
| Page-write success | ≥ 99.0% over 30 days | `1 - (failed page writes / total page writes)` |
| Page version-conflict rate | ≤ 2.0% over 30 days | `409 responses on PUT /v1/pages/{id} / total PUT /v1/pages/{id}` |
| Transition rejection rate (legitimate) | ≤ 5.0% over 30 days | `transition_rejected_total{reason="invalid_state"} / transition_attempts_total` |
| Search latency p95 | ≤ 200 ms | derived from `http_request_duration_ms{endpoint="/v1/search"}` |
| Audit emission lag | < 1 s p99 | `audit_emit_duration_ms` percentile |
| Comment write success | ≥ 99.0% over 30 days | combined work-item + page comment writes |
| Idempotency replay rate | < 10% over 30 days | informational; `idempotency_replay_total / idempotency_attempts_total` |

## Error budget

Each endpoint's monthly error budget is `1 - target_ceiling` of total
requests. For 1% endpoints that is 1% of monthly request volume; spending
more than 50% of the budget inside a single 24-hour window triggers a paging
review per the runbook.

## What this document does NOT claim

- It does not claim that any of the above numbers have been measured.
- It does not claim integration with Datadog, Honeycomb, New Relic,
  Lightstep, Grafana Cloud, Splunk, or any other managed observability
  vendor. Phase 8 emits stdlib-only logs and an in-process metrics registry
  (see `docs/operations-runbook.md`).
- It does not claim a live CDN, edge, or autoscaler is integrated.

## Review cadence

SLO targets in this file are reviewed once per quarter as part of the
release-readiness checklist. Adjustments require a PR plus runbook update.
