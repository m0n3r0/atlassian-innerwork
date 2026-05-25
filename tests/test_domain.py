"""Tests for the Innerwork work-graph domain (Phase B slice 1).

Covers:
* default workflow shape and reachability
* invalid-transition rejection at the model layer
* project/work-item CRUD round trips in SQLite
* project-scoped key allocation (ENG-1, ENG-2, ...)
* transition history is append-only and ordered
* restart-and-read-back persistence across DomainStore instances
"""

from __future__ import annotations

from pathlib import Path

import pytest

from innerwork.domain import (
    ALLOWED_TRANSITIONS,
    INITIAL_STATE,
    WORKFLOW_STATES,
    InvalidTransitionError,
    allowed_next_states,
    assert_transition_allowed,
    default_workflow,
    validate_project_key,
)
from innerwork.domain_store import (
    DomainStore,
    DuplicateProjectKeyError,
    ProjectNotFoundError,
    WorkItemNotFoundError,
)

# ----- domain model -------------------------------------------------------------


def test_default_workflow_has_three_states_with_explicit_reopen_edges():
    wf = default_workflow()
    assert wf.states == ("todo", "in_progress", "done")
    assert wf.initial_state == "todo"
    pairs = set(wf.transitions)
    assert ("todo", "in_progress") in pairs
    assert ("in_progress", "done") in pairs
    assert ("done", "in_progress") in pairs  # explicit reopen
    assert ("in_progress", "todo") in pairs  # explicit reopen


def test_initial_state_is_member_of_workflow_states():
    assert INITIAL_STATE in WORKFLOW_STATES


def test_allowed_next_states_for_each_state():
    assert allowed_next_states("todo") == ("in_progress",)
    assert set(allowed_next_states("in_progress")) == {"done", "todo"}
    assert allowed_next_states("done") == ("in_progress",)


def test_assert_transition_allowed_rejects_self_transitions():
    with pytest.raises(InvalidTransitionError, match="no-op"):
        assert_transition_allowed("todo", "todo")


def test_assert_transition_allowed_rejects_unknown_states():
    with pytest.raises(InvalidTransitionError, match="unknown to_state"):
        assert_transition_allowed("todo", "blocked")
    with pytest.raises(InvalidTransitionError, match="unknown from_state"):
        assert_transition_allowed("blocked", "done")


def test_assert_transition_allowed_rejects_skip_states():
    with pytest.raises(InvalidTransitionError, match="not allowed"):
        assert_transition_allowed("todo", "done")


def test_validate_project_key_enforces_format():
    assert validate_project_key("ENG") == "ENG"
    assert validate_project_key("ENG2") == "ENG2"
    with pytest.raises(ValueError):
        validate_project_key("eng")
    with pytest.raises(ValueError):
        validate_project_key("E")  # too short
    with pytest.raises(ValueError):
        validate_project_key("TOOLONGKEY1")  # 11 chars


# ----- store: projects ----------------------------------------------------------


def _store(tmp_path: Path) -> DomainStore:
    return DomainStore(tmp_path / "innerwork.db")


def test_create_and_get_project_round_trip(tmp_path: Path):
    store = _store(tmp_path)
    project = store.create_project(project_id="p-1", key="ENG", name="Engineering", owner="eml")
    assert project.key == "ENG"
    assert store.get_project("p-1").name == "Engineering"
    assert store.get_project_by_key("ENG").project_id == "p-1"
    assert [p.key for p in store.list_projects()] == ["ENG"]


def test_create_project_rejects_duplicate_key(tmp_path: Path):
    store = _store(tmp_path)
    store.create_project(project_id="p-1", key="ENG", name="Engineering", owner="eml")
    with pytest.raises(DuplicateProjectKeyError):
        store.create_project(project_id="p-2", key="ENG", name="Other", owner="x")


def test_get_project_missing_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(ProjectNotFoundError):
        store.get_project("nope")


# ----- store: work items --------------------------------------------------------


def test_create_work_item_allocates_project_scoped_key(tmp_path: Path):
    store = _store(tmp_path)
    store.create_project(project_id="p-1", key="ENG", name="Engineering", owner="eml")
    store.create_project(project_id="p-2", key="DOC", name="Docs", owner="eml")

    eng1 = store.create_work_item(work_item_id="w-1", project_id="p-1", title="Set up CI")
    eng2 = store.create_work_item(work_item_id="w-2", project_id="p-1", title="Add migrations")
    doc1 = store.create_work_item(work_item_id="w-3", project_id="p-2", title="Write README")

    assert eng1.key == "ENG-1"
    assert eng2.key == "ENG-2"
    assert doc1.key == "DOC-1"
    assert eng1.state == "todo"
    assert eng1.created_at == eng1.updated_at


