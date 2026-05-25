"""Innerwork domain model: projects, work items, and workflow transitions.

This is the first slice of the Phase B work-and-knowledge MVP defined in
``docs/production-grade-roadmap.md``. It is intentionally small and
clean-room:

* A Project owns a short uppercase key (e.g. ``ENG``) and a human name.
* A WorkItem belongs to a Project, has a project-scoped numeric suffix
  (e.g. ``ENG-1``), and moves through a fixed default workflow.
* The default workflow is ``todo -> in_progress -> done`` with explicit
  reopen edges. Invalid transitions raise ``InvalidTransitionError``.

There is no UI, no permissions, no comments, no assignees-as-users, and
no links to pages yet. Those land in follow-up slices (Phase B/D/F of
the roadmap). This module deliberately exposes pure dataclasses so the
SQL store, the REST layer, and the CLI can serialise them deterministically.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Workflow definition
# ---------------------------------------------------------------------------

#: Canonical workflow state names. Lowercase, snake_case, stable identifiers.
WORKFLOW_STATES: tuple[str, ...] = ("todo", "in_progress", "done")

#: Initial state assigned to a freshly created work item.
INITIAL_STATE: str = "todo"

#: Allowed transitions as ``(from_state, to_state)`` pairs. Reopen edges are
#: explicit so the rule set stays auditable.
ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("todo", "in_progress"),
        ("in_progress", "done"),
        ("in_progress", "todo"),
        ("done", "in_progress"),
    }
)


class InvalidTransitionError(ValueError):
    """Raised when a workflow transition is not permitted."""


def is_terminal_state(state: str) -> bool:
    """Return True for states that admit no outgoing transitions by default.

    ``done`` is terminal in the sense that no automatic downstream transition
    exists, but it is still reachable via the explicit reopen edge to
    ``in_progress``.
    """

    return state == "done"


def assert_transition_allowed(from_state: str, to_state: str) -> None:
    if from_state not in WORKFLOW_STATES:
        raise InvalidTransitionError(f"unknown from_state: {from_state!r}")
    if to_state not in WORKFLOW_STATES:
        raise InvalidTransitionError(f"unknown to_state: {to_state!r}")
    if from_state == to_state:
        raise InvalidTransitionError(f"transition is a no-op: {from_state!r} -> {to_state!r}")
    if (from_state, to_state) not in ALLOWED_TRANSITIONS:
        raise InvalidTransitionError(
            f"transition not allowed by default workflow: {from_state!r} -> {to_state!r}"
        )


# ---------------------------------------------------------------------------
# Identifier validation
# ---------------------------------------------------------------------------

_PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
_NON_EMPTY_TEXT_MAX = 200
_DESCRIPTION_MAX = 4000


def validate_project_key(key: str) -> str:
    if not isinstance(key, str):
        raise ValueError("project key must be a string")
    if not _PROJECT_KEY_RE.match(key):
        raise ValueError(
            f"project key must be 2-10 chars, uppercase A-Z then [A-Z0-9], got {key!r}"
        )
    return key


def _validate_non_empty(
    text: str, *, field_name: str, max_length: int = _NON_EMPTY_TEXT_MAX
) -> str:
    if not isinstance(text, str):
        raise ValueError(f"{field_name} must be a string")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    if len(cleaned) > max_length:
        raise ValueError(f"{field_name} must be <= {max_length} characters")
    return cleaned


def _validate_optional_text(text: str | None, *, field_name: str, max_length: int) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        raise ValueError(f"{field_name} must be a string or null")
    if len(text) > max_length:
        raise ValueError(f"{field_name} must be <= {max_length} characters")
    return text


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Project:
    """A clean-room work-graph project. Owns a unique uppercase ``key``."""

    project_id: str
    key: str
    name: str
    owner: str
    created_at: str

    def __post_init__(self) -> None:
        validate_project_key(self.key)
        _validate_non_empty(self.name, field_name="name")
        _validate_non_empty(self.owner, field_name="owner")
        _validate_non_empty(self.project_id, field_name="project_id")
        _validate_non_empty(self.created_at, field_name="created_at")

    def to_dict(self) -> dict[str, str]:
        return {
            "project_id": self.project_id,
            "key": self.key,
            "name": self.name,
            "owner": self.owner,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class WorkItem:
    """A work-graph item belonging to a project, with a workflow state."""

    work_item_id: str
    project_id: str
    key: str  # e.g. "ENG-1"
    title: str
    description: str
    state: str
    assignee: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.work_item_id, field_name="work_item_id")
        _validate_non_empty(self.project_id, field_name="project_id")
        _validate_non_empty(self.key, field_name="key", max_length=32)
        _validate_non_empty(self.title, field_name="title")
        _validate_optional_text(
            self.description, field_name="description", max_length=_DESCRIPTION_MAX
        )
        if self.state not in WORKFLOW_STATES:
            raise ValueError(f"state must be one of {WORKFLOW_STATES}, got {self.state!r}")
        # Assignee is optional, stored as empty string when unset so the field
        # is non-null in the SQL schema. When present it must be non-blank.
        if self.assignee and not self.assignee.strip():
            raise ValueError("assignee must be a non-blank string when present")
        _validate_non_empty(self.created_at, field_name="created_at")
        _validate_non_empty(self.updated_at, field_name="updated_at")

    def with_state(self, *, new_state: str, updated_at: str) -> WorkItem:
        return WorkItem(
            work_item_id=self.work_item_id,
            project_id=self.project_id,
            key=self.key,
            title=self.title,
            description=self.description,
            state=new_state,
            assignee=self.assignee,
            created_at=self.created_at,
            updated_at=updated_at,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "state": self.state,
            "assignee": self.assignee,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class Transition:
    """Append-only record of a workflow state change.

    ``transition_id`` is assigned by the store. ``actor`` is a free-text
    identifier (placeholder until identity lands in Phase D).
    """

    transition_id: int
    work_item_id: str
    from_state: str
    to_state: str
    actor: str
    occurred_at: str
    reason: str = ""

    def to_dict(self) -> dict[str, str | int]:
        return {
            "transition_id": self.transition_id,
            "work_item_id": self.work_item_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "actor": self.actor,
            "occurred_at": self.occurred_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WorkflowDefinition:
    """Snapshot of the workflow for introspection by the API/CLI."""

    states: tuple[str, ...] = WORKFLOW_STATES
    initial_state: str = INITIAL_STATE
    transitions: tuple[tuple[str, str], ...] = field(
        default_factory=lambda: tuple(sorted(ALLOWED_TRANSITIONS))
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "states": list(self.states),
            "initial_state": self.initial_state,
            "transitions": [{"from_state": f, "to_state": t} for f, t in self.transitions],
        }


def default_workflow() -> WorkflowDefinition:
    return WorkflowDefinition()


def allowed_next_states(state: str) -> tuple[str, ...]:
    """Return the states reachable from ``state`` in one transition."""

    return tuple(sorted(t for f, t in ALLOWED_TRANSITIONS if f == state))


__all__: Iterable[str] = (
    "ALLOWED_TRANSITIONS",
    "INITIAL_STATE",
    "InvalidTransitionError",
    "Project",
    "Transition",
    "WORKFLOW_STATES",
    "WorkItem",
    "WorkflowDefinition",
    "allowed_next_states",
    "assert_transition_allowed",
    "default_workflow",
    "is_terminal_state",
    "validate_project_key",
)
