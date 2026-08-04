"""Tests for the ``innerwork doctor`` read-only database validation command.

Covers the full §8 matrix of docs/roadmap_innerwork_doctor_scoping.md:
the exit-code contract (0 healthy / 1 findings / 2 usage), the JSON
shape/stability contract, the read-only guarantee, the opt-in integrity
check, the schema drift checks, the audit checks, and the drift-guard
test that keeps the ``EXPECTED_*`` mirrors honest against the real store
DDL.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from innerwork import doctor
from innerwork.audit import SqliteAuditSink, make_event
from innerwork.domain_store import DomainStore
from innerwork.sql_state_store import SqliteStateStore


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


def _make_domain_db(db: Path) -> None:
    """Create a fresh DomainStore database (writes DDL — test fixture only)."""

    DomainStore(db)


def _make_broker_db(db: Path) -> None:
    """Add broker tables + schema version to a store, as SqliteStateStore does."""

    SqliteStateStore(db)


def _make_drifted_broker_db(db: Path) -> None:
    """Domain store + broker tables where ``operations`` lacks ``description``."""

    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE services (service_id TEXT PRIMARY KEY, "
            "payload_json TEXT NOT NULL, updated_at TEXT NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE operations (operation_id TEXT PRIMARY KEY, "
            "service_id TEXT NOT NULL, state TEXT NOT NULL, "
            "payload_json TEXT NOT NULL, created_at TEXT NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE idempotency_keys (key TEXT PRIMARY KEY, "
            "request_hash TEXT NOT NULL, operation_id TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '1')")


def _make_audit_db(db: Path) -> None:
    """Create an audit database via the real sink (writes DDL — fixture only)."""

    sink = SqliteAuditSink(db)
    sink.record(
        make_event(
            actor="test",
            actor_kind="system",
            surface="jira_workflow",
            entity_kind="work_item",
            entity_id="ENG-1",
            action="create",
        )
    )


def _corrupt_db_page_cell_count(db: Path) -> None:
    """Corrupt a non-page-1 b-tree root page's cell-count field.

    Structural corruption that ``PRAGMA integrity_check`` detects while
    the file header and ``sqlite_master`` (page 1) stay readable, so the
    default header+open checks still pass.
    """

    data = bytearray(db.read_bytes())
    page_size = int.from_bytes(data[16:18], "big")
    with sqlite3.connect(db) as conn:
        root = conn.execute(
            "SELECT rootpage FROM sqlite_master WHERE name = 'work_items'"
        ).fetchone()
    assert root is not None and root[0] != 1
    data[(root[0] - 1) * page_size + 3] ^= 0xFF
    db.write_bytes(bytes(data))


# ----------------------------------------------------------------------
# §8 matrix
# ----------------------------------------------------------------------


def test_help_lists_doctor_with_example():
    result = _run_cli("doctor", "--help")
    assert result.returncode == 0, result.stderr
    assert "examples:" in result.stdout
    assert "--json" in result.stdout
    assert "--integrity-check" in result.stdout
    assert "--audit-log" in result.stdout
    top = _run_cli("--help")
    assert top.returncode == 0
    assert "doctor" in top.stdout


def test_healthy_fresh_db_exit_0(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    result = _run_cli("doctor", str(db))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "OK: database is healthy (0 warnings, 0 errors)\n"


def test_missing_index_warning_exit_1(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP INDEX ix_work_items_project")
    result = _run_cli("doctor", str(db))
    assert result.returncode == 1
    assert "schema.index.ix_work_items_project" in result.stdout
    machine = _run_cli("doctor", str(db), "--json")
    payload = json.loads(machine.stdout)
    assert payload["ok"] is True  # errors == 0
    assert payload["exit_code"] == 1  # warnings fail the exit code
    assert payload["counts"]["warning"] == 1
    assert payload["counts"]["error"] == 0


def test_missing_table_exit_1(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE projects")
    result = _run_cli("doctor", str(db))
    assert result.returncode == 1
    assert "schema.table.projects" in result.stdout


def test_missing_column_exit_1(tmp_path: Path):
    """An old-schema (v3) store without visibility/members errors on S3."""

    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE projects RENAME TO projects_v3")
        conn.execute(
            "CREATE TABLE projects ("
            "project_id TEXT PRIMARY KEY,"
            "key TEXT NOT NULL UNIQUE,"
            "name TEXT NOT NULL,"
            "owner TEXT NOT NULL,"
            "created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO projects (project_id, key, name, owner, created_at) "
            "SELECT project_id, key, name, owner, created_at FROM projects_v3"
        )
        conn.execute("DROP TABLE projects_v3")
    result = _run_cli("doctor", str(db))
    assert result.returncode == 1
    assert "schema.columns.projects" in result.stdout
    assert "visibility" in result.stdout


def test_schema_version_drift_exit_1(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE meta SET value = '3' WHERE key = 'domain_schema_version'"
        )
    result = _run_cli("doctor", str(db))
    assert result.returncode == 1
    assert "schema.domain_version" in result.stdout
    assert "expected '4'" in result.stdout
    assert "'3'" in result.stdout


def test_missing_meta_table_exit_1(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE meta")
    result = _run_cli("doctor", str(db))
    assert result.returncode == 1
    assert "schema.domain_version" in result.stdout


def test_path_does_not_exist_exit_1(tmp_path: Path):
    missing = tmp_path / "nope.db"
    result = _run_cli("doctor", str(missing))
    assert result.returncode == 1
    assert "target.exists" in result.stdout
    assert "schema.domain_version" not in result.stdout  # schema group skipped
    assert "schema.table." not in result.stdout


def test_path_is_directory_exit_1(tmp_path: Path):
    result = _run_cli("doctor", str(tmp_path))
    assert result.returncode == 1
    assert "target.exists" in result.stdout
    assert "path is a directory, not a database file" in result.stdout


def test_not_a_sqlite_db_exit_1(tmp_path: Path):
    bad = tmp_path / "notdb.txt"
    bad.write_text("this is not a sqlite database at all\n", encoding="utf-8")
    result = _run_cli("doctor", str(bad))
    assert result.returncode == 1
    assert "target.sqlite_header" in result.stdout
    assert "schema.domain_version" not in result.stdout  # schema group skipped
    assert "schema.table." not in result.stdout


def test_corrupt_file_open_error_exit_1(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    data = db.read_bytes()
    truncated = tmp_path / "truncated.db"
    truncated.write_bytes(data[:512])  # valid header, page 1 cut short
    result = _run_cli("doctor", str(truncated))
    assert result.returncode == 1
    assert "target.openable" in result.stdout
    assert "schema.domain_version" not in result.stdout  # schema group skipped


def test_integrity_check_opt_in(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    _corrupt_db_page_cell_count(db)
    # Without the flag: header + open checks pass, so exit 0 and the
    # integrity id is absent — the report never claims it ran.
    without = _run_cli("doctor", str(db))
    assert without.returncode == 0, without.stdout
    assert "target.integrity" not in without.stdout
    json_without = json.loads(_run_cli("doctor", str(db), "--json").stdout)
    assert "target.integrity" not in [c["id"] for c in json_without["checks"]]
    # With the flag: the page scan finds the corruption.
    with_flag = _run_cli("doctor", str(db), "--integrity-check")
    assert with_flag.returncode == 1
    assert "target.integrity" in with_flag.stdout
    json_with = json.loads(
        _run_cli("doctor", str(db), "--integrity-check", "--json").stdout
    )
    assert "target.integrity" in [c["id"] for c in json_with["checks"]]


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permission bits")
def test_unreadable_file_exit_1(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    db.chmod(0)
    try:
        result = _run_cli("doctor", str(db))
        assert result.returncode == 1
        assert "target.readable" in result.stdout
    finally:
        db.chmod(0o644)


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permission bits")
def test_not_writable_warning_exit_1(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    db.chmod(0o444)
    try:
        result = _run_cli("doctor", str(db))
        assert result.returncode == 1
        assert "target.writable" in result.stdout
    finally:
        db.chmod(0o644)


def test_disk_space_warning(tmp_path: Path, monkeypatch):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    monkeypatch.setattr(
        doctor.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=1024, total=1_000_000, used=999_000),
    )
    report = doctor.run_doctor(db)
    ids = [finding.id for finding in report.checks]
    assert "target.disk_space" in ids
    assert report.counts["warning"] >= 1
    assert report.exit_code == 1


def test_backup_age_info_never_fails(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    result = _run_cli("doctor", str(db), "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    age = next(c for c in payload["checks"] if c["id"] == "target.age")
    assert age["severity"] == "info"
    assert age["ok"] is True
    assert payload["target"]["age_days"] is not None


def test_broker_tables_absent_info(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    result = _run_cli("doctor", str(db), "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    ids = [c["id"] for c in payload["checks"]]
    assert "schema.broker_scope" in ids
    assert not any(
        cid.startswith("schema.broker_columns") or cid.startswith("schema.broker_version")
        for cid in ids
    )
    assert payload["schema_versions"]["broker"]["found"] is None
    assert payload["schema_versions"]["broker"]["ok"] is True


def test_broker_drift_warning(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_drifted_broker_db(db)
    result = _run_cli("doctor", str(db), "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    ids = [c["id"] for c in payload["checks"]]
    assert "schema.broker_columns.operations" in ids


def test_audit_checks_pass(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    audit = tmp_path / "audit.db"
    _make_domain_db(db)
    _make_audit_db(audit)
    result = _run_cli("doctor", str(db), "--audit-log", str(audit))
    assert result.returncode == 0, result.stdout
    assert "OK: database is healthy" in result.stdout
    machine = _run_cli("doctor", str(db), "--audit-log", str(audit), "--json")
    payload = json.loads(machine.stdout)
    assert payload["counts"]["error"] == 0
    assert not any(
        c["id"].startswith("schema.audit_") and not c["ok"] for c in payload["checks"]
    )


def test_audit_trigger_missing_is_error(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    audit = tmp_path / "audit.db"
    _make_domain_db(db)
    _make_audit_db(audit)
    with sqlite3.connect(audit) as conn:
        conn.execute("DROP TRIGGER audit_log_no_update")
    result = _run_cli("doctor", str(db), "--audit-log", str(audit))
    assert result.returncode == 1
    assert "schema.audit_triggers" in result.stdout


def test_audit_index_missing_is_warning(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    audit = tmp_path / "audit.db"
    _make_domain_db(db)
    _make_audit_db(audit)
    with sqlite3.connect(audit) as conn:
        conn.execute("DROP INDEX idx_audit_log_entity")
    result = _run_cli("doctor", str(db), "--audit-log", str(audit))
    assert result.returncode == 1
    assert "schema.audit_indexes" in result.stdout


def test_audit_path_missing_is_error(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    result = _run_cli("doctor", str(db), "--audit-log", str(tmp_path / "no-audit.db"))
    assert result.returncode == 1
    assert "schema.audit_target" in result.stdout


def test_no_url_no_path_exit_2():
    result = _run_cli("doctor", env_extra={"INNERWORK_DATABASE_URL": ""})
    assert result.returncode == 2
    assert "--database-url" in result.stderr
    assert "INNERWORK_DATABASE_URL" in result.stderr
    assert result.stdout == ""
    json_result = _run_cli("doctor", "--json", env_extra={"INNERWORK_DATABASE_URL": ""})
    assert json_result.returncode == 2
    assert json_result.stdout == ""


def test_unsupported_scheme_exit_2():
    result = _run_cli("doctor", "--database-url", "postgres://localhost/x")
    assert result.returncode == 2
    assert "only sqlite:/// URLs" in result.stderr
    assert result.stdout == ""


def test_positional_wins_over_flag(tmp_path: Path):
    good = tmp_path / "good.db"
    _make_domain_db(good)
    result = _run_cli(
        "doctor", str(good), "--database-url", "sqlite:///does-not-exist.db"
    )
    assert result.returncode == 0
    assert "OK: database is healthy" in result.stdout


def test_json_shape_stable(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    first = _run_cli("doctor", str(db), "--json")
    second = _run_cli("doctor", str(db), "--json")
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout  # deterministic bytes
    payload = json.loads(first.stdout)
    assert set(payload.keys()) == {
        "ok",
        "exit_code",
        "target",
        "schema_versions",
        "checks",
        "counts",
        "summary",
    }
    assert payload["exit_code"] == first.returncode
    for check in payload["checks"]:
        assert set(check.keys()) == {"id", "severity", "ok", "message"}
        assert check["severity"] in {"error", "warning", "info"}
    ids = [c["id"] for c in payload["checks"]]
    target_ids = [cid for cid in ids if cid.startswith("target.")]
    schema_ids = [
        cid for cid in ids if cid.startswith("schema.") and not cid.startswith("schema.audit")
    ]
    audit_ids = [cid for cid in ids if cid.startswith("schema.audit")]
    assert ids == target_ids + schema_ids + audit_ids  # T -> S -> A order


def test_json_matches_human_report(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP INDEX ix_work_items_project")
    human = _run_cli("doctor", str(db))
    machine = _run_cli("doctor", str(db), "--json")
    assert human.returncode == 1 and machine.returncode == 1
    payload = json.loads(machine.stdout)
    human_lines = human.stdout.strip().splitlines()
    assert human_lines[-1] == payload["summary"]
    assert payload["counts"] == {"error": 0, "warning": 1, "info": 3}
    for check in payload["checks"]:
        assert f"[{check['id']}]" in human.stdout


def test_read_only_guarantee(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    audit = tmp_path / "audit.db"
    _make_domain_db(db)
    _make_audit_db(audit)

    def snapshot() -> dict[str, object]:
        return {
            "sha256": hashlib.sha256(db.read_bytes()).hexdigest(),
            "mtime_ns": db.stat().st_mtime_ns,
            "size": db.stat().st_size,
        }

    before = snapshot()
    dir_before = sorted(p.name for p in tmp_path.iterdir())
    result = _run_cli("doctor", str(db), "--integrity-check", "--audit-log", str(audit))
    assert result.returncode == 0, result.stdout
    assert before == snapshot()
    assert dir_before == sorted(p.name for p in tmp_path.iterdir())


def test_drift_guard_expected_schema_matches_store(tmp_path: Path):
    # Domain store: every expected table/column/index exists.
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table_name, columns in doctor.EXPECTED_DOMAIN_TABLES.items():
            assert table_name in tables
            actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
            assert set(columns) <= actual
        index_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        for index_name in doctor.EXPECTED_DOMAIN_INDEXES:
            assert index_name in index_names
    # Broker store: every expected broker table exists with its columns.
    broker = tmp_path / "broker.db"
    _make_broker_db(broker)
    with sqlite3.connect(broker) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table_name, columns in doctor.EXPECTED_BROKER_TABLES.items():
            assert table_name in tables
            actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
            assert set(columns) <= actual
    # Audit store: expected columns, triggers, and indexes all present.
    audit = tmp_path / "audit.db"
    _make_audit_db(audit)
    with sqlite3.connect(audit) as conn:
        actual = {row[1] for row in conn.execute("PRAGMA table_info(audit_log)")}
        assert set(doctor.EXPECTED_AUDIT_COLUMNS) <= actual
        triggers = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        assert set(doctor.EXPECTED_AUDIT_TRIGGERS) <= triggers
        index_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        assert set(doctor.EXPECTED_AUDIT_INDEXES) <= index_names


def test_existing_suites_stay_green() -> None:
    """The pre-existing regression suites are untouched by this feature."""

    tests_dir = Path(__file__).resolve().parent
    for name in ("test_cli.py", "test_domain_cli.py", "test_migration.py"):
        assert (tests_dir / name).is_file()


def test_doctor_imports_stdlib_only() -> None:
    """The doctor module imports only stdlib (read-only guarantee, §9)."""

    source = inspect.getsource(doctor)
    allowed = {
        "os",
        "shutil",
        "sqlite3",
        "stat",
        "time",
        "dataclasses",
        "datetime",
        "pathlib",
        "typing",
    }
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("from __future__"):
            continue
        if stripped.startswith("import ") or stripped.startswith("from "):
            module = stripped.split()[1].split(".")[0]
            assert module in allowed, f"non-stdlib import in doctor.py: {line}"


# ----------------------------------------------------------------------
# QA regression additions (t_487a74f3): gaps found during the QA gate
# ----------------------------------------------------------------------


def test_empty_file_is_not_a_sqlite_db_exit_1(tmp_path: Path):
    """A zero-byte file is the canonical 'empty input' — header check errors."""
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    result = _run_cli("doctor", str(empty))
    assert result.returncode == 1
    assert "target.sqlite_header" in result.stdout
    assert "schema.domain_version" not in result.stdout  # schema group skipped


def test_json_target_null_when_path_missing(tmp_path: Path):
    """JSON contract rule 4: size/mtime/age_days are null for a missing path."""
    result = _run_cli("doctor", str(tmp_path / "nope.db"), "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["target"]["exists"] is False
    assert payload["target"]["size_bytes"] is None
    assert payload["target"]["mtime"] is None
    assert payload["target"]["age_days"] is None


def test_disk_usage_oserror_is_silent(tmp_path: Path, monkeypatch):
    """T8: when free space is unknowable the doctor never fabricates a finding."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)

    def boom(_path):
        raise OSError("simulated statfs failure")

    monkeypatch.setattr(doctor.shutil, "disk_usage", boom)
    report = doctor.run_doctor(db)
    ids = [finding.id for finding in report.checks]
    assert "target.disk_space" not in ids
    assert report.exit_code == 0


