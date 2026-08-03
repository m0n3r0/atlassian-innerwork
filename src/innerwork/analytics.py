"""Phase 6 deterministic analytics.

Aggregate, read-only views over :class:`DomainStore`. Every function returns
plain Python (dicts / dataclasses) so callers can serialize them straight to
JSON. Results are stable across runs given identical input (no clocks, no
random IDs).

Permission filtering: when a :class:`Principal` is passed, projects and spaces
the principal cannot read are excluded from the rollup before counting. When
``principal`` is ``None`` the analytics run over the full domain (back-compat
with internal/CLI callers).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .domain import WORKFLOW_STATES
from .permissions import Principal, can_read

if TYPE_CHECKING:  # pragma: no cover — typing only
    from .domain_store import DomainStore


__all__ = (
    "AnalyticsError",
    "ProjectRollup",
    "SpaceRollup",
    "DomainRollup",
    "ProjectCycleTime",
    "PageWritesRollup",
    "ContributorsRollup",
    "DomainWindowMetrics",
    "project_rollup",
    "space_rollup",
    "domain_rollup",
    "windowed_domain_rollup",
)


class AnalyticsError(ValueError):
    """Raised on invalid analytics requests (unknown project, etc.)."""


@dataclass(frozen=True)
class ProjectRollup:
    """Per-project work-item and comment counters."""

    project_id: str
    key: str
    name: str
    visibility: str
    work_item_count: int
    work_items_by_state: dict[str, int]
    comment_count: int
    transition_count: int

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "key": self.key,
            "name": self.name,
            "visibility": self.visibility,
            "work_item_count": self.work_item_count,
            "work_items_by_state": dict(self.work_items_by_state),
            "comment_count": self.comment_count,
            "transition_count": self.transition_count,
        }


@dataclass(frozen=True)
class SpaceRollup:
    """Per-space page and comment counters."""

    space_id: str
    key: str
    name: str
    visibility: str
    page_count: int
    page_version_count: int
    comment_count: int

    def to_dict(self) -> dict:
        return {
            "space_id": self.space_id,
            "key": self.key,
            "name": self.name,
            "visibility": self.visibility,
            "page_count": self.page_count,
            "page_version_count": self.page_version_count,
            "comment_count": self.comment_count,
        }


@dataclass(frozen=True)
class DomainRollup:
    """Whole-domain rollup, grouping per-project + per-space rollups."""

    project_count: int
    space_count: int
    work_item_count: int
    page_count: int
    work_items_by_state: dict[str, int]
    projects: tuple[ProjectRollup, ...] = field(default_factory=tuple)
    spaces: tuple[SpaceRollup, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "project_count": self.project_count,
            "space_count": self.space_count,
            "work_item_count": self.work_item_count,
            "page_count": self.page_count,
            "work_items_by_state": dict(self.work_items_by_state),
            "projects": [p.to_dict() for p in self.projects],
            "spaces": [s.to_dict() for s in self.spaces],
        }


# --------------------------------------------------------------------- helpers


def _project_readable(principal: Principal | None, proj) -> bool:
    if principal is None:
        return True
    return can_read(principal, visibility=proj.visibility, members=proj.members)


def _space_readable(principal: Principal | None, sp) -> bool:
    if principal is None:
        return True
    return can_read(principal, visibility=sp.visibility, members=sp.members)


def _empty_state_counter() -> dict[str, int]:
    return {state: 0 for state in WORKFLOW_STATES}


# ---------------------------------------------------------------- public ops


def project_rollup(
    store: DomainStore,
    project_id: str,
    *,
    principal: Principal | None = None,
) -> ProjectRollup:
    """Compute counters for a single project. Raises AnalyticsError if denied."""

    try:
        proj = store.get_project(project_id)
    except Exception as exc:
        raise AnalyticsError(f"project not found: {project_id!r}") from exc
    if not _project_readable(principal, proj):
        raise AnalyticsError(f"project not readable: {project_id!r}")

    by_state: dict[str, int] = _empty_state_counter()
    work_items = store.list_work_items(project_id=project_id)
    for item in work_items:
        by_state[item.state] = by_state.get(item.state, 0) + 1

    comment_count = 0
    transition_count = 0
    for item in work_items:
        comment_count += len(store.list_work_item_comments(item.work_item_id))
        transition_count += len(store.list_transitions(item.work_item_id))

    return ProjectRollup(
        project_id=proj.project_id,
        key=proj.key,
        name=proj.name,
        visibility=proj.visibility,
        work_item_count=len(work_items),
        work_items_by_state=by_state,
        comment_count=comment_count,
        transition_count=transition_count,
    )


def space_rollup(
    store: DomainStore,
    space_id: str,
    *,
    principal: Principal | None = None,
) -> SpaceRollup:
    """Compute counters for a single space. Raises AnalyticsError if denied."""

    try:
        sp = store.get_space(space_id)
    except Exception as exc:
        raise AnalyticsError(f"space not found: {space_id!r}") from exc
    if not _space_readable(principal, sp):
        raise AnalyticsError(f"space not readable: {space_id!r}")

    pages = store.list_pages(space_id=space_id)
    page_version_count = 0
    comment_count = 0
    for pg in pages:
        page_version_count += len(store.list_page_versions(pg.page_id))
        comment_count += len(store.list_page_comments(pg.page_id))

    return SpaceRollup(
        space_id=sp.space_id,
        key=sp.key,
        name=sp.name,
        visibility=sp.visibility,
        page_count=len(pages),
        page_version_count=page_version_count,
        comment_count=comment_count,
    )


def domain_rollup(
    store: DomainStore,
    *,
    principal: Principal | None = None,
) -> DomainRollup:
    """Whole-domain rollup, gated by ``principal`` if supplied.

    Projects/spaces the principal cannot read are silently elided. Counters
    reflect ONLY readable projects/spaces — this is by design so the rollup
    matches what the same principal would see via search and ai_context.
    """

    projects: list[ProjectRollup] = []
    domain_state_total: Counter[str] = Counter()
    total_work_items = 0
    for proj in store.list_projects():
        if not _project_readable(principal, proj):
            continue
        rollup = project_rollup(store, proj.project_id, principal=principal)
        projects.append(rollup)
        total_work_items += rollup.work_item_count
        domain_state_total.update(rollup.work_items_by_state)

    spaces: list[SpaceRollup] = []
    total_pages = 0
    for sp in store.list_spaces():
        if not _space_readable(principal, sp):
            continue
        rollup = space_rollup(store, sp.space_id, principal=principal)
        spaces.append(rollup)
        total_pages += rollup.page_count

    # Stable ordering: by key (project key / space key) so JSON snapshots are
    # diff-friendly.
    projects.sort(key=lambda r: r.key)
    spaces.sort(key=lambda r: r.key)

    by_state = _empty_state_counter()
    for state, count in domain_state_total.items():
        by_state[state] = count

    return DomainRollup(
        project_count=len(projects),
        space_count=len(spaces),
        work_item_count=total_work_items,
        page_count=total_pages,
        work_items_by_state=by_state,
        projects=tuple(projects),
        spaces=tuple(spaces),
    )


# ------------------------------------------------------------------ windowed mode
#
# Optional time-windowed aggregations behind ``innerwork metrics
# --window-start/--window-end``. Fully additive: ``domain_rollup`` /
# ``project_rollup`` / ``space_rollup`` and their dataclasses are untouched,
# and the default CLI path (no flags) never reaches this code.
#
# Window semantics (locked by docs/roadmap_time_windowed_metrics_scoping.md):
# half-open [start, end) compared in UTC after normalization; every stored
# timestamp the windowed path reads is parsed, and an unparseable one raises
# AnalyticsError (loud — silently skipping a row would undercount). All SQL is
# parameterized; user-supplied bounds are parsed to datetime objects and never
# interpolated into query text. SQL-side timestamp filtering is deliberately
# avoided: stored values may carry arbitrary ISO-8601 offsets, so lexicographic
# string comparison against a UTC bound is unsound. Rows are filtered in Python
# after exact UTC normalization instead.


@dataclass(frozen=True)
class ProjectCycleTime:
    """Per-project done-cycle-time statistics over the window."""

    project_id: str
    key: str
    completed_count: int
    cycle_time_avg_seconds: float | None
    cycle_time_min_seconds: float | None
    cycle_time_max_seconds: float | None

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "key": self.key,
            "completed_count": self.completed_count,
            "cycle_time_avg_seconds": self.cycle_time_avg_seconds,
            "cycle_time_min_seconds": self.cycle_time_min_seconds,
            "cycle_time_max_seconds": self.cycle_time_max_seconds,
        }


@dataclass(frozen=True)
class PageWritesRollup:
    """Page-write activity over the window (from ``page_versions``)."""

    total_versions: int
    pages_touched: int
    by_space: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "total_versions": self.total_versions,
            "pages_touched": self.pages_touched,
            "by_space": dict(self.by_space),
        }


@dataclass(frozen=True)
class ContributorsRollup:
    """Distinct windowed-activity contributors, with per-actor event counts."""

    distinct: int
    by_actor: dict[str, int]

    def to_dict(self) -> dict:
        return {"distinct": self.distinct, "by_actor": dict(self.by_actor)}


@dataclass(frozen=True)
class DomainWindowMetrics:
    """The top-level ``window`` object appended to a windowed metrics run."""

    start: str | None
    end: str | None
    state_counts: dict[str, int]
    cycle_time_per_project: tuple[ProjectCycleTime, ...]
    page_writes: PageWritesRollup
    contributors: ContributorsRollup

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "state_counts": dict(self.state_counts),
            "cycle_time_per_project": [p.to_dict() for p in self.cycle_time_per_project],
            "page_writes": self.page_writes.to_dict(),
            "contributors": self.contributors.to_dict(),
        }


def _parse_window_bound(value: str, flag: str) -> datetime:
    """Parse an ISO-8601 CLI bound; naive values (no offset) are rejected."""
    text = value.strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AnalyticsError(
            f"invalid {flag}: {value!r} (expected ISO-8601 with a UTC offset, "
            "e.g. 2024-01-03T00:00:00Z)"
        ) from exc
    if parsed.tzinfo is None:
        raise AnalyticsError(
            f"invalid {flag}: {value!r} has no UTC offset (naive timestamps "
            "are rejected; use Z or ±HH:MM)"
        )
    return parsed.astimezone(timezone.utc)


def _parse_stored_timestamp(table: str, column: str, value: str) -> datetime:
    """Parse a stored timestamp; naive stored values are treated as UTC."""
    text = value.strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AnalyticsError(f"unparseable {column} in {table}: {value!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _echo_bound(bound: datetime | None) -> str | None:
    """Normalize a parsed bound to its UTC ``Z``-suffixed echo form."""
    if bound is None:
        return None
    return bound.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _in_window(ts: datetime, start: datetime | None, end: datetime | None) -> bool:
    """Half-open membership test: ``start <= ts < end`` in UTC."""
    if start is not None and ts < start:
        return False
    if end is not None and ts >= end:
        return False
    return True


def windowed_domain_rollup(
    store: DomainStore,
    *,
    window_start: str | None = None,
    window_end: str | None = None,
    principal: Principal | None = None,
) -> DomainWindowMetrics:
    """Compute the four windowed activity aggregations over ``[start, end)``.

    Activity-over-window deltas restricted to projects/spaces ``principal``
    can read (same ``can_read`` gate as :func:`domain_rollup`). An omitted
    bound is unbounded on that side. Window bounds must carry an explicit UTC
    offset; stored naive timestamps are treated as UTC. Unparseable stored
    timestamps raise :class:`AnalyticsError` naming the table and value.
    """

    start = (
        _parse_window_bound(window_start, "--window-start")
        if window_start is not None
        else None
    )
    end = (
        _parse_window_bound(window_end, "--window-end") if window_end is not None else None
    )
    if start is not None and end is not None and end <= start:
        raise AnalyticsError(
            "invalid window: --window-end must be after --window-start "
            f"(got start={_echo_bound(start)!r}, end={_echo_bound(end)!r})"
        )

    projects = [p for p in store.list_projects() if _project_readable(principal, p)]
    spaces = [s for s in store.list_spaces() if _space_readable(principal, s)]
    readable_project_ids = {p.project_id for p in projects}
    readable_space_ids = {s.space_id for s in spaces}

    state_counts = _empty_state_counter()
    cycle_times: dict[str, list[float]] = {}
    actor_events: Counter[str] = Counter()
    version_total = 0
    pages_touched: set[str] = set()
    versions_by_space: Counter[str] = Counter()

    with store._connect() as connection:
        # Transitions into each state (+ done-cycle times), scoped by project.
        rows = connection.execute(
            """
            SELECT t.work_item_id, t.to_state, t.actor, t.occurred_at,
                   w.project_id, w.created_at
            FROM work_item_transitions t
            JOIN work_items w ON w.work_item_id = t.work_item_id
            """
        ).fetchall()
        for row in rows:
            if row[4] not in readable_project_ids:
                continue
            occurred = _parse_stored_timestamp(
                "work_item_transitions", "occurred_at", row[3]
            )
            if not _in_window(occurred, start, end):
                continue
            state_counts[row[1]] = state_counts.get(row[1], 0) + 1
            actor_events[row[2]] += 1
            if row[1] == "done":
                created = _parse_stored_timestamp("work_items", "created_at", row[5])
                cycle_times.setdefault(row[4], []).append(
                    (occurred - created).total_seconds()
                )

        # Page versions -> page-write activity, scoped by space.
        rows = connection.execute(
            """
            SELECT v.page_id, v.author, v.created_at, p.space_id
            FROM page_versions v
            JOIN pages p ON p.page_id = v.page_id
            """
        ).fetchall()
        for row in rows:
            if row[3] not in readable_space_ids:
                continue
            created = _parse_stored_timestamp("page_versions", "created_at", row[2])
            if not _in_window(created, start, end):
                continue
            version_total += 1
            pages_touched.add(row[0])
            versions_by_space[row[3]] += 1
            actor_events[row[1]] += 1

        # Work-item comments (contributor events), scoped by project.
        rows = connection.execute(
            """
            SELECT c.author, c.created_at, w.project_id
            FROM work_item_comments c
            JOIN work_items w ON w.work_item_id = c.work_item_id
            """
        ).fetchall()
        for row in rows:
            if row[2] not in readable_project_ids:
                continue
            created = _parse_stored_timestamp("work_item_comments", "created_at", row[1])
            if not _in_window(created, start, end):
                continue
            actor_events[row[0]] += 1

        # Page comments (contributor events), scoped by space.
        rows = connection.execute(
            """
            SELECT c.author, c.created_at, p.space_id
            FROM page_comments c
            JOIN pages p ON p.page_id = c.page_id
            """
        ).fetchall()
        for row in rows:
            if row[2] not in readable_space_ids:
                continue
            created = _parse_stored_timestamp("page_comments", "created_at", row[1])
            if not _in_window(created, start, end):
                continue
            actor_events[row[0]] += 1

    # Every readable project is present (zeros/null when idle), sorted by key
    # like the point-in-time rollup's ``projects`` list.
    cycle_rows: list[ProjectCycleTime] = []
    for proj in sorted(projects, key=lambda p: p.key):
        times = cycle_times.get(proj.project_id, [])
        completed = len(times)
        if completed:
            avg: float | None = sum(times) / completed
            lo: float | None = min(times)
            hi: float | None = max(times)
        else:
            avg = lo = hi = None
        cycle_rows.append(
            ProjectCycleTime(
                project_id=proj.project_id,
                key=proj.key,
                completed_count=completed,
                cycle_time_avg_seconds=avg,
                cycle_time_min_seconds=lo,
                cycle_time_max_seconds=hi,
            )
        )

    by_space = {
        sp.key: versions_by_space.get(sp.space_id, 0)
        for sp in sorted(spaces, key=lambda s: s.key)
    }
    by_actor = {actor: actor_events[actor] for actor in sorted(actor_events)}

    return DomainWindowMetrics(
        start=_echo_bound(start),
        end=_echo_bound(end),
        state_counts=state_counts,
        cycle_time_per_project=tuple(cycle_rows),
        page_writes=PageWritesRollup(
            total_versions=version_total,
            pages_touched=len(pages_touched),
            by_space=by_space,
        ),
        contributors=ContributorsRollup(distinct=len(by_actor), by_actor=by_actor),
    )
