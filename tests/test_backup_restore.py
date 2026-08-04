"""Tests for backup/restore scripts."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import backup as backup_script  # noqa: E402
import restore as restore_script  # noqa: E402


def _seed_db(path: Path, rows: int = 3) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
        conn.executemany("INSERT INTO t(val) VALUES (?)", [(f"row-{i}",) for i in range(rows)])
        conn.commit()
    finally:
        conn.close()


def _count(path: Path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()


def test_backup_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "src.db"
    dst = tmp_path / "backup.db"
    _seed_db(src, rows=5)
    backup_script.backup(src, dst)
    assert dst.exists()
    assert _count(dst) == 5


def test_backup_missing_source(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        backup_script.backup(tmp_path / "missing.db", tmp_path / "out.db")


def test_restore_refuses_overwrite(tmp_path: Path) -> None:
    src = tmp_path / "src.db"
    bk = tmp_path / "bk.db"
    dst = tmp_path / "dst.db"
    _seed_db(src, rows=2)
    backup_script.backup(src, bk)
    dst.write_text("existing")
    with pytest.raises(FileExistsError):
        restore_script.restore(bk, dst)


def test_restore_force(tmp_path: Path) -> None:
    src = tmp_path / "src.db"
    bk = tmp_path / "bk.db"
    dst = tmp_path / "dst.db"
    _seed_db(src, rows=4)
    backup_script.backup(src, bk)
    dst.write_text("existing")
    restore_script.restore(bk, dst, force=True)
    assert _count(dst) == 4


def test_restore_missing_backup(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        restore_script.restore(tmp_path / "missing.db", tmp_path / "out.db")


def test_backup_overwrites_stale_non_db_dest(tmp_path: Path) -> None:
    """A stale/partial file at the dest (e.g. an interrupted earlier run)
    must not block a fresh backup — the runbook promises the dest is
    overwritten."""
    src = tmp_path / "src.db"
    dst = tmp_path / "backup.db"
    _seed_db(src, rows=3)
    dst.write_text("stale partial garbage")
    backup_script.backup(src, dst)
    assert _count(dst) == 3
    assert (dst.stat().st_mode & 0o777) == 0o600


def test_restore_corrupt_backup_leaves_no_dest(tmp_path: Path) -> None:
    """Restoring from a corrupt backup must fail loudly and must not leave
    a usable-looking file at the destination."""
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"this is not a sqlite database" + b"\x00" * 64)
    dest = tmp_path / "dest.db"
    with pytest.raises(sqlite3.DatabaseError):
        restore_script.restore(corrupt, dest)
    assert not dest.exists()
    # No temp artifacts left behind.
    assert [p for p in tmp_path.iterdir() if ".restore-" in p.name] == []


def test_restore_failed_force_preserves_existing_dest(tmp_path: Path) -> None:
    """A --force restore from a corrupt backup must never destroy the store
    it is replacing: the existing destination is untouched on failure."""
    src = tmp_path / "src.db"
    dst = tmp_path / "dst.db"
    _seed_db(src, rows=2)
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a database")
    _seed_db(dst, rows=7)  # the "good" store currently in place
    with pytest.raises(sqlite3.DatabaseError):
        restore_script.restore(corrupt, dst, force=True)
    assert _count(dst) == 7  # old store intact
    # The failed restore must leave no temp artifacts and must not have
    # replaced the destination's permissions.
    assert [p for p in tmp_path.iterdir() if ".restore-" in p.name] == []
