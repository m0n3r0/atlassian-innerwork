"""Tests for the Innerwork knowledge-graph domain (Phase B slice 2).

Covers:
* Space, Page, PageVersion, and Link dataclass validation
* SQLite CRUD round trips for spaces, pages, page versions, and links
* Page edits append immutable versions and advance the page header
* Cross-graph WorkItem <-> Page links enforce endpoint existence
* Duplicate (work_item_id, page_id, kind) links are rejected
* Restart-and-read-back persistence across DomainStore instances
"""

from __future__ import annotations

from pathlib import Path

import pytest

from innerwork.domain_store import (
    DomainStore,
    DuplicateLinkError,
    DuplicateSpaceKeyError,
    LinkNotFoundError,
    PageNotFoundError,
    SpaceNotFoundError,
    WorkItemNotFoundError,
)
from innerwork.knowledge import (
    LINK_KINDS,
    Link,
    Page,
    PageVersion,
    Space,
    validate_link_kind,
    validate_space_key,
)

# ----- knowledge model ---------------------------------------------------------


def test_space_key_validator_accepts_uppercase_and_rejects_bad_input():
    assert validate_space_key("DOCS") == "DOCS"
    assert validate_space_key("RFC2") == "RFC2"
    with pytest.raises(ValueError):
        validate_space_key("docs")
    with pytest.raises(ValueError):
        validate_space_key("A")  # too short
    with pytest.raises(ValueError):
        validate_space_key("HELLOTHEREYO")  # too long
    with pytest.raises(ValueError):
        validate_space_key("HAS-DASH")


def test_link_kind_validator_normalises_and_validates():
    assert validate_link_kind("documents") == "documents"
    assert validate_link_kind("  References  ") == "references"
    with pytest.raises(ValueError):
        validate_link_kind("bogus")
    assert LINK_KINDS == {"documents", "references", "implements", "blocks"}


def test_space_dataclass_validates_fields():
    Space(space_id="s1", key="DOCS", name="Docs", owner="eml", created_at="now")
    with pytest.raises(ValueError):
        Space(space_id="s1", key="DOCS", name="", owner="eml", created_at="now")


def test_page_dataclass_rejects_bad_version():
    with pytest.raises(ValueError):
        Page(
            page_id="p1",
            space_id="s1",
            current_version=0,
            created_at="now",
            updated_at="now",
        )


def test_page_version_validates_body_length():
    PageVersion(
        version_id=1,
        page_id="p1",
        version_number=1,
        title="t",
        body="b",
        author="eml",
        created_at="now",
    )
    with pytest.raises(ValueError):
        PageVersion(
            version_id=1,
            page_id="p1",
            version_number=1,
            title="t",
            body="x" * 200_001,
            author="eml",
            created_at="now",
        )


def test_link_dataclass_rejects_bad_kind():
    with pytest.raises(ValueError):
        Link(
            link_id="l1",
            work_item_id="w1",
            page_id="p1",
            kind="bogus",
            created_by="eml",
            created_at="now",
        )


# ----- store: spaces -----------------------------------------------------------


def _store(tmp_path: Path) -> DomainStore:
    return DomainStore(tmp_path / "innerwork.db")


def test_create_and_get_space_roundtrip(tmp_path: Path):
    store = _store(tmp_path)
    space = store.create_space(space_id="s1", key="DOCS", name="Docs", owner="eml")
    assert space.key == "DOCS"
    assert store.get_space("s1") == space
    assert tuple(s.key for s in store.list_spaces()) == ("DOCS",)


def test_duplicate_space_key_rejected(tmp_path: Path):
    store = _store(tmp_path)
    store.create_space(space_id="s1", key="DOCS", name="Docs", owner="eml")
    with pytest.raises(DuplicateSpaceKeyError):
        store.create_space(space_id="s2", key="DOCS", name="Docs2", owner="eml")


