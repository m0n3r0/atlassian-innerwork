# Collaboration (Phase F)

Phase F adds two cross-cutting facilities on top of the comment + idempotency
baseline:

1. **Mentions & notifications** — `src/innerwork/notify.py`
2. **JSON import/export round-trip** — `src/innerwork/portability.py`

Both modules are pure / in-process. No external connectors (email, Slack,
webhooks) are dispatched — the notifier records intent and suppression reasons
so downstream adapters can drain the queue at their own cadence.

---

## Mentions

A mention is a `@handle` token embedded in comment body text. Handles are
matched case-insensitively, normalised to lowercase, and constrained to the
regex

    [A-Za-z0-9][A-Za-z0-9_-]{1,31}

The first character must be alphanumeric; the remaining 1–31 characters may
also include `_` and `-`. The leading `@` is consumed by the matcher but not
stored.

Resolution is performed against a `UserDirectory` mapping handle → user id.
Unknown handles are dropped silently (the mention is not promoted to a
notification). This keeps mention parsing pure and decoupled from the user
store.

Public surface:

- `extract_mentions(body: str) -> list[str]` — ordered, deduplicated, lowercase
- `UserDirectory.lookup(handle: str) -> User | None`

---

## Notifications

A `Notifier` accepts mention events from the comment subsystem and decides
whether to enqueue a delivery record or drop it.

Suppression reasons (recorded explicitly on the queue row so audits can
distinguish "lost" from "intentionally dropped"):

| Reason         | Trigger                                                            |
| -------------- | ------------------------------------------------------------------ |
| `disabled`     | Target user has notifications disabled                             |
| `quiet_hours`  | Target user is inside their quiet-hours window at enqueue time     |
| `rate_limited` | Target user already received N notifications in the sliding window |
| `self`         | Author mentioned themselves                                        |

Suppression is evaluated **at enqueue time** using an injected `clock` (default
`datetime.now(tz=utc)`). This makes quiet-hours and rate-limit behaviour
deterministic under test.

### Quiet hours

`User.quiet_hours` is an optional `(start, end)` pair of `time` values
interpreted in the user's local timezone. Windows wrapping midnight (e.g.
22:00 → 07:00) are handled by inverting the comparison.

### Rate limiting

Per-user sliding window: at most `rate_limit_max` notifications per
`rate_limit_window` (defaulting to 10 per 60 seconds). Counts are kept
in-memory on the `Notifier` instance — restart-safe persistence is out of
scope for Phase F.

### Public surface

```
Notifier(directory, clock=..., rate_limit_max=10, rate_limit_window=60)
  .notify_comment(comment, body) -> list[NotificationEvent]
  .pending() -> tuple[NotificationEvent, ...]
  .suppressed() -> tuple[SuppressedEvent, ...]
  .drain() -> tuple[NotificationEvent, ...]
```

`NotificationEvent` carries `(user_id, comment_id, target, scope, enqueued_at)`.
`SuppressedEvent` adds a `reason` from the table above.

---

## JSON import / export

`portability.py` snapshots and restores the entire domain state as a single
deterministic JSON document.

### Envelope

```
{
  "format_version": 1,
  "schema_version": 3,
  "projects": [...],
  "work_items": [...],
  "transitions": [...],
  "spaces": [...],
  "pages": [...],
  "page_versions": [...],
  "links": [...],
  "work_item_comments": [...],
  "page_comments": [...]
}
```

`format_version` (`PORTABILITY_FORMAT_VERSION`) is decoupled from
`DOMAIN_SCHEMA_VERSION`: a future schema migration can keep emitting the
same envelope shape, and a future envelope format can target the same
schema. The reader validates both before touching the database.

### Determinism

Rows inside each collection are sorted by primary key. JSON is serialised
with stable key order. Re-exporting an imported snapshot is byte-identical
to the original — this is asserted by
`tests/test_portability.py::test_round_trip_re_export_is_byte_identical`.

`json_indent` is configurable; the round-trip invariant holds for any
indent setting.

### Import contract

`import_snapshot(store, envelope)` enforces:

1. **Envelope shape** — collection keys, version fields, types.
2. **Schema/format compatibility** — both versions must match the current
   constants.
3. **Fresh target** — the destination store must contain zero rows across
   all nine canonical tables. A non-empty target raises
   `DomainImportError` *before* any insert.

Rows are inserted in FK-safe order (`_COLLECTION_ORDER`). After insert the
importer reseeds two derived counters:

- `project_sequences` — rebuilt by parsing the `KEY-NNN` suffix of every
  imported work item so future `create_work_item` calls don't collide.
- `sqlite_sequence` — bumped for `work_item_transitions.transition_id`
  and `page_versions.version_id` (the two AUTOINCREMENT columns) so new
  inserts don't conflict with the imported ids. The reserved
  `sqlite_sequence` table is never CREATEd; the importer INSERT-OR-UPDATEs
  the existing row.

### What is **not** in the snapshot

- **Idempotency cache** — request-scoped, rebuilds itself from traffic.
- **Notification queue / suppression log** — observable but transient.

Both are deliberately excluded so a restored snapshot is a clean
collaboration substrate, not a re-creation of a moment-in-time runtime.

### Versioning policy

- `PORTABILITY_FORMAT_VERSION` bumps when the envelope key set or row
  shape changes.
- `DOMAIN_SCHEMA_VERSION` bumps when the SQLite schema changes.
- Mismatch on either field raises `DomainImportError` rather than
  attempting a best-effort migration. A future migrator will live in its
  own module.
