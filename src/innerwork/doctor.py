"""Read-only validation of a database file against the current schema.

``innerwork doctor`` (CLI) validates a SQLite store file without ever
writing to it: every connection opens ``file:...?mode=ro``, the
write-capable store/audit-sink classes are never constructed, and no DDL
or write-adjacent PRAGMA is issued. The expected-schema constants below
are a *mirror* of the DDL in ``domain_store.py`` / ``sql_state_store.py``
/ ``audit.py``; the drift-guard test keeps the mirror honest against
fresh stores.

Check catalog (stable ids; scoping ``roadmap_innerwork_doctor_scoping.md``
§3):
- Group T (target & file, every run): ``target.exists``,
  ``target.readable``, ``target.sqlite_header``, ``target.openable``,
  ``target.writable``, ``target.disk_space``, ``target.age``;
  ``target.integrity`` only when the ``--integrity-check`` flag is set.
- Group S (schema, when the T2-T5 gate passes): ``schema.domain_version``,
  ``schema.table.<name>``, ``schema.columns.<name>``, ``schema.index.<name>``,
  ``schema.broker_scope``, ``schema.broker_columns.<name>``,
  ``schema.broker_version``.
- Group A (audit database, only when an audit path resolves):
  ``schema.audit_skipped``, ``schema.audit_target``,
  ``schema.audit_log_table``, ``schema.audit_columns``,
  ``schema.audit_triggers``, ``schema.audit_indexes``.

Exit-code contract: 0 = no error or warning findings (info allowed),
1 = at least one error or warning finding, 2 = usage (handled by the
CLI resolver, never here).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

__all__ = (
    "DoctorReport",
    "EXPECTED_AUDIT_COLUMNS",
    "EXPECTED_AUDIT_INDEXES",
    "EXPECTED_AUDIT_TRIGGERS",
    "EXPECTED_BROKER_SCHEMA_VERSION",
    "EXPECTED_BROKER_TABLES",
    "EXPECTED_DOMAIN_INDEXES",
    "EXPECTED_DOMAIN_SCHEMA_VERSION",
    "EXPECTED_DOMAIN_TABLES",
    "Finding",
    "TargetInfo",
    "render_human_report",
    "run_doctor",
)

# ----------------------------------------------------------------------
# Expected-schema mirrors. Single source of truth is the DDL in the
# schema-authority modules (domain_store.py, sql_state_store.py, audit.py);
# tests/test_doctor.py::test_drift_guard_expected_schema_matches_store
# keeps these honest against fresh stores, so a future schema change
# breaks the mirror loudly before the doctor can lie.
# ----------------------------------------------------------------------

EXPECTED_DOMAIN_SCHEMA_VERSION = "4"  # mirror of DOMAIN_SCHEMA_VERSION
EXPECTED_BROKER_SCHEMA_VERSION = "1"  # mirror of SQLITE_SCHEMA_VERSION

EXPECTED_DOMAIN_TABLES: dict[str, tuple[str, ...]] = {
    "projects": (
        "project_id",
        "key",
        "name",
        "owner",
        "created_at",
        "visibility",
        "members",
    ),
    "project_sequences": ("project_id", "next_sequence"),
    "work_items": (
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
    "work_item_transitions": (
        "transition_id",
        "work_item_id",
        "from_state",
        "to_state",
        "actor",
        "occurred_at",
        "reason",
    ),
    "spaces": (
        "space_id",
        "key",
        "name",
        "owner",
        "created_at",
        "visibility",
        "members",
    ),
    "pages": ("page_id", "space_id", "current_version", "created_at", "updated_at"),
    "page_versions": (
        "version_id",
        "page_id",
        "version_number",
        "title",
        "body",
        "author",
        "created_at",
    ),
    "work_item_page_links": (
        "link_id",
        "work_item_id",
        "page_id",
        "kind",
        "created_by",
        "created_at",
    ),
    "work_item_comments": ("comment_id", "work_item_id", "author", "body", "created_at"),
    "page_comments": ("comment_id", "page_id", "author", "body", "created_at"),
    "v1_idempotency_keys": ("scope", "key", "request_hash", "response_body", "created_at"),
}

# index name -> the table it is created on
EXPECTED_DOMAIN_INDEXES: dict[str, str] = {
    "ix_work_items_project": "work_items",
    "ix_work_items_state": "work_items",
    "ix_pages_space": "pages",
    "ux_work_item_page_links_triple": "work_item_page_links",
    "ix_links_work_item": "work_item_page_links",
    "ix_links_page": "work_item_page_links",
    "ix_work_item_comments_work_item": "work_item_comments",
    "ix_page_comments_page": "page_comments",
}

EXPECTED_BROKER_TABLES: dict[str, tuple[str, ...]] = {
    "services": ("service_id", "payload_json", "updated_at"),
    "operations": (
        "operation_id",
        "service_id",
        "state",
        "description",
        "payload_json",
        "created_at",
    ),
    "idempotency_keys": ("key", "request_hash", "operation_id", "created_at"),
}

EXPECTED_AUDIT_COLUMNS: tuple[str, ...] = (
    "event_id",
    "ts",
    "actor",
    "actor_kind",
    "surface",
    "entity_kind",
    "entity_id",
    "action",
    "before_json",
    "after_json",
    "metadata_json",
)

EXPECTED_AUDIT_TRIGGERS: tuple[str, ...] = ("audit_log_no_update", "audit_log_no_delete")

EXPECTED_AUDIT_INDEXES: tuple[str, ...] = (
    "idx_audit_log_entity",
    "idx_audit_log_surface",
    "idx_audit_log_actor",
)

# T2-T5 gate the schema group: if any of them fails, the file cannot be
# meaningfully schema-checked and Group S is skipped (T7-T9 still run).
_T_GATE_IDS: frozenset[str] = frozenset(
    {"target.exists", "target.readable", "target.sqlite_header", "target.openable"}
)

Severity = Literal["error", "warning", "info"]

_SEVERITY_LABELS: dict[str, str] = {
    "error": "ERROR",
    "warning": "WARN ",
    "info": "INFO ",
}

_SQLITE_HEADER = b"SQLite format 3\x00"

_DISK_SPACE_FLOOR = 64 * 1024 * 1024  # 64 MiB


@dataclass(frozen=True)
class Finding:
    """A single check result. ``ok`` is false exactly for error/warning."""

    id: str
    severity: Severity
    message: str

    @property
    def ok(self) -> bool:
        return self.severity == "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "ok": self.ok,
            "message": self.message,
        }


@dataclass
class TargetInfo:
    """Facts about the target file; always present in the JSON report."""

    path: Path
    exists: bool
    size_bytes: int | None = None
    mtime: str | None = None
    age_days: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "mtime": self.mtime,
            "age_days": self.age_days,
        }


@dataclass
class DoctorReport:
    """The full doctor result; ``to_dict`` is the locked JSON contract."""

    target: TargetInfo
    schema_versions: dict[str, dict[str, Any]]
    checks: list[Finding] = field(default_factory=list)
    schema_skipped: bool = False

    @property
    def counts(self) -> dict[str, int]:
        counts = {"error": 0, "warning": 0, "info": 0}
        for finding in self.checks:
            counts[finding.severity] += 1
        return counts

    @property
    def ok(self) -> bool:
        return self.counts["error"] == 0

    @property
    def exit_code(self) -> int:
        return 0 if self.counts["error"] == 0 and self.counts["warning"] == 0 else 1

    @property
    def summary(self) -> str:
        counts = self.counts
        warnings = counts["warning"]
        errors = counts["error"]
        info = counts["info"]
        return (
            f"{warnings} warning{'s' if warnings != 1 else ''}, "
            f"{errors} error{'s' if errors != 1 else ''}, "
            f"{info} info"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "target": self.target.to_dict(),
            "schema_versions": self.schema_versions,
            "checks": [finding.to_dict() for finding in self.checks],
            "counts": self.counts,
            "summary": self.summary,
        }


def _connect_ro(path: Path) -> sqlite3.Connection:
    """Open ``path`` read-only at the VFS layer (creates no sidecars)."""

    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def run_doctor(
    path: Path | str,
    *,
    integrity_check: bool = False,
    audit_path: Path | str | None = None,
) -> DoctorReport:
    """Validate a database file and return a :class:`DoctorReport`.

    Never writes to ``path``: raw ``sqlite3`` reads through ``mode=ro``
    connections only. ``integrity_check`` runs ``PRAGMA integrity_check``
    (a full page scan) — off by default, and the report never claims
    integrity was verified without it. When ``audit_path`` resolves, the
    audit database is validated too; otherwise a single
    ``schema.audit_skipped`` info finding is emitted.
    """

    target_path = Path(path).resolve()
    findings: list[Finding] = []

    # ------------------------------------------------------------------
    # Group T — target & file
    # ------------------------------------------------------------------
    exists = True
    is_dir = False
    size_bytes: int | None = None
    mtime_iso: str | None = None
    age_days: float | None = None
    try:
        stat_result = target_path.stat()
        exists = True
        is_dir = stat.S_ISDIR(stat_result.st_mode)
        size_bytes = stat_result.st_size
        mtime_iso = datetime.fromtimestamp(
            stat_result.st_mtime, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        age_days = round((time.time() - stat_result.st_mtime) / 86400.0, 1)
    except OSError:
        exists = False

    if not exists:
        # T2: the path does not exist — nothing further can be probed.
        findings.append(
            Finding("target.exists", "error", f"path does not exist: {target_path}")
        )
    elif is_dir:
        # T2: a directory is not a database file — stop the file probes.
        findings.append(
            Finding(
                "target.exists",
                "error",
                f"path is a directory, not a database file: {target_path}",
            )
        )
    else:
        # T3: readable (access bits + a probe open).
        readable = True
        try:
            if not os.access(target_path, os.R_OK):
                raise PermissionError(target_path)
            with target_path.open("rb"):
                pass
        except OSError:
            readable = False
        if not readable:
            findings.append(
                Finding("target.readable", "error", f"path is not readable: {target_path}")
            )
        else:
            # T4: SQLite file header magic.
            header_ok = True
            try:
                with target_path.open("rb") as handle:
                    if handle.read(16) != _SQLITE_HEADER:
                        header_ok = False
                        findings.append(
                            Finding(
                                "target.sqlite_header",
                                "error",
                                f"not a SQLite database (bad file header): {target_path}",
                            )
                        )
            except OSError as exc:
                header_ok = False
                findings.append(
                    Finding(
                        "target.sqlite_header",
                        "error",
                        f"cannot read file header: {target_path}: {exc}",
                    )
                )
            if header_ok:
                # T5: read-only open + schema probe (catches truncation,
                # corrupt header-valid files, and locked databases).
                connection: sqlite3.Connection | None = None
                try:
                    connection = _connect_ro(target_path)
                    connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
                except sqlite3.Error as exc:
                    findings.append(
                        Finding(
                            "target.openable",
                            "error",
                            f"cannot open database at {target_path}: {exc}",
                        )
                    )
                except OSError as exc:
                    findings.append(
                        Finding(
                            "target.openable",
                            "error",
                            f"cannot open database at {target_path}: {exc}",
                        )
                    )
                if connection is not None:
                    if integrity_check:
                        # T6: opt-in full page scan; never claimed otherwise.
                        try:
                            rows = connection.execute("PRAGMA integrity_check").fetchall()
                            results = [row[0] for row in rows]
                        except sqlite3.Error as exc:
                            results = []
                            findings.append(
                                Finding(
                                    "target.integrity",
                                    "error",
                                    f"database integrity check failed: {exc}",
                                )
                            )
                        if results and results != ["ok"]:
                            findings.append(
                                Finding(
                                    "target.integrity",
                                    "error",
                                    "database integrity check failed: "
                                    + "; ".join(results),
                                )
                            )
                    connection.close()
        # T7: writable (reads fine, but serve/writes would fail).
        if not os.access(target_path, os.W_OK):
            findings.append(
                Finding(
                    "target.writable",
                    "warning",
                    "database file is read-only; reads work but serve/writes "
                    f"will fail: {target_path}",
                )
            )
        # T8: disk space heuristic — free < max(64 MiB, 2 x db size).
        try:
            usage = shutil.disk_usage(target_path)
            if usage.free < max(_DISK_SPACE_FLOOR, 2 * (size_bytes or 0)):
                findings.append(
                    Finding(
                        "target.disk_space",
                        "warning",
                        f"low disk space: only {usage.free} bytes free, "
                        f"database is {size_bytes or 0} bytes "
                        "(free < max(64 MiB, 2 x db size))",
                    )
                )
        except OSError:
            pass  # free space unknown — never fabricate a finding
        # T9: file age — advisory only (backup cadence is unknowable).
        if age_days is not None:
            findings.append(
                Finding(
                    "target.age",
                    "info",
                    f"database file is {age_days:.1f} days old; confirm backups "
                    "are fresh (docs/operations-runbook.md)",
                )
            )

    t_gate_failed = any(finding.id in _T_GATE_IDS for finding in findings)

    # ------------------------------------------------------------------
    # Group S — schema (only when the T2-T5 gate passed)
    # ------------------------------------------------------------------
    schema_skipped = True
    domain_found: str | None = None
    broker_found: str | None = None
    domain_ok = False
    broker_ok = False
    if not t_gate_failed:
        try:
            connection = _connect_ro(target_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                index_rows = connection.execute(
                    "SELECT name, tbl_name FROM sqlite_master WHERE type='index'"
                ).fetchall()
                index_names = {row[0] for row in index_rows}
                index_tables = {row[0]: row[1] for row in index_rows}

                # S1: persisted domain schema version vs the code mirror.
                if "meta" not in tables:
                    findings.append(
                        Finding(
                            "schema.domain_version",
                            "error",
                            "meta table is missing; cannot verify the domain "
                            f"schema version (expected {EXPECTED_DOMAIN_SCHEMA_VERSION!r})",
                        )
                    )
                else:
                    row = connection.execute(
                        "SELECT value FROM meta WHERE key='domain_schema_version'"
                    ).fetchone()
                    domain_found = row[0] if row is not None else None
                    if domain_found is None:
                        findings.append(
                            Finding(
                                "schema.domain_version",
                                "error",
                                "domain_schema_version is not set in meta; expected "
                                f"{EXPECTED_DOMAIN_SCHEMA_VERSION!r}",
                            )
                        )
                    elif domain_found != EXPECTED_DOMAIN_SCHEMA_VERSION:
                        findings.append(
                            Finding(
                                "schema.domain_version",
                                "error",
                                "stale schema version vs code: "
                                f"meta['domain_schema_version'] = {domain_found!r}, "
                                f"expected {EXPECTED_DOMAIN_SCHEMA_VERSION!r}",
                            )
                        )
                domain_ok = domain_found == EXPECTED_DOMAIN_SCHEMA_VERSION

                # S2: the 11 domain tables exist.
                for table_name in EXPECTED_DOMAIN_TABLES:
                    if table_name not in tables:
                        findings.append(
                            Finding(
                                f"schema.table.{table_name}",
                                "error",
                                f"table '{table_name}' is missing",
                            )
                        )

                # S3: expected columns subset; extras are forward-compatible.
                for table_name, expected_columns in EXPECTED_DOMAIN_TABLES.items():
                    if table_name not in tables:
                        continue  # already reported by S2
                    actual_columns = {
                        row[1]
                        for row in connection.execute(f"PRAGMA table_info({table_name})")
                    }
                    missing = [c for c in expected_columns if c not in actual_columns]
                    extra = sorted(actual_columns - set(expected_columns))
                    if missing:
                        findings.append(
                            Finding(
                                f"schema.columns.{table_name}",
                                "error",
                                f"table '{table_name}' is missing column(s): "
                                + ", ".join(missing),
                            )
                        )
                    if extra:
                        findings.append(
                            Finding(
                                f"schema.columns.{table_name}",
                                "info",
                                f"table '{table_name}' has extra column(s): "
                                + ", ".join(extra)
                                + " (forward-compatible)",
                            )
                        )

                # S4: domain indexes (missing or wrong-shape -> warning).
                for index_name, expected_table in EXPECTED_DOMAIN_INDEXES.items():
                    if index_name not in index_names:
                        findings.append(
                            Finding(
                                f"schema.index.{index_name}",
                                "warning",
                                f"index '{index_name}' is missing (performance)",
                            )
                        )
                    elif index_tables[index_name] != expected_table:
                        findings.append(
                            Finding(
                                f"schema.index.{index_name}",
                                "warning",
                                f"index '{index_name}' exists but is attached to "
                                f"table '{index_tables[index_name]}', expected "
                                f"'{expected_table}'",
                            )
                        )

                # S5: broker tables absent -> info (a domain-only file is
                # legitimate; the CLI never wires the state store).
                broker_tables_present = any(
                    name in tables for name in EXPECTED_BROKER_TABLES
                )
                if not broker_tables_present:
                    findings.append(
                        Finding(
                            "schema.broker_scope",
                            "info",
                            "domain-only file (no edge-broker tables) - fine if "
                            "you only use domain commands",
                        )
                    )
                else:
                    # S6: broker table column drift.
                    for broker_name, expected_columns in EXPECTED_BROKER_TABLES.items():
                        if broker_name not in tables:
                            continue
                        actual_columns = {
                            row[1]
                            for row in connection.execute(
                                f"PRAGMA table_info({broker_name})"
                            )
                        }
                        missing = [
                            c for c in expected_columns if c not in actual_columns
                        ]
                        extra = sorted(actual_columns - set(expected_columns))
                        if missing:
                            findings.append(
                                Finding(
                                    f"schema.broker_columns.{broker_name}",
                                    "warning",
                                    f"broker table '{broker_name}' is missing "
                                    "column(s): " + ", ".join(missing),
                                )
                            )
                        if extra:
                            findings.append(
                                Finding(
                                    f"schema.broker_columns.{broker_name}",
                                    "info",
                                    f"broker table '{broker_name}' has extra "
                                    "column(s): "
                                    + ", ".join(extra)
                                    + " (forward-compatible)",
                                )
                            )
                    # S7: persisted broker schema version vs the code mirror.
                    if "meta" in tables:
                        row = connection.execute(
                            "SELECT value FROM meta WHERE key='schema_version'"
                        ).fetchone()
                        broker_found = row[0] if row is not None else None
                    if broker_found != EXPECTED_BROKER_SCHEMA_VERSION:
                        found_text = broker_found if broker_found is not None else "missing"
                        findings.append(
                            Finding(
                                "schema.broker_version",
                                "warning",
                                "broker schema version drift: "
                                f"meta['schema_version'] = {found_text}, expected "
                                f"{EXPECTED_BROKER_SCHEMA_VERSION!r}",
                            )
                        )
                broker_ok = (not broker_tables_present) or (
                    broker_found == EXPECTED_BROKER_SCHEMA_VERSION
                )
            finally:
                connection.close()
        except sqlite3.Error as exc:
            # The schema became unreadable after T5 proved it openable
            # (concurrent corruption); report it under the openable id
            # rather than inventing a new check.
            findings.append(
                Finding(
                    "target.openable",
                    "error",
                    f"cannot open database at {target_path}: {exc}",
                )
            )
        else:
            schema_skipped = False

    # ------------------------------------------------------------------
    # Group A — audit database (only when an audit path resolves)
    # ------------------------------------------------------------------
    resolved_audit: Path | None = (
        Path(audit_path).resolve() if audit_path is not None else None
    )
    if resolved_audit is None:
        findings.append(
            Finding(
                "schema.audit_skipped",
                "info",
                "no audit database configured (set --audit-log or "
                "INNERWORK_AUDIT_DB)",
            )
        )
    else:
        audit_ok = True
        try:
            if not resolved_audit.is_file():
                raise FileNotFoundError(resolved_audit)
            with resolved_audit.open("rb") as handle:
                if handle.read(16) != _SQLITE_HEADER:
                    raise ValueError("not a SQLite database")
        except (OSError, ValueError):
            audit_ok = False
            findings.append(
                Finding(
                    "schema.audit_target",
                    "error",
                    "audit database not found/not a SQLite database at "
                    f"{resolved_audit}",
                )
            )
        if audit_ok:
            try:
                connection = _connect_ro(resolved_audit)
                try:
                    tables = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    }
                    triggers = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='trigger'"
                        )
                    }
                    index_names = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='index'"
                        )
                    }
                    # A2: audit_log table.
                    if "audit_log" not in tables:
                        findings.append(
                            Finding(
                                "schema.audit_log_table",
                                "error",
                                "audit_log table is missing in the audit database",
                            )
                        )
                    else:
                        # A3: expected columns subset; extras forward-compatible.
                        actual_columns = {
                            row[1]
                            for row in connection.execute(
                                "PRAGMA table_info(audit_log)"
                            )
                        }
                        missing = [
                            c for c in EXPECTED_AUDIT_COLUMNS if c not in actual_columns
                        ]
                        extra = sorted(actual_columns - set(EXPECTED_AUDIT_COLUMNS))
                        if missing:
                            findings.append(
                                Finding(
                                    "schema.audit_columns",
                                    "error",
                                    "audit_log is missing column(s): "
                                    + ", ".join(missing),
                                )
                            )
                        if extra:
                            findings.append(
                                Finding(
                                    "schema.audit_columns",
                                    "info",
                                    "audit_log has extra column(s): "
                                    + ", ".join(extra)
                                    + " (forward-compatible)",
                                )
                            )
                    # A4: the append-only triggers are a phase-7 security
                    # property — losing one is an error, not a hint.
                    for trigger_name in EXPECTED_AUDIT_TRIGGERS:
                        if trigger_name not in triggers:
                            findings.append(
                                Finding(
                                    "schema.audit_triggers",
                                    "error",
                                    f"append-only trigger '{trigger_name}' is "
                                    "missing (audit integrity/security)",
                                )
                            )
                    # A5: audit indexes (missing -> warning).
                    for index_name in EXPECTED_AUDIT_INDEXES:
                        if index_name not in index_names:
                            findings.append(
                                Finding(
                                    "schema.audit_indexes",
                                    "warning",
                                    f"audit index '{index_name}' is missing "
                                    "(performance)",
                                )
                            )
                finally:
                    connection.close()
            except sqlite3.Error as exc:
                findings.append(
                    Finding(
                        "schema.audit_target",
                        "error",
                        f"audit database cannot be opened at {resolved_audit}: {exc}",
                    )
                )

    return DoctorReport(
        target=TargetInfo(
            path=target_path,
            exists=exists,
            size_bytes=size_bytes,
            mtime=mtime_iso,
            age_days=age_days,
        ),
        schema_versions={
            "domain": {
                "expected": int(EXPECTED_DOMAIN_SCHEMA_VERSION),
                "found": domain_found,
                "ok": domain_ok,
            },
            "broker": {
                "expected": int(EXPECTED_BROKER_SCHEMA_VERSION),
                "found": broker_found,
                "ok": broker_ok,
            },
        },
        checks=findings,
        schema_skipped=schema_skipped,
    )


def render_human_report(report: DoctorReport) -> str:
    """Render the §3.3 human report (findings + summary; OK line if clean)."""

    if report.counts["error"] == 0 and report.counts["warning"] == 0:
        return "OK: database is healthy (0 warnings, 0 errors)\n"
    lines = [
        f"{_SEVERITY_LABELS[finding.severity]} [{finding.id}] {finding.message}"
        for finding in report.checks
    ]
    if report.schema_skipped:
        lines.append("schema checks skipped: file is not a usable SQLite database")
    lines.append(report.summary)
    return "\n".join(lines) + "\n"
