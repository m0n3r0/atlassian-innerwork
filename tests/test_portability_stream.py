"""Tests for streaming portability export (export_domain_json_stream, atomic --out).

Scoping: ``docs/roadmap_streaming_export_scoping.md`` §6, locked by task
``t_93948c32``. The referee gate is byte-identity: the streamed artifact
MUST equal ``json.dumps(export_domain(store, include_audit=...,
audit_actor_kind=...), indent=..., sort_keys=False)`` for the same store
and settings. Rows are fetched via ``fetchmany(batch_size)`` — never
``fetchall`` (the ban test enforces this).

The CLI surface is unchanged (no ``--stream`` flag): ``export`` always
streams, writes ``--out`` atomically via a temp file + ``os.replace``,
and appends the trailing newline after the call.
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest

from innerwork.audit import MemoryAuditSink, SqliteAuditSink, make_event
from innerwork.domain_store import DOMAIN_SCHEMA_VERSION, DomainStore
from innerwork.portability import (
    PORTABILITY_FORMAT_VERSION,
    PORTABILITY_FORMAT_VERSION_AUDIT,
    DomainImportError,
    export_domain,
    export_domain_json,
    export_domain_json_stream,
    import_domain_json,
)

# --------------------------------------------------------------- helpers


def _seed(store: DomainStore) -> None:
    """Seed a store with rows touching every collection in _COLLECTION_ORDER.

    Deliberately adversarial for the byte-identity referee: unicode names
    and bodies, control characters, ``\\u``-escapable content, and an
    EMPTY ``page_comments`` collection (empty-collection rendering).
    """

    store.create_project(
        project_id="p1",
        key="ALPHA",
        name="Ünïcødé プロジェクト 🚀",
        owner="eml",
        created_at="2026-05-01T00:00:00Z",
    )
    store.create_project(
        project_id="p2",
        key="BETA",
        name="Beta",
        owner="eml",
        created_at="2026-05-01T00:00:00Z",
    )
    w1 = store.create_work_item(
        work_item_id="w1",
        project_id="p1",
        title="tïtle — 中文 \u0001",
        description="d\u00e9scription with control \u0002 and emoji \U0001f680",
        assignee="alice",
        created_at="2026-05-02T00:00:00Z",
    )
    w2 = store.create_work_item(
        work_item_id="w2",
        project_id="p1",
        title="t2",
        description="line1\nline2 with \u2028 separator",
        created_at="2026-05-02T00:00:00Z",
    )
    store.create_work_item(
        work_item_id="w3",
        project_id="p2",
        title="t3",
        created_at="2026-05-02T00:00:00Z",
    )
    store.transition_work_item(
        work_item_id=w1.work_item_id,
        to_state="in_progress",
        actor="alice",
        reason="kickoff",
        occurred_at="2026-05-03T00:00:00Z",
    )
    store.transition_work_item(
        work_item_id=w2.work_item_id,
        to_state="in_progress",
        actor="bob",
        occurred_at="2026-05-03T01:00:00Z",
    )

    store.create_space(
        space_id="s1",
        key="DOCS",
        name="Döcs",
        owner="eml",
        created_at="2026-05-01T00:00:00Z",
    )
    page, _v = store.create_page(
        page_id="pg1",
        space_id="s1",
        title="héllo wörld",
        body="b\u00f6dy with \n newline",
        author="eml",
        created_at="2026-05-04T00:00:00Z",
    )

    store.create_link(
        link_id="l1",
        work_item_id=w1.work_item_id,
        page_id=page.page_id,
        kind="documents",
        created_by="eml",
        created_at="2026-05-05T00:00:00Z",
    )

    store.create_work_item_comment(
        comment_id="wc1",
        work_item_id=w1.work_item_id,
        author="alice",
        body="first work comment — コメント",
        created_at="2026-05-06T00:00:00Z",
    )
    store.create_work_item_comment(
        comment_id="wc2",
        work_item_id=w1.work_item_id,
        author="bob",
        body="reply \u0000 escape",
        created_at="2026-05-06T01:00:00Z",
    )
    # page_comments intentionally left EMPTY — the referee test needs an
    # empty collection rendered as `[]` next to non-empty ones.


def _seed_many(store: DomainStore, n: int) -> None:
    """Seed ``n`` work items in a fresh project (for multi-batch tests)."""

    store.create_project(
        project_id="bulk",
        key="BULK",
        name="Bulk",
        owner="eml",
        created_at="2026-05-01T00:00:00Z",
    )
    for i in range(n):
        store.create_work_item(
            work_item_id=f"bulk-{i}",
            project_id="bulk",
            title=f"bulk item {i}",
            description="x" * 200,
            created_at="2026-05-02T00:00:00Z",
        )


def _store(tmp_path: Path, name: str = "db.sqlite") -> DomainStore:
    return DomainStore(tmp_path / name)


def _stream(
    store: DomainStore,
    *,
    indent: int | None = 2,
    batch_size: int = 500,
    include_audit: bool = False,
    audit_actor_kind: str = "system",
) -> str:
    out = io.StringIO()
    export_domain_json_stream(
        store,
        out,
        indent=indent,
        batch_size=batch_size,
        include_audit=include_audit,
        audit_actor_kind=audit_actor_kind,
    )
    return out.getvalue()


def _reference(
    store: DomainStore,
    *,
    indent: int | None = 2,
    include_audit: bool = False,
    audit_actor_kind: str = "system",
) -> str:
    payload = export_domain(
        store, include_audit=include_audit, audit_actor_kind=audit_actor_kind
    )
    return json.dumps(payload, indent=indent, sort_keys=False)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")}
    return subprocess.run(
        [sys.executable, "-m", "innerwork.cli", *args],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


class _FailingSink(io.StringIO):
    """A TextIO sink that raises OSError once ``limit`` chars are written."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit
        self.written = 0

    def write(self, s: str) -> int:  # type: ignore[override]
        self.written += len(s)
        if self.written > self.limit:
            raise OSError("simulated disk full")
        return super().write(s)


