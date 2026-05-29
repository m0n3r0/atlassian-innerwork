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
    "project_rollup",
    "space_rollup",
    "domain_rollup",
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
