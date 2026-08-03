"""Tests for the markdown-tree importer (module + CLI).

Covers the locked mapping rules from
``docs/roadmap_markdown_importer_scoping.md`` §2–§3 and the acceptance
gates from §5: directory→space/page mapping, frontmatter handling
(title/author override, unknown-key warnings, malformed input),
fresh-target enforcement, and the portability round-trip
(import → export → import → export byte-identical).

The checked-in fixture tree deliberately contains ``root.md`` (the
root-level error case), so every test that needs a *successful* import
works on a tmp copy of the fixture with ``root.md`` removed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from innerwork.domain_store import DomainStore
from innerwork.knowledge import PageVersion
from innerwork.markdown_importer import (
    MarkdownImportError,
    MarkdownPage,
    MarkdownTree,
    import_markdown_tree,
    scan_markdown_tree,
)
from innerwork.portability import export_domain_json, import_domain_json

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "markdown_tree"

FIXED_CREATED_AT = "2026-01-01T00:00:00Z"


def _fixture_copy(tmp_path: Path) -> Path:
    """Copy the checked-in fixture without its root-level ``root.md``."""

    dst = tmp_path / "markdown_tree"
    shutil.copytree(FIXTURE_DIR, dst)
    (dst / "root.md").unlink()
    return dst


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")}
    return subprocess.run(
        [sys.executable, "-m", "innerwork.cli", *args],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


def _scanned_pages(tree: MarkdownTree) -> dict[str, MarkdownPage]:
    return {page.title: page for space in tree.spaces for page in space.pages}


def _store_page_versions(store: DomainStore) -> dict[str, PageVersion]:
    out: dict[str, PageVersion] = {}
    for page in store.list_pages():
        version = store.get_page_version(page.page_id, page.current_version)
        out[version.title] = version
    return out


# ---------------------------------------------------------------------------
# scan_markdown_tree: directory → space/page mapping
# ---------------------------------------------------------------------------


def test_scan_tree_maps_directories_to_spaces(tmp_path: Path) -> None:
    tree = scan_markdown_tree(_fixture_copy(tmp_path), author="importer")
    assert [space.key for space in tree.spaces] == ["DOCS", "ENG"]
    assert [space.name for space in tree.spaces] == ["docs", "eng"]

    pages = _scanned_pages(tree)
    assert len(pages) == 4
    assert set(pages) == {
        "Docs Home",
        "guides/getting-started",
        "Runbook",
        "empty",
    }
    # frontmatter title wins; nested path flattens into the title
    assert pages["Docs Home"].space_key == "DOCS"
    assert pages["Docs Home"].body == "# Docs Home\n\nWelcome to the docs space."
    assert pages["guides/getting-started"].space_key == "DOCS"
    assert "[[setup-guide]]" in pages["guides/getting-started"].body
    # non-md file ignored, empty file becomes an empty-body page
    assert pages["empty"].body == ""


def test_nested_dirs_flatten_into_titles(tmp_path: Path) -> None:
    tree = scan_markdown_tree(_fixture_copy(tmp_path), author="importer")
    pages = _scanned_pages(tree)
    assert pages["guides/getting-started"].title == "guides/getting-started"
    # still lives in DOCS, not a new space
    assert pages["guides/getting-started"].space_key == "DOCS"


def test_frontmatter_title_and_author(tmp_path: Path) -> None:
    tree = scan_markdown_tree(_fixture_copy(tmp_path), author="importer")
    pages = _scanned_pages(tree)
    # frontmatter wins over stem / --author default
    assert pages["Docs Home"].author == "alice@example.test"
    assert pages["guides/getting-started"].author == "importer"


def test_unknown_frontmatter_keys_warned(tmp_path: Path) -> None:
    tree = scan_markdown_tree(_fixture_copy(tmp_path), author="importer")
    assert any(
        "eng/runbook.md" in warning and "tags" in warning
        for warning in tree.warnings
    )
    # the unknown key's value is not stored anywhere
    runbook = _scanned_pages(tree)["Runbook"]
    assert not runbook.body.startswith("---")
    assert "ops" not in runbook.body


def test_malformed_frontmatter_raises(tmp_path: Path) -> None:
    unclosed = tmp_path / "unclosed"
    (unclosed / "space").mkdir(parents=True)
    (unclosed / "space" / "page.md").write_text(
        "---\ntitle: X\n# body\n", encoding="utf-8"
    )
    with pytest.raises(MarkdownImportError, match="never closed"):
        scan_markdown_tree(unclosed, author="importer")

    bad_yaml = tmp_path / "bad_yaml"
    (bad_yaml / "space").mkdir(parents=True)
    (bad_yaml / "space" / "page.md").write_text(
        "---\ntitle: [unclosed\n---\nbody\n", encoding="utf-8"
    )
    with pytest.raises(MarkdownImportError, match="invalid YAML"):
        scan_markdown_tree(bad_yaml, author="importer")


def test_empty_file_imports_empty_body(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    import_markdown_tree(
        store, _fixture_copy(tmp_path), author="importer", created_at=FIXED_CREATED_AT
    )
    versions = _store_page_versions(store)
    assert versions["empty"].body == ""


def test_invalid_space_key_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad_key"
    (bad / "x").mkdir(parents=True)  # sanitizes to "X" — 1 char, below the 2-char minimum
    with pytest.raises(MarkdownImportError, match="space key"):
        scan_markdown_tree(bad, author="importer")


def test_space_key_collision_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "collision"
    (bad / "a-b").mkdir(parents=True)  # -> AB
    (bad / "a_b").mkdir()  # -> AB
    with pytest.raises(MarkdownImportError, match="collision"):
        scan_markdown_tree(bad, author="importer")


def test_root_level_md_rejected() -> None:
    with pytest.raises(MarkdownImportError, match="root.md"):
        scan_markdown_tree(FIXTURE_DIR, author="importer")


def test_body_over_limit_rejected(tmp_path: Path) -> None:
    big = tmp_path / "big"
    (big / "space").mkdir(parents=True)
    (big / "space" / "huge.md").write_text(
        "# H\n" + "x" * 200_001, encoding="utf-8"
    )
    with pytest.raises(MarkdownImportError, match="body exceeds"):
        scan_markdown_tree(big, author="importer")


# ---------------------------------------------------------------------------
# import_markdown_tree: writes through DomainStore
# ---------------------------------------------------------------------------


def test_import_markdown_tree_populates_store(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    summary = import_markdown_tree(
        store, _fixture_copy(tmp_path), author="importer", created_at=FIXED_CREATED_AT
    )
    assert summary == {
        "spaces": 2,
        "pages": 4,
        "warnings": ["eng/runbook.md: unknown frontmatter key(s): tags"],
        "dry_run": False,
    }

    spaces = {space.key: space for space in store.list_spaces()}
    assert set(spaces) == {"DOCS", "ENG"}
    assert spaces["DOCS"].name == "docs"
    assert spaces["DOCS"].owner == "importer"
    assert spaces["ENG"].name == "eng"

    versions = _store_page_versions(store)
    assert len(versions) == 4
    assert versions["Docs Home"].title == "Docs Home"
    assert versions["Docs Home"].author == "alice@example.test"
    assert versions["Docs Home"].body == "# Docs Home\n\nWelcome to the docs space."
    assert versions["guides/getting-started"].title == "guides/getting-started"
    assert versions["guides/getting-started"].author == "importer"
    assert versions["empty"].body == ""
    # every imported page is exactly version 1 (no history)
    for page in store.list_pages():
        assert page.current_version == 1


def test_fresh_target_required(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    store.create_space(
        space_id="existing", key="EXIST", name="Existing", owner="tester"
    )
    with pytest.raises(MarkdownImportError, match="not empty"):
        import_markdown_tree(
            store, _fixture_copy(tmp_path), author="importer"
        )
    # nothing was added
    assert len(store.list_spaces()) == 1
    assert len(store.list_pages()) == 0


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    store = DomainStore(tmp_path / "store.db")
    summary = import_markdown_tree(
        store, _fixture_copy(tmp_path), author="importer", dry_run=True
    )
    assert summary["dry_run"] is True
    assert summary["spaces"] == 2
    assert summary["pages"] == 4
    assert store.list_spaces() == ()
    assert store.list_pages() == ()


# ---------------------------------------------------------------------------
# Portability round-trip: import → export → import → export byte-identical
# ---------------------------------------------------------------------------


def test_roundtrip_import_export_import_byte_identical(tmp_path: Path) -> None:
    store_a = DomainStore(tmp_path / "a.db")
    import_markdown_tree(
        store_a,
        _fixture_copy(tmp_path),
        author="importer",
        created_at=FIXED_CREATED_AT,
    )
    first_export = export_domain_json(store_a)

    store_b = DomainStore(tmp_path / "b.db")
    import_domain_json(store_b, first_export)
    second_export = export_domain_json(store_b)

    assert first_export == second_export
    # sanity: the round-tripped store still reflects the tree
    versions = _store_page_versions(store_b)
    assert set(versions) == {
        "Docs Home",
        "guides/getting-started",
        "Runbook",
        "empty",
    }


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def test_cli_import_markdown_summary(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'import.db'}"
    r = _run_cli("import-markdown", str(_fixture_copy(tmp_path)), "--database-url", db_url)
    assert r.returncode == 0, r.stderr
    summary = json.loads(r.stdout)
    assert summary["spaces"] == 2
    assert summary["pages"] == 4
    assert summary["dry_run"] is False
    assert len(summary["warnings"]) == 1
    assert "runbook" in summary["warnings"][0]
    # rows really landed
    store = DomainStore(tmp_path / "import.db")
    assert len(store.list_spaces()) == 2
    assert len(store.list_pages()) == 4


def test_cli_dry_run_no_write(tmp_path: Path) -> None:
    db_path = tmp_path / "dry.db"
    db_url = f"sqlite:///{db_path}"
    r = _run_cli(
        "import-markdown",
        str(_fixture_copy(tmp_path)),
        "--database-url",
        db_url,
        "--dry-run",
    )
    assert r.returncode == 0, r.stderr
    summary = json.loads(r.stdout)
    assert summary["dry_run"] is True
    assert summary["spaces"] == 2
    assert summary["pages"] == 4
    store = DomainStore(db_path)
    assert store.list_spaces() == ()
    assert store.list_pages() == ()


def test_cli_missing_dir_exit_2(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'x.db'}"
    r = _run_cli("import-markdown", str(tmp_path / "nope"), "--database-url", db_url)
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "error" in r.stderr.lower()


def test_cli_root_md_exit_2(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'x.db'}"
    r = _run_cli("import-markdown", str(FIXTURE_DIR), "--database-url", db_url)
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "root.md" in r.stderr