def test_domain_version_key_missing_in_meta_exit_1(tmp_path: Path):
    """S1: meta exists but the version key row is gone -> error, not a crash."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM meta WHERE key='domain_schema_version'")
    result = _run_cli("doctor", str(db))
    assert result.returncode == 1
    assert "schema.domain_version" in result.stdout
    assert "not set in meta" in result.stdout


def test_extra_column_is_info_only(tmp_path: Path):
    """S3: forward-compatible extra columns are info, never error (exit 0)."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE projects ADD COLUMN extra_note TEXT")
    result = _run_cli("doctor", str(db), "--json")
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    extra = [
        c
        for c in payload["checks"]
        if c["id"] == "schema.columns.projects" and c["severity"] == "info"
    ]
    assert extra and "extra_note" in extra[0]["message"]


def test_index_on_wrong_table_is_warning(tmp_path: Path):
    """S4: an index present-but-attached-to-the-wrong-table is a warning."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP INDEX ix_work_items_project")
        conn.execute(
            "CREATE INDEX ix_work_items_project ON pages(current_version)"
        )
    result = _run_cli("doctor", str(db))
    assert result.returncode == 1
    assert "schema.index.ix_work_items_project" in result.stdout
    assert "attached to table 'pages'" in result.stdout


def test_partial_broker_tables_and_missing_version_warning(tmp_path: Path):
    """S6/S7: a broker subset (only services) is fine column-wise but the
    missing schema_version row is a drift warning naming 'missing'."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE services (service_id TEXT PRIMARY KEY, "
            "payload_json TEXT NOT NULL, updated_at TEXT NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP)"
        )
    result = _run_cli("doctor", str(db), "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    ids = [c["id"] for c in payload["checks"]]
    assert "schema.broker_scope" not in ids  # broker tables present
    assert "schema.broker_columns.services" not in ids  # full columns
    drift = next(c for c in payload["checks"] if c["id"] == "schema.broker_version")
    assert drift["severity"] == "warning"
    assert "missing" in drift["message"]


def test_broker_extra_column_is_info(tmp_path: Path):
    """S6: forward-compatible broker extra column -> info, exit 0."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    SqliteStateStore(db)  # full broker set + schema_version=1
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE operations ADD COLUMN extra_note TEXT")
    result = _run_cli("doctor", str(db), "--json")
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    extra = [
        c
        for c in payload["checks"]
        if c["id"] == "schema.broker_columns.operations" and c["severity"] == "info"
    ]
    assert extra and "extra_note" in extra[0]["message"]


def test_broker_version_drift_value_warning(tmp_path: Path):
    """S7: schema_version stored but drifted from the code mirror -> warning."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    SqliteStateStore(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE meta SET value='0' WHERE key='schema_version'")
    result = _run_cli("doctor", str(db))
    assert result.returncode == 1
    assert "schema.broker_version" in result.stdout
    assert "expected '1'" in result.stdout


