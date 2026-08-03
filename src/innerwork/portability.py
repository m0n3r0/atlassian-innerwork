"""Domain export/import — deterministic JSON round-trip.

The portability module is a thin, pure shim on top of :class:`DomainStore`.
``export_domain`` snapshots every persisted row into a plain ``dict`` with
deterministic key ordering. ``import_domain`` replays a snapshot into a
*fresh* store (empty domain tables), preserving auto-assigned identifiers
(``transition_id``, ``version_id``) so a re-export produces byte-identical
JSON.

The contract intentionally covers only the canonical Phase A–F domain
tables (projects, work_items, transitions, spaces, pages, page_versions,
links, work_item_comments, page_comments). Idempotency-cache rows and
transient state owned by other modules (``notify``) are NOT part of the
portable surface.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from typing import Any, TextIO

from .audit import AuditEvent, make_event
from .domain_store import DOMAIN_SCHEMA_VERSION, DomainStore
from .field_acl import redact_for

__all__ = (
    "PORTABILITY_FORMAT_VERSION",
    "PORTABILITY_FORMAT_VERSION_AUDIT",
    "DomainImportError",
    "export_domain",
    "export_domain_json",
    "export_domain_json_stream",
    "import_domain",
    "import_domain_json",
)


# Bump if the portable wire format itself changes shape, independent of
# the underlying DB schema version.
PORTABILITY_FORMAT_VERSION = 1

# Emitted ONLY when `export --include-audit` is used (or the API-level
# `include_audit=True` parameter). Default exports stay at version 1 so
# existing snapshots round-trip byte-identical.
PORTABILITY_FORMAT_VERSION_AUDIT = 2

# Ordered list of top-level collection keys in every export. The order is
# load-bearing for both byte-stable round-trip and for FK-safe inserts.
_COLLECTION_ORDER: tuple[str, ...] = (
    "projects",
    "work_items",
    "transitions",
    "spaces",
    "pages",
    "page_versions",
    "links",
    "work_item_comments",
    "page_comments",
)


class DomainImportError(ValueError):
    """Raised when an import payload is malformed or its schema is unsupported."""


# ----------------------------------------------------------------- export

def export_domain(
    store: DomainStore,
    *,
    include_audit: bool = False,
    audit_actor_kind: str = "system",
) -> dict[str, Any]:
    """Return a deterministic snapshot of every persisted domain row.

    Output shape (default):::

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
          "page_comments": [...],
        }

    With ``include_audit=True`` the ``format_version`` bumps to
    :data:`PORTABILITY_FORMAT_VERSION_AUDIT` (2) and a trailing ``audit``
    collection is appended — the sink's rows, redacted for
    ``audit_actor_kind`` (default ``"system"`` → verbatim). The audit
    collection is NOT part of :data:`_COLLECTION_ORDER`; default exports
    stay byte-identical to version 1.

    Each list is sorted by a stable primary key so identical stores produce
    identical bytes (modulo dict-key insertion order, preserved by Python
    3.7+ and ``json.dumps(sort_keys=False)``).
    """

    format_version = (
        PORTABILITY_FORMAT_VERSION_AUDIT if include_audit else PORTABILITY_FORMAT_VERSION
    )
    payload: dict[str, Any] = {
        "format_version": format_version,
        "schema_version": DOMAIN_SCHEMA_VERSION,
    }
    with store._connect() as connection:  # noqa: SLF001 — portability owns the schema
        payload["projects"] = _rows(
            connection,
            "SELECT project_id, key, name, owner, created_at "
            "FROM projects ORDER BY project_id",
            ("project_id", "key", "name", "owner", "created_at"),
        )
        payload["work_items"] = _rows(
            connection,
            "SELECT work_item_id, project_id, key, title, description, "
            "state, assignee, created_at, updated_at "
            "FROM work_items ORDER BY work_item_id",
            (
                "work_item_id",
                "project_id",
                "key",
                "title",
                "description",
                "state",
                "assignee",
                "created_at",
                "updated_at",
            ),
        )
        payload["transitions"] = _rows(
            connection,
            "SELECT transition_id, work_item_id, from_state, to_state, "
            "actor, occurred_at, reason "
            "FROM work_item_transitions ORDER BY transition_id",
            (
                "transition_id",
                "work_item_id",
                "from_state",
                "to_state",
                "actor",
                "occurred_at",
                "reason",
            ),
        )
        payload["spaces"] = _rows(
            connection,
            "SELECT space_id, key, name, owner, created_at "
            "FROM spaces ORDER BY space_id",
            ("space_id", "key", "name", "owner", "created_at"),
        )
        payload["pages"] = _rows(
            connection,
            "SELECT page_id, space_id, current_version, created_at, updated_at "
            "FROM pages ORDER BY page_id",
            ("page_id", "space_id", "current_version", "created_at", "updated_at"),
        )
        payload["page_versions"] = _rows(
            connection,
            "SELECT version_id, page_id, version_number, title, body, author, created_at "
            "FROM page_versions ORDER BY version_id",
            (
                "version_id",
                "page_id",
                "version_number",
                "title",
                "body",
                "author",
                "created_at",
            ),
        )
        payload["links"] = _rows(
            connection,
            "SELECT link_id, work_item_id, page_id, kind, created_by, created_at "
            "FROM work_item_page_links ORDER BY link_id",
            (
                "link_id",
                "work_item_id",
                "page_id",
                "kind",
                "created_by",
                "created_at",
            ),
        )
        payload["work_item_comments"] = _rows(
            connection,
            "SELECT comment_id, work_item_id, author, body, created_at "
            "FROM work_item_comments ORDER BY comment_id",
            ("comment_id", "work_item_id", "author", "body", "created_at"),
        )
        payload["page_comments"] = _rows(
            connection,
            "SELECT comment_id, page_id, author, body, created_at "
            "FROM page_comments ORDER BY comment_id",
            ("comment_id", "page_id", "author", "body", "created_at"),
        )
    if include_audit:
        payload["audit"] = _export_audit_rows(store, audit_actor_kind)
    return payload


def _export_audit_rows(store: DomainStore, actor_kind: str) -> list[dict[str, Any]]:
    """Snapshot the wired sink's rows as JSON objects, redacted per actor kind.

    Raises :class:`DomainImportError` when ``include_audit`` is requested but
    no sink is wired — an export that silently emits an empty audit
    collection would be dishonest. Rows are the sink's ``query()`` output in
    its native order; every row passes through ``field_acl.redact_for``
    (``"system"`` bypasses all ACLs → verbatim; ``"user"``/``"service"`` mask
    the ``actor`` field per ``DEFAULT_POLICY``).
    """

    sink = getattr(store, "audit_sink", None)
    if sink is None:
        raise DomainImportError(
            "--include-audit requires an audit sink; pass --audit-log or "
            "set INNERWORK_AUDIT_DB"
        )
    return [
        redact_for(actor_kind, "AuditEvent", event.as_jsonable())
        for event in sink.query()
    ]


def export_domain_json(
    store: DomainStore,
    *,
    indent: int | None = 2,
    include_audit: bool = False,
    audit_actor_kind: str = "system",
) -> str:
    """Return ``export_domain(store)`` serialized to deterministic JSON.

    The payload (including any ``audit`` collection) is snapshotted BEFORE
    ``_audit_portability`` emits the ``portability_export`` event, so a
    payload never contains the export event it just triggered.
    """

    payload = export_domain(
        store, include_audit=include_audit, audit_actor_kind=audit_actor_kind
    )
    _audit_portability(
        store,
        action="export",
        counts={
            k: len(v) for k, v in payload.items() if isinstance(v, list)
        },
        format_version=(
            PORTABILITY_FORMAT_VERSION_AUDIT
            if include_audit
            else PORTABILITY_FORMAT_VERSION
        ),
    )
    return json.dumps(payload, indent=indent, sort_keys=False)


# Streaming mirror of the per-collection SELECTs in export_domain, kept in
# lockstep with the queries above (the byte-identity referee test in
# tests/test_portability_stream.py enforces parity — any drift breaks it).
_STREAM_COLLECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "projects",
        "SELECT project_id, key, name, owner, created_at "
        "FROM projects ORDER BY project_id",
        ("project_id", "key", "name", "owner", "created_at"),
    ),
    (
        "work_items",
        "SELECT work_item_id, project_id, key, title, description, "
        "state, assignee, created_at, updated_at "
        "FROM work_items ORDER BY work_item_id",
        (
            "work_item_id",
            "project_id",
            "key",
            "title",
            "description",
            "state",
            "assignee",
            "created_at",
            "updated_at",
        ),
    ),
    (
        "transitions",
        "SELECT transition_id, work_item_id, from_state, to_state, "
        "actor, occurred_at, reason "
        "FROM work_item_transitions ORDER BY transition_id",
        (
            "transition_id",
            "work_item_id",
            "from_state",
            "to_state",
            "actor",
            "occurred_at",
            "reason",
        ),
    ),
    (
        "spaces",
        "SELECT space_id, key, name, owner, created_at "
        "FROM spaces ORDER BY space_id",
        ("space_id", "key", "name", "owner", "created_at"),
    ),
    (
        "pages",
        "SELECT page_id, space_id, current_version, created_at, updated_at "
        "FROM pages ORDER BY page_id",
        ("page_id", "space_id", "current_version", "created_at", "updated_at"),
    ),
    (
        "page_versions",
        "SELECT version_id, page_id, version_number, title, body, author, created_at "
        "FROM page_versions ORDER BY version_id",
        (
            "version_id",
            "page_id",
            "version_number",
            "title",
            "body",
            "author",
            "created_at",
        ),
    ),
    (
        "links",
        "SELECT link_id, work_item_id, page_id, kind, created_by, created_at "
        "FROM work_item_page_links ORDER BY link_id",
        ("link_id", "work_item_id", "page_id", "kind", "created_by", "created_at"),
    ),
    (
        "work_item_comments",
        "SELECT comment_id, work_item_id, author, body, created_at "
        "FROM work_item_comments ORDER BY comment_id",
        ("comment_id", "work_item_id", "author", "body", "created_at"),
    ),
    (
        "page_comments",
        "SELECT comment_id, page_id, author, body, created_at "
        "FROM page_comments ORDER BY comment_id",
        ("comment_id", "page_id", "author", "body", "created_at"),
    ),
)


def export_domain_json_stream(
    store: DomainStore,
    out: TextIO,
    *,
    indent: int | None = 2,
    batch_size: int = 500,
    include_audit: bool = False,
    audit_actor_kind: str = "system",
) -> dict[str, int]:
    """Write the portability envelope to ``out`` incrementally.

    Byte-identical to ``json.dumps(export_domain(store, include_audit=...,
    audit_actor_kind=...), indent=indent, sort_keys=False)`` for the same
    store and settings — the referee gate. Rows are fetched in
    ``batch_size`` batches via ``fetchmany`` (never ``fetchall``), so peak
    additional memory is bounded by one batch, not by store size.

    ``out`` is owned by the caller: this function writes and flushes but
    never closes it. The CLI streams to a temp file for ``--out`` and to
    stdout otherwise, appending the trailing ``\\n`` after the call.
    ``_audit_portability`` fires only after the envelope has been fully
    written (a failed export records no ``portability_export`` event).
    Returns ``{collection: rows_written}`` — same shape as
    :func:`import_domain`'s return, ``audit`` included when requested.
    """

    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")

    format_version = (
        PORTABILITY_FORMAT_VERSION_AUDIT if include_audit else PORTABILITY_FORMAT_VERSION
    )
    # Fail-before-write: the audit snapshot (and its sink-missing check)
    # happens BEFORE the first byte so a missing sink leaves ``out`` empty.
    audit_rows = _export_audit_rows(store, audit_actor_kind) if include_audit else None
    collection_keys = _COLLECTION_ORDER + (("audit",) if include_audit else ())
    counts: dict[str, int] = {}

    if indent is None:
        pad = ""
        out.write("{")
        out.write(f'"format_version": {format_version}, ')
        out.write(f'"schema_version": {DOMAIN_SCHEMA_VERSION}, ')
    else:
        pad = " " * indent
        out.write("{")
        out.write(f'\n{pad}"format_version": {format_version},')
        out.write(f'\n{pad}"schema_version": {DOMAIN_SCHEMA_VERSION},')

    with store._connect() as connection:  # noqa: SLF001 — portability owns the schema
        for index, key in enumerate(collection_keys):
            last = index == len(collection_keys) - 1
            if indent is None:
                out.write(f'"{key}": ')
            else:
                out.write(f'\n{pad}"{key}": ')
            if key == "audit":
                count = _write_stream_array(out, iter(audit_rows or ()), indent=indent, key_pad=pad)
            else:
                query, columns = _stream_collection_query(key)
                cursor = connection.execute(query)
                count = _write_stream_array(
                    out,
                    _iter_batched_rows(cursor, columns, batch_size),
                    indent=indent,
                    key_pad=pad,
                )
            counts[key] = count
            if not last:
                out.write(", " if indent is None else ",")
    out.write("}" if indent is None else "\n}")
    out.flush()

    _audit_portability(
        store,
        action="export",
        counts=counts,
        format_version=format_version,
    )
    return counts


def _stream_collection_query(key: str) -> tuple[str, tuple[str, ...]]:
    for name, query, columns in _STREAM_COLLECTIONS:
        if name == key:
            return query, columns
    raise KeyError(key)  # pragma: no cover — collection_keys mirrors _COLLECTION_ORDER


def _iter_batched_rows(
    cursor: Any,
    columns: tuple[str, ...],
    batch_size: int,
) -> Iterator[dict[str, Any]]:
    """Yield row dicts from ``cursor`` in bounded ``fetchmany`` batches."""
    while True:
        batch = cursor.fetchmany(batch_size)
        if not batch:
            return
        for raw in batch:
            yield dict(zip(columns, raw, strict=True))


def _write_stream_array(
    out: TextIO,
    rows: Iterator[dict[str, Any]],
    *,
    indent: int | None,
    key_pad: str,
) -> int:
    """Write one collection value (``[...]`` / ``[]``) for ``rows``.

    Returns the number of rows written. Pretty mode reproduces the
    ``json.dumps(payload, indent=...)`` grammar exactly: each row is
    ``json.dumps(row, indent=indent)`` re-indented by ``2 * indent``
    spaces; compact mode mirrors the default separators ``(', ', ': ')``.
    """
    if indent is None:
        return _write_stream_array_compact(out, rows)
    return _write_stream_array_pretty(out, rows, indent=indent, key_pad=key_pad)


def _write_stream_array_compact(
    out: TextIO, rows: Iterator[dict[str, Any]]
) -> int:
    count = 0
    first = True
    for row in rows:
        if first:
            out.write("[")
            out.write(json.dumps(row, ensure_ascii=True, sort_keys=False))
            first = False
        else:
            out.write(", ")
            out.write(json.dumps(row, ensure_ascii=True, sort_keys=False))
        count += 1
    out.write("[]" if first else "]")
    out.flush()
    return count


def _write_stream_array_pretty(
    out: TextIO,
    rows: Iterator[dict[str, Any]],
    *,
    indent: int,
    key_pad: str,
) -> int:
    row_pad = " " * (2 * indent)
    count = 0
    first = True
    for row in rows:
        if first:
            out.write("[")
            first = False
        else:
            out.write(",")
        out.write("\n" + row_pad + _reindent_row(row, indent, row_pad))
        count += 1
    if first:
        out.write("[]")
    else:
        out.write("\n" + key_pad + "]")
    out.flush()
    return count


def _reindent_row(row: dict[str, Any], indent: int, row_pad: str) -> str:
    """``json.dumps(row, indent=indent)`` with every line prefixed by ``row_pad``.

    The caller prepends the leading ``row_pad`` (via ``"\\n" + row_pad``), so
    this only re-indents the *continuation* lines.
    """
    raw = json.dumps(row, indent=indent, ensure_ascii=True, sort_keys=False)
    return raw.replace("\n", "\n" + row_pad)


def _audit_portability(
    store: DomainStore,
    *,
    action: str,
    counts: dict[str, int],
    format_version: int,
) -> None:
    """Best-effort audit emission for portability export/import.

    No-op when the store has no audit sink wired (phase 5/6 callers).
    Records the *effective* ``format_version`` (2 for audit-bearing exports)
    so the audit trail itself distinguishes audit-bearing payloads.
    """

    if getattr(store, "audit_sink", None) is None:
        return
    surface = "portability_export" if action == "export" else "portability_import"
    store._audit(  # noqa: SLF001 — portability is a peer of the store
        surface=surface,
        actor="portability",
        entity_kind="Domain",
        entity_id=str(store.path),
        action=action,
        before=None,
        after=None,
        metadata={"counts": counts, "format_version": format_version},
    )


def _rows(
    connection: Any,
    query: str,
    columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows = connection.execute(query).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


# ----------------------------------------------------------------- import

def import_domain(store: DomainStore, payload: Mapping[str, Any]) -> dict[str, int]:
    """Replay ``payload`` into a *fresh* ``store``.

    The store MUST be empty of every collection covered by the payload
    (projects, work items, spaces, pages, links, comments). Importing into
    a non-empty store raises :class:`DomainImportError` so partial overlays
    cannot silently corrupt FK or sequence state.

    Returns a count summary ``{collection: rows_inserted}``.
    """

    format_version = _validate_envelope(payload)
    _validate_fresh_target(store)
    audit_events = (
        _validate_audit_rows(payload)
        if format_version == PORTABILITY_FORMAT_VERSION_AUDIT
        else ()
    )
    _validate_audit_sink(store, audit_events)
    counts: dict[str, int] = {}
    with store._connect() as connection:  # noqa: SLF001
        # FK-safe ordering — parents first.
        counts["projects"] = _insert_many(
            connection,
            payload.get("projects", []),
            "INSERT INTO projects(project_id, key, name, owner, created_at) "
            "VALUES (:project_id, :key, :name, :owner, :created_at)",
        )
        counts["work_items"] = _insert_many(
            connection,
            payload.get("work_items", []),
            "INSERT INTO work_items("
            "work_item_id, project_id, key, title, description, "
            "state, assignee, created_at, updated_at"
            ") VALUES ("
            ":work_item_id, :project_id, :key, :title, :description, "
            ":state, :assignee, :created_at, :updated_at"
            ")",
        )
        counts["transitions"] = _insert_many(
            connection,
            payload.get("transitions", []),
            "INSERT INTO work_item_transitions("
            "transition_id, work_item_id, from_state, to_state, "
            "actor, occurred_at, reason"
            ") VALUES ("
            ":transition_id, :work_item_id, :from_state, :to_state, "
            ":actor, :occurred_at, :reason"
            ")",
        )
        counts["spaces"] = _insert_many(
            connection,
            payload.get("spaces", []),
            "INSERT INTO spaces(space_id, key, name, owner, created_at) "
            "VALUES (:space_id, :key, :name, :owner, :created_at)",
        )
        counts["pages"] = _insert_many(
            connection,
            payload.get("pages", []),
            "INSERT INTO pages("
            "page_id, space_id, current_version, created_at, updated_at"
            ") VALUES ("
            ":page_id, :space_id, :current_version, :created_at, :updated_at"
            ")",
        )
        counts["page_versions"] = _insert_many(
            connection,
            payload.get("page_versions", []),
            "INSERT INTO page_versions("
            "version_id, page_id, version_number, title, body, author, created_at"
            ") VALUES ("
            ":version_id, :page_id, :version_number, :title, :body, :author, :created_at"
            ")",
        )
        counts["links"] = _insert_many(
            connection,
            payload.get("links", []),
            "INSERT INTO work_item_page_links("
            "link_id, work_item_id, page_id, kind, created_by, created_at"
            ") VALUES ("
            ":link_id, :work_item_id, :page_id, :kind, :created_by, :created_at"
            ")",
        )
        counts["work_item_comments"] = _insert_many(
            connection,
            payload.get("work_item_comments", []),
            "INSERT INTO work_item_comments("
            "comment_id, work_item_id, author, body, created_at"
            ") VALUES ("
            ":comment_id, :work_item_id, :author, :body, :created_at"
            ")",
        )
        counts["page_comments"] = _insert_many(
            connection,
            payload.get("page_comments", []),
            "INSERT INTO page_comments("
            "comment_id, page_id, author, body, created_at"
            ") VALUES ("
            ":comment_id, :page_id, :author, :body, :created_at"
            ")",
        )
        _rebuild_project_sequences(connection, payload.get("work_items", []))
        _bump_autoincrement(
            connection, "work_item_transitions", payload.get("transitions", [])
        )
        _bump_autoincrement(connection, "page_versions", payload.get("page_versions", []))
    # Restore pass — AFTER the 9 domain collections and sequence rebuild, in
    # payload order. The portability_import event from `_audit_portability`
    # below is recorded after this pass, so an import's own event never
    # collides with a payload row.
    for event in audit_events:
        store.audit_sink.record(event)
    if format_version == PORTABILITY_FORMAT_VERSION_AUDIT:
        counts["audit"] = len(audit_events)
    _audit_portability(
        store, action="import", counts=counts, format_version=format_version
    )
    return counts


def import_domain_json(store: DomainStore, raw: str) -> dict[str, int]:
    """Parse ``raw`` JSON and call :func:`import_domain`."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DomainImportError(f"payload is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DomainImportError("payload root must be a JSON object")
    return import_domain(store, payload)


