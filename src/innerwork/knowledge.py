"""Innerwork knowledge-graph domain: spaces, pages, page versions, and links.

This is the second slice of the Phase B work-and-knowledge MVP. It adds:

* ``Space``: a knowledge container with a short uppercase ``key`` (e.g. ``DOCS``).
* ``Page``: a document inside a space. Pages are mutable headers, but every
  edit appends a new immutable ``PageVersion``.
* ``PageVersion``: immutable snapshot of (title, body, author) at a point in
  time, identified by a monotonically increasing per-page ``version_number``.
* ``Link``: a cross-graph edge between a ``WorkItem`` and a ``Page``, with a
  validated ``kind``.

Like the work-graph slice, this module exposes pure dataclasses. Persistence
lives in ``DomainStore``; the REST layer lives in ``domain_api``.

Permissions, comments, page hierarchy, and rich content blocks are explicit
non-goals for this slice; they land in later Phase B/D slices.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Identifier and content validation
# ---------------------------------------------------------------------------

_SPACE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
_NON_EMPTY_TEXT_MAX = 200
_PAGE_BODY_MAX = 200_000
_LINK_KIND_MAX = 40

#: Allowed link kinds. Small closed vocabulary keeps the cross-graph surface
#: auditable; richer ontology lands in later slices.
LINK_KINDS: frozenset[str] = frozenset(
    {
        "documents",  # work item is documented by page
        "references",  # work item references page
        "implements",  # work item implements page (e.g. RFC/design doc)
        "blocks",  # work item blocks page (e.g. doc waiting on impl)
    }
)


def validate_space_key(key: str) -> str:
    if not isinstance(key, str):
        raise ValueError("space key must be a string")
    if not _SPACE_KEY_RE.match(key):
        raise ValueError(f"space key must be 2-10 chars, uppercase A-Z then [A-Z0-9], got {key!r}")
    return key


def validate_link_kind(kind: str) -> str:
    if not isinstance(kind, str):
        raise ValueError("link kind must be a string")
    cleaned = kind.strip().lower()
    if cleaned not in LINK_KINDS:
        raise ValueError(f"link kind must be one of {sorted(LINK_KINDS)}, got {kind!r}")
    return cleaned


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


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Space:
    """A knowledge-graph space. Owns a unique uppercase ``key``."""

    space_id: str
    key: str
    name: str
    owner: str
    created_at: str

    def __post_init__(self) -> None:
        validate_space_key(self.key)
        _validate_non_empty(self.space_id, field_name="space_id")
        _validate_non_empty(self.name, field_name="name")
        _validate_non_empty(self.owner, field_name="owner")
        _validate_non_empty(self.created_at, field_name="created_at")

    def to_dict(self) -> dict[str, str]:
        return {
            "space_id": self.space_id,
            "key": self.key,
            "name": self.name,
            "owner": self.owner,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class Page:
    """A knowledge-graph page. Header pointer to the current immutable version."""

    page_id: str
    space_id: str
    current_version: int
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.page_id, field_name="page_id")
        _validate_non_empty(self.space_id, field_name="space_id")
        if not isinstance(self.current_version, int) or self.current_version < 1:
            raise ValueError("current_version must be a positive integer")
        _validate_non_empty(self.created_at, field_name="created_at")
        _validate_non_empty(self.updated_at, field_name="updated_at")

    def to_dict(self) -> dict[str, str | int]:
        return {
            "page_id": self.page_id,
            "space_id": self.space_id,
            "current_version": self.current_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class PageVersion:
    """Immutable snapshot of a page at a particular ``version_number``."""

    version_id: int
    page_id: str
    version_number: int
    title: str
    body: str
    author: str
    created_at: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.page_id, field_name="page_id")
        if not isinstance(self.version_number, int) or self.version_number < 1:
            raise ValueError("version_number must be a positive integer")
        _validate_non_empty(self.title, field_name="title")
        if not isinstance(self.body, str):
            raise ValueError("body must be a string")
        if len(self.body) > _PAGE_BODY_MAX:
            raise ValueError(f"body must be <= {_PAGE_BODY_MAX} characters")
        _validate_non_empty(self.author, field_name="author")
        _validate_non_empty(self.created_at, field_name="created_at")

    def to_dict(self) -> dict[str, str | int]:
        return {
            "version_id": self.version_id,
            "page_id": self.page_id,
            "version_number": self.version_number,
            "title": self.title,
            "body": self.body,
            "author": self.author,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class Link:
    """A cross-graph edge between a work item and a page."""

    link_id: str
    work_item_id: str
    page_id: str
    kind: str
    created_by: str
    created_at: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.link_id, field_name="link_id")
        _validate_non_empty(self.work_item_id, field_name="work_item_id")
        _validate_non_empty(self.page_id, field_name="page_id")
        validate_link_kind(self.kind)
        _validate_non_empty(self.created_by, field_name="created_by")
        _validate_non_empty(self.created_at, field_name="created_at")
        if len(self.kind) > _LINK_KIND_MAX:
            raise ValueError(f"link kind must be <= {_LINK_KIND_MAX} characters")

    def to_dict(self) -> dict[str, str]:
        return {
            "link_id": self.link_id,
            "work_item_id": self.work_item_id,
            "page_id": self.page_id,
            "kind": self.kind,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }


__all__: Iterable[str] = (
    "LINK_KINDS",
    "Link",
    "Page",
    "PageVersion",
    "Space",
    "validate_link_kind",
    "validate_space_key",
)
