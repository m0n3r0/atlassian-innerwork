#!/usr/bin/env python3
"""Rollback drill — exercises backup -> mutate -> restore against a temp DB.

Operators run this drill before a release (and CI runs it on every push)
to prove that the documented rollback procedure in
``docs/operations-runbook.md`` actually works against the current code.

The drill is stdlib-only and idempotent. It:

  1. Creates a fresh SQLite database under ``--workdir``.
  2. Seeds it with deterministic rows.
  3. Backs it up to ``backup-pre-mutation.db`` via the same
     ``Connection.backup`` mechanism ``scripts/backup.py`` uses.
  4. Performs a destructive mutation (drops + recreates a table).
  5. Restores the backup over the live DB.
  6. Verifies the row count + checksum match the pre-mutation state.
  7. Prints a structured JSON summary an on-call can paste into a retro.

Exit code 0 on success, 1 on any failure. Failures are diagnosable from
the JSON summary on stdout.

Usage:
    python scripts/rollback_drill.py --workdir /tmp/innerwork-drill
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

SEED_ROW_COUNT = 1_000


def _seed_db(path: Path) -> None:
    """Seed a deterministic table the drill will mutate and restore."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE rollback_drill_rows ("
            "id INTEGER PRIMARY KEY, "
            "payload TEXT NOT NULL, "
            "checksum TEXT NOT NULL)"
        )
        rows = [
            (
                i,
                f"row-{i:06d}",
                hashlib.sha256(f"row-{i:06d}".encode()).hexdigest(),
            )
            for i in range(SEED_ROW_COUNT)
        ]
        conn.executemany(
            "INSERT INTO rollback_drill_rows (id, payload, checksum) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _checksum(path: Path) -> tuple[int, str]:
    """Return (row_count, sha256-of-sorted-checksums) for the drill table."""
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT checksum FROM rollback_drill_rows ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    digest = hashlib.sha256()
    for (checksum,) in rows:
        digest.update(checksum.encode())
    return len(rows), digest.hexdigest()


def _backup(src: Path, dst: Path) -> None:
    """Mirror of ``scripts/backup.py``: online backup via Connection.backup."""
    if dst.exists():
        dst.unlink()
    src_conn = sqlite3.connect(src)
    dst_conn = sqlite3.connect(dst)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


def _restore(backup: Path, live: Path) -> None:
    """Mirror of ``scripts/restore.py --force``: replace live DB with backup."""
    if live.exists():
        live.unlink()
    shutil.copyfile(backup, live)


def _destructive_mutation(path: Path) -> None:
    """Simulate a release-introduced bug that wipes the drill table."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("DROP TABLE rollback_drill_rows")
        conn.execute(
            "CREATE TABLE rollback_drill_rows ("
            "id INTEGER PRIMARY KEY, "
            "payload TEXT NOT NULL, "
            "checksum TEXT NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


def _run(workdir: Path) -> dict[str, Any]:
    """Run the drill and return a structured summary."""
    workdir.mkdir(parents=True, exist_ok=True)
    live = workdir / "innerwork.db"
    backup = workdir / "backup-pre-mutation.db"

    started_at = time.time()
    summary: dict[str, Any] = {
        "drill": "rollback",
        "workdir": str(workdir),
        "steps": [],
        "ok": False,
    }

    def step(name: str, fn) -> None:  # type: ignore[no-untyped-def]
        step_start = time.perf_counter()
        fn()
        summary["steps"].append(
            {
                "name": name,
                "duration_ms": round((time.perf_counter() - step_start) * 1000.0, 3),
            }
        )

    step("seed", lambda: _seed_db(live))
    pre_count, pre_checksum = _checksum(live)
    summary["pre_mutation"] = {"row_count": pre_count, "checksum": pre_checksum}

    step("backup", lambda: _backup(live, backup))
    step("destructive_mutation", lambda: _destructive_mutation(live))

    mid_count, _ = _checksum(live)
    summary["post_mutation"] = {"row_count": mid_count}
    if mid_count != 0:
        summary["error"] = (
            f"destructive mutation left {mid_count} rows; "
            "drill cannot prove restore semantics"
        )
        summary["elapsed_ms"] = round((time.time() - started_at) * 1000.0, 3)
        return summary

    step("restore", lambda: _restore(backup, live))
    post_count, post_checksum = _checksum(live)
    summary["post_restore"] = {"row_count": post_count, "checksum": post_checksum}

    if post_count != pre_count or post_checksum != pre_checksum:
        summary["error"] = "restore did not reproduce pre-mutation state"
    else:
        summary["ok"] = True

    summary["elapsed_ms"] = round((time.time() - started_at) * 1000.0, 3)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("/tmp/innerwork-rollback-drill"),
        help="Directory for ephemeral drill artifacts.",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Skip cleanup so an operator can inspect the artifacts.",
    )
    args = parser.parse_args(argv)

    try:
        summary = _run(args.workdir)
    except Exception as exc:  # noqa: BLE001 — drill must surface any error
        summary = {
            "drill": "rollback",
            "workdir": str(args.workdir),
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    print(json.dumps(summary, indent=2, sort_keys=True))

    if not args.keep_workdir and args.workdir.exists():
        shutil.rmtree(args.workdir, ignore_errors=True)

    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