def test_get_space_missing(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(SpaceNotFoundError):
        store.get_space("does-not-exist")


# ----- store: pages and versions ----------------------------------------------


def test_create_page_seeds_version_1(tmp_path: Path):
    store = _store(tmp_path)
    store.create_space(space_id="s1", key="DOCS", name="Docs", owner="eml")
    page, version = store.create_page(
        page_id="p1",
        space_id="s1",
        title="Hello",
        body="World",
        author="eml",
    )
    assert page.current_version == 1
    assert version.version_number == 1
    assert version.title == "Hello"
    assert version.body == "World"
    assert store.get_page("p1") == page
    versions = store.list_page_versions("p1")
    assert len(versions) == 1
    assert versions[0].title == "Hello"


def test_update_page_appends_immutable_version_and_advances_header(tmp_path: Path):
    store = _store(tmp_path)
    store.create_space(space_id="s1", key="DOCS", name="Docs", owner="eml")
    store.create_page(page_id="p1", space_id="s1", title="v1", body="body-1", author="eml")
    page2, v2 = store.update_page(page_id="p1", title="v2", body="body-2", author="eml")
    assert page2.current_version == 2
    assert v2.version_number == 2
    page3, v3 = store.update_page(page_id="p1", title="v3", body="body-3", author="someone")
    assert page3.current_version == 3
    assert v3.author == "someone"
    versions = store.list_page_versions("p1")
    assert [v.version_number for v in versions] == [1, 2, 3]
    assert [v.title for v in versions] == ["v1", "v2", "v3"]
    # Old versions are immutable: we can still fetch v1 verbatim.
    v1 = store.get_page_version("p1", 1)
    assert v1.title == "v1"
    assert v1.body == "body-1"


def test_create_page_into_missing_space_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(SpaceNotFoundError):
        store.create_page(
            page_id="p1",
            space_id="missing",
            title="t",
            body="b",
            author="eml",
        )


def test_update_missing_page_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(PageNotFoundError):
        store.update_page(page_id="p1", title="t", body="b", author="eml")


def test_list_pages_filters_by_space(tmp_path: Path):
    store = _store(tmp_path)
    store.create_space(space_id="s1", key="DOCS", name="Docs", owner="eml")
    store.create_space(space_id="s2", key="RFC", name="RFCs", owner="eml")
    store.create_page(page_id="p1", space_id="s1", title="a", body="", author="eml")
    store.create_page(page_id="p2", space_id="s2", title="b", body="", author="eml")
    assert {p.page_id for p in store.list_pages(space_id="s1")} == {"p1"}
    assert {p.page_id for p in store.list_pages()} == {"p1", "p2"}


# ----- store: links ------------------------------------------------------------


def _make_work_item_and_page(store: DomainStore) -> tuple[str, str]:
    project = store.create_project(project_id="pr1", key="ENG", name="Eng", owner="eml")
    item = store.create_work_item(work_item_id="w1", project_id=project.project_id, title="t")
    store.create_space(space_id="s1", key="DOCS", name="Docs", owner="eml")
    page, _ = store.create_page(page_id="p1", space_id="s1", title="t", body="", author="eml")
    return item.work_item_id, page.page_id


def test_create_and_list_link(tmp_path: Path):
    store = _store(tmp_path)
    wid, pid = _make_work_item_and_page(store)
    link = store.create_link(
        link_id="l1",
        work_item_id=wid,
        page_id=pid,
        kind="documents",
        created_by="eml",
    )
    assert link.kind == "documents"
    assert store.get_link("l1") == link
    assert tuple(link_row.link_id for link_row in store.list_links_for_work_item(wid)) == ("l1",)
    assert tuple(link_row.link_id for link_row in store.list_links_for_page(pid)) == ("l1",)


def test_create_link_validates_endpoints(tmp_path: Path):
    store = _store(tmp_path)
    wid, pid = _make_work_item_and_page(store)
    with pytest.raises(WorkItemNotFoundError):
        store.create_link(
            link_id="l1",
            work_item_id="ghost",
            page_id=pid,
            kind="documents",
            created_by="eml",
        )
    with pytest.raises(PageNotFoundError):
        store.create_link(
            link_id="l1",
            work_item_id=wid,
            page_id="ghost",
            kind="documents",
            created_by="eml",
        )


def test_duplicate_link_triple_rejected(tmp_path: Path):
    store = _store(tmp_path)
    wid, pid = _make_work_item_and_page(store)
    store.create_link(
        link_id="l1",
        work_item_id=wid,
        page_id=pid,
        kind="documents",
        created_by="eml",
    )
    with pytest.raises(DuplicateLinkError):
        store.create_link(
            link_id="l2",
            work_item_id=wid,
            page_id=pid,
            kind="documents",
            created_by="someone-else",
        )
    # Different kind is OK.
    store.create_link(
        link_id="l3",
        work_item_id=wid,
        page_id=pid,
        kind="references",
        created_by="eml",
    )


def test_delete_link_removes_it(tmp_path: Path):
    store = _store(tmp_path)
    wid, pid = _make_work_item_and_page(store)
    store.create_link(
        link_id="l1",
        work_item_id=wid,
        page_id=pid,
        kind="documents",
        created_by="eml",
    )
    store.delete_link("l1")
    with pytest.raises(LinkNotFoundError):
        store.get_link("l1")
    with pytest.raises(LinkNotFoundError):
        store.delete_link("l1")


# ----- restart-and-read-back ---------------------------------------------------


def test_knowledge_store_persists_across_instances(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    a = DomainStore(db)
    a.create_space(space_id="s1", key="DOCS", name="Docs", owner="eml")
    a.create_page(page_id="p1", space_id="s1", title="t", body="b", author="eml")
    a.update_page(page_id="p1", title="t2", body="b2", author="eml")
    b = DomainStore(db)
    page = b.get_page("p1")
    assert page.current_version == 2
    versions = b.list_page_versions("p1")
    assert [v.title for v in versions] == ["t", "t2"]