# ----------------------------------------------------------------- helpers

def _validate_envelope(payload: Mapping[str, Any]) -> int:
    """Validate the envelope header; return the effective ``format_version``.

    Accepts ``format_version`` 1 (legacy) and 2 (audit-bearing). The version
    is authoritative: a v1 payload carrying an ``audit`` key and a v2
    payload missing it are both rejected loudly — the envelope must not lie
    about what it carries.
    """

    fmt = payload.get("format_version")
    if fmt not in (PORTABILITY_FORMAT_VERSION, PORTABILITY_FORMAT_VERSION_AUDIT):
        raise DomainImportError(
            f"unsupported format_version: expected {PORTABILITY_FORMAT_VERSION} "
            f"or {PORTABILITY_FORMAT_VERSION_AUDIT}, got {fmt!r}"
        )
    schema = payload.get("schema_version")
    if schema != DOMAIN_SCHEMA_VERSION:
        raise DomainImportError(
            f"schema_version mismatch: store at {DOMAIN_SCHEMA_VERSION}, payload at {schema!r}"
        )
    for key in _COLLECTION_ORDER:
        if key in payload and not isinstance(payload[key], list):
            raise DomainImportError(f"collection {key!r} must be a list")
    if "audit" in payload and fmt == PORTABILITY_FORMAT_VERSION:
        raise DomainImportError("audit collection requires format_version 2")
    if fmt == PORTABILITY_FORMAT_VERSION_AUDIT and "audit" not in payload:
        raise DomainImportError("format_version 2 payload must include an audit collection")
    if "audit" in payload and not isinstance(payload["audit"], list):
        raise DomainImportError("collection 'audit' must be a list")
    return fmt


