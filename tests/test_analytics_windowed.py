"""Tests for optional time-windowed analytics aggregations.

Locked by docs/roadmap_time_windowed_metrics_scoping.md §6: every fixture
timestamp is explicit so expected values are hand-computed literals; the
arithmetic behind each literal is written in a comment on the same line.

The master fixture ("hand" seed) uses the window

    W = [2024-01-03T00:00:00Z, 2024-01-05T00:00:00Z)   (half-open)

All events are inside W unless marked OUT.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from innerwork.analytics import (
    AnalyticsError,
    DomainWindowMetrics,
    domain_rollup,
    windowed_domain_rollup,
)
from innerwork.domain_store import DomainStore
from innerwork.migrators import build_synthetic_fixture
from innerwork.permissions import AnonymousPrincipal, Principal
from innerwork.portability import import_domain

W_START = "2024-01-03T00:00:00Z"
W_END = "2024-01-05T00:00:00Z"


def _store(tmp_path: Path) -> DomainStore:
    return DomainStore(path=tmp_path / "inner.db")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")}
    return subprocess.run(
        [sys.executable, "-m", "innerwork.cli", *args],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


def _seed_hand(store: DomainStore) -> None:
    """Deterministic fixture with every timestamp explicit (all in 2024-01)."""
    store.create_project(
        project_id="pp", key="PUB", name="Public", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    store.create_project(
        project_id="pi", key="INT", name="Internal", owner="eml",
        visibility="internal", created_at="2024-01-01T00:00:00Z",
    )
    store.create_project(
        project_id="pr", key="RES", name="Restricted", owner="eml",
        visibility="restricted", members=("alice",), created_at="2024-01-01T00:00:00Z",
    )

    store.create_work_item(
        work_item_id="wa", project_id="pp", title="A", description="",
        assignee="eml", created_at="2024-01-02T00:00:00Z",
    )
    store.create_work_item(
        work_item_id="wb", project_id="pp", title="B", description="",
        assignee="eml", created_at="2024-01-02T12:00:00Z",
    )
    store.create_work_item(
        work_item_id="wc", project_id="pi", title="C", description="",
        assignee="eml", created_at="2024-01-02T00:00:00Z",
    )
    store.create_work_item(
        work_item_id="wd", project_id="pr", title="D", description="",
        assignee="eml", created_at="2024-01-02T00:00:00Z",
    )

    # wa: todo -> in_progress @ Jan3 09:00 (IN), in_progress -> done @ Jan4 09:00 (IN)
    store.transition_work_item(
        work_item_id="wa", to_state="in_progress", actor="alice",
        occurred_at="2024-01-03T09:00:00Z",
    )
    store.transition_work_item(
        work_item_id="wa", to_state="done", actor="alice",
        occurred_at="2024-01-04T09:00:00Z",
    )
    # wb: todo -> in_progress @ Jan2 10:00 (OUT), in_progress -> done @ Jan4 20:00 (IN)
    store.transition_work_item(
        work_item_id="wb", to_state="in_progress", actor="bob",
        occurred_at="2024-01-02T10:00:00Z",
    )
    store.transition_work_item(
        work_item_id="wb", to_state="done", actor="bob",
        occurred_at="2024-01-04T20:00:00Z",
    )
    # wc: todo -> in_progress @ Jan6 10:00 (OUT)
    store.transition_work_item(
        work_item_id="wc", to_state="in_progress", actor="carol",
        occurred_at="2024-01-06T10:00:00Z",
    )
    # wd: todo -> in_progress @ Jan2 11:00 (OUT) — restricted project
    store.transition_work_item(
        work_item_id="wd", to_state="in_progress", actor="dave",
        occurred_at="2024-01-02T11:00:00Z",
    )

    store.create_work_item_comment(
        comment_id="c1", work_item_id="wa", author="alice", body="in",
        created_at="2024-01-03T12:00:00Z",
    )
    store.create_work_item_comment(
        comment_id="c2", work_item_id="wa", author="alice", body="out",
        created_at="2024-01-06T12:00:00Z",
    )
    store.create_work_item_comment(
        comment_id="c3", work_item_id="wd", author="dave", body="in restricted",
        created_at="2024-01-03T13:00:00Z",
    )

    store.create_space(
        space_id="sp", key="DOCS", name="Docs", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    store.create_space(
        space_id="sr", key="SRES", name="SRes", owner="eml",
        visibility="restricted", members=("alice",), created_at="2024-01-01T00:00:00Z",
    )

    # pg1: v1 @ Jan2 08:00 (OUT), v2 @ Jan3 10:00 (IN), v3 @ Jan4 11:00 (IN)
    store.create_page(
        page_id="pg1", space_id="sp", title="One", body="v1", author="alice",
        created_at="2024-01-02T08:00:00Z",
    )
    store.update_page(
        page_id="pg1", title="One", body="v2", author="alice",
        created_at="2024-01-03T10:00:00Z",
    )
    store.update_page(
        page_id="pg1", title="One", body="v3", author="bob",
        created_at="2024-01-04T11:00:00Z",
    )
    # pg2: v1 @ Jan2 09:00 (OUT), v2 @ Jan3 12:00 (IN) — restricted space
    store.create_page(
        page_id="pg2", space_id="sr", title="Two", body="v1", author="dave",
        created_at="2024-01-02T09:00:00Z",
    )
    store.update_page(
        page_id="pg2", title="Two", body="v2", author="dave",
        created_at="2024-01-03T12:00:00Z",
    )

    store.create_page_comment(
        comment_id="pc1", page_id="pg1", author="bob", body="in",
        created_at="2024-01-04T14:00:00Z",
    )
    store.create_page_comment(
        comment_id="pc2", page_id="pg2", author="dave", body="in restricted",
        created_at="2024-01-04T15:00:00Z",
    )


# ---------------------------------------------------------------- windowed core


def test_default_output_byte_identical(tmp_path: Path) -> None:
    """No flags -> exactly today's rollup, no ``window`` key, byte-identical."""
    store = _store(tmp_path)
    _seed_hand(store)
    url = f"sqlite:///{tmp_path / 'inner.db'}"

    result = _run_cli("metrics", "--database-url", url)
    assert result.returncode == 0, result.stderr
    assert "window" not in json.loads(result.stdout)
    expected = json.dumps(domain_rollup(store).to_dict(), indent=2, sort_keys=True) + "\n"
    assert result.stdout == expected


