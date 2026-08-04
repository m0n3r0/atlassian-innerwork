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
| Backup | Operator |
| Restore | Operator |
| Upgrade | Operator |
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

## Backup

The reference app uses SQLite for durable state. `scripts/backup.py` and
`scripts/restore.py` use the stdlib `sqlite3.Connection.backup` API (the
SQLite online-backup API), so snapshots are consistent even while the
process is serving traffic, under any journal mode (DELETE or WAL). A raw
`cp` / file copy of a live database is **not** a consistent snapshot and
is not supported — use `backup.py`.

### What to back up

Three things matter. Only two are files; there is no config file to copy.

1. **Domain store.** The file named by `INNERWORK_DATABASE_URL` (for
   example `/var/lib/innerwork/innerwork.db`). If the variable is unset,
   the app runs against in-memory SQLite and state is lost on restart —
   a store file must exist before backup matters.

   ```sh
   python scripts/backup.py /var/lib/innerwork/innerwork.db \
       /var/backups/innerwork-$(date +%Y%m%dT%H%M%SZ).db
   ```

2. **Audit store, if enabled.** The file named by `--audit-log` /
   `INNERWORK_AUDIT_DB`. The audit store exists only if you created one:
   audit rows are emitted only by CLI invocations that wire the sink, and
   `innerwork serve` does not wire one. If you use the flag, back the
   file up the same way:

   ```sh
   python scripts/backup.py /var/lib/innerwork/audit.db \
       /var/backups/innerwork-audit-$(date +%Y%m%dT%H%M%SZ).db
   ```

3. **Config.** There is no config file loader; the whole config surface
   is the environment-variable table in the Configuration section
   (`INNERWORK_DATABASE_URL`, `INNERWORK_AUDIT_DB`, `INNERWORK_STATE_PATH`,
   `PORT`, `UVICORN_LOG_LEVEL`). "Backing up the config" means recording
   the current env-var set — the deployment manifest or a documented
   shell snippet. There is no file copy to script.

### How to take a consistent snapshot

Run `backup.py` against the live database. It streams pages via
`sqlite3.Connection.backup`, which is safe while other processes write
and needs no manual WAL checkpoint. The destination is overwritten, so
the `$(date)`-stamped name above yields one file per snapshot.

Verify a backup before declaring it good. Prefer the stdlib Python
one-liner — it is always available, whereas the `sqlite3` shell may not
be installed on the host:

```sh
# stdlib Python one-liner (always available)
python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check;').fetchall())" \
    /var/backups/innerwork-20260529T120000Z.db

# ...or, if the sqlite3 CLI is installed
sqlite3 /var/backups/innerwork-20260529T120000Z.db "PRAGMA integrity_check;"
```

A healthy backup prints `[('ok',)]` (Python) or `ok` (sqlite3).

### Where to store it

- Keep backups in a **separate directory** from the live database; the
  script creates the destination parent with `mkdir -p`.
- The script chmods the backup file to `0o600`, so it is not
  world-readable even when the parent directory is shared.
- **Off-host copies are an operator decision.** The repo ships no
  off-host / cloud integration — there is no object-storage or remote
  sync command. If your RPO requires off-host copies, layer your own
  (scp, rclone, object storage, ...) on top of the snapshot files.
- Backup file **names** must not carry secrets (no `...-prod-creds.db`).
  Backup logs are command lines only.

### Retention guidance (operator guidance)

The reference cadence: hourly snapshot, daily off-host copy, weekly
restore drill — adjust to your RPO/RTO. A concrete rule of thumb: keep
24 hourly, 30 daily, and 12 weekly snapshots, or align retention to your
RPO/RTO targets. **No retention / pruning tool ships** — rotation is
operator-managed (for example a cron job that deletes files older than
the policy).

## Restore

Restore into a clean environment, step by step. All commands below were
executed against ephemeral stores; substitute real paths.

1. **Stop the service** (or accept a brief write window). The scripts are
   online-safe, but restoring over a live store while the app writes can
   lose post-backup writes — stop the process for a true point-in-time
   restore.

2. **Restore into the destination path.**

   ```sh
   # Fresh destination (preferred for a clean environment)
   python scripts/restore.py /var/backups/innerwork-20260529T120000Z.db /var/lib/innerwork/innerwork.db

   # Replace an existing file (only after stopping the service)
   python scripts/restore.py /var/backups/innerwork-20260529T120000Z.db /var/lib/innerwork/innerwork.db --force
   ```

   `restore.py` refuses to overwrite an existing destination unless
   `--force` is passed. Using `--force` against a live, in-use store is
   the operator's responsibility. The restore is atomic: it copies into a
   sibling temp file and renames into place only on success, so a failed
   restore (corrupt or truncated backup) fails loudly and leaves an
   existing destination untouched. The restored file is chmodded `0o600`.