def _validate_audit_rows(payload: Mapping[str, Any]) -> tuple[AuditEvent, ...]:
    """Strictly validate the ``audit`` collection, returning reconstructed events.

    Every row is rebuilt through :func:`audit.make_event` with all fields
    taken from the row, so ``AuditEvent.__post_init__`` enforces the closed
    enums (``surface`` ∈ :data:`AUDIT_SURFACES`, ``actor_kind`` ∈
    {system,user,service}) and non-blank fields before anything is written —
    the no-event-injection gate. Raises :class:`DomainImportError` naming the
    offending row index and field.
    """

    raw = payload.get("audit", [])
    events: list[AuditEvent] = []
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise DomainImportError(f"audit row {index} must be a JSON object")
        if not isinstance(row.get("ts"), (int, float)):
            raise DomainImportError(f"audit row {index}: field 'ts' must be a number")
        if row.get("before") is not None and not isinstance(row.get("before"), dict):
            raise DomainImportError(f"audit row {index}: field 'before' must be null or an object")
        if row.get("after") is not None and not isinstance(row.get("after"), dict):
            raise DomainImportError(f"audit row {index}: field 'after' must be null or an object")
        if row.get("metadata") is not None and not isinstance(row.get("metadata"), dict):
            raise DomainImportError(f"audit row {index}: field 'metadata' must be an object")
        try:
            event = make_event(
                event_id=row["event_id"],
                ts=row["ts"],
                actor=row["actor"],
                actor_kind=row["actor_kind"],
                surface=row["surface"],
                entity_kind=row["entity_kind"],
                entity_id=row["entity_id"],
                action=row["action"],
                before=row.get("before"),
                after=row.get("after"),
                metadata=row.get("metadata"),
            )
        except KeyError as exc:
            raise DomainImportError(
                f"audit row {index}: missing required field {exc.args[0]!r}"
            ) from exc
        except ValueError as exc:
            raise DomainImportError(f"audit row {index}: {exc}") from exc
        events.append(event)
    return tuple(events)


