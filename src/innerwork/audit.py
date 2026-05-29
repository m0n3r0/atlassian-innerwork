"""Append-only audit log for phase 7 trust hardening.

This module provides a synchronous, append-only audit trail for security- and
privacy-relevant write operations across the domain (workflow transitions,
page version writes, mention delivery, permission grants/revokes, portability
export/import).

Design notes
------------
- Append-only at two layers: (1) no UPDATE/DELETE API in this module, and
  (2) SQL triggers ``audit_log_no_update`` / ``audit_log_no_delete`` that
  ``RAISE(ABORT)`` against the table. The SQL guard is documented as a soft
  guard, not a security boundary — SQLite is a local file and the host
  operator can always edit it out-of-band.
- ``SqliteAuditSink`` owns its own DB connection/path so it can be co-located
  with the domain DB or kept separate (for retention-policy reasons).
- ``JsonlAuditSink`` is the export surface for backups. No vendor SIEM
  integration ships in phase 7 — that is explicitly deferred.
- Read APIs are NOT audited; only writes. See ``phase7_scoping.md`` §1.3.

The module is local-file only: no network calls in any code path.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import time
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

__all__ = (
    "AUDIT_SCHEMA_VERSION",
    "AUDIT_SURFACES",
    "AuditEvent",
    "AuditSink",
    "AuditAppendOnlyError",
    "JsonlAuditSink",
    "SqliteAuditSink",
    "MemoryAuditSink",
    "ensure_audit_schema",
    "make_event",
)


AUDIT_SCHEMA_VERSION = 1

# Closed enum (scoping §1.1). Callers passing anything outside this set raise.
AUDIT_SURFACES: frozenset[str] = frozenset(
    {
        "jira_workflow",
        "confluence_page",
        "mention",
        "permission_change",
        "portability_export",
        "portability_import",
    }
)

_ACTOR_KINDS: frozenset[str] = frozenset({"system", "user", "service"})


class AuditAppendOnlyError(RuntimeError):
    """Raised when the SQL append-only guard rejects an UPDATE/DELETE."""


@dataclass(frozen=True)
class AuditEvent:
    """A single audit record. Immutable; build with :func:`make_event`."""

    event_id: str
    ts: float
    actor: str
    actor_kind: Literal["system", "user", "service"]
    surface: str
    entity_kind: str
    entity_id: str
    action: str
    before: Mapping[str, Any] | None = None
    after: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.surface not in AUDIT_SURFACES:
            raise ValueError(
                f"unknown audit surface {self.surface!r}; "
                f"valid surfaces: {sorted(AUDIT_SURFACES)}"
            )
        if self.actor_kind not in _ACTOR_KINDS:
            raise ValueError(
                f"actor_kind must be one of {sorted(_ACTOR_KINDS)}, "
                f"got {self.actor_kind!r}"
            )
        if not (self.actor or "").strip():
            raise ValueError("actor must be a non-blank string")
        if not (self.entity_kind or "").strip():
            raise ValueError("entity_kind must be non-blank")
        if not (self.entity_id or "").strip():
            raise ValueError("entity_id must be non-blank")
        if not (self.action or "").strip():
            raise ValueError("action must be non-blank")

    def as_jsonable(self) -> dict[str, Any]:
        payload = asdict(self)
        # dataclass asdict returns dict-of-dicts; that's already JSON-safe so
        # long as caller didn't stash non-JSON values. We don't try to coerce.
        return payload


def make_event(
    *,
    actor: str,
    actor_kind: Literal["system", "user", "service"],
    surface: str,
    entity_kind: str,
    entity_id: str,
    action: str,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    ts: float | None = None,
    event_id: str | None = None,
) -> AuditEvent:
    """Build an :class:`AuditEvent` with sensible defaults.

    ``ts`` defaults to ``time.time()`` (unix epoch). Order ties within the same
    second are broken by the SQLite ``rowid`` (documented monotonic insertion
    order — see ``phase7_scoping.md`` §1.2).
    """

    return AuditEvent(
        event_id=event_id or str(uuid.uuid4()),
        ts=time.time() if ts is None else float(ts),
        actor=actor,
        actor_kind=actor_kind,
        surface=surface,
        entity_kind=entity_kind,
        entity_id=entity_id,
        action=action,
        before=dict(before) if before is not None else None,
        after=dict(after) if after is not None else None,
        metadata=dict(metadata or {}),
    )


# ---------------------------------------------------------------- sinks


class AuditSink(Protocol):
    """Abstract sink. Implementations MUST be append-only."""

    def record(self, event: AuditEvent) -> None:
        ...

    def query(
        self,
        *,
        surface: str | None = None,
        entity_kind: str | None = None,
        entity_id: str | None = None,
        actor: str | None = None,
        limit: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        ...


_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    event_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    actor TEXT NOT NULL,
    actor_kind TEXT NOT NULL CHECK (actor_kind IN ('system','user','service')),
    surface TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity
    ON audit_log(entity_kind, entity_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_log_surface
    ON audit_log(surface, ts);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor
    ON audit_log(actor, ts);
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
"""


def ensure_audit_schema(connection: sqlite3.Connection) -> None:
    """Create ``audit_log`` + indices + append-only triggers if absent.

    Idempotent: safe to call on every connection open.
    """

    connection.executescript(_AUDIT_DDL)


