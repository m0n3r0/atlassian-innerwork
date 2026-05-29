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