def test_schema_phase_sqlite_error_reported_as_openable(tmp_path: Path, monkeypatch):
    """S-group: a concurrent sqlite error after T5 falls back to target.openable
    instead of inventing a new check id."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    real_connect = doctor._connect_ro
    calls = {"n": 0}

    def flaky(path):
        calls["n"] += 1
        if calls["n"] >= 2:  # first call is T5; second is the schema probe
            raise sqlite3.OperationalError("database is locked")
        return real_connect(path)

    monkeypatch.setattr(doctor, "_connect_ro", flaky)
    report = doctor.run_doctor(db)
    ids = [finding.id for finding in report.checks]
    assert "target.openable" in ids
    assert report.schema_skipped is True


def test_open_oserror_reported_as_openable(tmp_path: Path, monkeypatch):
    """T5: a non-sqlite OSError on the read-only open is still target.openable."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)

    def boom(_path):
        raise OSError("simulated open failure")

    monkeypatch.setattr(doctor, "_connect_ro", boom)
    report = doctor.run_doctor(db)
    ids = [finding.id for finding in report.checks]
    assert "target.openable" in ids
    assert report.schema_skipped is True


def test_header_read_oserror_reported(tmp_path: Path, monkeypatch):
    """T4: an OSError mid-header-read is reported under target.sqlite_header."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    real_open = Path.open
    state = {"n": 0}

    def flaky(self, *args, **kwargs):
        state["n"] += 1
        if state["n"] == 2:  # call 1 is the T3 probe open; call 2 is the header read
            raise OSError("simulated read failure")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky)
    report = doctor.run_doctor(db)
    ids = [finding.id for finding in report.checks]
    assert "target.sqlite_header" in ids


def test_audit_log_table_missing_is_error(tmp_path: Path):
    """A2: a valid SQLite file without audit_log is an error, not 'not a DB'."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    audit = tmp_path / "audit.db"
    with sqlite3.connect(audit) as conn:
        conn.execute("CREATE TABLE dummy (x TEXT)")
    result = _run_cli("doctor", str(db), "--audit-log", str(audit))
    assert result.returncode == 1
    assert "schema.audit_log_table" in result.stdout
    assert "schema.audit_target" not in result.stdout


