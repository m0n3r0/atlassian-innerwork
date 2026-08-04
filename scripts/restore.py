#!/usr/bin/env python3
"""Restore a SQLite backup produced by ``scripts/backup.py``.

Usage::

    python scripts/restore.py BACKUP DEST [--force]

By default this script refuses to overwrite an existing DEST file unless
``--force`` is passed. Restoration is performed via the stdlib
``sqlite3.Connection.backup`` API so it works on any SQLite file regardless
of size.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


def restore(backup: Path, dest: Path, *, force: bool = False) -> None:
    if not backup.exists():
        raise FileNotFoundError(f"backup not found: {backup}")
    if not backup.is_file():
        raise IsADirectoryError(f"backup must be a file: {backup}")
    if dest.exists() and not force:
        raise FileExistsError(
            f"destination exists; pass --force to overwrite: {dest}",
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Restore into a sibling temp file, then atomically rename into place.
    # If the source backup is corrupt or the copy is interrupted, the
    # existing destination is left untouched (a --force restore must never
    # destroy the store it is replacing).
    tmp = dest.with_name(f".{dest.name}.restore-{os.getpid()}.tmp")
    try:
        src_uri = f"file:{backup}?mode=ro"
        with sqlite3.connect(src_uri, uri=True) as src_conn, sqlite3.connect(tmp) as dst_conn:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path, help="Backup file to restore from")
    parser.add_argument("dest", type=Path, help="Destination database path")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite destination if it already exists",
    )
    args = parser.parse_args(argv)
    restore(args.backup, args.dest, force=args.force)
    print(f"restored {args.backup} -> {args.dest}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