def _validate_audit_sink(store: DomainStore, events: tuple[AuditEvent, ...]) -> None:
    """Enforce the import's audit pre-conditions before anything is written.

    1. A payload carrying audit rows requires a wired sink — restoring them
       into a store with no sink would silently drop them.
    2. All-or-nothing ``event_id`` conflict pre-check: any payload event_id
       already present in the sink aborts the whole import (domain rows
       included) before any INSERT.
    """

    if not events:
        return
    sink = getattr(store, "audit_sink", None)
    if sink is None:
        raise DomainImportError(
            "payload contains audit rows but no audit sink configured; "
            "pass --audit-log or set INNERWORK_AUDIT_DB"
        )
    existing = {event.event_id for event in sink.query()}
    for event in events:
        if event.event_id in existing:
            raise DomainImportError(
                f"audit event_id {event.event_id} already exists in the audit sink"
            )


def _validate_fresh_target(store: DomainStore) -> None:
    with store._connect() as connection:  # noqa: SLF001
        for table in (
            "projects",
            "work_items",
            "work_item_transitions",
            "spaces",
            "pages",
            "page_versions",
            "work_item_page_links",
            "work_item_comments",
            "page_comments",
        ):
            (count,) = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()
            if int(count) > 0:
                raise DomainImportError(
                    f"target store is not empty: {table} has {count} row(s)"
                )


