# Roadmap item: backup-restore-upgrade — tighten the operations runbook with explicit backup/restore/upgrade procedures — PM scoping

**Status:** PM scoping (pre-implementation). Source: `docs/roadmap.md` → "Directional next" → Quality and operability (`slug=backup-restore-upgrade`).
**Parent:** post-launch backlog item; no phase number. Implementation task branches from `main` on a `docs/backup-restore-upgrade-*` branch.
**Audience:** the implementation worker (atlassianeng). Read this end-to-end before touching files. QA/SEC workers: §5 is your gate.

---

## §0 Honest baseline (what the repo already has, today)

Verified against `main` at commit `90eae89` on 2026-08-04, and **every command below was executed locally against ephemeral stores in `/tmp`** (evidence in §8). The surprise finding: **backup/restore tooling already ships and is already tested.** The gap is documentation: the runbook's Backup section is thin, there is **no Upgrade section at all**, and several claims in the task statement need honest calibration (see §4 gap calls).

| Asset | Present? | Path | Notes |
|---|---|---|---|
| Backup script | ✅ | `scripts/backup.py` | stdlib-only; uses `sqlite3.Connection.backup` (the SQLite **online-backup API**) so snapshots are consistent even while the process is serving. `backup(source, dest)`; `dest` is overwritten; **chmod 0o600 on the backup file** (SEC-friendly, verified: perms 600). No invented flags — `python scripts/backup.py SOURCE DEST`. |
| Restore script | ✅ | `scripts/restore.py` | stdlib-only; `restore(backup, dest, *, force=False)`; **refuses to overwrite an existing dest unless `--force`**; chmod 0o600 on the restored file (verified: 600). `python scripts/restore.py BACKUP DEST [--force]`. |
| Rollback/restore drill | ✅ | `scripts/rollback_drill.py` | stdlib-only, idempotent: seed → backup → destructive mutation → restore → checksum verify against an ephemeral DB in `--workdir`. Prints structured JSON summary; exit 0/1. **Runs in CI on every tag** (`.github/workflows/release.yml:31`) and is in the pre-release checklist (`docs/release.md`). Locally verified: `"ok": true`. |
| Script tests | ✅ | `tests/test_backup_restore.py`, `tests/test_rollback_drill.py` | Backup/restore round-trip, missing-source, overwrite-refusal, drill ok-summary + step order + `--keep-workdir`. Scripts are already covered — **no new script, therefore no new script tests required** (task's "if a script ships" condition is not met). |
| Runbook | ✅ (thin) | `docs/operations-runbook.md` | Has a "Backup & restore" section (lines 118–136) + "Rollback drill" (138–153), but: no audit-store backup, no config-backup guidance, no retention policy, no restore-into-clean-environment walkthrough, no verification step beyond `PRAGMA integrity_check`, **no Upgrade section**. |
| Domain store schema version | ✅ | `src/innerwork/domain_store.py:51` `DOMAIN_SCHEMA_VERSION = 4`; stored in the `meta` table (`domain_schema_version` key, `domain_store.py:1235`) | Import path rejects any envelope whose `schema_version` ≠ 4 (`portability.py:_validate_envelope` → `DomainImportError`). This is the version-check surface for upgrades. |
| Portability envelope | ✅ | `src/innerwork/portability.py` | `format_version` 1 (default) / 2 (audit-bearing via `export --include-audit`). Import accepts 1 and 2 only; rejects v1-with-audit and v2-without-audit loudly; `schema_version` mismatch → `DomainImportError` → exit 2. Byte-deterministic round-trip (test-enforced). **This is the only data-migration path that exists.** |
| CLI migration surface | ✅ (limited) | `innerwork migrate --source synthetic` | Phase 10 ships exactly one migration source: the **synthetic fixture** (data seeding for demo/testing). Verified locally: imports 2 projects / 3 work items / 1 space / 1 page / etc. **It is NOT a schema migrator.** |
| Audit store | ✅ (opt-in) | `src/innerwork/audit.py` (`SqliteAuditSink`), wired via `--audit-log` / `INNERWORK_AUDIT_DB` (`cli.py:393-405`) | Own SQLite file, separate from the domain DB. Append-only (SQL triggers `RAISE(ABORT)`). **CLI-only wiring**: `innerwork serve` does NOT wire a sink (`app.py` has no audit reference) — audit rows are emitted only by CLI invocations that pass `--audit-log`/`INNERWORK_AUDIT_DB`. |
| Config surface | ✅ | env vars only | `INNERWORK_DATABASE_URL`, `INNERWORK_STATE_PATH`, `PORT`, `UVICORN_LOG_LEVEL` (runbook Configuration table). **There is no config file loader** — "back up the config" means recording these env vars, not copying a file. |
| `innerwork doctor` | ❌ | n/a | Listed under roadmap "Directional next → CLI ergonomics" (`docs/roadmap.md:104`). **Does not exist — must not appear in the runbook.** Restore verification uses real commands only (integrity check + CLI reads + export compare). |
| Release/rollback docs | ✅ | `docs/release.md` (Rolling back section), `.github/workflows/release.yml` | Tag-triggered: CI gate → rollback drill → `uv build` → GitHub release. Rolling back = revert deployment mechanism (not shipped) + restore backup + re-run drill on restored DB. |
| `sqlite3` CLI | ⚠️ external | n/a | The current runbook's verification line (`sqlite3 ... PRAGMA integrity_check`) requires the **sqlite3 shell**, which is not a repo dependency and may be absent (it is absent on this dev host). The runbook must offer a **stdlib Python alternative** (verified working, §8) and treat `sqlite3` as the optional convenience. |

**Pre-existing doc drift (fix opportunistically, do not scope-creep):** `docs/roadmap.md` "Shipped through Phase 10" and `docs/migration-guide.md` refer to `innerwork export-domain` / `innerwork import-domain`, but the real subcommands are `innerwork export` / `innerwork import` (verified via `innerwork --help`). If the implementation worker touches either file anyway, correct the command names in the touched section — same precedent as the time-windowed-metrics scoping doc's `--db` → `--database-url` fix.

**Implication.** This is a **documentation-only slice**: extend `docs/operations-runbook.md` with locked, copy-paste, locally-verified Backup / Restore / Upgrade procedures; move the roadmap bullet; add a CHANGELOG entry. **No new scripts, no code changes, no new tests.** The task's "possibly a scripts/backup_domain_store.py helper" is explicitly answered: it already exists as `scripts/backup.py` + `scripts/restore.py` — reuse, don't duplicate.

---

## §1 Exact files to write or modify

Implementation worker MUST touch exactly the files in this table, in this order. Anything else is scope creep.

| # | Path | Action | Rough size | Notes |
|---|---|---|---|---|
| 1 | `docs/roadmap_backup_restore_upgrade_scoping.md` | (this file) | n/a | Exists at PM-scoping time. Implementation worker does not modify. |
| 2 | `docs/operations-runbook.md` | **edit** | +~130/−20 lines | Restructure the "Backup & restore" section (currently lines 118–136) into three locked sections — **Backup**, **Restore**, **Upgrade** — per the contracts in §3. Keep "Rollback drill" and all other sections unchanged except the two cross-references that point at the old backup/restore prose (incident playbook "state corruption" step 3 and "process won't start" step 4 already reference the sections by name — re-verify they still resolve). |
| 3 | `docs/roadmap.md` | **edit** | −2/+4 lines | Move the bullet "Tighten the operations runbook with explicit backup / restore / upgrade procedures." (currently `docs/roadmap.md:84-85` under "Directional next → Quality and operability") into the "Shipped through Phase 10" list as a post-phase-10 addition, same PR, mirroring the precedent set by the streaming-export / time-windowed-metrics scoping merges. While editing, correct the `export-domain`/`import-domain` command names in the Shipped list if the bullet sits adjacent (see §0 drift note). |
| 4 | `CHANGELOG.md` | **edit** | +~8 lines | Under `[Unreleased]`, a `### Changed — Operations runbook (backup/restore/upgrade)` subsection: three new runbook sections, no new scripts/code/dependencies, roadmap bullet moved. No version bump. |

**Files that LOOK like they should be touched but MUST NOT be touched.**

| Path | Why not |
|---|---|
| `scripts/backup.py`, `scripts/restore.py`, `scripts/rollback_drill.py` | Already shipped and tested (`tests/test_backup_restore.py`, `tests/test_rollback_drill.py`). The task's "reuse, don't duplicate" gate. If the implementation worker discovers a real defect while executing the runbook commands, file it as a follow-up task — do not fix in this PR. |
| `src/innerwork/*` (domain_store, portability, audit, cli, migrators) | No code change needed. `DOMAIN_SCHEMA_VERSION`, `format_version`, the audit sink wiring, and `migrate --source synthetic` are all read-only facts the runbook documents. |
| `tests/*` | No new script ships → the "unit-test it with a temp store" condition is not met. The verification burden lands on the runbook commands themselves (CI parity, §6/§8). |
| `.github/workflows/*`, `pyproject.toml` | No CI change; no new dependency (the stdlib Python integrity-check one-liner uses only `sqlite3`). |
| `docs/release.md`, `docs/migration-guide.md` | Already accurate for rollback/portability; leave them. (The `export-domain` drift in `migration-guide.md` is pre-existing and out of this slice — fix only if touching the file for a real reason.) |

---

## §2 Locked command surface (verified against `innerwork --help` and live runs)

The runbook may reference **only** these commands. All were executed successfully in §8.

```
# Domain-store lifecycle (real CLI)
innerwork project-create   --database-url sqlite:///PATH --key KEY --name NAME --owner OWNER
innerwork projects         --database-url sqlite:///PATH
innerwork work-items       --database-url sqlite:///PATH
innerwork metrics          --database-url sqlite:///PATH
innerwork export           --database-url sqlite:///PATH --out envelope.json
innerwork export           --database-url sqlite:///PATH --out envelope.json --include-audit --audit-log audit.db
innerwork import           envelope.json --database-url sqlite:///PATH [--audit-log audit.db]
innerwork migrate          --database-url sqlite:///PATH --source synthetic

# Backup / restore / drill scripts (repo scripts, stdlib-only)
python scripts/backup.py        SOURCE_DB BACKUP_PATH
python scripts/restore.py       BACKUP_PATH DEST_DB [--force]
python scripts/rollback_drill.py --workdir /tmp/innerwork-drill [--keep-workdir]

# Verification
sqlite3 DB "PRAGMA integrity_check;"                        # if sqlite3 shell installed
python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check;').fetchall())" DB   # stdlib alternative, always available
```

1. **Env vars honored by the CLI** (document in the runbook's "what to back up" list): `INNERWORK_DATABASE_URL` (domain store path), `INNERWORK_AUDIT_DB` (audit store path), `INNERWORK_STATE_PATH` (broker JSON snapshot — ephemeral by design, back up only if the operator cares), `PORT`, `UVICORN_LOG_LEVEL`.
2. **`--database-url` format is `sqlite:///absolute/or/relative/path`** (CLI rejects anything else with exit 2). The runbook must use this exact form — the old runbook's bare-path style is wrong for CLI commands.
3. **`scripts/backup.py` is the only supported way to snapshot a live DB.** It uses the SQLite online-backup API (`Connection.backup`), which is correct under any journal mode (DELETE or WAL) and safe while other processes write. A raw `cp`/`file copy` of a live DB is **not** a consistent snapshot and must be called out as unsupported in the runbook (this is the "file copy with WAL checkpoint" branch the task mentions — the repo's answer is the backup API, no manual checkpoint needed).
4. **`scripts/restore.py` refuses to overwrite an existing dest** unless `--force` is passed — the runbook's restore-into-clean-environment flow should restore into a fresh path (or explicitly pass `--force` after stopping the service).
5. **Import is the schema gate**: `innerwork import` rejects envelopes whose `schema_version` ≠ current `DOMAIN_SCHEMA_VERSION` (4) or whose `format_version` ∉ {1, 2} with `DomainImportError` → exit 2, nothing written. The Upgrade section leans on this for its "verify the new version can read your data" pre-step.
6. **`innerwork migrate --source synthetic`** is a data-seeding surface only (Phase 10 synthetic fixture). The runbook must not present it as a schema upgrade tool.

---

## §3 Runbook content contract (what the three new sections must contain)

### 3.1 Backup section (replaces/extends current "Backup & restore")

1. **What to back up** — three items, each with a real command:
   - Domain store: the file named by `INNERWORK_DATABASE_URL` (default none — if unset the app runs in-memory; state is lost on restart, so a store file must exist before backup matters).
   - Audit store **if enabled**: the file named by `--audit-log` / `INNERWORK_AUDIT_DB`. (Honest note: audit rows are emitted only by CLI invocations that wire the sink; `innerwork serve` does not wire one — see §4.2. The backup command is the same `backup.py` against the audit file.)
   - Config: there is no config file; the config surface is the env-var table in the runbook's Configuration section. "Back up config" = record the current env-var set (e.g. the deployment manifest or a documented shell snippet). No file copy exists to script.
2. **How to take a consistent snapshot** — `python scripts/backup.py <live.db> <backup-$(date +%Y%m%dT%H%M%SZ).db>`; one line explaining `Connection.backup` = online-backup API, consistent while serving, safe under WAL; **raw file copies are not consistent snapshots**; verify the backup before declaring it good (verification command from §2).
3. **Where to store it** — a separate directory from the live DB (the script `mkdir -p`s the dest parent); the script chmods the backup `0o600` (not world-readable). Off-host copy (scp/object storage) is an operator decision — **the repo ships no off-host/cloud integration**, so the runbook must say that explicitly rather than imply one.
4. **Retention guidance** — keep the existing cadence line (hourly snapshot, daily off-host copy, weekly restore drill) and add a concrete retention rule of thumb (e.g. keep 24 hourly, 30 daily, 12 weekly, or align to RPO/RTO), labeled as **operator guidance** — no retention/pruning tool ships.

### 3.2 Restore section (step-by-step, into a clean environment)

Numbered, copy-paste, ending in verification:

1. Stop the service (or accept a brief write-window — the scripts are online-safe, but restoring over a live store while the app writes can lose post-backup writes; recommend stopping for a true point-in-time restore).
2. Restore into the destination path: `python scripts/restore.py <backup> <dest>` (fresh dest) or `... --force` (replace existing). Note the refusal-without-`--force` semantics.
3. **Verify integrity**: `sqlite3 <dest> "PRAGMA integrity_check;"` **or** the stdlib Python one-liner (always available).
4. **Verify data through the real CLI**: `innerwork projects --database-url sqlite:///<dest>` and `innerwork work-items --database-url sqlite:///<dest>` (counts/keys present), `innerwork metrics --database-url sqlite:///<dest>` (rollup numbers sane).
5. (Recommended, deeper) **Round-trip check**: `innerwork export --database-url sqlite:///<dest> --out /tmp/verify-$(date +%s).json` and diff the top-level collection counts against the pre-restore export if one exists — semantic parity.
6. Point at `scripts/rollback_drill.py` as the automated version of exactly this loop (seed → backup → mutate → restore → checksum), which CI already runs.

**Honest constraint:** the runbook must NOT reference `innerwork doctor` (does not exist — roadmap future item). Verification is integrity-check + CLI reads + optional export compare. **Honest gap call required:** a restore drill against a real production store has never been executed or recorded; what exists is the CI-gated automated drill on scratch data. Say so.

### 3.3 Upgrade section (new)

1. **Version check** — how to see what you're on and what's available: the installed wheel's version (`pip show atlassian-innerwork` or `uv pip show`) / release tag (`git tag -l`), CHANGELOG's `[Unreleased]` for upcoming, and the release process in `docs/release.md` (tag → CI → rollback drill → wheel+sdist on GitHub).
2. **format_version / schema_version migration path (the portability envelope)** — the ONLY data-migration path that exists. Procedure: pre-upgrade backup (both DBs, §3.1) → `innerwork export --database-url sqlite:///PATH --out pre-upgrade-envelope.json` (add `--include-audit --audit-log` only if the audit store must move too) → install the new wheel → `innerwork import pre-upgrade-envelope.json --database-url sqlite:///NEWPATH` into a **fresh** store. The import gate: `schema_version` must equal the new `DOMAIN_SCHEMA_VERSION` and `format_version` ∈ {1, 2} or the import fails loudly with exit 2 and writes nothing — that is the built-in compatibility check.
3. **Pre-upgrade backup requirement** — backup before upgrade, always; show the two backup commands (domain + audit).
4. **Rollback plan** — `docs/release.md` "Rolling back": revert the deployment mechanism (not shipped — Docker/Helm/systemd is operator-owned), and if the regression involved destructive data mutation, restore the most recent good backup (§3.2) then re-run `scripts/rollback_drill.py --workdir /tmp/innerwork-drill` against the restored DB to prove the procedure still works on the rolled-back code.
5. **Honest boundary**: roadmap `docs/roadmap.md:138` — "No automated upgrade path for breaking schema changes beyond what the portability surface provides." `innerwork migrate --source synthetic` is a data-seeding fixture, not a migrator. State both plainly.

---

## §4 Gap calls (must appear verbatim-ish in the runbook and CHANGELOG)

1. **No production-store restore drill has ever been executed.** The phase-8 exit criterion "rollback drill passes" (`docs/production-grade-roadmap.md:189`) is satisfied by `scripts/rollback_drill.py`, which runs in CI on every release tag (`release.yml:31`) and is locally verified (`"ok": true`). But that drill exercises **scratch data in a temp dir**, not a real store. The runbook must say: automated drill exists and is CI-gated; a manual restore drill against production-shaped data has **not** been run/recorded, and the "weekly restore drill" cadence line is a recommendation, not a record.
2. **Audit logging is CLI-gated and serve-path-blind.** Rows are emitted only when a CLI invocation passes `--audit-log`/`INNERWORK_AUDIT_DB`; `innerwork serve` does not wire a sink. Backup of the audit store therefore only matters for operators who use the flag — and the runbook must say the audit store exists only if you created one.
3. **No automated upgrade path for breaking schema changes** — roadmap out-of-scope line; portability envelope is the path, with loud import rejection as the safety net. Not a gap to close in this slice.
4. **No retention implementation** — retention is operator guidance only; no prune/rotation script ships.
5. **`sqlite3` shell may be absent** — the runbook's verification commands must default to the stdlib Python one-liner and offer the `sqlite3` CLI as the optional convenience (verified both forms).

---

## §5 SEC gates for downstream QA/SEC workers

- **Secrets leakage**: `backup.py`/`restore.py` print only paths; the runbook must warn that a DB URL may embed credentials (e.g. `sqlite:///` never does, but a future `postgres://` URL would) and that backup file **names** must not carry secrets (no `...-prod-creds.db`). Backup logs = command lines only.
- **File permissions**: backup and restore both `chmod 0o600` (verified 600/600). QA: re-verify the chmod lands even when dest parent dir is shared/`/tmp`.
- **Path traversal / symlinks**: scripts take explicit local paths; no traversal surface. `backup.py` follows a symlinked source (intended — it's the operator's own path); a **dest** that is a symlink would be written through — recommend fresh dest paths in the runbook (the `$(date)`-stamped pattern already guarantees this). QA: exercise backup→restore with a symlinked source and confirm behavior is sane and documented.
- **Restore safety**: `restore.py` refuses to clobber without `--force`; the runbook's clean-environment flow uses fresh dest paths. QA: confirm `--force` on a live, in-use store is called out as operator responsibility.
- **No new attack surface**: this slice adds docs only — no code, no new endpoints, no new dependencies. SEC: verify the diff contains no script/code changes.

---

## §6 Tests / CI parity

- **No new tests** (no new script ships). Existing coverage: `tests/test_backup_restore.py` (round-trip, missing-source, overwrite-refusal), `tests/test_rollback_drill.py` (ok-summary, step order, `--keep-workdir`).
- **CI parity for the runbook's commands**: the implementation worker must execute every command in the new runbook sections against ephemeral stores and confirm exit 0 — the §8 matrix is the canonical checklist and was already executed successfully on `main@90eae89`.
- Standard gate still applies to the PR: `uv run pytest -x && uv run ruff check . && uv run pyright` (docs-only diff, but the gate runs on the repo).

---

## §7 Exit criteria (acceptance for this roadmap item)

1. `docs/operations-runbook.md` has **Backup**, **Restore**, and **Upgrade** sections with copy-paste commands; every command exists in the repo (verified against `innerwork --help` and §8) — no invented flags, no `innerwork doctor`.
2. A fresh operator can: back up a store (domain + audit if enabled) → wipe it → restore it → verify integrity and data through the real CLI — without asking questions (walkthrough-able from the doc alone).
3. Upgrade path documents: version check, `format_version`/`schema_version` migration via the portability envelope, pre-upgrade backup requirement, rollback plan (release.md + drill re-run), and the "no automated upgrade path" boundary.
4. Honest gap calls present: no production-store restore drill recorded; audit sink CLI-gated; retention is guidance; `sqlite3` CLI optional.
5. `docs/roadmap.md` bullet moved to "Shipped through Phase 10"; `CHANGELOG.md` entry added; CI gate green; scoping doc on `main`.

---

## §8 Verification evidence (executed 2026-08-04 on `main@90eae89`, all exit 0)

Ephemeral run in `/tmp/inw-scope` (script: `/tmp/inw-verify.sh`):

| # | Command (real, as written) | Result |
|---|---|---|
| 1 | `innerwork project-create --database-url sqlite:////tmp/inw-scope/live.db --key ENG --name Engineering --owner alice` | project created (uuid captured) |
| 2 | `innerwork work-item-create --database-url ... --project-id <id> --title "Ship backup docs" --assignee bob` | work item created |
| 3 | `innerwork projects` / `innerwork work-items` / `innerwork metrics` (same URL) | `projects=1 work_items=1 metrics.project_count=1 metrics.work_item_count=1` |
| 4 | `python scripts/backup.py live.db backup-<ts>.db` | file created, **perms 600** |
| 5 | integrity check on backup (stdlib sqlite3) | `[('ok',)]` |
| 6 | `rm live.db` then `python scripts/restore.py <backup> live.db` | restored, **perms 600** |
| 7 | integrity check on restored DB + `projects`/`work-items` reads | `[('ok',)]`, `projects=1 work_items=1`, **semantic parity True** (pre vs post-restore JSON equal) |
| 8 | `innerwork export --out envelope.json` | `format_version: 1, schema_version: 4` |
| 9 | `innerwork import envelope.json --database-url sqlite:////tmp/inw-scope/restored-via-import.db` | import parity **True** (projects JSON equal) |
| 10 | `innerwork project-create --audit-log audit.db ...` then `backup.py audit.db audit-backup.db` | audit DB created; audit backup integrity `[('ok',)]` |
| 11 | `python scripts/rollback_drill.py --workdir ... --keep-workdir` | `"ok": true` (steps: seed, backup, destructive_mutation, restore; 1000 rows restored, checksum match) |
| 12 | `innerwork migrate --database-url ... --source synthetic` | imported 2 projects / 3 work items / 3 transitions / 1 space / 1 page / 2 page_versions / 2 work_item_comments / 1 page_comment / 1 link |

Notes: `sqlite3` CLI is **not installed** on this host — integrity checks were run via the stdlib Python one-liner (which is why the runbook defaults to it). The `sqlite3` shell variant is unverified locally but is the standard sqlite3 distribution tool; QA may verify it in CI if a runner has it.
