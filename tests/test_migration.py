"""End-to-end tests for Phase 10 migration: synthetic fixture + portability CLI.

These cover:

* ``innerwork.migrators.build_synthetic_fixture`` builds a payload whose
  envelope matches the current portability format / schema versions.
* The on-disk fixture (``tests/fixtures/synthetic_migration.json``) equals
  ``build_synthetic_fixture()`` byte-for-byte structurally (round-trip).
* CLI ``migrate --source synthetic`` populates a fresh store.
* CLI ``export`` of that store produces a JSON envelope.
* CLI ``import`` of that JSON envelope into a second fresh store yields the
  same row counts (round-trip is lossless).
* CLI ``metrics`` produces a domain rollup against the migrated store.
* Importing into a non-empty store fails with exit code 2 (no silent merge).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from innerwork.domain_store import DOMAIN_SCHEMA_VERSION, DomainStore
from innerwork.migrators import (
    SYNTHETIC_FIXTURE_PATH,
    build_synthetic_fixture,
    load_synthetic_fixture,
)
from innerwork.portability import PORTABILITY_FORMAT_VERSION, import_domain


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")}
    return subprocess.run(
        [sys.executable, "-m", "innerwork.cli", *args],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_synthetic_fixture_envelope_matches_portability_versions() -> None:
    payload = build_synthetic_fixture()
    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION
    assert payload["schema_version"] == DOMAIN_SCHEMA_VERSION
    # All nine collections from export_domain must be present so import
    # never has to fall back to defaults.
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
        assert isinstance(payload[key], list), f"missing collection: {key}"


def test_synthetic_fixture_on_disk_matches_builder() -> None:
    assert SYNTHETIC_FIXTURE_PATH.is_file(), (
        f"missing on-disk fixture: {SYNTHETIC_FIXTURE_PATH}"
    )
    on_disk = load_synthetic_fixture()
    in_memory = build_synthetic_fixture()
    assert on_disk == in_memory, (
        "on-disk synthetic fixture drifted from build_synthetic_fixture(); "
        "regenerate via the migrator and re-run."
    )


def test_synthetic_fixture_imports_into_fresh_store(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "fresh.db")
    counts = import_domain(store, build_synthetic_fixture())
    # Sanity: every collection inserted at least one row, matching the
    # deterministic fixture shape used by the CLI smoke tests below.
    assert counts["projects"] >= 1
    assert counts["work_items"] >= 1
    assert counts["spaces"] >= 1
    assert counts["pages"] >= 1


# ---------------------------------------------------------------------------
# CLI lifecycle
# ---------------------------------------------------------------------------


def test_cli_migrate_then_export_then_import_round_trip(tmp_path: Path) -> None:
    src_db = tmp_path / "src.db"
    src_url = f"sqlite:///{src_db}"

    # 1. migrate synthetic fixture into a fresh source store
    r = _run_cli("migrate", "--database-url", src_url, "--source", "synthetic")
    assert r.returncode == 0, r.stderr
    migrate_payload = json.loads(r.stdout)
    assert migrate_payload["source"] == "synthetic"
    src_counts = migrate_payload["imported"]
    assert src_counts["projects"] >= 1

    # 2. export to a file
    export_path = tmp_path / "export.json"
    r = _run_cli("export", "--database-url", src_url, "--out", str(export_path))
    assert r.returncode == 0, r.stderr
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["format_version"] == PORTABILITY_FORMAT_VERSION
    assert exported["schema_version"] == DOMAIN_SCHEMA_VERSION

    # 3. import into a second fresh store and assert counts match
    dst_db = tmp_path / "dst.db"
    dst_url = f"sqlite:///{dst_db}"
    r = _run_cli("import", "--database-url", dst_url, str(export_path))
    assert r.returncode == 0, r.stderr
    dst_counts = json.loads(r.stdout)["imported"]
    assert dst_counts == src_counts


def test_cli_export_stdout_when_no_out_flag(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'src.db'}"
    assert _run_cli("migrate", "--database-url", db_url).returncode == 0
    r = _run_cli("export", "--database-url", db_url)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION


def test_cli_import_into_non_empty_store_fails(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'src.db'}"
    # populate
    assert _run_cli("migrate", "--database-url", db_url).returncode == 0
    # export
    export_path = tmp_path / "export.json"
    assert (
        _run_cli(
            "export", "--database-url", db_url, "--out", str(export_path)
        ).returncode
        == 0
    )
    # re-import into same (now non-empty) store must fail
    r = _run_cli("import", "--database-url", db_url, str(export_path))
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "error" in r.stderr.lower()


def test_cli_metrics_after_migrate(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'src.db'}"
    assert _run_cli("migrate", "--database-url", db_url).returncode == 0
    r = _run_cli("metrics", "--database-url", db_url)
    assert r.returncode == 0, r.stderr
    rollup = json.loads(r.stdout)
    # whole-domain rollup keys per analytics.DomainRollup.to_dict()
    assert rollup["project_count"] >= 1
    assert rollup["work_item_count"] >= 1
    assert "projects" in rollup
    assert "spaces" in rollup
