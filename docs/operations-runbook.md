# Operations Runbook

> **Status: Reference design.** This runbook describes how an operator
> would run the Atlassian Innerwork reference application in a
> production-grade deployment. The repo ships the API service, the
> in-process observability primitives, SQLite-backed durable state, and
> backup/restore/rollback scripts. It does **not** ship a managed
> control-plane, edge fleet, autoscaler, CDN, or APM/SIEM integration.
> Wherever this runbook talks about an "operator" decision, the assumption
> is the human running the deployment, not an automated system.

The richer "what a production-grade SaaS would also operate" service map
(product catalog, broker control plane, regional edge, shared platform
surfaces) lives in `docs/archive/operations-runbook.md`. That document is
not a current state-of-the-world description; it is the long-form design
intent we are converging toward.

## What this runbook covers

| Section | Audience |
|---|---|
| Service map (today's reality) | New operator |
| Configuration | Operator + dev |
| Boot / health probes | Operator |
| Observability surfaces | Operator |
| SLOs | Operator + product |
| Backup & restore | Operator |
| Rollback drill | Operator |
| Incident playbooks | On-call |
| Release process | Maintainer |

## Service map (today's reality)

- **API service.** FastAPI app, single process. Entry point:
  ``innerwork.app:create_app`` (factory) or ``uvicorn innerwork.app:app``.
- **Durable state.** SQLite. Two paths:
  - ``INNERWORK_DATABASE_URL=sqlite:///path/to/innerwork.db`` for the
    work-graph + knowledge-graph domain store.
  - ``INNERWORK_STATE_PATH=/path/to/broker-state.json`` for the broker
    in-memory snapshot (JSON file persisted on every mutation).
- **Observability.** In-process, stdlib-only. See
  `docs/observability.md` for design + emission semantics. The
  ``/metrics`` endpoint serves Prometheus text format on the same port as
  the API.
- **Background workers.** None. Domain mutations are synchronous against
  SQLite via the request-handling thread.
- **Edge / data plane.** None shipped. The catalog endpoints
  (``/v2/catalog``, ``/v2/products``) describe an aspirational design;
  the broker is in-process bookkeeping today.

## Configuration

All configuration is via environment variables. There is no config file
loader.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `INNERWORK_DATABASE_URL` | No | in-memory SQLite | Use a `file:` URL in prod so state survives restart. |
| `INNERWORK_STATE_PATH` | No | tempdir | JSON file path; created on first write. |
| `PORT` | No | 8000 | Uvicorn listens on this. |
| `UVICORN_LOG_LEVEL` | No | `info` | Mirror this to log aggregation. |

The observability middleware honors `x-request-id` from upstream. If a
trusted edge / API gateway sits in front, prefer to propagate a request
id it has already minted.

## Boot / health probes

After process start, two endpoints are wired:

- `GET /healthz` — returns 200 with snapshot version + service count. Use
  for liveness + readiness. Returns immediately; no I/O outside the
  in-memory broker map.
- `GET /metrics` — Prometheus text exposition. Safe to scrape every 15 s.
  No authentication on this endpoint; if exposed publicly, terminate it
  behind a reverse proxy with IP allow-listing.

Verification one-liners:

```sh
# Liveness
curl -fsS http://localhost:8000/healthz | jq .

# Metrics drain
curl -fsS http://localhost:8000/metrics | head

# Request-id propagation
curl -fsSH "x-request-id: ops-smoke-001" \
    http://localhost:8000/v1/system/request-id | jq .
```

## Observability surfaces

| Surface | Where to look |
|---|---|
| Structured logs | stdout, single-line JSON (`docs/observability.md`) |
| Request-id correlation | `request_id` field in every log; `x-request-id` response header |
| Counters | `/metrics` — `http_requests_total`, `http_request_errors_total`, `domain_writes_total`, `domain_write_conflicts_total` |
| Latency | `/metrics` — `http_request_duration_ms`, `span_duration_ms` |
| Trace spans | `spans` array in log payloads when a `trace_span(...)` context is active |

### What is *not* shipped

- No external trace exporter (no OTel collector, no Jaeger, no Datadog APM).
- No log shipper. Operators are expected to capture stdout into their
  existing log aggregation (Fluent Bit, Vector, syslog, journald, etc.).
- No alerting rules. The SLOs in `docs/slos.md` are target values; an
  operator must compose their own alerting against whatever Prometheus,
  Loki, or vendor stack they use.

## SLOs

See `docs/slos.md` for per-endpoint latency / error-rate targets and the
business-level metrics. Treat those numbers as **review targets**, not
measurements. When the targets drift, file a follow-up issue rather than
silently relaxing them.

## Backup & restore

The reference app uses SQLite for durable state. The `scripts/backup.py`
and `scripts/restore.py` helpers use stdlib `sqlite3.Connection.backup`
so backups are consistent even while the process is serving traffic.

```sh
# Backup
python scripts/backup.py /var/lib/innerwork/innerwork.db /var/backups/innerwork-$(date +%Y%m%dT%H%M%SZ).db

# Verify the backup loads (good practice before declaring the backup good)
sqlite3 /var/backups/innerwork-20260529T120000Z.db "PRAGMA integrity_check;"

# Restore
python scripts/restore.py /var/backups/innerwork-20260529T120000Z.db /var/lib/innerwork/innerwork.db --force
```

Recommended cadence for the reference deployment: hourly snapshot, daily
off-host copy, weekly restore drill. Adjust according to your RPO target.

## Rollback drill

`scripts/rollback_drill.py` is a stdlib-only, idempotent drill that walks
an operator through the rollback steps without touching production. It
runs against an ephemeral SQLite database created in `--workdir`,
exercises the backup → mutate → restore loop, and prints a structured
summary that an on-call can paste into an incident retro.

```sh
python scripts/rollback_drill.py --workdir /tmp/innerwork-drill
```

The drill is also part of the CI matrix; the release workflow blocks if
it fails. See `docs/release.md` for the release pipeline; if that
document does not yet exist, the workflow at
`.github/workflows/release.yml` is the source of truth.

## Incident playbooks

### Symptom: `http_request_errors_total` spikes for a single endpoint

1. `curl /metrics` and confirm the endpoint label.
2. Inspect logs filtered by `endpoint=` value and `level=ERROR`.
3. Capture a sample `request_id` and replay against staging.
4. If the failure is a 409 / 428 (idempotency / version conflict),
   suspect a client-side retry storm — coordinate with the client owner
   before relaxing anything server-side.
5. If the failure is a 5xx, follow the standard
   [systematic-debugging](https://github.com/anthropic) loop: reproduce,
   isolate, hypothesize, verify, then ship the fix on a feature branch.

### Symptom: latency p99 above SLO

1. Pull the relevant `http_request_duration_ms` bucket histogram from
   `/metrics`.
2. Sample 20 requests' worth of `request_id`s from the log stream and
   confirm whether the slowdown is uniform or skewed to a particular
   tenant / payload shape.
3. Check `span_duration_ms` for hot in-process spans. If the bulk of the
   time is inside a single span, that's your culprit.
4. If the SLite database file has grown large, consider
   `PRAGMA optimize;` + `VACUUM` during a maintenance window.

### Symptom: process won't start

1. Validate config: `INNERWORK_DATABASE_URL`, `INNERWORK_STATE_PATH`
   point at writable locations.
2. Confirm `python -c "import innerwork.app; innerwork.app.create_app()"`
   succeeds in the same venv.
3. Inspect the JSON log line emitted on the failure (`level=ERROR`,
   `exc` field has the traceback).
4. Roll back to the previous release tag if you cannot resolve in 10 min;
   the rollback drill validates the procedure end-to-end.

### Symptom: state corruption / partial write

1. Stop the process.
2. `sqlite3 innerwork.db "PRAGMA integrity_check;"`
3. If integrity check fails, restore from the most recent good backup
   (see Backup & restore).
4. After restore, replay any lost mutations from upstream sources if
   available; otherwise log the data loss in the incident retro.

## Release process

The release pipeline is defined in `.github/workflows/release.yml`:

1. CI gate (ruff + pyright + pytest) must be green on `main`.
2. Tag with `vMAJOR.MINOR.PATCH`.
3. Pushing the tag triggers the release workflow, which:
   - Re-runs lint + type-check + tests against the tagged commit.
   - Builds the wheel + sdist via `python -m build`.
   - Executes the rollback drill (`scripts/rollback_drill.py`).
   - Attaches the build artifacts and a generated changelog to the
     GitHub release.
4. Operator pulls the wheel and deploys via the existing
   environment-specific mechanism (Docker / systemd / Helm — none ship
   in this repo).

Before any release, walk the SLO doc + this runbook and confirm nothing
material has changed without a documentation update.