def test_windowed_state_counts_hand_computed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_hand(store)
    windowed = windowed_domain_rollup(store, window_start=W_START, window_end=W_END)
    assert isinstance(windowed, DomainWindowMetrics)
    # Transitions into each state inside [Jan3 00:00, Jan5 00:00):
    #   in_progress: wa t1 @ Jan3 09:00 -> 1
    #   done:        wa t2 @ Jan4 09:00 + wb t4 @ Jan4 20:00 -> 2
    #   todo:        0 (no transition into todo inside the window)
    assert windowed.state_counts == {"todo": 0, "in_progress": 1, "done": 2}


def test_windowed_cycle_time_hand_computed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    # Clean cycle-time fixture: 86400 s and 43200 s gaps, one idle project.
    store.create_project(
        project_id="cp", key="CYC", name="Cycle", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    store.create_project(
        project_id="ci", key="NIL", name="Nil", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    store.create_work_item(
        work_item_id="xa", project_id="cp", title="A", description="",
        assignee="eml", created_at="2024-01-01T00:00:00Z",
    )
    store.create_work_item(
        work_item_id="xb", project_id="cp", title="B", description="",
        assignee="eml", created_at="2024-01-01T12:00:00Z",
    )
    store.create_work_item(
        work_item_id="xc", project_id="ci", title="C", description="",
        assignee="eml", created_at="2024-01-01T00:00:00Z",
    )
    store.transition_work_item(
        work_item_id="xa", to_state="in_progress", actor="eml",
        occurred_at="2024-01-01T06:00:00Z",
    )
    # xa: created Jan1 00:00 -> done Jan2 00:00 = 86400 s (24 h)
    store.transition_work_item(
        work_item_id="xa", to_state="done", actor="eml",
        occurred_at="2024-01-02T00:00:00Z",
    )
    store.transition_work_item(
        work_item_id="xb", to_state="in_progress", actor="eml",
        occurred_at="2024-01-01T18:00:00Z",
    )
    # xb: created Jan1 12:00 -> done Jan2 00:00 = 43200 s (12 h)
    store.transition_work_item(
        work_item_id="xb", to_state="done", actor="eml",
        occurred_at="2024-01-02T00:00:00Z",
    )
    store.transition_work_item(
        work_item_id="xc", to_state="in_progress", actor="eml",
        occurred_at="2024-01-01T06:00:00Z",
    )  # no done transition -> idle project

    windowed = windowed_domain_rollup(
        store,
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-02-01T00:00:00Z",
    )
    rows = {p.key: p for p in windowed.cycle_time_per_project}
    assert list(windowed.cycle_time_per_project) == sorted(
        windowed.cycle_time_per_project, key=lambda p: p.key
    )
    # avg = (86400 + 43200) / 2 = 64800.0; min 43200.0; max 86400.0
    assert rows["CYC"].completed_count == 2
    assert rows["CYC"].cycle_time_avg_seconds == 64800.0
    assert rows["CYC"].cycle_time_min_seconds == 43200.0
    assert rows["CYC"].cycle_time_max_seconds == 86400.0
    # Idle project: explicit zeros and null stats, never elided.
    assert rows["NIL"].completed_count == 0
    assert rows["NIL"].cycle_time_avg_seconds is None
    assert rows["NIL"].cycle_time_min_seconds is None
    assert rows["NIL"].cycle_time_max_seconds is None


def test_windowed_page_writes_hand_computed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_hand(store)
    windowed = windowed_domain_rollup(store, window_start=W_START, window_end=W_END)
    page_writes = windowed.page_writes.to_dict()
    # Versions inside W: pg1 v2 (Jan3 10:00), pg1 v3 (Jan4 11:00), pg2 v2 (Jan3 12:00)
    #   total_versions = 3; pages_touched = {pg1, pg2} = 2
    #   by_space: DOCS = 2 (pg1 v2+v3), SRES = 1 (pg2 v2)
    assert page_writes == {
        "total_versions": 3,
        "pages_touched": 2,
        "by_space": {"DOCS": 2, "SRES": 1},
    }


def test_windowed_contributors_hand_computed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_hand(store)
    windowed = windowed_domain_rollup(store, window_start=W_START, window_end=W_END)
    # Events inside W, per actor:
    #   alice: wa t1 + wa t2 (2 transitions) + c1 (1 wi comment) + pg1 v2 (1 page version) = 4
    #   bob:   wb t4 (1 transition) + pc1 (1 page comment) + pg1 v3 (1 page version) = 3
    #   dave:  c3 (1 wi comment) + pc2 (1 page comment) + pg2 v2 (1 page version) = 3
    assert windowed.contributors.to_dict() == {
        "distinct": 3,
        "by_actor": {"alice": 4, "bob": 3, "dave": 3},
    }


# --------------------------------------------------------------- zero activity


def test_zero_activity_window(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_project(
        project_id="zp", key="ZER", name="Zero", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    store.create_work_item(
        work_item_id="zx", project_id="zp", title="X", description="",
        assignee="eml", created_at="2024-01-02T00:00:00Z",
    )
    store.create_space(
        space_id="zs", key="ZSP", name="ZSp", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    store.create_page(
        page_id="zx1", space_id="zs", title="P", body="v1", author="eml",
        created_at="2024-01-02T00:00:00Z",
    )
    # No events inside [Feb 1, Mar 1): explicit zeros/empty/null, no error.
    windowed = windowed_domain_rollup(
        store,
        window_start="2024-02-01T00:00:00Z",
        window_end="2024-03-01T00:00:00Z",
    )
    assert windowed.state_counts == {"todo": 0, "in_progress": 0, "done": 0}
    assert [p.key for p in windowed.cycle_time_per_project] == ["ZER"]
    assert windowed.cycle_time_per_project[0].completed_count == 0
    assert windowed.cycle_time_per_project[0].cycle_time_avg_seconds is None
    assert windowed.page_writes.to_dict() == {
        "total_versions": 0,
        "pages_touched": 0,
        "by_space": {"ZSP": 0},
    }
    assert windowed.contributors.to_dict() == {"distinct": 0, "by_actor": {}}

    url = f"sqlite:///{tmp_path / 'inner.db'}"
    result = _run_cli(
        "metrics", "--database-url", url,
        "--window-start", "2024-02-01T00:00:00Z",
        "--window-end", "2024-03-01T00:00:00Z",
    )
    assert result.returncode == 0, result.stderr


# ------------------------------------------------------------- boundary semantics


def test_boundary_start_inclusive_end_exclusive(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_project(
        project_id="bp", key="BND", name="Boundary", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    store.create_work_item(
        work_item_id="bx", project_id="bp", title="X", description="",
        assignee="eml", created_at="2024-01-01T00:00:00Z",
    )
    # Exactly at start -> counted (start inclusive).
    store.transition_work_item(
        work_item_id="bx", to_state="in_progress", actor="alice",
        occurred_at="2024-01-03T00:00:00Z",
    )
    # Exactly at end -> NOT counted (end exclusive).
    store.transition_work_item(
        work_item_id="bx", to_state="done", actor="alice",
        occurred_at="2024-01-05T00:00:00Z",
    )
    store.create_space(
        space_id="bs", key="BSP", name="BSp", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    # Page version exactly at start -> counted; exactly at end -> not counted.
    store.create_page(
        page_id="bx1", space_id="bs", title="P", body="v1", author="alice",
        created_at="2024-01-03T00:00:00Z",
    )
    store.update_page(
        page_id="bx1", title="P", body="v2", author="bob",
        created_at="2024-01-05T00:00:00Z",
    )

    windowed = windowed_domain_rollup(store, window_start=W_START, window_end=W_END)
    assert windowed.state_counts == {"todo": 0, "in_progress": 1, "done": 0}
    assert windowed.page_writes.to_dict() == {
        "total_versions": 1,
        "pages_touched": 1,
        "by_space": {"BSP": 1},
    }
    # bob's version sits exactly on `end` -> excluded, so only alice contributes.
    assert windowed.contributors.to_dict() == {"distinct": 1, "by_actor": {"alice": 2}}


def test_page_comment_out_of_window_excluded(tmp_path: Path) -> None:
    """Out-of-window page comments are excluded from contributors."""
    store = _store(tmp_path)
    store.create_space(
        space_id="cs", key="CSP", name="CSp", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    store.create_page(
        page_id="csp1", space_id="cs", title="P", body="v1", author="eml",
        created_at="2024-01-01T00:00:00Z",
    )
    # Inside the window -> counted.
    store.create_page_comment(
        comment_id="pci", page_id="csp1", author="alice", body="in",
        created_at="2024-01-03T12:00:00Z",
    )
    # After the window end -> excluded (half-open [start, end)).
    store.create_page_comment(
        comment_id="pco", page_id="csp1", author="bob", body="out",
        created_at="2024-01-06T12:00:00Z",
    )
    windowed = windowed_domain_rollup(store, window_start=W_START, window_end=W_END)
    assert windowed.contributors.to_dict() == {"distinct": 1, "by_actor": {"alice": 1}}


def test_partial_windows(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_hand(store)
    d = windowed_domain_rollup(store, window_start=W_START).to_dict()
    # start-only: [Jan3 00:00, +inf) — includes wc t5 @ Jan6 10:00.
    assert d["start"] == "2024-01-03T00:00:00Z"
    assert d["end"] is None
    assert d["state_counts"] == {"todo": 0, "in_progress": 2, "done": 2}

    d = windowed_domain_rollup(store, window_end=W_END).to_dict()
    # end-only: (-inf, Jan5 00:00) — includes wb t3 and wd t6 (both Jan2).
    assert d["start"] is None
    assert d["end"] == "2024-01-05T00:00:00Z"
    assert d["state_counts"] == {"todo": 0, "in_progress": 3, "done": 2}


def test_timezone_equivalence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_hand(store)
    # 2024-01-03T09:00:00+09:00 == 2024-01-03T00:00:00Z (both 00:00 UTC).
    via_offset = windowed_domain_rollup(
        store, window_start="2024-01-03T09:00:00+09:00", window_end=W_END
    ).to_dict()
    via_z = windowed_domain_rollup(store, window_start=W_START, window_end=W_END).to_dict()
    assert via_offset == via_z
    assert via_offset["start"] == "2024-01-03T00:00:00Z"


def test_naive_stored_timestamp_treated_as_utc(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_project(
        project_id="np", key="NAV", name="Naive", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    store.create_work_item(
        work_item_id="nx", project_id="np", title="X", description="",
        assignee="eml", created_at="2024-01-01T00:00:00Z",
    )
    # Naive stored occurred_at is interpreted as UTC: exactly equal to the
    # inclusive start -> inside the window.
    store.transition_work_item(
        work_item_id="nx", to_state="in_progress", actor="eml",
        occurred_at="2024-01-03T00:00:00",
    )
    windowed = windowed_domain_rollup(store, window_start=W_START, window_end=W_END)
    assert windowed.state_counts["in_progress"] == 1


# --------------------------------------------------------------- flag validation


def test_flag_validation_errors(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_hand(store)
    url = f"sqlite:///{tmp_path / 'inner.db'}"

    # end <= start -> exit 2, error on stderr, empty stdout, no traceback.
    r = _run_cli(
        "metrics", "--database-url", url,
        "--window-start", W_END,
        "--window-end", W_START,
    )
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr.startswith("error: ")
    assert "Traceback" not in r.stderr

    # Malformed / naive flag values -> exit 2 each.
    for bad in ("not-a-date", "2024-13-99T00:00:00Z", "2024-01-03T00:00:00"):
        r = _run_cli(
            "metrics", "--database-url", url,
            "--window-start", bad,
        )
        assert r.returncode == 2, bad
        assert r.stdout == "", bad
        assert r.stderr.startswith("error: "), bad
        assert "Traceback" not in r.stderr, bad


def test_flag_validation_in_process(tmp_path: Path) -> None:
    """Malformed / naive / inverted / zero-length windows raise AnalyticsError."""
    store = _store(tmp_path)
    _seed_hand(store)

    # Malformed values -> AnalyticsError (never a crash / partial result).
    for bad in ("not-a-date", "2024-13-99T00:00:00Z", ""):
        with pytest.raises(AnalyticsError):
            windowed_domain_rollup(store, window_start=bad, window_end=W_END)

    # Naive (offset-less) values are rejected, even with valid ISO shape.
    with pytest.raises(AnalyticsError):
        windowed_domain_rollup(store, window_start="2024-01-03T00:00:00", window_end=W_END)

    # Inverted window (end before start) -> AnalyticsError.
    with pytest.raises(AnalyticsError):
        windowed_domain_rollup(store, window_start=W_END, window_end=W_START)

    # Zero-length window (end == start) -> AnalyticsError; empty result never
    # leaks out with a plausible-looking but wrong window.
    with pytest.raises(AnalyticsError):
        windowed_domain_rollup(store, window_start=W_START, window_end=W_START)


def test_unparseable_stored_timestamp_loud(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_project(
        project_id="up", key="BAD", name="Bad", owner="eml",
        visibility="public", created_at="2024-01-01T00:00:00Z",
    )
    store.create_work_item(
        work_item_id="ux", project_id="up", title="X", description="",
        assignee="eml", created_at="garbage",
    )
    store.transition_work_item(
        work_item_id="ux", to_state="in_progress", actor="eml",
        occurred_at="2024-01-03T09:00:00Z",
    )
    store.transition_work_item(
        work_item_id="ux", to_state="done", actor="eml",
        occurred_at="2024-01-04T09:00:00Z",
    )
    # Windowed path hits the item's created_at for cycle time -> loud error.
    with pytest.raises(AnalyticsError) as excinfo:
        windowed_domain_rollup(store, window_start=W_START, window_end=W_END)
    message = str(excinfo.value)
    assert "work_items" in message and "garbage" in message

    # Default path never parses timestamps -> still works.
    assert domain_rollup(store).work_item_count == 1

    # CLI: exit 2, empty stdout.
    url = f"sqlite:///{tmp_path / 'inner.db'}"
    r = _run_cli(
        "metrics", "--database-url", url,
        "--window-start", W_START,
        "--window-end", W_END,
    )
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr.startswith("error: ")


# -------------------------------------------------------------- permission model


def test_permission_filtering(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_hand(store)

    anon = windowed_domain_rollup(
        store, window_start=W_START, window_end=W_END, principal=AnonymousPrincipal
    )
    # Anonymous sees only PUBLIC project/space: restricted events (wd, pg2)
    # contribute nothing anywhere.
    assert anon.state_counts == {"todo": 0, "in_progress": 1, "done": 2}
    assert [p.key for p in anon.cycle_time_per_project] == ["PUB"]
    assert anon.page_writes.to_dict() == {
        "total_versions": 2,
        "pages_touched": 1,
        "by_space": {"DOCS": 2},
    }
    assert anon.contributors.to_dict() == {"distinct": 2, "by_actor": {"alice": 4, "bob": 3}}

    # alice is a member of RES and SRES -> full view, restricted rows present.
    member = windowed_domain_rollup(
        store, window_start=W_START, window_end=W_END, principal=Principal(id="alice")
    )
    assert [p.key for p in member.cycle_time_per_project] == ["INT", "PUB", "RES"]
    assert member.page_writes.to_dict()["by_space"] == {"DOCS": 2, "SRES": 1}
    assert member.contributors.to_dict()["distinct"] == 3


# ------------------------------------------------------------------ synthetic


def test_synthetic_fixture_full_window(tmp_path: Path) -> None:
    store = _store(tmp_path)
    import_domain(store, build_synthetic_fixture())
    d = windowed_domain_rollup(
        store,
        window_start="2024-01-01T00:00:00+00:00",
        window_end="2024-02-01T00:00:00+00:00",
    ).to_dict()

    # Countable from tests/fixtures/synthetic_migration.json transitions:
    #   wi-001 todo->in_progress, wi-001 in_progress->done, wi-002 todo->in_progress
    #   -> in_progress = 2, done = 1, todo = 0
    assert d["state_counts"] == {"todo": 0, "in_progress": 2, "done": 1}

    # Cycle time: wi-001 created Jan3 09:00 -> done Jan4 17:30 =
    #   86400 (1 day) + 8.5*3600 (8.5 h) = 117000.0 s
    rows = {p["key"]: p for p in d["cycle_time_per_project"]}
    assert rows["PHX"]["completed_count"] == 1
    assert rows["PHX"]["cycle_time_avg_seconds"] == 117000.0
    assert rows["PHX"]["cycle_time_min_seconds"] == 117000.0
    assert rows["PHX"]["cycle_time_max_seconds"] == 117000.0
    assert rows["ORC"]["completed_count"] == 0
    assert rows["ORC"]["cycle_time_avg_seconds"] is None

    # page_versions: v1 Jan3 11:00, v2 Jan4 14:00 -> both inside the window.
    assert d["page_writes"] == {
        "total_versions": 2,
        "pages_touched": 1,
        "by_space": {"DOCS": 2},
    }

    # Contributors: alice 3 transitions + 2 page versions + 1 wi comment = 6;
    # bob 1 page comment + 1 wi comment = 2.
    assert d["contributors"] == {
        "distinct": 2,
        "by_actor": {"alice@example.test": 6, "bob@example.test": 2},
    }


# ----------------------------------------------------------------------- misc


def test_cli_help_documents_flags() -> None:
    r = _run_cli("metrics", "--help")
    assert r.returncode == 0, r.stderr
    assert "--window-start" in r.stdout
    assert "--window-end" in r.stdout


def test_deterministic_two_runs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_hand(store)
    first = json.dumps(
        windowed_domain_rollup(store, window_start=W_START, window_end=W_END).to_dict(),
        sort_keys=True,
    )
    second = json.dumps(
        windowed_domain_rollup(store, window_start=W_START, window_end=W_END).to_dict(),
        sort_keys=True,
    )
    assert first == second


def test_no_new_dependencies() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "innerwork"
        / "analytics.py"
    ).read_text(encoding="utf-8")
    for module in ("dateutil", "pandas", "numpy", "pendulum", "arrow"):
        assert f"import {module}" not in source
