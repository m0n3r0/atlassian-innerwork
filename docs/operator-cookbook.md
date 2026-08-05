# Operator Cookbook

> **Status:** living cookbook for operators of the reference deployment,
> written to sit alongside the `docs/operations-runbook.md`. Every command
> below was verified against the actual CLI (`innerwork <cmd> --help`,
> `scripts/*.py --help`, and live runs) at the time of writing; where a
> capability does **not** exist (no in-app log files, no retention tool, no
> persisted search index), this document says so instead of inventing a
> recipe. The authoritative step-by-step procedures live in
> `docs/operations-runbook.md`; this cookbook links to them and does **not**
> restate or contradict them.

## What this cookbook covers

| Section | Audience |
|---|---|
| Daily and weekly checklists | Operator |
| Backup and restore drills | Operator + on-call |
| Diagnosing common failure modes | Operator + on-call |
| Upgrading the CLI | Operator + maintainer |
| Routine maintenance | Operator |
| Command reference (verified) | Everyone |

The environment-variable configuration surface, service map, and observability
layout are in `docs/operations-runbook.md` (Configuration and Observability
surfaces sections). The SLO targets are review targets, not measurements —
see `docs/slos.md`.

## Daily and weekly checklists

### Daily

1. **Liveness + readiness.** The `/healthz` endpoint returns immediately
   with no I/O outside the in-memory broker map:

   ```sh
   curl -fsS http://localhost:8000/healthz | jq .
   ```

2. **Error counters.** Drain `/metrics` and look for
   `http_request_errors_total` / `http_request_duration_ms` drift:

   ```sh
   curl -fsS http://localhost:8000/metrics | grep -E 'http_request_errors|http_requests_total'
   ```

   The metrics endpoint is unauthenticated; if exposed publicly, terminate it
   behind a reverse proxy with IP allow-listing (runbook, Boot / health
   probes).

3. **Store health.** Run the doctor against the domain store. Exit 0 means
   healthy (no findings at error **or** warning severity):

   ```sh
   innerwork doctor /var/lib/innerwork/innerwork.db
   ```

   `innerwork doctor` is read-only and also checks the audit database when one
   is configured (`--audit-log PATH` or `INNERWORK_AUDIT_DB`). See
   `docs/migration-guide.md` §2.5 for the full exit-code contract and the
   `--json` shape.

4. **Log scan.** The app emits single-line JSON logs to **stdout only** (no
   in-app log files — see Routine maintenance). Scan the captured stream for
   `level=ERROR` and correlate with the `request_id` field.

### Weekly

1. **Verify the latest backup.** A backup is not good until it has passed an
   integrity check. Use the stdlib one-liner from the runbook's Backup section
   (it is always available, whereas the `sqlite3` shell may not be installed):

   ```sh
   python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check;').fetchall())" \
       /var/backups/innerwork-$(date -d '7 days ago' +%Y%m%dT%H%M%SZ).db
   ```

   A healthy snapshot prints `[('ok',)]`.

2. **Run the rollback drill.** `scripts/rollback_drill.py` exercises
   backup → mutate → restore against an ephemeral scratch database and prints
   a structured summary an on-call can paste into an incident retro:

   ```sh
   python scripts/rollback_drill.py --workdir /tmp/innerwork-drill
   ```

   CI already runs this on every release; running it weekly proves the
   procedure works against the current code between releases.

3. **Version check.** Compare the installed wheel against the changelog
   (details in Upgrading the CLI):

   ```sh
   uv pip show atlassian-innerwork   # or: pip show atlassian-innerwork
   ```

   Read `CHANGELOG.md` — everything under `[Unreleased]` will arrive in the
   next release. **No git tag exists yet** (`git tag -l` is empty); the first
   release will be `v0.1.0`.

4. **Confirm the off-host copy path.** The repo ships no off-host / cloud
   integration; copying snapshots off the host is an operator decision
   (runbook, Backup → Where to store it). Verify your scp/rclone/object-storage
   job ran and the newest remote snapshot matches a local one.

