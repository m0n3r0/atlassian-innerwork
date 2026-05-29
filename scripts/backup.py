#!/usr/bin/env python3
"""Backup a SQLite database file using sqlite3.Connection.backup().

Usage::

    python scripts/backup.py SOURCE DEST

Both arguments are filesystem paths. ``SOURCE`` must be a readable SQLite
database. ``DEST`` is the target file path; it will be overwritten.

Uses only the Python stdlib so it ships with no dependency footprint. The
``Connection.backup`` API safely streams pages and works correctly even
while the source database is being written by other processes.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


def backup(source: Path, dest: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"source database not found: {source}")
    if not source.is_file():
        raise IsADirectoryError(f"source must be a file: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Open source read-only to avoid accidentally creating a file if it
    # was deleted between exists() and connect().
    src_uri = f"file:{source}?mode=ro"
    with sqlite3.connect(src_uri, uri=True) as src_conn, sqlite3.connect(dest) as dst_conn:
        src_conn.backup(dst_conn)
        dst_conn.commit()
    # Best-effort permission match: 0o600 by default to avoid leaking
    # backups via world-readable files in shared dirs.
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source SQLite database file")
    parser.add_argument("dest", type=Path, help="Destination backup path")
    args = parser.parse_args(argv)
    backup(args.source, args.dest)
    print(f"backed up {args.source} -> {args.dest}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