def _seed_audit_sink(store: DomainStore, sink: Any) -> int:
    """Record events with nested before/after/metadata dicts; return count."""

    events = [
        make_event(
            event_id="evt-1",
            ts=1785778000.123,
            actor="alice",
            actor_kind="user",
            surface="jira_workflow",
            entity_kind="WorkItem",
            entity_id="w1",
            action="transition",
            before={"state": "todo"},
            after={"state": "in_progress"},
            metadata={"transition_id": 1, "reason": "kïckoff \u0001"},
        ),
        make_event(
            event_id="evt-2",
            ts=1785778001.5,
            actor="portability",
            actor_kind="system",
            surface="portability_export",
            entity_kind="Domain",
            entity_id=str(store.path),
            action="export",
            metadata={"counts": {"projects": 1}},
        ),
        make_event(
            event_id="evt-3",
            ts=1785778002.75,
            actor="bot",
            actor_kind="service",
            surface="mention",
            entity_kind="Page",
            entity_id="pg1",
            action="dispatch",
            after={"mentioned": ["alice"]},
            metadata={"nested": {"list": [1, 2, {"k": "v"}]}},
        ),
    ]
    for event in events:
        sink.record(event)
    store.audit_sink = sink
    return len(events)


# ------------------------------------------------------- byte-identity referee


