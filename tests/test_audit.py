"""Tests for the phase 7 append-only audit log."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import pytest

from innerwork.audit import (
    AuditAppendOnlyError,  # noqa: F401  (re-exported for convenience)
    AuditEvent,
    JsonlAuditSink,
    MemoryAuditSink,
    SqliteAuditSink,
    ensure_audit_schema,
    make_event,
)


def _event(
    *,
    actor: str = "alice",
    actor_kind: Literal["system", "user", "service"] = "user",
    surface: str = "jira_workflow",
    entity_kind: str = "WorkItem",
    entity_id: str = "WI-1",
    action: str = "transition",
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    ts: float | None = None,
) -> AuditEvent:
    return make_event(
        actor=actor,
        actor_kind=actor_kind,
        surface=surface,
        entity_kind=entity_kind,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
        metadata=metadata,
        ts=ts,
    )


def test_memory_sink_round_trip() -> None:
    sink = MemoryAuditSink()
    sink.record(_event())
    sink.record(_event(entity_id="WI-2", action="create"))
    rows = sink.query()
    assert len(rows) == 2
    assert {row.entity_id for row in rows} == {"WI-1", "WI-2"}


def test_sqlite_sink_appends(tmp_path: Path) -> None:
    sink = SqliteAuditSink(tmp_path / "audit.db")
    sink.record(_event())
    sink.record(_event(entity_id="WI-2"))
    rows = sink.query()
    assert [r.entity_id for r in rows] == ["WI-1", "WI-2"]


def test_sqlite_sink_filters(tmp_path: Path) -> None:
    sink = SqliteAuditSink(tmp_path / "audit.db")
    sink.record(_event(surface="jira_workflow"))
    sink.record(_event(surface="confluence_page", entity_kind="Page", entity_id="P-1"))
    sink.record(_event(surface="mention", entity_kind="Notification", entity_id="U-1"))
    pages = sink.query(surface="confluence_page")
    assert len(pages) == 1
    assert pages[0].entity_kind == "Page"


def test_append_only_update_trigger(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    sink = SqliteAuditSink(db_path)
    sink.record(_event())
    # Direct sqlite3 UPDATE must abort.
    conn = sqlite3.connect(str(db_path))
    try:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE audit_log SET actor = 'bob'")
            conn.commit()
    finally:
        conn.close()


def test_append_only_delete_trigger(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    sink = SqliteAuditSink(db_path)
    sink.record(_event())
    conn = sqlite3.connect(str(db_path))
    try:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM audit_log")
            conn.commit()
    finally:
        conn.close()


def test_make_event_validates() -> None:
    with pytest.raises(ValueError):
        make_event(
            actor="",
            actor_kind="user",
            surface="x",
            entity_kind="X",
            entity_id="1",
            action="a",
        )


def test_jsonl_sink(tmp_path: Path) -> None:
    sink = JsonlAuditSink(tmp_path / "audit.jsonl")
    sink.record(_event())
    sink.record(_event(entity_id="WI-2"))
    rows = sink.query()
    assert [r.entity_id for r in rows] == ["WI-1", "WI-2"]


def test_ensure_schema_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_audit_schema(conn)
        ensure_audit_schema(conn)
    finally:
        conn.close()


def test_export_jsonl(tmp_path: Path) -> None:
    sink = SqliteAuditSink(tmp_path / "audit.db")
    sink.record(_event())
    sink.record(_event(entity_id="WI-2"))
    out = tmp_path / "dump.jsonl"
    n = sink.export_jsonl(out)
    assert n == 2
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