class SqliteAuditSink:
    """Default sink — writes append-only rows into a local SQLite file.

    The sink owns its connection lifecycle. A new connection is opened per
    ``record()`` call to keep multi-thread safety trivial; phase 7 audit
    volume is low enough this is not a hot path.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            ensure_audit_schema(connection)

    @contextlib.contextmanager
    def _connect(self) -> Any:
        connection = sqlite3.connect(str(self.path))
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def record(self, event: AuditEvent) -> None:
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO audit_log(
                        event_id, ts, actor, actor_kind, surface,
                        entity_kind, entity_id, action,
                        before_json, after_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.ts,
                        event.actor,
                        event.actor_kind,
                        event.surface,
                        event.entity_kind,
                        event.entity_id,
                        event.action,
                        _dumps_or_none(event.before),
                        _dumps_or_none(event.after),
                        json.dumps(dict(event.metadata), sort_keys=True),
                    ),
                )
            except sqlite3.IntegrityError as exc:  # pragma: no cover - defensive
                raise AuditAppendOnlyError(str(exc)) from exc

    def query(
        self,
        *,
        surface: str | None = None,
        entity_kind: str | None = None,
        entity_id: str | None = None,
        actor: str | None = None,
        limit: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        clauses: list[str] = []
        params: list[Any] = []
        if surface is not None:
            clauses.append("surface = ?")
            params.append(surface)
        if entity_kind is not None:
            clauses.append("entity_kind = ?")
            params.append(entity_kind)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if actor is not None:
            clauses.append("actor = ?")
            params.append(actor)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        limit_sql = f" LIMIT {int(limit)}" if limit else ""
        query = (
            "SELECT event_id, ts, actor, actor_kind, surface, entity_kind, "
            "entity_id, action, before_json, after_json, metadata_json "
            f"FROM audit_log {where} ORDER BY ts, rowid{limit_sql}"
        )
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return tuple(_row_to_event(row) for row in rows)

    def export_jsonl(self, target: str | Path) -> int:
        """Dump all rows to a JSONL file. Returns the number of rows written."""

        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with target_path.open("w", encoding="utf-8") as handle:
            for event in self.query():
                handle.write(json.dumps(event.as_jsonable(), sort_keys=True))
                handle.write("\n")
                count += 1
        return count


class JsonlAuditSink:
    """Append-only sink writing one JSON object per line.

    Used by ``scripts/backup.py`` to export the audit log to a portable file.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Touch the file so callers can stat it post-construction.
        self.path.touch(exist_ok=True)

    def record(self, event: AuditEvent) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.as_jsonable(), sort_keys=True))
            handle.write("\n")

    def query(
        self,
        *,
        surface: str | None = None,
        entity_kind: str | None = None,
        entity_id: str | None = None,
        actor: str | None = None,
        limit: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        events: list[AuditEvent] = []
        if not self.path.exists():
            return ()
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                event = AuditEvent(
                    event_id=payload["event_id"],
                    ts=float(payload["ts"]),
                    actor=payload["actor"],
                    actor_kind=payload["actor_kind"],
                    surface=payload["surface"],
                    entity_kind=payload["entity_kind"],
                    entity_id=payload["entity_id"],
                    action=payload["action"],
                    before=payload.get("before"),
                    after=payload.get("after"),
                    metadata=payload.get("metadata") or {},
                )
                if surface is not None and event.surface != surface:
                    continue
                if entity_kind is not None and event.entity_kind != entity_kind:
                    continue
                if entity_id is not None and event.entity_id != entity_id:
                    continue
                if actor is not None and event.actor != actor:
                    continue
                events.append(event)
                if limit is not None and len(events) >= limit:
                    break
        return tuple(events)


class MemoryAuditSink:
    """In-memory sink for tests. Append-only by convention (no remove API)."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)

    def query(
        self,
        *,
        surface: str | None = None,
        entity_kind: str | None = None,
        entity_id: str | None = None,
        actor: str | None = None,
        limit: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        out: list[AuditEvent] = []
        for event in self._events:
            if surface is not None and event.surface != surface:
                continue
            if entity_kind is not None and event.entity_kind != entity_kind:
                continue
            if entity_id is not None and event.entity_id != entity_id:
                continue
            if actor is not None and event.actor != actor:
                continue
            out.append(event)
            if limit is not None and len(out) >= limit:
                break
        return tuple(out)


# ---------------------------------------------------------------- helpers

def _dumps_or_none(payload: Mapping[str, Any] | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(dict(payload), sort_keys=True)


def _row_to_event(row: Iterable[Any]) -> AuditEvent:
    (
        event_id,
        ts,
        actor,
        actor_kind,
        surface,
        entity_kind,
        entity_id,
        action,
        before_json,
        after_json,
        metadata_json,
    ) = tuple(row)
    return AuditEvent(
        event_id=event_id,
        ts=float(ts),
        actor=actor,
        actor_kind=actor_kind,
        surface=surface,
        entity_kind=entity_kind,
        entity_id=entity_id,
        action=action,
        before=json.loads(before_json) if before_json else None,
        after=json.loads(after_json) if after_json else None,
        metadata=json.loads(metadata_json) if metadata_json else {},
    )
