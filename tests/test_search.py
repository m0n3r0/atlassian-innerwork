"""Tests for the Phase 6 cross-graph search module."""

from __future__ import annotations

from pathlib import Path

import pytest

from innerwork.domain_store import DomainStore
from innerwork.search import (
    SEARCHABLE_KINDS,
    SearchQueryError,
    search_domain,
    tokenize,
)


def _store(tmp_path: Path) -> DomainStore:
    return DomainStore(path=tmp_path / "inner.db")


def _seed(store: DomainStore):
    p1 = store.create_project(project_id="p1", key="ENG", name="Engineering", owner="eml")
    p2 = store.create_project(project_id="p2", key="MKT", name="Marketing", owner="eml")
    w1 = store.create_work_item(
        work_item_id="w1",
        project_id=p1.project_id,
        title="Onboarding flow rewrite",
        description="Migrate the onboarding flow off legacy state machine",
        assignee="eml",
    )
    w2 = store.create_work_item(
        work_item_id="w2",
        project_id=p1.project_id,
        title="Index rebuild",
        description="Recompute search index nightly",
        assignee="eml",
    )
    w3 = store.create_work_item(
        work_item_id="w3",
        project_id=p2.project_id,
        title="Launch email",
        description="Draft the onboarding launch email",
        assignee="mkt",
    )
    s1 = store.create_space(space_id="s1", key="DOCS", name="Docs", owner="eml")
    s2 = store.create_space(space_id="s2", key="OPS", name="Ops", owner="eml")
    pg1, _ = store.create_page(
        page_id="pg1",
        space_id=s1.space_id,
        title="Onboarding runbook",
        body="Step by step guide for onboarding new tenants.",
        author="eml",
    )
    pg2, _ = store.create_page(
        page_id="pg2",
        space_id=s2.space_id,
        title="Incident response",
        body="What to do when the index is corrupt.",
        author="ops",
    )
    store.create_work_item_comment(
        comment_id="c1",
        work_item_id=w1.work_item_id,
        author="eml",
        body="Pinging the onboarding squad for review.",
    )
    store.create_page_comment(
        comment_id="c2",
        page_id=pg1.page_id,
        author="ops",
        body="Add a note about the legacy index migration.",
    )
    return p1, p2, w1, w2, w3, s1, s2, pg1, pg2


def test_tokenize_basic():
    assert tokenize("Hello, WORLD! foo-bar") == ("hello", "world", "foo", "bar")
    assert tokenize("a I") == ()  # below min length
    assert tokenize("a I or") == ("or",)  # 2-char tokens are kept


def test_searchable_kinds_constant():
    assert SEARCHABLE_KINDS == ("work_item", "page", "comment")


def test_search_finds_work_items_and_pages(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    result = search_domain(store, query="onboarding")
    kinds_seen = {h.kind for h in result.hits}
    assert {"work_item", "page", "comment"} <= kinds_seen
    titles = [h.title for h in result.hits if h.kind == "work_item"]
    assert "Onboarding flow rewrite" in titles
    # Title hits outscore body hits.
    onboarding_titles = [h.score for h in result.hits if h.title == "Onboarding flow rewrite"]
    onboarding_body_only = [h.score for h in result.hits if h.title == "Launch email"]
    assert max(onboarding_titles) > max(onboarding_body_only)


def test_search_kinds_filter(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    result = search_domain(store, query="onboarding", kinds=["page"])
    assert all(h.kind == "page" for h in result.hits)
    assert result.kinds == ("page",)


def test_search_project_filter_scopes_work_items_and_comments(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    result = search_domain(store, query="onboarding", project_id="p1")
    for hit in result.hits:
        if hit.kind == "work_item":
            assert hit.project_id == "p1"
        if hit.kind == "comment" and hit.parent_kind == "work_item":
            assert hit.project_id == "p1"


def test_search_space_filter_scopes_pages(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    result = search_domain(store, query="index", space_id="s2")
    page_hits = [h for h in result.hits if h.kind == "page"]
    assert all(h.space_id == "s2" for h in page_hits)


def test_search_limit_caps_results_but_reports_total(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    result = search_domain(store, query="onboarding", limit=1)
    assert len(result.hits) == 1
    assert result.total >= 1


def test_search_empty_token_query_returns_no_hits(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    result = search_domain(store, query="!!!")
    assert result.hits == ()
    assert result.tokens == ()


def test_search_validation_errors(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(SearchQueryError):
        search_domain(store, query="")
    with pytest.raises(SearchQueryError):
        search_domain(store, query="x" * 201)
    with pytest.raises(SearchQueryError):
        search_domain(store, query="ok", kinds=["bogus"])
    with pytest.raises(SearchQueryError):
        search_domain(store, query="ok", limit=0)
    with pytest.raises(SearchQueryError):
        search_domain(store, query="ok", limit=101)


def test_search_determinism(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    a = search_domain(store, query="onboarding")
    b = search_domain(store, query="onboarding")
    assert a.to_dict() == b.to_dict()
