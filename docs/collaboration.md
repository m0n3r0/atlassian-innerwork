# Collaboration (Phase F)

Phase F adds two cross-cutting facilities on top of the comment + idempotency
baseline:

1. **Mentions & notifications** — `src/innerwork/notify.py`
2. **JSON import/export round-trip** — `src/innerwork/portability.py`

Both modules are pure / in-process. No external connectors (email, Slack,
webhooks) are dispatched — the notifier records every delivered notification
and every suppression with its reason so downstream adapters (added in later
phases) can drain the logs at their own cadence. The module never claims a
third-party connector exists.

---

## Mentions

A mention is an `@handle` token embedded in a comment body or page body.
Handles are matched against:

    (?:^|(?<=[^\w]))@([A-Za-z0-9][A-Za-z0-9_-]{1,31})

- The leading `@` must be at start-of-string or preceded by a non-word
  character. This means `alice@example.com` does **not** produce a mention.
- The first character must be alphanumeric; the remaining 1–31 characters
  may also include `_` and `-`. Total handle length is 2–32 characters.
- Matches are normalised to lowercase; the leading `@` is consumed.

### Public surface

```
parse_mentions(body: str) -> tuple[str, ...]
```

Returns the ordered, deduplicated lowercase tuple of handles in `body`.
Raises `TypeError` if `body` is not a `str`. Unknown handles are *not*
resolved at this layer — that is the directory's job.

```
UserDirectory(users: Iterable[User] = ())
  .register(user: User) -> None
  .get(user_id: str) -> User | None
  .get_by_handle(handle: str) -> User | None
  .resolve_handles(handles: Iterable[str]) -> tuple[User, ...]
```

`resolve_handles` is the bridge from `parse_mentions` output to concrete
users: it silently drops unknown handles (mentions are best-effort and must
not raise on typos) and deduplicates by `user_id`.

A `User` is `(user_id, handle, display_name)`; all three must be non-blank
and the handle must itself satisfy the mention regex.

---

## Notifications

### Event kinds (closed vocabulary)

```
EVENT_KINDS = frozenset({
    "work_item.assigned",
    "work_item.transitioned",
    "work_item.mentioned",
    "page.mentioned",
    "page.subscribed_update",
})
```

`validate_event_kind(kind)` rejects any string outside this set. Keeping the
vocabulary closed keeps preference auditing and routing tractable.

### Per-user preferences

```
NotificationPreferences(
    user_id: str,
    enabled_kinds: frozenset[str] = frozenset(EVENT_KINDS),
    quiet_hours: QuietHours | None = None,
    page_subscriptions: frozenset[str] = frozenset(),
)
```

- Every kind is opt-in by default; constructor rejects unknown kinds.
- `subscribes_to(page_id)` powers the `page.subscribed_update` fan-out.

### Quiet hours (UTC)

```
QuietHours(start_hour: int, end_hour: int)
```

- Integer UTC hours in `[0, 24)`. Sub-hour resolution is intentionally out
  of scope for Phase F.
- `start_hour == end_hour` means quiet hours are disabled.
- Wrap-around windows (e.g. `22 -> 6`) are supported via inverted comparison.
- `is_quiet(now)` requires a timezone-aware datetime and normalises to UTC
  before bucketing.

Suppressed notifications are **never queued or delivered** — they are only
recorded on the `Notifier.suppressed` log with `reason="quiet_hours"`.

### Token-bucket rate limiting

```
RateLimitConfig(capacity: int = 5, refill_per_second: float = 1/30)
```

- Per-user token bucket; one token consumed per delivered notification.
- Default: burst of 5, then one token every 30 seconds.
- Refill is computed against `event.occurred_at` (driven by the notifier's
  injected `clock`), so behaviour is deterministic in tests.

Order of checks inside `Notifier.dispatch`, evaluated per target user:

1. Unknown `user_id` in the directory → suppressed `disabled`.
2. Target user is the actor (matched by `user_id` *or* `handle`) →
   suppressed `self`.
3. `prefs.wants(event.kind)` is false → suppressed `disabled`.
4. Quiet hours active at `event.occurred_at` → suppressed `quiet_hours`.
5. No token available → suppressed `rate_limited`.
6. Otherwise delivered: a `Notification` is appended to `dispatched` and
   included in the return tuple.

Suppression reasons live in `SuppressedNotification.reason`:

| Reason         | Trigger                                                      |
| -------------- | ------------------------------------------------------------ |
| `disabled`     | Unknown user, or target has opted out of this event kind     |
| `self`         | Actor and target are the same user                           |
| `quiet_hours`  | Target is inside their UTC quiet window at `occurred_at`     |
| `rate_limited` | Target's token bucket is empty at `occurred_at`              |

### Notifier surface