5. **Review SLO drift.** Treat the numbers in `docs/slos.md` as review
   targets; when they drift, file a follow-up issue rather than silently
   relaxing them (runbook, SLOs).

## Backup and restore drills

The locked, copy-paste procedures live in `docs/operations-runbook.md`
(Backup, Restore, Rollback drill) and were tightened under
`docs/roadmap_backup_restore_upgrade_scoping.md` (§2 locks the command
surface). This section is a **drill checklist only** — it links to the runbook
and adds nothing that contradicts it.

1. **Pre-flight.** `innerwork doctor /var/lib/innerwork/innerwork.db
   --integrity-check` must exit 0 before you trust the source store.
2. **Snapshot both stores.** Run `scripts/backup.py` against the domain store
   and, if an audit store exists, the audit store (runbook, Backup). Use
   `$(date +%Y%m%dT%H%M%SZ)`-stamped destinations so one run never overwrites
   another.
3. **Verify the snapshots** with the stdlib integrity one-liner (Daily
   checklist step 1). `[('ok',)]` or the drill stops here.
4. **Run the automated drill:** `python scripts/rollback_drill.py --workdir
   /tmp/innerwork-drill`. This is the same loop CI gates releases on.
5. **Periodically (monthly/quarterly), do a full restore into a scratch
   environment**, not just the automated drill: stop the service or accept a
   write window, `scripts/restore.py` into a fresh destination, verify with the
   integrity one-liner, `innerwork doctor`, CLI reads (`innerwork projects`,
   `innerwork work-items`, `innerwork metrics` against the restored store),
   and optionally an export compare (runbook, Restore steps 3–6).
6. **Honest gap call:** a manual restore drill against a real,
   production-shaped store has **not** been executed or recorded in this
   project; what exists is the CI-gated automated drill on scratch data
   (runbook, Restore). Do not claim a restore is production-proven until you
   have actually done step 5 and recorded it.

## Diagnosing common failure modes

### Symptom: "address already in use" / service won't bind

1. Preview the exact uvicorn command the CLI would run — no server starts:

   ```sh
   innerwork serve --dry-run
   ```

   The printed `command` and `environment` show the bind host, port, and
   `INNERWORK_DATABASE_URL` / `INNERWORK_STATE_PATH` that would be used.
2. Confirm what is holding the port (system tool, not an innerwork command):

   ```sh
   ss -ltnp | grep :8000      # or: lsof -i :8000
   ```

3. Rebind with `--port` (or the `PORT` env var) rather than killing an
   unrelated process, and check `UVICORN_LOG_LEVEL` if you need more startup
   detail.

### Symptom: corrupt or mismatched database file

1. **Schema/version drift or file-level problems:** `innerwork doctor
   DB_PATH`. Findings are grouped T (target & file: `target.exists`,
   `target.readable`, `target.sqlite_header`, `target.openable`,
   `target.writable`, `target.disk_space`, `target.age`), S (schema: domain
   version, tables, columns, indexes, broker scope), and A (audit DB, only
   when an audit path resolves). Any error or warning finding → exit 1;
   `--json` separates severities so automation can test `counts.error == 0`.
2. **Deep page scan:** `--integrity-check` runs `PRAGMA integrity_check`
   (scans every page; slow on large stores, off by default):

   ```sh
   innerwork doctor /var/lib/innerwork/innerwork.db --integrity-check
   ```

3. **Version mismatch on import:** `innerwork import` rejects any envelope
   whose `schema_version` differs from the current
   `DOMAIN_SCHEMA_VERSION` or whose `format_version` is not 1 or 2, loudly,
   with exit 2 and nothing written. That rejection **is** the built-in
   compatibility check — an export from an old version fails closed (runbook,
   Upgrade).
4. If integrity fails or the file is not restorable, restore from the most
   recent verified backup (runbook, Restore) and log any lost mutations in the
   incident retro.

### Symptom: permission errors on the store or backup

1. `innerwork doctor DB_PATH` surfaces the relevant findings directly:
   `target.readable` / `target.writable` are checked on every run, and the
   store file plus its parent directory must be writable by the service user.