3. **Verify integrity.**

   ```sh
   # stdlib Python one-liner (always available)
   python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check;').fetchall())" \
       /var/lib/innerwork/innerwork.db

   # ...or, if the sqlite3 CLI is installed
   sqlite3 /var/lib/innerwork/innerwork.db "PRAGMA integrity_check;"
   ```

4. **Verify data through the real CLI.** The `--database-url` format is
   `sqlite:///absolute/or/relative/path` — for an absolute path the URL
   is `sqlite:////var/lib/...` (three slashes plus the leading slash).

   ```sh
   innerwork projects   --database-url sqlite:////var/lib/innerwork/innerwork.db
   innerwork work-items --database-url sqlite:////var/lib/innerwork/innerwork.db
   innerwork metrics    --database-url sqlite:////var/lib/innerwork/innerwork.db
   ```

   Confirm the expected projects / work items are present and the rollup
   numbers look sane.

5. **(Recommended, deeper) Round-trip check.** Export the restored store
   and compare top-level collection counts against a pre-restore export
   if you kept one — semantic parity:

   ```sh
   innerwork export --database-url sqlite:////var/lib/innerwork/innerwork.db \
       --out /tmp/verify-$(date +%s).json
   ```

6. **Automated version.** `scripts/rollback_drill.py` (Rollback drill
   section) is exactly this loop — seed → backup → destructive mutation →
   restore → checksum — automated against scratch data; CI runs it on
   every release tag.

**Honest gap call:** a manual restore drill against a real,
production-shaped store has **not** been executed or recorded in this
project. What exists is the CI-gated automated drill on scratch data; the
"weekly restore drill" cadence above is a recommendation, not a record.
Verification of a restored store is integrity check + CLI reads + optional
export compare — there is no `innerwork doctor` command (that is a roadmap
future item).

## Upgrade

### Version check

- Installed wheel: `pip show atlassian-innerwork` (or `uv pip show
  atlassian-innerwork`).
- Released tags: `git tag -l`.
- Upcoming changes: `CHANGELOG.md` under `[Unreleased]`.
- Release process: `docs/release.md` (tag → CI gate → rollback drill →
  wheel + sdist on GitHub).

### The only data-migration path: the portability envelope

`innerwork export` / `innerwork import` are the only data-migration path
that exists. Every envelope carries a `format_version` (1 by default, 2
with `--include-audit`) and a `schema_version` (currently
`DOMAIN_SCHEMA_VERSION` = 4). Import rejects any envelope whose
`schema_version` differs or whose `format_version` is not 1 or 2, with a
loud error and exit 2 — nothing is written. That rejection is the
built-in compatibility check.

Upgrade procedure:

1. **Back up before upgrading — always** (both stores; see Backup):

   ```sh
   python scripts/backup.py /var/lib/innerwork/innerwork.db \
       /var/backups/pre-upgrade-$(date +%Y%m%dT%H%M%SZ).db
   python scripts/backup.py /var/lib/innerwork/audit.db \
       /var/backups/pre-upgrade-audit-$(date +%Y%m%dT%H%M%SZ).db   # only if an audit store exists
   ```

2. **Export the pre-upgrade state:**

   ```sh
   innerwork export --database-url sqlite:////var/lib/innerwork/innerwork.db \
       --out /var/backups/pre-upgrade-envelope.json
   ```

   Add `--include-audit --audit-log /var/lib/innerwork/audit.db` only if
   the audit store must move too (the envelope's `format_version` becomes
   2).

3. **Install the new wheel** via your deployment mechanism (Docker /
   systemd / Helm — none ship in this repo).

4. **Import into a fresh store:**

   ```sh
   innerwork import /var/backups/pre-upgrade-envelope.json \
       --database-url sqlite:////var/lib/innerwork/innerwork.db.new
   ```

   The envelope's `schema_version` must equal the new version's
   `DOMAIN_SCHEMA_VERSION`; if a release changed the schema, an export
   from the old version is rejected loudly — that is the compatibility
   check doing its job. Verify the fresh store (Restore steps 3–5), then
   swap it into place. Delete nothing until post-upgrade verification
   passes.

### Rollback plan

See `docs/release.md` → "Rolling back". Reverting the deployment
mechanism is operator-owned (no Docker / Helm / systemd ships). If the
regression involved destructive data mutation, restore the most recent
good backup (Restore section), then re-run the drill against the restored
database to prove the procedure still works on the rolled-back code:

```sh
python scripts/rollback_drill.py --workdir /tmp/innerwork-drill
```

### Honest boundary

There is **no automated upgrade path for breaking schema changes** beyond
what the portability surface provides (roadmap: explicitly out of scope).
`innerwork migrate --source synthetic` is a data-seeding fixture for
demo/testing, **not** a schema migrator — do not use it to upgrade a
store. Operators are expected to read the CHANGELOG and follow
`docs/migration-guide.md`.

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
   (see Restore).
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