def _insert_many(connection: Any, rows: list[dict[str, Any]], sql: str) -> int:
    if not rows:
        return 0
    connection.executemany(sql, rows)
    return len(rows)


_KEY_SUFFIX = re.compile(r"-(\d+)$")


def _rebuild_project_sequences(
    connection: Any, work_items: list[dict[str, Any]]
) -> None:
    """Reseed ``project_sequences`` so future ``create_work_item`` allocates non-colliding keys."""

    next_by_project: dict[str, int] = {}
    for item in work_items:
        key = item.get("key", "")
        match = _KEY_SUFFIX.search(key)
        if not match:
            continue
        project_id = item.get("project_id", "")
        suffix = int(match.group(1))
        current = next_by_project.get(project_id, 0)
        if suffix > current:
            next_by_project[project_id] = suffix
    # Wipe and re-seed deterministically across all projects.
    connection.execute("DELETE FROM project_sequences")
    rows = connection.execute(
        "SELECT project_id FROM projects ORDER BY project_id"
    ).fetchall()
    for (project_id,) in rows:
        next_seq = next_by_project.get(project_id, 0) + 1
        connection.execute(
            "INSERT INTO project_sequences(project_id, next_sequence) VALUES (?, ?)",
            (project_id, next_seq),
        )


def _bump_autoincrement(
    connection: Any, table: str, rows: list[dict[str, Any]]
) -> None:
    """Advance SQLite's ``sqlite_sequence`` so new auto IDs don't collide with imported ones."""

    if not rows:
        return
    if table == "work_item_transitions":
        max_id = max(int(r.get("transition_id", 0)) for r in rows)
    elif table == "page_versions":
        max_id = max(int(r.get("version_id", 0)) for r in rows)
    else:  # pragma: no cover — defensive
        return
    if max_id <= 0:
        return
    # sqlite_sequence is materialized by AUTOINCREMENT at schema-create
    # time; explicit-ID inserts above bypass the trigger that adds a per-
    # table row, so we INSERT-OR-UPDATE the counter ourselves. The table
    # itself is reserved — never CREATE it.
    existing = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)
    ).fetchone()
    if existing is None:
        connection.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)", (table, max_id)
        )
    else:
        current = int(existing[0])
        if max_id > current:
            connection.execute(
                "UPDATE sqlite_sequence SET seq = ? WHERE name = ?",
                (max_id, table),
            )
