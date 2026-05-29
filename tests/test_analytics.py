"""Tests for the Phase 6 deterministic analytics module."""

from __future__ import annotations

from pathlib import Path

import pytest

from innerwork.analytics import (
    AnalyticsError,
    DomainRollup,
    ProjectRollup,
    SpaceRollup,
    domain_rollup,
    project_rollup,
    space_rollup,
)
from innerwork.domain import WORKFLOW_STATES
from innerwork.domain_store import DomainStore
from innerwork.permissions import AnonymousPrincipal, Principal


def _store(tmp_path: Path) -> DomainStore:
    return DomainStore(path=tmp_path / "inner.db")


def _seed(store: DomainStore):
    """Seed two projects (one restricted) and two spaces (one public)."""
    p_pub = store.create_project(
        project_id="pp",
        key="PUB",
        name="Public",
        owner="eml",
        visibility="public",
    )
    p_int = store.create_project(
        project_id="pi",
        key="INT",
        name="Internal",
        owner="eml",
        visibility="internal",
    )
    p_res = store.create_project(
        project_id="pr",
        key="RES",
        name="Restricted",
        owner="eml",
        visibility="restricted",
        members=("alice", "sec"),
    )
    # Work items: pp has 2 (1 todo, 1 done), pi has 1 in_progress, pr has 1 todo.
    w_pp_a = store.create_work_item(
        work_item_id="wa", project_id="pp", title="A", description="", assignee="eml"
    )
    w_pp_b = store.create_work_item(
        work_item_id="wb", project_id="pp", title="B", description="", assignee="eml"
    )
    store.create_work_item(
        work_item_id="wc", project_id="pi", title="C", description="", assignee="eml"
    )
    store.create_work_item(
        work_item_id="wd", project_id="pr", title="D", description="", assignee="eml"
    )
    # Transition wb to done, wc to in_progress.
    store.transition_work_item(work_item_id="wb", to_state="in_progress", actor="eml")
    store.transition_work_item(work_item_id="wb", to_state="done", actor="eml")
    store.transition_work_item(work_item_id="wc", to_state="in_progress", actor="eml")
    # Comments: wa gets 2 comments.
    store.create_work_item_comment(
        comment_id="ca", work_item_id="wa", author="eml", body="hi"
    )
    store.create_work_item_comment(
        comment_id="cb", work_item_id="wa", author="eml", body="hello"
    )

    # Spaces
    s_pub = store.create_space(
        space_id="sp", key="SPUB", name="SPub", owner="eml", visibility="public"
    )
    s_res = store.create_space(
        space_id="sr",
        key="SRES",
        name="SRes",
        owner="eml",
        visibility="restricted",
        members=("alice",),
    )
    pg1, _ = store.create_page(
        page_id="pg1",
        space_id="sp",
        title="Welcome",
        body="hi",
        author="eml",
    )
    # add a second version
    store.update_page(
        page_id="pg1",
        title="Welcome",
        body="hi v2",
        author="eml",
    )
    store.create_page_comment(comment_id="pc1", page_id="pg1", author="eml", body="ok")
    # restricted-space page
    store.create_page(
        page_id="pg2",
        space_id="sr",
        title="Secret",
        body="shh",
        author="alice",
    )
    return p_pub, p_int, p_res, s_pub, s_res


# ----------------------------------------------------------------- project_rollup


def test_project_rollup_counts_states_comments_transitions(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    r = project_rollup(store, "pp")
    assert isinstance(r, ProjectRollup)
    assert r.project_id == "pp"
    assert r.work_item_count == 2
    # wa todo, wb done
    assert r.work_items_by_state["todo"] == 1
    assert r.work_items_by_state["done"] == 1
    assert r.work_items_by_state["in_progress"] == 0
    assert set(r.work_items_by_state.keys()) == set(WORKFLOW_STATES)
    assert r.comment_count == 2
    # wb transitioned twice (todo->in_progress, in_progress->done)
    assert r.transition_count == 2


def test_project_rollup_missing_project_raises(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(AnalyticsError):
        project_rollup(store, "no-such-project")


def test_project_rollup_denied_for_anonymous_on_restricted(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(AnalyticsError):
        project_rollup(store, "pr", principal=AnonymousPrincipal)


def test_project_rollup_allowed_member(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    r = project_rollup(store, "pr", principal=Principal(id="alice"))
    assert r.project_id == "pr"


# ----------------------------------------------------------------- space_rollup


def test_space_rollup_counts_pages_versions_comments(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    r = space_rollup(store, "sp")
    assert isinstance(r, SpaceRollup)
    assert r.page_count == 1
    assert r.page_version_count == 2
    assert r.comment_count == 1


def test_space_rollup_denied_anon_on_restricted(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(AnalyticsError):
        space_rollup(store, "sr", principal=AnonymousPrincipal)


# ----------------------------------------------------------------- domain_rollup


def test_domain_rollup_full_view_when_principal_none(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    r = domain_rollup(store)
    assert isinstance(r, DomainRollup)
    assert r.project_count == 3
    assert r.space_count == 2
    assert r.work_item_count == 4
    assert r.page_count == 2
    # Sorted by key.
    keys = [p.key for p in r.projects]
    assert keys == sorted(keys)


def test_domain_rollup_anonymous_sees_only_public(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    r = domain_rollup(store, principal=AnonymousPrincipal)
    # public project pp + public space sp only
    project_keys = [p.key for p in r.projects]
    space_keys = [s.key for s in r.spaces]
    assert project_keys == ["PUB"]
    assert space_keys == ["SPUB"]
    assert r.work_item_count == 2
    assert r.page_count == 1


def test_domain_rollup_named_principal_sees_internal_too(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    r = domain_rollup(store, principal=Principal(id="bob"))
    project_keys = {p.key for p in r.projects}
    assert project_keys == {"PUB", "INT"}  # restricted hidden


def test_domain_rollup_restricted_member_sees_restricted(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    r = domain_rollup(store, principal=Principal(id="alice"))
    project_keys = {p.key for p in r.projects}
    space_keys = {s.key for s in r.spaces}
    assert project_keys == {"PUB", "INT", "RES"}
    assert space_keys == {"SPUB", "SRES"}


def test_domain_rollup_to_dict_serializable(tmp_path: Path):
    import json

    store = _store(tmp_path)
    _seed(store)
    r = domain_rollup(store)
    payload = r.to_dict()
    json.dumps(payload)  # must not raise
    assert "projects" in payload and "spaces" in payload


def test_domain_rollup_state_counter_covers_all_workflow_states(tmp_path: Path):
    store = _store(tmp_path)
    _seed(store)
    r = domain_rollup(store)
    assert set(r.work_items_by_state.keys()) == set(WORKFLOW_STATES)