def test_audit_missing_column_is_error(tmp_path: Path):
    """A3: audit_log with a truncated column set is an error."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    audit = tmp_path / "audit.db"
    with sqlite3.connect(audit) as conn:
        conn.execute(
            "CREATE TABLE audit_log (event_id TEXT PRIMARY KEY, ts TEXT)"
        )
    result = _run_cli("doctor", str(db), "--audit-log", str(audit))
    assert result.returncode == 1
    assert "schema.audit_columns" in result.stdout
    assert "actor" in result.stdout  # a missing expected column is named


def test_audit_extra_column_is_info(tmp_path: Path):
    """A3: forward-compatible audit extra column -> info, exit 0."""
    db = tmp_path / "innerwork.db"
    audit = tmp_path / "audit.db"
    _make_domain_db(db)
    _make_audit_db(audit)
    with sqlite3.connect(audit) as conn:
        conn.execute("ALTER TABLE audit_log ADD COLUMN extra_note TEXT")
    result = _run_cli("doctor", str(db), "--audit-log", str(audit), "--json")
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    extra = [
        c
        for c in payload["checks"]
        if c["id"] == "schema.audit_columns" and c["severity"] == "info"
    ]
    assert extra and "extra_note" in extra[0]["message"]


def test_audit_target_not_sqlite_db_error(tmp_path: Path):
    """A1-gate: an audit path that is not a SQLite file -> schema.audit_target."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    audit = tmp_path / "audit.txt"
    audit.write_text("not a database\n", encoding="utf-8")
    result = _run_cli("doctor", str(db), "--audit-log", str(audit))
    assert result.returncode == 1
    assert "schema.audit_target" in result.stdout


