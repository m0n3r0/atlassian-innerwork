"""Tests for the Phase 8 rollback drill script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

DRILL = Path(__file__).resolve().parent.parent / "scripts" / "rollback_drill.py"


def _run_drill(workdir: Path, *extra: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(DRILL), "--workdir", str(workdir), *extra],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(proc.stdout)
    return proc.returncode, payload


def test_rollback_drill_reports_ok_on_clean_run(tmp_path: Path) -> None:
    rc, summary = _run_drill(tmp_path / "drill1")
    assert rc == 0, summary
    assert summary["ok"] is True
    assert summary["pre_mutation"]["row_count"] == 1000
    assert summary["post_mutation"]["row_count"] == 0
    assert summary["post_restore"]["row_count"] == 1000
    assert summary["pre_mutation"]["checksum"] == summary["post_restore"]["checksum"]
    step_names = [s["name"] for s in summary["steps"]]
    assert step_names == ["seed", "backup", "destructive_mutation", "restore"]


def test_rollback_drill_keeps_workdir_with_flag(tmp_path: Path) -> None:
    workdir = tmp_path / "drill2"
    rc, summary = _run_drill(workdir, "--keep-workdir")
    assert rc == 0, summary
    assert workdir.exists()
    # Both the live db and the backup should be retained for inspection.
    assert (workdir / "innerwork.db").exists()
    assert (workdir / "backup-pre-mutation.db").exists()


def test_rollback_drill_cleans_workdir_by_default(tmp_path: Path) -> None:
    workdir = tmp_path / "drill3"
    rc, summary = _run_drill(workdir)
    assert rc == 0, summary
    assert not workdir.exists()