```
Notifier(
    directory: UserDirectory,
    preferences: Mapping[str, NotificationPreferences] | None = None,
    *,
    rate_limit: RateLimitConfig | None = None,
    clock: callable[[], datetime] | None = None,
)
  .set_preferences(prefs) / .preferences_for(user_id)
  .subscribe_page(user_id, page_id) / .unsubscribe_page(user_id, page_id)
  .subscribers_for_page(page_id) -> tuple[str, ...]
  .dispatch(event: NotificationEvent) -> tuple[Notification, ...]
  .dispatched: list[Notification]
  .suppressed: list[SuppressedNotification]
```

`dispatch` is synchronous and single-threaded; it returns the tuple of
notifications actually delivered for that event. The `dispatched` and
`suppressed` lists are append-only logs intended for observability and
test assertions — not queues to be drained.

### Event and notification records

```
NotificationEvent(
    kind, actor, target_user_ids: tuple[str, ...], occurred_at: datetime,
    work_item_id=None, page_id=None, comment_id=None,
    summary="", payload={},
)
```

`occurred_at` must be timezone-aware; `target_user_ids` must be a tuple.

```
Notification(
    kind, user_id, actor, occurred_at: str, summary,
    work_item_id=None, page_id=None, comment_id=None,
)
```

`occurred_at` is serialised as `YYYY-MM-DDTHH:MM:SSZ` in UTC. `summary`
defaults to a deterministic string built from kind, actor, work-item /
page id, and target — never invented marketing copy.

### Convenience builders

The domain layer should construct events via the provided builders so the
shape stays canonical:

- `build_assignment_event(actor, assignee_user_id, work_item_id, occurred_at)`
- `build_transition_event(actor, watcher_user_ids, work_item_id, occurred_at, ...)`
- `build_mention_event_for_work_item(actor, mentioned_user_ids, work_item_id, comment_id, occurred_at)`
- `build_mention_event_for_page(actor, mentioned_user_ids, page_id, comment_id, occurred_at)`
- `build_page_subscription_event(actor, subscriber_user_ids, page_id, occurred_at, ...)`

---

## JSON import / export

`portability.py` snapshots and restores the entire canonical domain state
as a single deterministic JSON document.

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

`PORTABILITY_FORMAT_VERSION` (the envelope shape) is decoupled from
`DOMAIN_SCHEMA_VERSION` (the SQLite schema). The reader validates both
before touching the database.

### Public surface

```
export_domain(store: DomainStore) -> dict[str, Any]
export_domain_json(store: DomainStore, *, indent: int | None = 2) -> str
import_domain(store: DomainStore, payload: Mapping[str, Any]) -> dict[str, int]
import_domain_json(store: DomainStore, raw: str) -> dict[str, int]
```

`import_domain` / `import_domain_json` return a `{collection: rows_inserted}`
count summary. Both raise `DomainImportError` (subclass of `ValueError`) on
any contract violation.

### Determinism

Rows inside each collection are sorted by primary key. `export_domain_json`
emits JSON with stable key order. Re-exporting an imported snapshot is
byte-identical to the original; this is the contract anchor for round-trip
testing.

### Import contract

`import_domain(store, payload)` enforces, in order:

1. **Envelope shape** — `format_version` matches `PORTABILITY_FORMAT_VERSION`,
   `schema_version` matches `DOMAIN_SCHEMA_VERSION`, every present
   collection key is a list.
2. **Fresh target** — every one of the nine canonical tables (`projects`,
   `work_items`, `work_item_transitions`, `spaces`, `pages`, `page_versions`,
   `work_item_page_links`, `work_item_comments`, `page_comments`) must
   contain zero rows. A non-empty target raises `DomainImportError`
   *before* any insert, so partial overlays cannot silently corrupt FK or
   sequence state.
3. **FK-safe insert order** — `_COLLECTION_ORDER` (parents before children).

After insert the importer reseeds two derived counters:

- `project_sequences` is wiped and rebuilt by parsing the `KEY-NNN` suffix
  of every imported work item, so future `create_work_item` calls don't
  collide.
- `sqlite_sequence` is bumped (INSERT-OR-UPDATE — the reserved table is
  never CREATEd) for `work_item_transitions.transition_id` and
  `page_versions.version_id`, the two AUTOINCREMENT columns, so newly
  allocated ids don't conflict with the imported ones.

### What is **not** in the snapshot

- **Idempotency cache** — request-scoped, rebuilds itself from traffic.
- **Notification dispatched / suppressed logs** — observable but transient,
  owned by `notify.py` outside the persisted domain.

Both are deliberately excluded so a restored snapshot is a clean
collaboration substrate, not a re-creation of a moment-in-time runtime.

### Versioning policy

- `PORTABILITY_FORMAT_VERSION` bumps when the envelope key set or row
  shape changes.
- `DOMAIN_SCHEMA_VERSION` bumps when the SQLite schema changes.
- Mismatch on either field raises `DomainImportError` rather than
  attempting a best-effort migration. A future migrator will live in its
  own module.