def test_audit_corrupt_open_error(tmp_path: Path):
    """A1-gate: header-valid but truncated audit file -> schema.audit_target."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    full_audit = tmp_path / "full-audit.db"
    _make_audit_db(full_audit)
    audit = tmp_path / "truncated-audit.db"
    audit.write_bytes(full_audit.read_bytes()[:512])
    result = _run_cli("doctor", str(db), "--audit-log", str(audit))
    assert result.returncode == 1
    assert "schema.audit_target" in result.stdout


def test_integrity_check_rows_path_exit_1(tmp_path: Path):
    """T6: when integrity_check *returns* error rows (index-root corruption)
    rather than raising, the finding still fires — and only with the flag."""
    db = tmp_path / "innerwork.db"
    _make_domain_db(db)
    with sqlite3.connect(db) as conn:
        root = conn.execute(
            "SELECT rootpage FROM sqlite_master WHERE name='ix_work_items_project'"
        ).fetchone()
    assert root is not None and root[0] != 1
    data = bytearray(db.read_bytes())
    page_size = int.from_bytes(data[16:18], "big")
    data[(root[0] - 1) * page_size + 3] ^= 0xFF
    db.write_bytes(bytes(data))
    without = _run_cli("doctor", str(db))
    assert without.returncode == 0, without.stdout
    assert "target.integrity" not in without.stdout
    with_flag = _run_cli("doctor", str(db), "--integrity-check", "--json")
    assert with_flag.returncode == 1
    payload = json.loads(with_flag.stdout)
    integrity = [c for c in payload["checks"] if c["id"] == "target.integrity"]
    assert len(integrity) == 1 and integrity[0]["severity"] == "error"


def test_audit_path_from_env_var(tmp_path: Path):
    """CLI: INNERWORK_AUDIT_DB env resolves the audit target (no --audit-log)."""
    db = tmp_path / "innerwork.db"
    audit = tmp_path / "audit.db"
    _make_domain_db(db)
    _make_audit_db(audit)
    result = _run_cli(
        "doctor",
        str(db),
        "--json",
        env_extra={"INNERWORK_AUDIT_DB": str(audit)},
    )
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert not any(c["id"] == "schema.audit_skipped" for c in payload["checks"])
    assert all(
        c["ok"] for c in payload["checks"] if c["id"].startswith("schema.audit_")
    )