2. `scripts/restore.py` **refuses to overwrite an existing destination**
   unless `--force` is passed — a missing `--force` is a feature, not a
   misconfiguration. Using `--force` against a live, in-use store is the
   operator's responsibility (runbook, Restore).
3. Snapshot files are chmodded `0o600`, so they are not world-readable even
   in a shared backup directory; a restore that "works" but then fails to open
   for the service user is usually a permissions problem on the destination
   path, not the backup.

### Symptom: search results look stale

There is **no persisted search index** in this project. `src/innerwork/search.py`
is a pure-Python tokenized index queried **on demand** against the live
`DomainStore` — no FTS5, no embedding model, nothing to rebuild or refresh.
Consequences for operators:

- A "stale index" failure mode cannot occur; there is no index to rebuild.
- If search results look wrong, the store itself is the only source of truth.
  Re-query the entity directly (`innerwork work-items --project-id ...`,
  `innerwork projects`) and run `innerwork doctor` to rule out a corrupted or
  partially written store.
- Search is a Phase 6 slice and returns every matching entity (permissions /
  redaction are a Phase D item) — see `docs/phase-6.md`.

### Symptom: `innerwork doctor` exits 1

Exit 1 means at least one error **or warning** finding — warnings affect the
exit code by design (the roadmap contract is "0 = healthy, non-zero = issues
found"). Run with `--json` and inspect `counts` and the per-finding
`id`/`severity`/`message` fields before deciding the store is broken; a
warning (e.g. backup `target.age` older than the guidance) is not corruption.

## Upgrading the CLI

The authoritative upgrade procedure is the runbook's Upgrade section
(back up → export envelope → install → import into a fresh store → verify →
swap). This section is the operator's quick reference.

### Version check

```sh
uv pip show atlassian-innerwork    # installed wheel (or: pip show atlassian-innerwork)
git tag -l                          # released tags (none yet — first release v0.1.0)
```

- Upcoming changes: `CHANGELOG.md` under `[Unreleased]`.
- Release mechanics (tag → CI gate → rollback drill → wheel + sdist):
  `docs/release.md` and `.github/workflows/release.yml`.

### Upgrade steps (pointer form)

1. Back up **both** stores and export the pre-upgrade envelope — commands are
   in the runbook's Upgrade section; do not improvise around them.
2. Install the new wheel via your deployment mechanism (Docker / systemd /
   Helm — none ship in this repo).
3. Import the envelope into a **fresh** store path; the envelope's
   `schema_version` must equal the new `DOMAIN_SCHEMA_VERSION`, and a release
   that changed the schema rejects an old export loudly. Verify the fresh
   store (restore steps in the runbook), then swap it into place. Delete
   nothing until post-upgrade verification passes.

### Rollback path

Reverting the deployment mechanism is operator-owned. If the regression
involved destructive data mutation, restore the most recent good backup
(runbook, Restore), then re-prove the procedure on the rolled-back code:

```sh
python scripts/rollback_drill.py --workdir /tmp/innerwork-drill
```

### Honest boundary

There is **no automated upgrade path for breaking schema changes** beyond the
portability surface. `innerwork migrate --source synthetic` is a data-seeding
fixture for demo/testing — **not** a schema migrator — and must not be used to
upgrade a store (runbook, Upgrade → Honest boundary). The `synthetic` choice
is the only migration source that exists (`innerwork migrate --help`).

## Routine maintenance

### Log rotation

The app writes structured single-line JSON logs to **stdout only**; it never
opens a log file. Rotation therefore happens at the capture layer, entirely
operator-owned:

- systemd: let journald capture stdout and apply its own rotation.
- Docker: the logging driver's `max-size` / `max-file` options.
- Manual redirect: point stdout at a file and rotate it with `logrotate`.

There is no in-app log path to configure, and no log shipped in the repo.
Mirror `UVICORN_LOG_LEVEL` to your aggregation target (runbook,
Configuration).

### Pruning old analytics and audit data

- **Analytics:** `innerwork metrics` computes deterministic rollups **on
  demand** from the live store — there is no analytics table or analytics
  database, so there is nothing to prune. The same is true of the
  time-windowed mode (`--window-start` / `--window-end`); it aggregates the
  existing transition/page-version rows (`docs/metrics-dashboard.md` §4).
- **Audit:** the audit store (wired via `--audit-log` / `INNERWORK_AUDIT_DB`)
  is an append-only SQLite file designed to be kept separate from the domain
  DB "for retention-policy reasons" (`src/innerwork/audit.py`). No
  time-based audit pruning command exists; retention is operator-managed —
  rotate the audit DB file itself per your policy (a cron job that archives
  and removes old audit files, the same pattern as backup retention). The
  supported way to start an audit trail fresh is a v1 export (`innerwork
  export` **without** `--include-audit`) imported into a fresh store — the v1
  envelope deliberately carries no audit rows. This drops the **entire**
  audit trail, not a window; treat it as a deliberate data-lifecycle action.
  On a v2 import the audit rows restore through the wired sink with its
  append-only triggers intact (`docs/migration-guide.md` §6.5).
- **Backups:** no retention / pruning tool ships; rotation is operator-managed
  (runbook guidance: 24 hourly, 30 daily, 12 weekly, or align to RPO/RTO).

### Store file growth

If the SQLite store has grown large and latency is drifting, the runbook's
incident playbook (Symptom: latency p99 above SLO) suggests `PRAGMA optimize;`
+ `VACUUM` during a maintenance window. `innerwork doctor` is strictly
read-only and never issues write-adjacent PRAGMAs (`journal_mode`, `vacuum`,
`reindex` — `docs/migration-guide.md` §2.5), so a VACUUM is an explicit,
operator-scheduled action on a stopped or quiesced store, with a fresh backup
taken first.

## Command reference (verified)

Every command below was verified against `--help` and live runs on
`main` at the time of writing.

| Command | Purpose |
|---|---|
| `innerwork doctor [DB_PATH] [--integrity-check] [--json] [--audit-log PATH]` | Read-only schema/misconfiguration validation; exit 0 healthy, 1 findings, 2 usage |
| `innerwork projects` / `innerwork work-items [--project-id P] [--state S]` | Read the work-graph domain as JSON (both take `--database-url`) |
| `innerwork metrics [--window-start T] [--window-end T]` | Whole-domain analytics rollup, optionally time-windowed |
| `innerwork export [--out PATH] [--include-audit] [--audit-log PATH] [--progress]` | Portable JSON envelope; `--out` writes atomically |
| `innerwork import INPUT [--database-url URL] [--audit-log PATH]` | Replay an envelope into a fresh store; rejects version mismatch (exit 2) |
| `innerwork serve [--host H] [--port P] [--state PATH] [--database-url URL] [--dry-run]` | Run the FastAPI app; `--dry-run` prints the uvicorn command + env |
| `innerwork migrate [--source synthetic]` | Seed a demo store with the synthetic fixture — **not** a schema migrator |
| `innerwork import-markdown DIR [--author A] [--dry-run]` | Import a markdown tree into spaces/pages |
| `innerwork import-csv FILE [--owner A] [--delimiter auto\|comma\|tab] [--dry-run] [--allow-populated]` | Import CSV/TSV work-item rows |
| `innerwork validate MANIFEST` / `innerwork render MANIFEST` | EdgeService manifest validation / control-plane snapshot (legacy broker surface) |
| `innerwork workflow` / `innerwork catalog` / `innerwork products` / `innerwork phases` | Static JSON views (default workflow, broker catalog, product catalog, phases) |
| `python scripts/backup.py SOURCE DEST` | Online-backup snapshot via `sqlite3.Connection.backup` |
| `python scripts/restore.py BACKUP DEST [--force]` | Restore; refuses to overwrite an existing DEST without `--force` |
| `python scripts/rollback_drill.py [--workdir DIR] [--keep-workdir]` | Idempotent backup → mutate → restore drill on scratch data |

Security posture and operator responsibilities are documented in
`docs/threat-model.md` (§6, Operator responsibilities) — the checklists above
assume that posture (e.g. no telemetry, unauthenticated `/metrics` behind an
allow-listed proxy).
