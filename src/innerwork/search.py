"""Cross-graph search over work items, pages, and comments.

Phase 6 slice 1. Pure-Python tokenized index queried on demand against
the existing :class:`~innerwork.domain_store.DomainStore`. No FTS5 or
embedding model dependency, so behaviour is fully deterministic and
portable across every SQLite build we ship.

Scoring is intentionally simple — a stable, explainable baseline that
the API can document and tests can pin. It can be swapped for an FTS5
or vector backend later without changing the public ``search_domain``
contract.

Permissions and redaction live in Phase D; this slice returns every
matching entity. The ``provenance`` shape returned alongside each hit
is the seam future permission/redaction layers will wrap.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .permissions import Principal, can_read

if TYPE_CHECKING:  # pragma: no cover — typing only
    from .domain_store import DomainStore

SEARCHABLE_KINDS: tuple[str, ...] = ("work_item", "page", "comment")
"""Allowlist of entity kinds the search surface understands."""

_QUERY_MAX_LEN = 200
_TOKEN_MIN_LEN = 2
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100
_SNIPPET_RADIUS = 60

# Title hits weight more than body hits so that searching for a project
# name surfaces the project's items above incidental mentions in long
# comment threads. Comment hits use the body weight.
_TITLE_WEIGHT = 3
_BODY_WEIGHT = 1


class SearchQueryError(ValueError):
    """Raised when the search query or filters are invalid."""


@dataclass(frozen=True)
class Hit:
    """A single search hit.

    ``entity_id`` is the canonical id for ``kind`` (``work_item_id``,
    ``page_id``, or ``comment_id``). ``parent_id`` and ``parent_kind``
    point at the owning work item or page for ``comment`` hits, and are
    ``None`` for top-level hits.
    """

    kind: str
    entity_id: str
    title: str
    snippet: str
    score: int
    matched_tokens: tuple[str, ...]
    project_id: str | None = None
    space_id: str | None = None
    parent_kind: str | None = None
    parent_id: str | None = None
    created_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "entity_id": self.entity_id,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
            "matched_tokens": list(self.matched_tokens),
            "project_id": self.project_id,
            "space_id": self.space_id,
            "parent_kind": self.parent_kind,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class SearchResult:
    """Envelope returned by :func:`search_domain`."""

    query: str
    tokens: tuple[str, ...]
    kinds: tuple[str, ...]
    hits: tuple[Hit, ...]
    total: int
    limit: int
    project_id: str | None = None
    space_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "tokens": list(self.tokens),
            "kinds": list(self.kinds),
            "project_id": self.project_id,
            "space_id": self.space_id,
            "total": self.total,
            "limit": self.limit,
            "hits": [h.to_dict() for h in self.hits],
        }


# --------------------------------------------------------------------- API

def tokenize(text: str) -> tuple[str, ...]:
    """Lowercase + alnum tokenize. Drops tokens shorter than ``_TOKEN_MIN_LEN``.

    Exposed for tests and for the AI-context module to reuse a single
    tokenization rule across the codebase.
    """

    return tuple(t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= _TOKEN_MIN_LEN)


def _validate_kinds(kinds: Iterable[str] | None) -> tuple[str, ...]:
    if kinds is None:
        return SEARCHABLE_KINDS
    cleaned: list[str] = []
    seen: set[str] = set()
    for k in kinds:
        if k not in SEARCHABLE_KINDS:
            raise SearchQueryError(
                f"unknown kind {k!r}; allowed: {sorted(SEARCHABLE_KINDS)}"
            )
        if k not in seen:
            seen.add(k)
            cleaned.append(k)
    if not cleaned:
        raise SearchQueryError("kinds filter cannot be empty")
    return tuple(cleaned)


def _validate_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise SearchQueryError("limit must be an int")
    if limit < 1 or limit > _MAX_LIMIT:
        raise SearchQueryError(f"limit must be between 1 and {_MAX_LIMIT}")
    return limit


def _validate_query(query: str) -> str:
    if not isinstance(query, str):
        raise SearchQueryError("query must be a string")
    cleaned = query.strip()
    if not cleaned:
        raise SearchQueryError("query must be a non-blank string")
    if len(cleaned) > _QUERY_MAX_LEN:
        raise SearchQueryError(f"query is too long (max {_QUERY_MAX_LEN} characters)")
    return cleaned


def _snippet(body: str, tokens: Iterable[str]) -> str:
    """Return a small window around the first matched token, or the head of body."""

    if not body:
        return ""
    lower = body.lower()
    earliest = -1
    for token in tokens:
        idx = lower.find(token)
        if idx == -1:
            continue
        if earliest == -1 or idx < earliest:
            earliest = idx
    if earliest == -1:
        head = body[: _SNIPPET_RADIUS * 2].strip()
        return head + ("…" if len(body) > _SNIPPET_RADIUS * 2 else "")
    start = max(0, earliest - _SNIPPET_RADIUS)
    end = min(len(body), earliest + _SNIPPET_RADIUS)
    fragment = body[start:end].strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{fragment}{suffix}"


def _score(title: str, body: str, query_tokens: tuple[str, ...]) -> tuple[int, list[str]]:
    """Return ``(score, matched_tokens)`` for a single document."""

    title_tokens = set(tokenize(title))
    body_tokens = set(tokenize(body))
    score = 0
    matched: list[str] = []
    for token in query_tokens:
        hit_title = token in title_tokens
        hit_body = token in body_tokens
        if not (hit_title or hit_body):
            continue
        matched.append(token)
        if hit_title:
            score += _TITLE_WEIGHT
        if hit_body:
            score += _BODY_WEIGHT
    return score, matched


def search_domain(
    store: DomainStore,
    *,
    query: str,
    kinds: Iterable[str] | None = None,
    limit: int = _DEFAULT_LIMIT,
    project_id: str | None = None,
    space_id: str | None = None,
    principal: Principal | None = None,
) -> SearchResult:
    """Search across work items, pages, and comments.

    Args:
        store: the domain store to query.
        query: free-text query string. Tokenized via :func:`tokenize`.
        kinds: optional subset of :data:`SEARCHABLE_KINDS`. Defaults to all.
        limit: maximum hits to return, 1..100. Excess hits are discarded but
            counted in ``total``.
        project_id: restrict work-item and work-item-comment hits to this
            project. Pages and page-comments are unaffected unless
            ``space_id`` is also set.
        space_id: restrict page and page-comment hits to this space.

    Raises:
        SearchQueryError: on invalid query, kind, or limit.
    """

    cleaned_query = _validate_query(query)
    kinds_tuple = _validate_kinds(kinds)
    limit_value = _validate_limit(limit)
    effective_principal = principal  # None means "no filtering" (back-compat)
    tokens = tokenize(cleaned_query)
    if not tokens:
        return SearchResult(
            query=cleaned_query,
            tokens=(),
            kinds=kinds_tuple,
            hits=(),
            total=0,
            limit=limit_value,
            project_id=project_id,
            space_id=space_id,
        )

    # Permission caches keyed by id so each project/space is checked once.
    _project_read: dict[str, bool] = {}
    _space_read: dict[str, bool] = {}

    def _project_allowed(pid: str | None) -> bool:
        if pid is None or effective_principal is None:
            return True
        cached = _project_read.get(pid)
        if cached is not None:
            return cached
        try:
            proj = store.get_project(pid)
        except Exception:
            _project_read[pid] = False
            return False
        ok = can_read(
            effective_principal,
            visibility=proj.visibility,
            members=proj.members,
        )
        _project_read[pid] = ok
        return ok

    def _space_allowed(sid: str | None) -> bool:
        if sid is None or effective_principal is None:
            return True
        cached = _space_read.get(sid)
        if cached is not None:
            return cached
        try:
            sp = store.get_space(sid)
        except Exception:
            _space_read[sid] = False
            return False
        ok = can_read(
            effective_principal,
            visibility=sp.visibility,
            members=sp.members,
        )
        _space_read[sid] = ok
        return ok

    hits: list[Hit] = []

    if "work_item" in kinds_tuple:
        for item in store.list_work_items(project_id=project_id):
            if not _project_allowed(item.project_id):
                continue
            score, matched = _score(item.title, item.description, tokens)
            if score == 0:
                continue
            hits.append(
                Hit(
                    kind="work_item",
                    entity_id=item.work_item_id,
                    title=item.title,
                    snippet=_snippet(item.description, matched),
                    score=score,
                    matched_tokens=tuple(matched),
                    project_id=item.project_id,
                    space_id=None,
                    parent_kind=None,
                    parent_id=None,
                    created_at=item.created_at,
                )
            )

    if "page" in kinds_tuple:
        for page in store.list_pages(space_id=space_id):
            if not _space_allowed(page.space_id):
                continue
            current = store.get_page_version(page.page_id, page.current_version)
            score, matched = _score(current.title, current.body, tokens)
            if score == 0:
                continue
            hits.append(
                Hit(
                    kind="page",
                    entity_id=page.page_id,
                    title=current.title,
                    snippet=_snippet(current.body, matched),
                    score=score,
                    matched_tokens=tuple(matched),
                    project_id=None,
                    space_id=page.space_id,
                    parent_kind=None,
                    parent_id=None,
                    created_at=page.created_at,
                )
            )

    if "comment" in kinds_tuple:
        # Work-item comments.
        for item in store.list_work_items(project_id=project_id):
            if not _project_allowed(item.project_id):
                continue
            for comment in store.list_work_item_comments(item.work_item_id):
                score, matched = _score("", comment.body, tokens)
                if score == 0:
                    continue
                hits.append(
                    Hit(
                        kind="comment",
                        entity_id=comment.comment_id,
                        title=f"comment on {item.key}",
                        snippet=_snippet(comment.body, matched),
                        score=score,
                        matched_tokens=tuple(matched),
                        project_id=item.project_id,
                        space_id=None,
                        parent_kind="work_item",
                        parent_id=item.work_item_id,
                        created_at=comment.created_at,
                    )
                )
        # Page comments.
        for page in store.list_pages(space_id=space_id):
            if not _space_allowed(page.space_id):
                continue
            current = store.get_page_version(page.page_id, page.current_version)
            for comment in store.list_page_comments(page.page_id):
                score, matched = _score("", comment.body, tokens)
                if score == 0:
                    continue
                hits.append(
                    Hit(
                        kind="comment",
                        entity_id=comment.comment_id,
                        title=f"comment on page {current.title}",
                        snippet=_snippet(comment.body, matched),
                        score=score,
                        matched_tokens=tuple(matched),
                        project_id=None,
                        space_id=page.space_id,
                        parent_kind="page",
                        parent_id=page.page_id,
                        created_at=comment.created_at,
                    )
                )

    # Deterministic ordering: score desc, then created_at asc, then
    # entity_id asc. The asc tie-breakers keep result lists stable when
    # rows share the same ingest second.
    hits.sort(key=lambda h: (-h.score, h.created_at, h.entity_id))
    total = len(hits)
    capped = tuple(hits[:limit_value])
    return SearchResult(
        query=cleaned_query,
        tokens=tokens,
        kinds=kinds_tuple,
        hits=capped,
        total=total,
        limit=limit_value,
        project_id=project_id,
        space_id=space_id,
    )


__all__: Iterable[str] = (
    "Hit",
    "SEARCHABLE_KINDS",
    "SearchQueryError",
    "SearchResult",
    "search_domain",
    "tokenize",
)
