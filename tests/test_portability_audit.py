"""Tests for optional audit-log inclusion in the portability payload.

Covers the ``--include-audit`` / ``format_version 2`` envelope (scoping
``docs/roadmap_audit_export_flag_scoping.md`` §6): the default-off
invariant, version markers, audit-row export/redaction, strict import
validation (no event injection), no-loss/no-dup round-trip, append-only
survival, and the CLI surface.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from innerwork.audit import MemoryAuditSink, SqliteAuditSink, make_event
from innerwork.domain_store import DOMAIN_SCHEMA_VERSION, DomainStore
from innerwork.portability import (
    PORTABILITY_FORMAT_VERSION,
    PORTABILITY_FORMAT_VERSION_AUDIT,
    DomainImportError,
    export_domain,
    export_domain_json,
    import_domain,
    import_domain_json,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "audit_export"


# --------------------------------------------------------------- helpers


def _seed(store: DomainStore) -> None:
    """Seed a store with rows touching every collection in _COLLECTION_ORDER."""

    store.create_project(
        project_id="p1",
        key="ALPHA",
        name="Alpha",
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
        title="t1",
        description="d1",
        assignee="alice",
        created_at="2026-05-02T00:00:00Z",
    )
    w2 = store.create_work_item(
        work_item_id="w2",
        project_id="p1",
        title="t2",
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
        name="Docs",
        owner="eml",
        created_at="2026-05-01T00:00:00Z",
    )
    page, _v = store.create_page(
        page_id="pg1",
        space_id="s1",
        title="hello",
        body="world",
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
        body="first work comment",
        created_at="2026-05-06T00:00:00Z",
    )
    store.create_work_item_comment(
        comment_id="wc2",
        work_item_id=w1.work_item_id,
        author="bob",
        body="reply",
        created_at="2026-05-06T01:00:00Z",
    )
    store.create_page_comment(
        comment_id="pc1",
        page_id=page.page_id,
        author="eml",
        body="page comment",
        created_at="2026-05-07T00:00:00Z",
    )


def _store(tmp_path: Path, name: str = "db.sqlite") -> DomainStore:
    return DomainStore(tmp_path / name)


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _sink_events(sink: MemoryAuditSink) -> int:
    """Record the fixture's four audit rows (surfaces/actor kinds) into a sink."""

    for row in _load_fixture("with_audit_v2.json")["audit"]:
        sink.record(
            make_event(
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
        )
    return len(_load_fixture("with_audit_v2.json")["audit"])


def _run_cli(
    *args: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "innerwork.cli", *args],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


# --------------------------------------------------------- default-off invariant


def test_default_export_unchanged_byte_identical(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    payload = export_domain(store)

    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION
    assert "audit" not in payload
    assert list(payload) == [
        "format_version",
        "schema_version",
        "projects",
        "work_items",
        "transitions",
        "spaces",
        "pages",
        "page_versions",
        "links",
        "work_item_comments",
        "page_comments",
    ]
    # Byte-level lock against the legacy-shape reference fixture.
    assert export_domain_json(store) == (
        FIXTURE_DIR / "without_audit_v1.json"
    ).read_text(encoding="utf-8").rstrip("\n")


# ------------------------------------------------------- export shape + marker


def test_include_audit_bumps_format_version_and_appends_collection(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _seed(store)
    store.audit_sink = MemoryAuditSink()
    _sink_events(store.audit_sink)

    payload = export_domain(store, include_audit=True)

    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION_AUDIT
    assert payload["schema_version"] == DOMAIN_SCHEMA_VERSION
    assert isinstance(payload["audit"], list)
    assert list(payload)[-1] == "audit"  # trailing key, not in _COLLECTION_ORDER


def test_export_audit_requires_wired_sink(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(DomainImportError, match="audit sink"):
        export_domain(store, include_audit=True)


def test_export_audit_rows_match_sink(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    sink = MemoryAuditSink()
    store.audit_sink = sink
    count = _sink_events(sink)

    payload = export_domain(store, include_audit=True)

    assert len(payload["audit"]) == len(sink.query()) == count
    for row, event in zip(payload["audit"], sink.query(), strict=True):
        assert row["surface"] == event.surface
        assert row["actor"] == event.actor
        assert row["actor_kind"] == event.actor_kind
        assert row["entity_id"] == event.entity_id
        assert row["before"] == (dict(event.before) if event.before else None)
        assert row["after"] == (dict(event.after) if event.after else None)
        assert row["metadata"] == dict(event.metadata)


def test_export_audit_includes_portability_events(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    store.audit_sink = MemoryAuditSink()
    export_domain_json(store)  # plain export emits a portability_export row

    payload = export_domain(store, include_audit=True)

    surfaces = {row["surface"] for row in payload["audit"]}
    assert "portability_export" in surfaces
    portability_rows = [
        row for row in payload["audit"] if row["surface"] == "portability_export"
    ]
    assert portability_rows
    assert portability_rows[0]["actor"] == "portability"
    assert portability_rows[0]["metadata"]["format_version"] == PORTABILITY_FORMAT_VERSION


def test_export_audit_redaction_system_verbatim(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    store.audit_sink = MemoryAuditSink()
    _sink_events(store.audit_sink)

    payload = export_domain(store, include_audit=True)

    assert any(row["actor"] == "alice" for row in payload["audit"])
    assert any(row["actor"] == "bob" for row in payload["audit"])


def test_export_audit_redaction_user_masks_actor(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed(store)
    store.audit_sink = MemoryAuditSink()
    _sink_events(store.audit_sink)

    payload = export_domain(store, include_audit=True, audit_actor_kind="user")

    for row in payload["audit"]:
        assert row["actor"] == "[redacted-actor]"
        assert row["surface"]  # non-ACL fields unchanged
        assert row["entity_id"]


# --------------------------------------------------------- import: v1 legacy


def test_import_v1_legacy_payload_still_works(tmp_path: Path) -> None:
    store = _store(tmp_path)
    raw = (FIXTURE_DIR / "without_audit_v1.json").read_text(encoding="utf-8")

    counts = import_domain_json(store, raw)

    fixture = json.loads(raw)
    for key in (
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
        assert counts[key] == len(fixture[key])
    assert "audit" not in counts
    # Re-export is byte-identical to the legacy snapshot; no audit collection.
    assert export_domain_json(store) == raw.rstrip("\n")
    assert "audit" not in export_domain(store)


def test_import_v1_rejects_audit_key(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _load_fixture("without_audit_v1.json")
    payload["audit"] = []

    with pytest.raises(DomainImportError, match="format_version 2"):
        import_domain(store, payload)


# ------------------------------------------------------- import: v2 envelope


def test_import_v2_requires_audit_key(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _load_fixture("with_audit_v2.json")
    del payload["audit"]

    with pytest.raises(DomainImportError, match="must include an audit collection"):
        import_domain(store, payload)


def test_import_v2_audit_not_list(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _load_fixture("with_audit_v2.json")
    payload["audit"] = {"not": "a list"}

    with pytest.raises(DomainImportError, match="'audit' must be a list"):
        import_domain(store, payload)


def test_import_v2_restores_audit_rows(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sink = MemoryAuditSink()
    store.audit_sink = sink
    payload = _load_fixture("with_audit_v2.json")

    counts = import_domain(store, payload)

    restored = sink.query()
    payload_ids = {row["event_id"] for row in payload["audit"]}
    restored_ids = {event.event_id for event in restored}
    assert payload_ids <= restored_ids
    assert len(restored_ids) == len(payload_ids) + 1  # +1 = the import's own event
    assert counts["audit"] == len(payload["audit"])
    assert counts["projects"] == len(payload["projects"])
    assert counts["work_items"] == len(payload["work_items"])


def test_import_v2_no_sink_errors(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _load_fixture("with_audit_v2.json")

    with pytest.raises(DomainImportError, match="no audit sink"):
        import_domain(store, payload)
    # Store untouched — the sink check runs before any INSERT.
    assert list(store.list_projects()) == []


def test_import_v2_empty_audit_no_sink_ok(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _load_fixture("with_audit_v2.json")
    payload["audit"] = []

    counts = import_domain(store, payload)

    assert counts["audit"] == 0
    assert counts["projects"] == len(payload["projects"])


# -------------------------------------------------- import: strict validation


def test_import_v2_rejects_unknown_surface(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _load_fixture("with_audit_v2.json")
    payload["audit"][0]["surface"] = "bogus"
    store.audit_sink = MemoryAuditSink()

    with pytest.raises(DomainImportError, match="unknown audit surface"):
        import_domain(store, payload)


def test_import_v2_rejects_bad_actor_kind(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _load_fixture("with_audit_v2.json")
    payload["audit"][0]["actor_kind"] = "root"
    store.audit_sink = MemoryAuditSink()

    with pytest.raises(DomainImportError, match="actor_kind"):
        import_domain(store, payload)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda row: row.update(actor=""), "non-blank"),
        (lambda row: row.update(ts="not-a-number"), "'ts' must be a number"),
        (lambda row: row.update(before=["nope"]), "'before' must be null or an object"),
        (lambda row: row.update(after=42), "'after' must be null or an object"),
        (lambda row: row.update(metadata=[1, 2]), "'metadata' must be an object"),
    ],
)
def test_import_v2_rejects_malformed_row(tmp_path: Path, mutate, match) -> None:
    store = _store(tmp_path)
    payload = _load_fixture("with_audit_v2.json")
    mutate(payload["audit"][0])
    store.audit_sink = MemoryAuditSink()

    with pytest.raises(DomainImportError, match=match):
        import_domain(store, payload)


def test_import_v2_rejects_non_object_row(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _load_fixture("with_audit_v2.json")
    payload["audit"][0] = "not-an-object"
    store.audit_sink = MemoryAuditSink()

    with pytest.raises(DomainImportError, match="JSON object"):
        import_domain(store, payload)


def test_import_v2_rejects_missing_required_field(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _load_fixture("with_audit_v2.json")
    del payload["audit"][0]["actor"]
    store.audit_sink = MemoryAuditSink()

    with pytest.raises(DomainImportError, match="'actor'"):
        import_domain(store, payload)


def test_import_v2_event_id_conflict_writes_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sink = MemoryAuditSink()
    store.audit_sink = sink
    payload = _load_fixture("with_audit_v2.json")
    # Pre-seed the sink with one of the payload's event_ids.
    sink.record(
        make_event(
            event_id=payload["audit"][0]["event_id"],
            ts=1.0,
            actor="existing",
            actor_kind="system",
            surface="portability_export",
            entity_kind="Domain",
            entity_id="x",
            action="export",
        )
    )

    with pytest.raises(DomainImportError, match="already exists in the audit sink"):
        import_domain(store, payload)
    # All-or-nothing: no domain rows, no additional audit rows.
    assert list(store.list_projects()) == []
    assert len(sink.query()) == 1


# ------------------------------------------------------- round-trip no-loss/no-dup


def test_round_trip_audit_no_loss_no_duplication(tmp_path: Path) -> None:
    src = _store(tmp_path, "src.sqlite")
    _seed(src)
    src.audit_sink = MemoryAuditSink()
    _sink_events(src.audit_sink)
    p1 = export_domain_json(src, include_audit=True)

    dst = _store(tmp_path, "dst.sqlite")
    dst.audit_sink = MemoryAuditSink()
    import_domain_json(dst, p1)
    p2 = export_domain_json(dst, include_audit=True)

    p1_payload = json.loads(p1)
    p2_payload = json.loads(p2)
    # (1) Domain collections byte-identical across the cycle.
    for key in (
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
        assert p2_payload[key] == p1_payload[key]
    # (2) Every P1 audit event_id present exactly once in the destination sink.
    dst_ids = {event.event_id for event in dst.audit_sink.query()}
    assert len(dst_ids) == len(p1_payload["audit"]) + 2  # import + re-export events
    for row in p1_payload["audit"]:
        assert row["event_id"] in dst_ids
    # (3) P2's audit collection grew by exactly the portability events.
    p1_ids = {row["event_id"] for row in p1_payload["audit"]}
    p2_ids = {row["event_id"] for row in p2_payload["audit"]}
    assert p1_ids <= p2_ids
    assert len(p2_ids) == len(p1_ids) + 1  # only the import event joined the payload
    new_surfaces = {row["surface"] for row in p2_payload["audit"] if row["event_id"] not in p1_ids}
    assert new_surfaces == {"portability_import"}


def test_sink_stays_append_only_after_restore(tmp_path: Path) -> None:
    import sqlite3

    store = _store(tmp_path, "db.sqlite")
    audit_path = tmp_path / "audit.db"
    sink = SqliteAuditSink(audit_path)
    store.audit_sink = sink
    import_domain(store, _load_fixture("with_audit_v2.json"))

    connection = sqlite3.connect(str(audit_path))
    try:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute("UPDATE audit_log SET actor = 'bob'")
            connection.commit()
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute("DELETE FROM audit_log")
            connection.commit()
    finally:
        connection.close()


# ----------------------------------------------------------------- CLI surface


def test_cli_export_include_audit(tmp_path: Path) -> None:
    db = tmp_path / "innerwork.db"
    audit_db = tmp_path / "audit.db"
    url = f"sqlite:///{db}"
    store = DomainStore(db)
    _seed(store)
    store.audit_sink = SqliteAuditSink(audit_db)
    _sink_events(store.audit_sink)

    result = _run_cli(
        "export",
        "--database-url",
        url,
        "--include-audit",
        "--audit-log",
        str(audit_db),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION_AUDIT
    assert "audit" in payload


def test_cli_export_include_audit_no_sink_exit_2(tmp_path: Path) -> None:
    db = tmp_path / "innerwork.db"
    url = f"sqlite:///{db}"
    store = DomainStore(db)
    _seed(store)

    result = _run_cli("export", "--database-url", url, "--include-audit")

    assert result.returncode == 2
    assert "--audit-log" in result.stderr and "INNERWORK_AUDIT_DB" in result.stderr


def test_cli_export_default_no_audit_key(tmp_path: Path) -> None:
    db = tmp_path / "innerwork.db"
    url = f"sqlite:///{db}"
    store = DomainStore(db)
    _seed(store)

    result = _run_cli("export", "--database-url", url)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION
    assert "audit" not in payload


def test_cli_import_audit_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "innerwork.db"
    audit_db = tmp_path / "audit.db"
    url = f"sqlite:///{db}"
    snapshot = FIXTURE_DIR / "with_audit_v2.json"

    result = _run_cli(
        "import",
        str(snapshot),
        "--database-url",
        url,
        "--audit-log",
        str(audit_db),
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["imported"]["audit"] == 4
    sink = SqliteAuditSink(audit_db)
    assert len(sink.query()) == 5  # 4 restored + 1 portability_import


def test_cli_import_v2_no_sink_exit_2(tmp_path: Path) -> None:
    db = tmp_path / "innerwork.db"
    url = f"sqlite:///{db}"
    snapshot = FIXTURE_DIR / "with_audit_v2.json"

    result = _run_cli("import", str(snapshot), "--database-url", url)

    assert result.returncode == 2
    assert "no audit sink" in result.stderr


def test_cli_audit_log_flag_wires_sink_for_writes(tmp_path: Path) -> None:
    db = tmp_path / "innerwork.db"
    audit_db = tmp_path / "audit.db"
    url = f"sqlite:///{db}"

    created = _run_cli(
        "project-create",
        "--database-url",
        url,
        "--audit-log",
        str(audit_db),
        "--key",
        "ENG",
        "--name",
        "Engineering",
        "--owner",
        "eml",
    )
    assert created.returncode == 0, created.stderr
    project = json.loads(created.stdout)
    item = json.loads(
        _run_cli(
            "work-item-create",
            "--database-url",
            url,
            "--audit-log",
            str(audit_db),
            "--project-id",
            project["project_id"],
            "--title",
            "Set up CI",
        ).stdout
    )
    transitioned = _run_cli(
        "work-item-transition",
        "--database-url",
        url,
        "--audit-log",
        str(audit_db),
        "--work-item-id",
        item["work_item_id"],
        "--to-state",
        "in_progress",
        "--actor",
        "eml",
    )
    assert transitioned.returncode == 0, transitioned.stderr

    exported = _run_cli(
        "export",
        "--database-url",
        url,
        "--include-audit",
        "--audit-log",
        str(audit_db),
    )
    assert exported.returncode == 0, exported.stderr
    payload = json.loads(exported.stdout)
    surfaces = {row["surface"] for row in payload["audit"]}
    assert "jira_workflow" in surfaces  # F1 fix: CLI writes now emit audit rows