def test_create_work_item_under_missing_project_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(ProjectNotFoundError):
        store.create_work_item(work_item_id="w-1", project_id="missing", title="x")


def test_list_work_items_filters_by_project_and_state(tmp_path: Path):
    store = _store(tmp_path)
    store.create_project(project_id="p-1", key="ENG", name="Engineering", owner="eml")
    store.create_project(project_id="p-2", key="DOC", name="Docs", owner="eml")
    a = store.create_work_item(work_item_id="w-1", project_id="p-1", title="A")
    store.create_work_item(work_item_id="w-2", project_id="p-1", title="B")
    store.create_work_item(work_item_id="w-3", project_id="p-2", title="C")
    store.transition_work_item(work_item_id=a.work_item_id, to_state="in_progress", actor="eml")

    eng_items = store.list_work_items(project_id="p-1")
    assert [i.key for i in eng_items] == ["ENG-1", "ENG-2"]

    in_progress = store.list_work_items(state="in_progress")
    assert [i.work_item_id for i in in_progress] == ["w-1"]

    with pytest.raises(ValueError):
        store.list_work_items(state="bogus")


# ----- store: transitions -------------------------------------------------------


def test_transition_happy_path_updates_state_and_records_history(tmp_path: Path):
    store = _store(tmp_path)
    store.create_project(project_id="p-1", key="ENG", name="Engineering", owner="eml")
    item = store.create_work_item(work_item_id="w-1", project_id="p-1", title="A")

    after, t1 = store.transition_work_item(
        work_item_id=item.work_item_id, to_state="in_progress", actor="eml"
    )
    assert after.state == "in_progress"
    assert after.updated_at >= item.updated_at
    assert t1.from_state == "todo" and t1.to_state == "in_progress"
    assert t1.transition_id >= 1

    done, t2 = store.transition_work_item(
        work_item_id=item.work_item_id, to_state="done", actor="eml", reason="merged"
    )
    assert done.state == "done"
    assert t2.reason == "merged"

    history = store.list_transitions(item.work_item_id)
    assert [(t.from_state, t.to_state) for t in history] == [
        ("todo", "in_progress"),
        ("in_progress", "done"),
    ]


def test_transition_rejects_invalid_target(tmp_path: Path):
    store = _store(tmp_path)
    store.create_project(project_id="p-1", key="ENG", name="Engineering", owner="eml")
    item = store.create_work_item(work_item_id="w-1", project_id="p-1", title="A")

    with pytest.raises(InvalidTransitionError):
        store.transition_work_item(work_item_id=item.work_item_id, to_state="done", actor="eml")
    # State unchanged after rejected transition
    assert store.get_work_item(item.work_item_id).state == "todo"
    assert store.list_transitions(item.work_item_id) == ()


def test_transition_rejects_blank_actor(tmp_path: Path):
    store = _store(tmp_path)
    store.create_project(project_id="p-1", key="ENG", name="Engineering", owner="eml")
    item = store.create_work_item(work_item_id="w-1", project_id="p-1", title="A")
    with pytest.raises(ValueError):
        store.transition_work_item(
            work_item_id=item.work_item_id, to_state="in_progress", actor="   "
        )


def test_transition_missing_work_item_raises(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(WorkItemNotFoundError):
        store.transition_work_item(work_item_id="nope", to_state="in_progress", actor="eml")


# ----- store: persistence -------------------------------------------------------


def test_state_survives_restart(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    first = DomainStore(db)
    first.create_project(project_id="p-1", key="ENG", name="Engineering", owner="eml")
    item = first.create_work_item(work_item_id="w-1", project_id="p-1", title="Set up CI")
    first.transition_work_item(work_item_id=item.work_item_id, to_state="in_progress", actor="eml")

    second = DomainStore(db)  # simulate process restart
    reopened = second.get_work_item("w-1")
    assert reopened.state == "in_progress"
    assert reopened.key == "ENG-1"
    assert [t.to_state for t in second.list_transitions("w-1")] == ["in_progress"]

    # Sequence allocator is also persisted across restarts.
    item2 = second.create_work_item(work_item_id="w-2", project_id="p-1", title="Next")
    assert item2.key == "ENG-2"


# ----- sanity --------------------------------------------------------------------


def test_allowed_transitions_set_is_a_subset_of_workflow_states_squared():
    for f, t in ALLOWED_TRANSITIONS:
        assert f in WORKFLOW_STATES
        assert t in WORKFLOW_STATES
        assert f != t
