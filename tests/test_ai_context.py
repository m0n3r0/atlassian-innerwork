"""Tests for the Phase 6 AI-context bundler."""

from __future__ import annotations

from pathlib import Path

import pytest

from innerwork.ai_context import (
    AIContextError,
    CONTEXT_KINDS,
    DEFAULT_TOKEN_BUDGET,
    ContextBundle,
    ContextEntry,
    build_ai_context,
)
from innerwork.domain_store import DomainStore
from innerwork.permissions import AnonymousPrincipal, Principal


def _store(tmp_path: Path) -> DomainStore:
    return DomainStore(path=tmp_path / "ctx.db")


def _seed(store: DomainStore):
    store.create_project(
        project_id="pp",
        key="PUB",
        name="Public",
        owner="eml",
        visibility="public",
    )
    store.create_project(
        project_id="pr",
        key="RES",
        name="Restricted",
        owner="eml",
        visibility="restricted",
        members=("alice",),
    )
    store.create_space(
        space_id="sp",
        key="SPUB",
        name="SPub",
        owner="eml",
        visibility="public",
    )
    store.create_work_item(
        work_item_id="wa",
        project_id="pp",
        title="Login bug",
        description="users cannot log in via SSO",
        assignee="eml",
    )
    store.create_work_item(
        work_item_id="wr",
        project_id="pr",
        title="Secret feature",
        description="restricted SSO planning",
        assignee="alice",
    )
    store.create_work_item_comment(
        comment_id="ca",
        work_item_id="wa",
        author="eml",
        body="repro steps for SSO login bug",
    )
    store.transition_work_item(work_item_id="wa", to_state="in_progress", actor="eml")
    store.create_page(
        page_id="pg1",
        space_id="sp",
        title="SSO Runbook",
        body="how to debug SSO login flows",
        author="eml",
    )
    store.create_link(
        link_id="l1",
        work_item_id="wa",
        page_id="pg1",
        kind="documents",
        created_by="eml",
    )


# ----------------------------------------------------------------- module surface


def test_context_kinds_constant():
    assert CONTEXT_KINDS == ("work_item", "page", "comment", "transition", "link")


# ----------------------------------------------------------------- validation


def test_build_requires_query_or_anchor(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(AIContextError):
        build_ai_context(store)


def test_build_anchor_kind_and_id_must_pair(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(AIContextError):
        build_ai_context(store, anchor_kind="work_item")
    with pytest.raises(AIContextError):
        build_ai_context(store, anchor_id="wa")


def test_build_rejects_unknown_anchor_kind(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(AIContextError):
        build_ai_context(store, anchor_kind="garbage", anchor_id="wa")


def test_build_rejects_query_over_max_length(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(AIContextError):
        build_ai_context(store, query="x" * 201)


def test_build_rejects_invalid_budget(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(AIContextError):
        build_ai_context(store, query="sso", token_budget=10)
    with pytest.raises(AIContextError):
        build_ai_context(store, query="sso", token_budget=True)  # type: ignore[arg-type]


def test_build_rejects_invalid_max_items(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(AIContextError):
        build_ai_context(store, query="sso", max_items=0)
    with pytest.raises(AIContextError):
        build_ai_context(store, query="sso", max_items=101)


# ----------------------------------------------------------------- happy paths


def test_query_only_bundle_finds_login_work_item(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    bundle = build_ai_context(store, query="SSO login")
    assert isinstance(bundle, ContextBundle)
    assert bundle.query is not None
    assert bundle.anchor_kind is None
    kinds = {e.kind for e in bundle.entries}
    assert "work_item" in kinds


def test_anchor_work_item_expands_to_comments_links_pages(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    bundle = build_ai_context(store, anchor_kind="work_item", anchor_id="wa")
    by_kind = {e.kind: [x.entity_id for x in bundle.entries if x.kind == e.kind] for e in bundle.entries}
    assert "wa" in by_kind["work_item"]
    assert "ca" in by_kind.get("comment", [])
    assert any(e.kind == "transition" for e in bundle.entries)
    assert "l1" in by_kind.get("link", [])
    assert "pg1" in by_kind.get("page", [])
    # First entry is the anchor itself
    assert bundle.entries[0].kind == "work_item"
    assert bundle.entries[0].entity_id == "wa"
    assert bundle.entries[0].provenance["reason"] == "anchor"


def test_anchor_page_expands_to_links_and_work_items(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    bundle = build_ai_context(store, anchor_kind="page", anchor_id="pg1")
    kinds = {e.kind for e in bundle.entries}
    assert "page" in kinds
    assert "link" in kinds
    assert "work_item" in kinds  # linked from page


def test_anchor_missing_work_item_raises(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    # store.get_work_item raises WorkItemNotFoundError, not AIContextError
    from innerwork.domain_store import WorkItemNotFoundError
    with pytest.raises(WorkItemNotFoundError):
        build_ai_context(store, anchor_kind="work_item", anchor_id="nope")


# ----------------------------------------------------------------- determinism


def test_bundle_is_deterministic(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    a = build_ai_context(store, query="SSO login")
    b = build_ai_context(store, query="SSO login")
    a_keys = [(e.kind, e.entity_id) for e in a.entries]
    b_keys = [(e.kind, e.entity_id) for e in b.entries]
    assert a_keys == b_keys


# ----------------------------------------------------------------- budget cap


def test_budget_truncation_marks_truncated_flag(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    bundle = build_ai_context(
        store, anchor_kind="work_item", anchor_id="wa", token_budget=200
    )
    assert bundle.token_budget == 200
    assert bundle.approx_tokens <= bundle.token_budget
    if bundle.omitted_candidates > 0:
        assert bundle.truncated is True


def test_max_items_cap_truncates(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    bundle = build_ai_context(
        store, anchor_kind="work_item", anchor_id="wa", max_items=1
    )
    assert len(bundle.entries) == 1
    assert bundle.truncated is True


# ----------------------------------------------------------------- permissions


def test_anonymous_cannot_anchor_restricted(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(AIContextError):
        build_ai_context(
            store,
            anchor_kind="work_item",
            anchor_id="wr",
            principal=AnonymousPrincipal,
        )


def test_member_can_anchor_restricted(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    bundle = build_ai_context(
        store,
        anchor_kind="work_item",
        anchor_id="wr",
        principal=Principal(id="alice"),
    )
    assert bundle.entries[0].entity_id == "wr"


def test_query_results_filtered_by_principal(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    # Anonymous cannot see restricted project, so wr should not appear even though
    # its description contains "SSO".
    bundle = build_ai_context(store, query="SSO", principal=AnonymousPrincipal)
    ids = {e.entity_id for e in bundle.entries if e.kind == "work_item"}
    assert "wr" not in ids


# ----------------------------------------------------------------- serialization


def test_bundle_to_dict_round_trip(tmp_path: Path):
    import json

    store = _store(tmp_path)
    _seed(store)
    bundle = build_ai_context(store, anchor_kind="work_item", anchor_id="wa")
    payload = bundle.to_dict()
    assert payload["anchor_kind"] == "work_item"
    assert payload["anchor_id"] == "wa"
    json.dumps(payload)  # must not raise


def test_default_token_budget_used_when_omitted(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    bundle = build_ai_context(store, query="login")
    assert bundle.token_budget == DEFAULT_TOKEN_BUDGET


def test_query_with_only_whitespace_returns_empty_bundle(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    # Blank query is normalized to no-op (not an error); with no anchor the
    # bundle is empty.
    bundle = build_ai_context(store, query="   ")
    assert bundle.entries == ()
    assert bundle.query is None
