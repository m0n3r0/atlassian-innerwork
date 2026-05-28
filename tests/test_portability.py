"""Tests for the domain export/import round-trip (Phase F slice)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from innerwork.domain_store import DOMAIN_SCHEMA_VERSION, DomainStore
from innerwork.portability import (
    PORTABILITY_FORMAT_VERSION,
    DomainImportError,
    export_domain,
    export_domain_json,
    import_domain,
    import_domain_json,
)


# --------------------------------------------------------------- helpers


def _seed(store: DomainStore) -> None:
    """Seed a store with rows touching every collection in _COLLECTION_ORDER."""

    store.create_project(
        project_id="p1",
        key="ALPHA",
        name="Alpha",
        owner="eml",
        created_at="2026-05-01T00:00:00Z",
    )
    store.create_project(
        project_id="p2",
        key="BETA",
        name="Beta",
        owner="eml",
        created_at="2026-05-01T00:00:00Z",
    )
    w1 = store.create_work_item(
        work_item_id="w1",
        project_id="p1",
        title="t1",
        description="d1",
        assignee="alice",
        created_at="2026-05-02T00:00:00Z",
    )
    w2 = store.create_work_item(
        work_item_id="w2",
        project_id="p1",
        title="t2",
        created_at="2026-05-02T00:00:00Z",
    )
    store.create_work_item(
        work_item_id="w3",
        project_id="p2",
        title="t3",
        created_at="2026-05-02T00:00:00Z",
    )
    store.transition_work_item(
        work_item_id=w1.work_item_id,
        to_state="in_progress",
        actor="alice",
        reason="kickoff",
        occurred_at="2026-05-03T00:00:00Z",
    )
    store.transition_work_item(
        work_item_id=w2.work_item_id,
        to_state="in_progress",
        actor="bob",
        occurred_at="2026-05-03T01:00:00Z",
    )

    store.create_space(
        space_id="s1",
        key="DOCS",
        name="Docs",
        owner="eml",
        created_at="2026-05-01T00:00:00Z",
    )
    page, _v = store.create_page(
        page_id="pg1",
        space_id="s1",
        title="hello",
        body="world",
        author="eml",
        created_at="2026-05-04T00:00:00Z",
    )

    store.create_link(
        link_id="l1",
        work_item_id=w1.work_item_id,
        page_id=page.page_id,
        kind="documents",
        created_by="eml",
        created_at="2026-05-05T00:00:00Z",
    )

    store.create_work_item_comment(
        comment_id="wc1",
        work_item_id=w1.work_item_id,
        author="alice",
        body="first work comment",
        created_at="2026-05-06T00:00:00Z",
    )
    store.create_work_item_comment(
        comment_id="wc2",
        work_item_id=w1.work_item_id,
        author="bob",
        body="reply",
        created_at="2026-05-06T01:00:00Z",
    )
    store.create_page_comment(
        comment_id="pc1",
        page_id=page.page_id,
        author="eml",
        body="page comment",
        created_at="2026-05-07T00:00:00Z",
    )


def _store(tmp_path: Path, name: str = "db.sqlite") -> DomainStore:
    return DomainStore(tmp_path / name)


# --------------------------------------------------------------- export shape


def test_export_envelope_contains_versions_and_all_collections(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    payload = export_domain(store)

    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION
    assert payload["schema_version"] == DOMAIN_SCHEMA_VERSION
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
        assert key in payload, key
        assert isinstance(payload[key], list)

    assert len(payload["projects"]) == 2
    assert len(payload["work_items"]) == 3
    assert len(payload["transitions"]) == 2
    assert len(payload["spaces"]) == 1
    assert len(payload["pages"]) == 1
    assert len(payload["page_versions"]) == 1
    assert len(payload["links"]) == 1
    assert len(payload["work_item_comments"]) == 2
    assert len(payload["page_comments"]) == 1


def test_export_is_deterministic(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    a = export_domain_json(store)
    b = export_domain_json(store)
    assert a == b


def test_export_empty_store_returns_empty_collections(tmp_path: Path):
    store = _store(tmp_path)
    payload = export_domain(store)
    assert payload["format_version"] == PORTABILITY_FORMAT_VERSION
    assert payload["schema_version"] == DOMAIN_SCHEMA_VERSION
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
        assert payload[key] == []


# --------------------------------------------------------------- round trip


def test_round_trip_re_export_is_byte_identical(tmp_path: Path):
    src = _store(tmp_path, "src.sqlite")
    _seed(src)
    snapshot = export_domain_json(src)

    dst = _store(tmp_path, "dst.sqlite")
    counts = import_domain_json(dst, snapshot)

    assert counts == {
        "projects": 2,
        "work_items": 3,
        "transitions": 2,
        "spaces": 1,
        "pages": 1,
        "page_versions": 1,
        "links": 1,
        "work_item_comments": 2,
        "page_comments": 1,
    }
    assert export_domain_json(dst) == snapshot


def test_round_trip_preserves_autoincrement_for_transitions_and_versions(
    tmp_path: Path,
):
    src = _store(tmp_path, "src.sqlite")
    _seed(src)
    snapshot = export_domain(src)

    dst = _store(tmp_path, "dst.sqlite")
    import_domain(dst, snapshot)

    # After import a NEW transition / page version must get a fresh ID
    # higher than anything in the snapshot — proving sqlite_sequence was
    # bumped instead of restarting at 1.
    max_transition_id = max(int(r["transition_id"]) for r in snapshot["transitions"])
    max_version_id = max(int(r["version_id"]) for r in snapshot["page_versions"])

    _, new_transition = dst.transition_work_item(
        work_item_id="w3",
        to_state="in_progress",
        actor="carol",
        occurred_at="2026-06-01T00:00:00Z",
    )
    assert int(new_transition.transition_id) > max_transition_id

    _, new_version = dst.update_page(
        page_id="pg1",
        title="hello v2",
        body="world v2",
        author="eml",
        created_at="2026-06-02T00:00:00Z",
    )
    assert int(new_version.version_id) > max_version_id


def test_round_trip_preserves_project_sequence(tmp_path: Path):
    src = _store(tmp_path, "src.sqlite")
    _seed(src)
    snapshot = export_domain(src)

    dst = _store(tmp_path, "dst.sqlite")
    import_domain(dst, snapshot)

    # ALPHA project has w1=ALPHA-1, w2=ALPHA-2 in seed. A new work item must
    # get ALPHA-3 — not ALPHA-1 (which would collide).
    new_item = dst.create_work_item(
        work_item_id="w-new",
        project_id="p1",
        title="next",
        created_at="2026-06-03T00:00:00Z",
    )
    assert new_item.key == "ALPHA-3"


# --------------------------------------------------------------- envelope errs


def test_import_rejects_missing_format_version(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(DomainImportError, match="format_version"):
        import_domain(store, {"schema_version": DOMAIN_SCHEMA_VERSION})


def test_import_rejects_wrong_format_version(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(DomainImportError, match="format_version"):
        import_domain(
            store,
            {
                "format_version": PORTABILITY_FORMAT_VERSION + 99,
                "schema_version": DOMAIN_SCHEMA_VERSION,
            },
        )


def test_import_rejects_wrong_schema_version(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(DomainImportError, match="schema_version"):
        import_domain(
            store,
            {
                "format_version": PORTABILITY_FORMAT_VERSION,
                "schema_version": DOMAIN_SCHEMA_VERSION + 99,
            },
        )


def test_import_rejects_non_list_collection(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(DomainImportError, match="projects"):
        import_domain(
            store,
            {
                "format_version": PORTABILITY_FORMAT_VERSION,
                "schema_version": DOMAIN_SCHEMA_VERSION,
                "projects": {"not": "a list"},
            },
        )


def test_import_json_rejects_invalid_json(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(DomainImportError, match="not valid JSON"):
        import_domain_json(store, "{not json")


def test_import_json_rejects_non_object_root(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(DomainImportError, match="root"):
        import_domain_json(store, "[]")


# --------------------------------------------------------------- fresh target


def test_import_rejects_non_empty_target(tmp_path: Path):
    src = _store(tmp_path, "src.sqlite")
    _seed(src)
    snapshot = export_domain(src)

    dst = _store(tmp_path, "dst.sqlite")
    dst.create_project(
        project_id="px",
        key="EXIST",
        name="exists",
        owner="eml",
        created_at="2026-05-01T00:00:00Z",
    )
    with pytest.raises(DomainImportError, match="not empty"):
        import_domain(dst, snapshot)


def test_import_empty_envelope_into_empty_store(tmp_path: Path):
    store = _store(tmp_path)
    counts = import_domain(
        store,
        {
            "format_version": PORTABILITY_FORMAT_VERSION,
            "schema_version": DOMAIN_SCHEMA_VERSION,
        },
    )
    assert counts == {
        "projects": 0,
        "work_items": 0,
        "transitions": 0,
        "spaces": 0,
        "pages": 0,
        "page_versions": 0,
        "links": 0,
        "work_item_comments": 0,
        "page_comments": 0,
    }


def test_export_json_indent_is_configurable(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    compact = export_domain_json(store, indent=None)
    pretty = export_domain_json(store, indent=2)
    # Both must parse to the same payload; compact is a strict subset of bytes.
    assert json.loads(compact) == json.loads(pretty)
    assert "\n" not in compact
    assert "\n" in pretty