def test_stream_bytes_equal_memory_resident(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    assert _stream(store) == _reference(store)


def test_stream_bytes_equal_memory_resident_compact(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    assert _stream(store, indent=None) == _reference(store, indent=None)


def test_stream_bytes_equal_memory_resident_multi_batch(tmp_path: Path) -> None:
    # > batch_size rows (default 500) in one collection → multiple fetchmany.
    store = _store(tmp_path)
    _seed_many(store, 600)
    assert _stream(store, batch_size=500) == _reference(store)


def test_stream_bytes_equal_memory_resident_batch_size_1(tmp_path: Path) -> None:
    # Every row its own batch — stresses the comma/indent logic.
    store = _store(tmp_path)
    _seed(store)
    assert _stream(store, batch_size=1) == _reference(store)


def test_stream_empty_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert _stream(store) == _reference(store)
    payload = json.loads(_stream(store))
    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION
    assert payload["schema_version"] == DOMAIN_SCHEMA_VERSION
    for collection in (
        "projects",
        "work_items",
        "transitions",
        "spaces",
        "pages",
        "page_versions",
        "links",
        "work_item_comments",
        "page_comments",
    ):
        assert payload[collection] == []


def test_stream_never_calls_fetchall(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The streaming export must fetch via ``fetchmany`` only.

    ``sqlite3.Cursor`` is an immutable C type, so the ban is enforced by
    wrapping ``sqlite3.connect`` with a connection whose cursors raise on
    ``fetchall`` — any ``fetchall`` in the streaming path blows up.
    """

    store = _store(tmp_path)
    _seed(store)
    real_connect = sqlite3.connect

    class _BannedCursor:
        def __init__(self, cursor: sqlite3.Cursor) -> None:
            self._cursor = cursor

        def fetchmany(self, size: int) -> list[Any]:
            return self._cursor.fetchmany(size)

        def fetchall(self) -> list[Any]:
            raise AssertionError(
                "fetchall() must never be called by the streaming export"
            )

    class _BannedConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def execute(
            self, sql: str, *parameters: Any
        ) -> _BannedCursor:
            return _BannedCursor(self._connection.execute(sql, *parameters))

        def __enter__(self) -> _BannedConnection:
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            self._connection.__exit__(exc_type, exc, traceback)

    def _wrapped(path: str | Path) -> _BannedConnection:
        return _BannedConnection(real_connect(path))

    monkeypatch.setattr(sqlite3, "connect", _wrapped)
    out = io.StringIO()
    export_domain_json_stream(store, out)
    assert json.loads(out.getvalue())["format_version"] == PORTABILITY_FORMAT_VERSION


def test_stream_is_deterministic(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    assert _stream(store) == _stream(store)


def test_stream_batch_size_validation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(ValueError):
        export_domain_json_stream(store, io.StringIO(), batch_size=0)
    with pytest.raises(ValueError):
        export_domain_json_stream(store, io.StringIO(), batch_size=-1)


# ------------------------------------------------------------- counts parity


def test_stream_counts_equal_export_domain_lengths(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    payload = export_domain(store)
    out = io.StringIO()
    counts = export_domain_json_stream(store, out)
    assert counts == {k: len(v) for k, v in payload.items() if isinstance(v, list)}


def test_stream_counts_include_audit_when_requested(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    sink = MemoryAuditSink()
    n = _seed_audit_sink(store, sink)
    payload = export_domain(store, include_audit=True)
    out = io.StringIO()
    counts = export_domain_json_stream(store, out, include_audit=True)
    assert counts["audit"] == n
    assert counts["audit"] == len(payload["audit"])


# ------------------------------------------------------------ audit composition


def test_stream_audit_bytes_equal_memory_resident_v2(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    sink = MemoryAuditSink()
    _seed_audit_sink(store, sink)
    # Reference FIRST: the streamed export appends its own portability_export
    # event to the sink after success, so a reference computed afterwards
    # would include that extra row (correct append-only behavior, not drift).
    expected = _reference(store, include_audit=True)
    streamed = _stream(store, include_audit=True)
    assert streamed == expected
    payload = json.loads(streamed)
    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION_AUDIT
    assert len(payload["audit"]) == 3


def test_stream_audit_redaction_user_masks_actor(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    sink = MemoryAuditSink()
    _seed_audit_sink(store, sink)
    expected = _reference(store, include_audit=True, audit_actor_kind="user")
    streamed = _stream(store, include_audit=True, audit_actor_kind="user")
    assert streamed == expected
    payload = json.loads(streamed)
    for row in payload["audit"]:
        assert row["actor"] == "[redacted-actor]"


def test_stream_audit_requires_sink_fail_before_write(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    out = io.StringIO()
    with pytest.raises(DomainImportError):
        export_domain_json_stream(store, out, include_audit=True)
    assert out.getvalue() == ""  # fail-before-write: not one byte emitted


def test_stream_portability_event_emitted_after_success(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    sink = MemoryAuditSink()
    store.audit_sink = sink
    out = io.StringIO()
    counts = export_domain_json_stream(store, out)
    events = sink.query(surface="portability_export")
    assert len(events) == 1
    assert events[0].metadata["counts"] == counts
    assert events[0].metadata["format_version"] == PORTABILITY_FORMAT_VERSION


def test_stream_interrupted_sink_records_no_audit_event(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    sink = MemoryAuditSink()
    store.audit_sink = sink
    failing = _FailingSink(limit=64)
    with pytest.raises(OSError):
        export_domain_json_stream(store, failing)
    assert sink.query(surface="portability_export") == ()  # never materialized


# ------------------------------------------------------------------ round-trip


def test_round_trip_streamed_export_import_reexport(tmp_path: Path) -> None:
    store_a = _store(tmp_path, "a.sqlite")
    _seed(store_a)
    p1 = _stream(store_a)

    store_b = _store(tmp_path, "b.sqlite")
    import_domain_json(store_b, p1)
    p2 = _stream(store_b)
    assert p2 == p1


def test_streamed_artifact_imports_like_memory_artifact(tmp_path: Path) -> None:
    store_a = _store(tmp_path, "a.sqlite")
    _seed(store_a)
    streamed = _stream(store_a)
    memory = export_domain_json(store_a, indent=2) + "\n"
    assert streamed + "\n" == memory

    store_b = _store(tmp_path, "b.sqlite")
    store_c = _store(tmp_path, "c.sqlite")
    counts_b = import_domain_json(store_b, streamed)
    counts_c = import_domain_json(store_c, memory)
    assert counts_b == counts_c


# --------------------------------------------------------------------- CLI


def test_cli_export_stdout_matches_default(tmp_path: Path) -> None:
    db = tmp_path / "src.db"
    store = DomainStore(db)
    _seed(store)
    url = f"sqlite:///{db}"
    r = _run_cli("export", "--database-url", url)
    assert r.returncode == 0, r.stderr
    assert r.stdout == _reference(store) + "\n"
    payload = json.loads(r.stdout)
    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION


def test_cli_export_out_file_round_trips(tmp_path: Path) -> None:
    db = tmp_path / "src.db"
    store = DomainStore(db)
    _seed(store)
    url = f"sqlite:///{db}"
    export_path = tmp_path / "export.json"
    r = _run_cli("export", "--database-url", url, "--out", str(export_path))
    assert r.returncode == 0, r.stderr
    assert export_path.read_text(encoding="utf-8") == _reference(store) + "\n"

    dst_db = tmp_path / "dst.db"
    dst_url = f"sqlite:///{dst_db}"
    r = _run_cli("import", "--database-url", dst_url, str(export_path))
    assert r.returncode == 0, r.stderr
    imported = json.loads(r.stdout)["imported"]
    assert imported == {
        k: len(v) for k, v in export_domain(store).items() if isinstance(v, list)
    }
    # re-export of the imported store is byte-identical
    r2 = _run_cli("export", "--database-url", dst_url)
    assert r2.returncode == 0, r2.stderr
    assert r2.stdout == export_path.read_text(encoding="utf-8")


def test_cli_export_out_include_audit_v2(tmp_path: Path) -> None:
    db = tmp_path / "src.db"
    store = DomainStore(db)
    _seed(store)
    audit_db = tmp_path / "audit.db"
    sink = SqliteAuditSink(audit_db)
    _seed_audit_sink(store, sink)
    url = f"sqlite:///{db}"
    export_path = tmp_path / "export-audit.json"

    r = _run_cli(
        "export",
        "--database-url",
        url,
        "--out",
        str(export_path),
        "--include-audit",
        "--audit-log",
        str(audit_db),
    )
    assert r.returncode == 0, r.stderr
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION_AUDIT
    assert len(payload["audit"]) == 3


def test_cli_export_include_audit_no_sink_exit_2(tmp_path: Path) -> None:
    db = tmp_path / "src.db"
    store = DomainStore(db)
    _seed(store)
    url = f"sqlite:///{db}"
    r = _run_cli("export", "--database-url", url, "--include-audit")
    assert r.returncode == 2
    assert r.stdout == ""  # fail-before-write: stdout stays empty
    assert "--audit-log" in r.stderr
    assert "INNERWORK_AUDIT_DB" in r.stderr


def test_cli_export_out_atomic_on_error(tmp_path: Path) -> None:
    """A failed export preserves the existing target and leaves no temp litter."""

    db = tmp_path / "src.db"
    store = DomainStore(db)
    _seed(store)
    url = f"sqlite:///{db}"
    export_path = tmp_path / "export.json"
    export_path.write_text("SENTINEL", encoding="utf-8")  # pre-existing file

    r = _run_cli(
        "export",
        "--database-url",
        url,
        "--out",
        str(export_path),
        "--include-audit",  # no sink → DomainImportError → exit 2
    )
    assert r.returncode == 2
    assert export_path.read_text(encoding="utf-8") == "SENTINEL"  # never clobbered
    litter = [p for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert litter == []  # temp file removed on every failure path
