# Migration Guide

Status: Phase 10 — synthetic-fixture round-trip only.

This guide explains the migration surface that `innerwork` ships in
Phase 10. The goals are:

1. Document what `innerwork export-domain` and `innerwork import-domain`
   actually do.
2. Show operators how to run the round-trip safely against a fresh
   target.
3. Define the contract for the synthetic-fixture importer
   (`innerwork migrate --source synthetic`).

> Phase 10 deliberately ships **no** Jira or Confluence importer. Any
> mention of "migration" in this release refers either to the generic
> `export_domain` / `import_domain` portability surface or to the
> synthetic fixture used to exercise it. This boundary is explicit in
> the launch plan and the beta program documentation.

Companion documents:

- `docs/launch-plan.md` — cutover and rollback procedure.
- `docs/beta-program.md` — what beta operators can expect.
- `docs/operations-runbook.md` — day-2 ops, including DB lifecycle.
- `docs/roadmap.md` — directional future migrator candidates.

---

## 1. Portability surface

The exported surface is implemented by `innerwork.portability` and covers
exactly these collections, in this order:

1. `projects`
2. `work_items`
3. `transitions`
4. `spaces`
5. `pages`
6. `page_versions`
7. `links`
8. `work_item_comments`
9. `page_comments`

The export envelope carries two version fields:

- `format_version` — the portable wire format (`PORTABILITY_FORMAT_VERSION`).
- `schema_version` — the underlying domain schema (`DOMAIN_SCHEMA_VERSION`).

A re-export of an import produces byte-identical JSON when serialized with
`indent=2` and `sort_keys=False`. That property is enforced by tests and
is the definition of "round-trip" for this guide.

What is **not** in the portable surface (by design):

- Idempotency cache rows.
- Transient notification state.
- Audit log rows. The audit log is a record of operations performed
  against the store; it is intentionally not replayed across a migration.
- Permissions configuration that lives outside the domain store (for
  example, environment variables consumed by the permissions module).

---

## 2. CLI surface

Phase 10 adds three subcommands to `innerwork` that wrap the existing
portability and analytics modules. These commands are thin and
side-effect-conservative: they never mutate an already-populated store.

### 2.1 `innerwork export-domain`

```
innerwork export-domain --db <path/to/domain.db> [--indent N]
```

- Reads from an existing `DomainStore` at `--db`.
- Writes deterministic JSON to stdout.
- `--indent` defaults to 2; pass `--indent 0` for a compact one-line form
  (still deterministic, still round-trippable).
- Exit code is 0 on success, non-zero with a printed error on any
  database or serialization failure.

### 2.2 `innerwork import-domain`

```
innerwork import-domain --db <path/to/fresh.db> --input <export.json>
```

- Refuses to run against a non-fresh target. The store must be empty
  across every collection the payload contains. If any collection is
  populated, the CLI prints a `DomainImportError` and exits non-zero —
  no rows are inserted.
- Reads the JSON envelope, validates `format_version`/`schema_version`,
  and replays inserts in FK-safe order (projects → work_items →
  transitions → spaces → pages → page_versions → links → comments).
- Auto-assigned identifiers (`transition_id`, `version_id`,
  `comment_id`, `link_id`) are preserved exactly so a subsequent
  `export-domain` produces byte-identical JSON to the input.
- Prints a JSON summary `{collection: rows_inserted}` to stdout on
  success.

### 2.3 `innerwork migrate --source synthetic`

```
innerwork migrate --source synthetic --db <path/to/fresh.db>
```

- Loads the bundled synthetic fixture
  (`src/innerwork/migrators/synthetic_fixture.py` /
  `tests/fixtures/synthetic_migration.json`).
- Validates it as a portable payload.
- Imports it into the supplied fresh `--db`.
- This command exists to exercise the import code path without
  shipping a real third-party importer.

`--source synthetic` is the only supported value in Phase 10. Any
other value is rejected by the CLI with a clear error.

### 2.4 `innerwork metrics`

```
innerwork metrics --db <path/to/domain.db> [--principal <name>]
```

