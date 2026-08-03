"""Tests for the CSV/TSV importer (module + CLI).

Covers the locked mapping rules from
``docs/roadmap_csv_importer_scoping.md`` §2–§3 and the acceptance gates
from §5: delimiter detection and override, BOM/CRLF/quoting/blank-line
handling, column mapping and status vocabulary, key allocation and
conflict semantics (within-file and across the store), fresh-target
enforcement, ``--allow-populated``, dry-run honesty, and the portability
round-trip (import → export → import → export byte-identical).

The three checked-in fixtures under ``tests/fixtures/csv_import/`` cover
the happy paths (comma + tab) and the edge cases (BOM, CRLF, quoted
comma/tab, blank line, unknown column, ``type`` column). Error-case
inputs are written as 2–4 line tmp files inside the tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from innerwork.csv_importer import (
    CsvImportError,
    CsvImportPlan,
    import_csv_file,
    scan_csv_file,
)
from innerwork.domain_store import DomainStore
from innerwork.portability import export_domain_json, import_domain_json

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "csv_import"
FIXTURE_CSV = FIXTURE_DIR / "work_items.csv"
FIXTURE_TSV = FIXTURE_DIR / "work_items.tsv"
FIXTURE_EDGE = FIXTURE_DIR / "edge_cases.csv"

FIXED_CREATED_AT = "2026-01-01T00:00:00Z"


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
# scan_csv_file: parse + map + validate (pure)
# ---------------------------------------------------------------------------


def test_parse_comma_file() -> None:
    plan = scan_csv_file(FIXTURE_CSV, owner="importer")
    assert isinstance(plan, CsvImportPlan)
    assert plan.delimiter == "comma"
    assert [p.key for p in plan.projects] == ["ENG", "OPS"]
    assert [p.name for p in plan.projects] == ["Engineering", "Operations"]
    assert len(plan.work_items) == 4
    assert plan.warnings == ()

    by_key = {item.key: item for item in plan.work_items}
    assert set(by_key) == {"ENG-1", "ENG-2", "ENG-3", "OPS-1"}
    assert by_key["ENG-1"].title == "Fix parser, v2"
    assert by_key["ENG-1"].state == "done"
    assert by_key["ENG-1"].description == "Fix the CSV parser, v2"
    assert by_key["ENG-1"].assignee == "alice"
    assert by_key["ENG-2"].title == "Add test coverage"
    assert by_key["ENG-2"].state == "in_progress"
    assert by_key["ENG-3"].explicit_key == "ENG-3"
    assert by_key["ENG-2"].explicit_key is None


def test_parse_tab_file() -> None:
    plan = scan_csv_file(FIXTURE_TSV, owner="importer")
    assert plan.delimiter == "tab"
    assert [p.key for p in plan.projects] == ["DATA", "MARK"]
    assert len(plan.work_items) == 4
    by_key = {item.key: item for item in plan.work_items}
    assert set(by_key) == {"DATA-1", "MARK-1", "MARK-2", "MARK-5"}
    assert by_key["MARK-2"].title == "Q3 campaign brief"
    assert by_key["MARK-2"].state == "done"
    # auto allocation skips the explicit suffixes already seen
    assert by_key["MARK-1"].title == "Schedule social posts"


def test_delimiter_override_wins(tmp_path: Path) -> None:
    tab_in_csv = tmp_path / "data.csv"  # .csv extension, tab-delimited content
    tab_in_csv.write_text("project\ttitle\nENG\tOne\n", encoding="utf-8")
    plan = scan_csv_file(tab_in_csv, owner="importer", delimiter="tab")
    assert plan.delimiter == "tab"
    assert [item.title for item in plan.work_items] == ["One"]

    comma_in_tsv = tmp_path / "data.tsv"  # .tsv extension, comma content
    comma_in_tsv.write_text("project,title\nENG,One\n", encoding="utf-8")
    plan = scan_csv_file(comma_in_tsv, owner="importer", delimiter="comma")
    assert plan.delimiter == "comma"
    assert [item.title for item in plan.work_items] == ["One"]


def test_bom_crlf_quoted_and_blank_lines() -> None:
    plan = scan_csv_file(FIXTURE_EDGE, owner="importer")
    assert plan.delimiter == "comma"
    items = list(plan.work_items)
    assert len(items) == 2  # the blank line mid-file is skipped
    assert [item.title for item in items] == ["Fix parser, v2", "Untriaged task"]
    # quoted comma preserved in the title, quoted tab preserved in the description
    assert items[0].title == "Fix parser, v2"
    assert items[0].description == "Adds\ta\ttab"
    assert items[1].state == "todo"  # "open" maps to todo


def test_unknown_columns_warned(tmp_path: Path) -> None:
    plan = scan_csv_file(FIXTURE_EDGE, owner="importer")
    assert len(plan.warnings) == 2
    assert any("priority" in warning for warning in plan.warnings)
    assert any("type" in warning for warning in plan.warnings)

    # import still succeeds and reports the same warnings
    store = DomainStore(tmp_path / "store.db")
    summary = import_csv_file(store, FIXTURE_EDGE, owner="importer")
    assert summary["projects"] == 1
    assert summary["work_items"] == 2
    assert summary["warnings"] == list(plan.warnings)


def test_missing_required_column_rejected(tmp_path: Path) -> None:
    no_title = tmp_path / "no_title.csv"
    no_title.write_text("project,status\nENG,todo\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="title"):
        scan_csv_file(no_title, owner="importer")

    no_project = tmp_path / "no_project.csv"
    no_project.write_text("title,status\nFix it,todo\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="project"):
        scan_csv_file(no_project, owner="importer")


def test_missing_header_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(CsvImportError, match="empty"):
        scan_csv_file(empty, owner="importer")

    only_blanks = tmp_path / "blanks.csv"
    only_blanks.write_text("\n\n\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="empty"):
        scan_csv_file(only_blanks, owner="importer")


def test_header_only_rejected(tmp_path: Path) -> None:
    header_only = tmp_path / "header_only.csv"
    header_only.write_text("project,title\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="no data rows"):
        scan_csv_file(header_only, owner="importer")


def test_duplicate_normalized_header_rejected(tmp_path: Path) -> None:
    dup = tmp_path / "dup.csv"
    dup.write_text("project,title,Title\nENG,One,Two\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="duplicate header"):
        scan_csv_file(dup, owner="importer")

    # two aliases mapping to the same canonical column are equally ambiguous
    dup_alias = tmp_path / "dup_alias.csv"
    dup_alias.write_text("project,project_key,title\nENG,ENG2,One\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="duplicate project column"):
        scan_csv_file(dup_alias, owner="importer")


def test_short_row_rejected(tmp_path: Path) -> None:
    short = tmp_path / "short.csv"
    short.write_text("project,title,status\nENG,Fix it\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="row 2"):
        scan_csv_file(short, owner="importer")


def test_long_row_rejected(tmp_path: Path) -> None:
    long = tmp_path / "long.csv"
    long.write_text("project,title\nENG,Fix it,extra\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="row 2"):
        scan_csv_file(long, owner="importer")


def test_project_key_sanitized(tmp_path: Path) -> None:
    f = tmp_path / "keys.csv"
    f.write_text("project,title\neng,One\na-b,Two\n", encoding="utf-8")
    plan = scan_csv_file(f, owner="importer")
    assert [p.key for p in plan.projects] == ["AB", "ENG"]
    # without project_name, the name is the verbatim project cell
    assert [p.name for p in plan.projects] == ["a-b", "eng"]


def test_invalid_project_key_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad_key.csv"
    bad.write_text("project,title\nx,One\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="x"):
        scan_csv_file(bad, owner="importer")

    collision = tmp_path / "collision.csv"
    collision.write_text("project,title\na-b,One\na_b,Two\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="collision"):
        scan_csv_file(collision, owner="importer")


def test_status_mapping(tmp_path: Path) -> None:
    aliases = {
        "todo": ["todo", "backlog", "open", "to do", "to-do"],
        "in_progress": ["in_progress", "in progress", "wip", "doing", "inprogress"],
        "done": ["done", "closed", "complete", "completed", "resolved"],
    }
    lines = ["project,title,status"]
    expected: list[str] = []
    for index, (state, values) in enumerate(aliases.items(), start=1):
        for value in values:
            lines.append(f"P1,T{index},{value}")
            expected.append(state)
    f = tmp_path / "statuses.csv"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    plan = scan_csv_file(f, owner="importer")
    assert [item.state for item in plan.work_items] == expected

    # a file without a status column defaults every row to todo
    no_status = tmp_path / "no_status.csv"
    no_status.write_text("project,title\nP1,One\n", encoding="utf-8")
    plan = scan_csv_file(no_status, owner="importer")
    assert [item.state for item in plan.work_items] == ["todo"]


def test_invalid_status_rejected(tmp_path: Path) -> None:
    f = tmp_path / "bad_status.csv"
    f.write_text("project,title,status\nP1,One,Blocked\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="Blocked"):
        scan_csv_file(f, owner="importer")


def test_bad_key_prefix_rejected(tmp_path: Path) -> None:
    wrong_prefix = tmp_path / "wrong_prefix.csv"
    wrong_prefix.write_text("project,title,key\nOTHER,One,ENG-1\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="does not match project"):
        scan_csv_file(wrong_prefix, owner="importer")

    malformed = tmp_path / "malformed.csv"
    malformed.write_text("project,title,key\nENG,One,1\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="invalid work item key"):
        scan_csv_file(malformed, owner="importer")


def test_dup_key_in_file_rejected(tmp_path: Path) -> None:
    f = tmp_path / "dup_key.csv"
    f.write_text("project,title,key\nENG,One,ENG-1\nENG,Two,ENG-1\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="rows 2 and 3"):
        scan_csv_file(f, owner="importer")


# ---------------------------------------------------------------------------
# import_csv_file: fresh-target, conflicts, scoped insert
# ---------------------------------------------------------------------------


def test_import_csv_populates_store(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    summary = import_csv_file(store, FIXTURE_CSV, owner="importer", created_at=FIXED_CREATED_AT)
    assert summary == {
        "projects": 2,
        "work_items": 4,
        "warnings": [],
        "dry_run": False,
        "delimiter": "comma",
    }

    projects = {p.key: p for p in store.list_projects()}
    assert set(projects) == {"ENG", "OPS"}
    assert projects["ENG"].name == "Engineering"
    assert projects["ENG"].owner == "importer"
    assert projects["OPS"].name == "Operations"

    items = {i.key: i for i in store.list_work_items()}
    assert set(items) == {"ENG-1", "ENG-2", "ENG-3", "OPS-1"}
    assert items["ENG-1"].title == "Fix parser, v2"
    assert items["ENG-1"].state == "done"
    assert items["ENG-1"].description == "Fix the CSV parser, v2"
    assert items["ENG-1"].assignee == "alice"
    assert items["ENG-2"].title == "Add test coverage"
    assert items["ENG-2"].state == "in_progress"
    assert items["ENG-2"].assignee == "bob"
    assert items["ENG-3"].title == "Document the importer"
    assert items["ENG-3"].state == "todo"
    assert items["ENG-3"].assignee == "carol"
    assert items["OPS-1"].title == "Provision staging cluster"
    assert items["OPS-1"].state == "todo"
    assert items["OPS-1"].assignee == ""


def test_explicit_keys_used_and_sequences_bumped(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    import_csv_file(store, FIXTURE_CSV, owner="importer", created_at=FIXED_CREATED_AT)
    keys = {item.key for item in store.list_work_items()}
    assert keys == {"ENG-1", "ENG-2", "ENG-3", "OPS-1"}
    # sequences re-seeded so a later create_work_item does not collide
    eng = store.get_project_by_key("ENG")
    later = store.create_work_item(
        work_item_id="later-1", project_id=eng.project_id, title="Later item"
    )
    assert later.key == "ENG-4"
    ops = store.get_project_by_key("OPS")
    later = store.create_work_item(
        work_item_id="later-2", project_id=ops.project_id, title="Later item"
    )
    assert later.key == "OPS-2"


def test_fresh_target_required(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    store.create_project(project_id="p1", key="ENG", name="Eng", owner="tester")
    with pytest.raises(CsvImportError, match="not empty"):
        import_csv_file(store, FIXTURE_CSV, owner="importer")
    # nothing was written
    assert len(store.list_projects()) == 1
    assert len(store.list_work_items()) == 0


def test_allow_populated_imports(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    store.create_project(project_id="p1", key="ENG", name="Existing Eng", owner="tester")
    store.create_work_item(work_item_id="w1", project_id="p1", title="Existing item")  # ENG-1
    f = tmp_path / "add.csv"
    f.write_text(
        "project,project_name,title,status\n"
        "ENG,New Name,Added item,open\n"
        "OPS,Operations,New project item,done\n",
        encoding="utf-8",
    )
    summary = import_csv_file(store, f, owner="importer", allow_populated=True)
    assert summary["projects"] == 2
    assert summary["work_items"] == 2

    # existing rows untouched; auto key continues from the store's sequence
    projects = {p.key: p for p in store.list_projects()}
    assert projects["ENG"].name == "Existing Eng"
    assert projects["OPS"].name == "Operations"
    items = {i.key: i for i in store.list_work_items()}
    assert items["ENG-1"].title == "Existing item"
    assert items["ENG-2"].title == "Added item"
    assert items["ENG-2"].state == "todo"  # "open" -> todo
    assert items["OPS-1"].title == "New project item"
    assert items["OPS-1"].state == "done"
    # project_name-on-existing warning present
    warnings = cast(list[str], summary["warnings"])
    assert any("project name ignored" in w for w in warnings)


def test_natural_key_conflict_rejected(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    import_csv_file(store, FIXTURE_CSV, owner="importer")
    # no key column -> natural key (project, title); the title already exists
    f = tmp_path / "conflict.csv"
    f.write_text("project,title\nENG,Add test coverage\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="Add test coverage"):
        import_csv_file(store, f, owner="importer", allow_populated=True)
    # the second import wrote nothing
    assert len(store.list_work_items()) == 4


def test_explicit_key_conflict_rejected(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    project = store.create_project(project_id="p1", key="ENG", name="Eng", owner="tester")
    # the first work item gets key ENG-1
    store.create_work_item(work_item_id="w1", project_id=project.project_id, title="Existing")
    f = tmp_path / "conflict.csv"
    f.write_text("project,title,key\nENG,New item,ENG-1\n", encoding="utf-8")
    with pytest.raises(CsvImportError, match="ENG-1"):
        import_csv_file(store, f, owner="importer", allow_populated=True)
    assert len(store.list_work_items()) == 1


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    summary = import_csv_file(store, FIXTURE_CSV, owner="importer", dry_run=True)
    assert summary["dry_run"] is True
    assert summary["projects"] == 2
    assert summary["work_items"] == 4
    assert store.list_projects() == ()
    assert store.list_work_items() == ()


def test_roundtrip_import_export_import_byte_identical(tmp_path: Path) -> None:
    store_a = DomainStore(tmp_path / "a.db")
    import_csv_file(store_a, FIXTURE_CSV, owner="importer", created_at=FIXED_CREATED_AT)
    first_export = export_domain_json(store_a)

    store_b = DomainStore(tmp_path / "b.db")
    import_domain_json(store_b, first_export)
    second_export = export_domain_json(store_b)

    assert first_export == second_export
    # sanity: the round-tripped store still reflects the CSV
    items_b = {i.key: i for i in store_b.list_work_items()}
    assert set(items_b) == {"ENG-1", "ENG-2", "ENG-3", "OPS-1"}
    assert items_b["ENG-1"].state == "done"
    assert items_b["ENG-2"].title == "Add test coverage"


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def test_cli_help_lists_options() -> None:
    r = _run_cli("import-csv", "--help")
    assert r.returncode == 0, r.stderr
    for flag in (
        "file",
        "--database-url",
        "--owner",
        "--delimiter",
        "--dry-run",
        "--allow-populated",
    ):
        assert flag in r.stdout


def test_cli_import_csv_summary(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'import.db'}"
    r = _run_cli("import-csv", str(FIXTURE_CSV), "--database-url", db_url)
    assert r.returncode == 0, r.stderr
    summary = json.loads(r.stdout)
    assert summary == {
        "projects": 2,
        "work_items": 4,
        "warnings": [],
        "dry_run": False,
        "delimiter": "comma",
    }
    store = DomainStore(tmp_path / "import.db")
    assert len(store.list_projects()) == 2
    assert len(store.list_work_items()) == 4


def test_cli_import_tsv_summary(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'tsv.db'}"
    r = _run_cli("import-csv", str(FIXTURE_TSV), "--database-url", db_url)
    assert r.returncode == 0, r.stderr
    summary = json.loads(r.stdout)
    assert summary["delimiter"] == "tab"
    assert summary["projects"] == 2
    assert summary["work_items"] == 4


def test_cli_dry_run_no_write(tmp_path: Path) -> None:
    db_path = tmp_path / "dry.db"
    db_url = f"sqlite:///{db_path}"
    r = _run_cli("import-csv", str(FIXTURE_CSV), "--database-url", db_url, "--dry-run")
    assert r.returncode == 0, r.stderr
    summary = json.loads(r.stdout)
    assert summary["dry_run"] is True
    assert summary["projects"] == 2
    assert summary["work_items"] == 4
    store = DomainStore(db_path)
    assert store.list_projects() == ()
    assert store.list_work_items() == ()


def test_cli_missing_file_exit_2(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'x.db'}"
    r = _run_cli("import-csv", str(tmp_path / "nope.csv"), "--database-url", db_url)
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "error" in r.stderr.lower()


def test_cli_fresh_target_exit_2(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    store = DomainStore(db_path)
    store.create_project(project_id="p1", key="ENG", name="Eng", owner="tester")
    r = _run_cli("import-csv", str(FIXTURE_CSV), "--database-url", f"sqlite:///{db_path}")
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "not empty" in r.stderr
    assert len(store.list_work_items()) == 0


def test_cli_invalid_status_exit_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("project,title,status\nENG,One,Blocked\n", encoding="utf-8")
    r = _run_cli("import-csv", str(bad), "--database-url", f"sqlite:///{tmp_path / 'z.db'}")
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "Blocked" in r.stderr