- Calls `innerwork.analytics.domain_rollup` and prints the resulting
  `DomainRollup.to_dict()` as JSON.
- `--principal` is optional; if omitted, the rollup runs over the full
  domain (back-compat with internal callers).
- The output schema is documented in `docs/metrics-dashboard.md`.

---

## 3. Recommended round-trip procedure

For operators who want to verify the migration path before launch:

```sh
# 1. Snapshot the source store.
innerwork export-domain --db ./prod-domain.db > /tmp/snapshot.json

# 2. Provision a fresh target (DomainStore creates the schema on first open).
rm -f /tmp/fresh-target.db

# 3. Replay the snapshot.
innerwork import-domain --db /tmp/fresh-target.db --input /tmp/snapshot.json

# 4. Re-export and diff for byte equality.
innerwork export-domain --db /tmp/fresh-target.db > /tmp/roundtrip.json
diff -u /tmp/snapshot.json /tmp/roundtrip.json
```

The expected outcome is an empty `diff`. Any divergence is a bug —
file it under the `bug` label per `docs/beta-program.md` §4.

---

## 4. Failure modes and recovery

| Failure | Cause | Recovery |
|---|---|---|
| `DomainImportError: target store not empty` | Operator pointed `--db` at a populated database | Run against a freshly-initialised database. The portability module deliberately refuses partial overlays. |
| `DomainImportError: unsupported format_version` | Snapshot produced by a different `innerwork` version | Re-export the source with the same `innerwork` version as the target, or follow the upgrade path in CHANGELOG. |
| `DomainImportError: unsupported schema_version` | Domain schema migrated between source and target | Re-export the source from a build that matches the target's `DOMAIN_SCHEMA_VERSION`, or rebuild the source against the newer schema before re-exporting. |
| `sqlite3.IntegrityError` mid-import | FK or unique constraint violated | The portability code is FK-ordered, so this should not happen; if it does, treat it as a bug and capture the input JSON for triage. The target database is in an inconsistent state — discard it. |

The portability code uses a single SQLite connection per import. On any
exception inside `import_domain`, the connection is closed without an
explicit `COMMIT`, so the database file should be safe to discard. There
is no automatic rollback to a known-good state because the contract is
"target must be fresh"; if the import fails, the target was meant to be
disposable.

---

## 5. Synthetic fixture contract

The synthetic fixture lives at `tests/fixtures/synthetic_migration.json`
and is loaded both by:

- `tests/test_migration.py` — round-trip equivalence test.
- `src/innerwork/migrators/synthetic_fixture.py` — runtime loader used
  by `innerwork migrate --source synthetic`.

Fixture contents are intentionally small but cover every collection
(`projects`, `work_items`, `transitions`, `spaces`, `pages`,
`page_versions`, `links`, `work_item_comments`, `page_comments`) so the
round-trip exercises every insert path.

Fixture rules:

- All identifiers are stable strings or integers — no clocks, no random
  IDs.
- `created_at` / `updated_at` use fixed ISO-8601 strings.
- The fixture is checked in and must be regenerated only by editing
  the JSON directly or by re-running an export that has been reviewed
  by a maintainer.

---

## 6. What this guide is NOT

- It is **not** a guide for migrating from hosted Jira or Confluence.
  Phase 10 ships no such importer. The roadmap document lists this as a
  directional future item; no commitment is implied.
- It is **not** a backup strategy. SQLite backup is operationally
  separate (file copy with proper locking, or `VACUUM INTO`). See
  `docs/operations-runbook.md`.
- It is **not** an upgrade guide. Schema upgrades happen through
  `innerwork upgrade`; portability snapshots are tagged with the
  schema version they were taken under and refuse to load against a
  newer schema.

---

## 7. Cross-references

- `docs/launch-plan.md`
- `docs/beta-program.md`
- `docs/operations-runbook.md`
- `docs/roadmap.md`
- `docs/metrics-dashboard.md`
- `CHANGELOG.md` (entries under `[Phase 10]`).
