"""AI-context bundling for assistant integrations.

Phase 6 slice 2. Given a free-text query or an anchor work item / page,
return a compact, provenance-tagged bundle of related entities the
assistant may use to ground its answer. The bundle respects a token
budget (approximated as characters, since we are LLM-agnostic) and is
deterministic — the same store + query produces the same bundle, which
lets us write contract tests against the API.

The shape this module returns is intentionally the seam Phase D
(permissions, redaction) and Phase G (provenance + budget guarantees)
will wrap. Today every entity reachable from the query is included; the
slot for permission filtering is :func:`_collect_candidates`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .permissions import AnonymousPrincipal, Principal, can_read
from .search import SearchQueryError, search_domain, tokenize

if TYPE_CHECKING:  # pragma: no cover — typing only
    from .domain_store import DomainStore

CONTEXT_KINDS: tuple[str, ...] = ("work_item", "page", "comment", "transition", "link")

DEFAULT_TOKEN_BUDGET = 4000
_MIN_TOKEN_BUDGET = 200
_MAX_TOKEN_BUDGET = 32_000
_DEFAULT_MAX_ITEMS = 20
_MAX_MAX_ITEMS = 100
# Characters per "token" — a deliberately conservative proxy used until
# we wire the bundle to a real tokenizer. Documented in the phase doc.
CHARS_PER_TOKEN = 4


class AIContextError(ValueError):
    """Raised on invalid AI-context requests."""


@dataclass(frozen=True)
class ContextEntry:
    """One entity included in an AI-context bundle.

    ``payload`` is the canonical dict for the entity (already produced
    by the domain model's ``to_dict``). ``provenance`` describes how the
    entity entered the bundle so callers can audit assistant outputs.
    ``approx_tokens`` is the budget cost using the ``CHARS_PER_TOKEN``
    proxy.
    """

    kind: str
    entity_id: str
    payload: Mapping[str, object]
    provenance: Mapping[str, object]
    approx_tokens: int

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "entity_id": self.entity_id,
            "payload": self.payload,
            "provenance": self.provenance,
            "approx_tokens": self.approx_tokens,
        }


@dataclass(frozen=True)
class ContextBundle:
    """Envelope returned by :func:`build_ai_context`."""

    query: str | None
    anchor_kind: str | None
    anchor_id: str | None
    token_budget: int
    approx_tokens: int
    truncated: bool
    entries: tuple[ContextEntry, ...]
    omitted_candidates: int

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "anchor_kind": self.anchor_kind,
            "anchor_id": self.anchor_id,
            "token_budget": self.token_budget,
            "approx_tokens": self.approx_tokens,
            "truncated": self.truncated,
            "omitted_candidates": self.omitted_candidates,
            "entries": [e.to_dict() for e in self.entries],
        }


# ----------------------------------------------------------- size accounting

def _approx_tokens(payload: Mapping[str, object]) -> int:
    """Approximate token cost of including ``payload`` in the bundle."""

    # Char count over the textual fields a typical model would actually
    # read. Deterministic and tokenizer-agnostic.
    text = ""
    for key in ("title", "body", "description", "snippet", "reason", "name"):
        value = payload.get(key)
        if isinstance(value, str):
            text += value
            text += "\n"
    # Plus a fixed overhead for the structured wrapper.
    overhead = 32
    return max(1, (len(text) + overhead) // CHARS_PER_TOKEN)


# --------------------------------------------------------- candidate gather

def _entry_for_work_item(
    store: "DomainStore",
    work_item_id: str,
    *,
    reason: str,
    source_kind: str | None = None,
    source_id: str | None = None,
) -> ContextEntry:
    item = store.get_work_item(work_item_id)
    payload = item.to_dict()
    return ContextEntry(
        kind="work_item",
        entity_id=item.work_item_id,
        payload=payload,
        provenance={
            "reason": reason,
            "source_kind": source_kind,
            "source_id": source_id,
        },
        approx_tokens=_approx_tokens(payload),
    )


def _entry_for_page(
    store: "DomainStore",
    page_id: str,
    *,
    reason: str,
    source_kind: str | None = None,
    source_id: str | None = None,
) -> ContextEntry:
    page = store.get_page(page_id)
    version = store.get_page_version(page_id, page.current_version)
    payload = {
        "page_id": page.page_id,
        "space_id": page.space_id,
        "current_version": page.current_version,
        "created_at": page.created_at,
        "updated_at": page.updated_at,
        "title": version.title,
        "body": version.body,
        "author": version.author,
        "version_number": version.version_number,
    }
    return ContextEntry(
        kind="page",
        entity_id=page.page_id,
        payload=payload,
        provenance={
            "reason": reason,
            "source_kind": source_kind,
            "source_id": source_id,
        },
        approx_tokens=_approx_tokens(payload),
    )


def _entry_for_comment(
    comment,
    *,
    parent_kind: str,
    parent_id: str,
    reason: str,
) -> ContextEntry:
    payload = comment.to_dict()
    return ContextEntry(
        kind="comment",
        entity_id=comment.comment_id,
        payload=payload,
        provenance={
            "reason": reason,
            "parent_kind": parent_kind,
            "parent_id": parent_id,
        },
        approx_tokens=_approx_tokens(payload),
    )


def _entry_for_transition(
    transition,
    *,
    work_item_id: str,
    reason: str,
) -> ContextEntry:
    payload = transition.to_dict()
    return ContextEntry(
        kind="transition",
        entity_id=f"t{transition.transition_id}",
        payload=payload,
        provenance={
            "reason": reason,
            "parent_kind": "work_item",
            "parent_id": work_item_id,
        },
        approx_tokens=_approx_tokens(payload),
    )


def _entry_for_link(link, *, reason: str) -> ContextEntry:
    payload = link.to_dict()
    return ContextEntry(
        kind="link",
        entity_id=link.link_id,
        payload=payload,
        provenance={
            "reason": reason,
            "work_item_id": link.work_item_id,
            "page_id": link.page_id,
        },
        approx_tokens=_approx_tokens(payload),
    )


def _expand_work_item(store: "DomainStore", work_item_id: str) -> Iterable[ContextEntry]:
    """Yield comments, transitions, and linked pages for a work item."""

    for comment in store.list_work_item_comments(work_item_id):
        yield _entry_for_comment(
            comment,
            parent_kind="work_item",
            parent_id=work_item_id,
            reason="anchor_work_item_comment",
        )
    for transition in store.list_transitions(work_item_id):
        yield _entry_for_transition(
            transition,
            work_item_id=work_item_id,
            reason="anchor_work_item_transition",
        )
    for link in store.list_links_for_work_item(work_item_id):
        yield _entry_for_link(link, reason="anchor_work_item_link")
        yield _entry_for_page(
            store,
            link.page_id,
            reason="linked_from_work_item",
            source_kind="work_item",
            source_id=work_item_id,
        )


def _expand_page(store: "DomainStore", page_id: str) -> Iterable[ContextEntry]:
    """Yield comments and linked work items for a page."""

    for comment in store.list_page_comments(page_id):
        yield _entry_for_comment(
            comment,
            parent_kind="page",
            parent_id=page_id,
            reason="anchor_page_comment",
        )
    for link in store.list_links_for_page(page_id):
        yield _entry_for_link(link, reason="anchor_page_link")
        yield _entry_for_work_item(
            store,
            link.work_item_id,
            reason="linked_from_page",
            source_kind="page",
            source_id=page_id,
        )


# ----------------------------------------------------------- public API

def _validate_token_budget(budget: int) -> int:
    if not isinstance(budget, int) or isinstance(budget, bool):
        raise AIContextError("token_budget must be an int")
    if budget < _MIN_TOKEN_BUDGET or budget > _MAX_TOKEN_BUDGET:
        raise AIContextError(
            f"token_budget must be between {_MIN_TOKEN_BUDGET} and {_MAX_TOKEN_BUDGET}"
        )
    return budget


def _validate_max_items(max_items: int) -> int:
    if not isinstance(max_items, int) or isinstance(max_items, bool):
        raise AIContextError("max_items must be an int")
    if max_items < 1 or max_items > _MAX_MAX_ITEMS:
        raise AIContextError(f"max_items must be between 1 and {_MAX_MAX_ITEMS}")
    return max_items


def build_ai_context(
    store: "DomainStore",
    *,
    query: str | None = None,
    anchor_kind: str | None = None,
    anchor_id: str | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    max_items: int = _DEFAULT_MAX_ITEMS,
    principal: Principal | None = None,
) -> ContextBundle:
    """Build a deterministic context bundle for an assistant call.

    Either ``query`` or (``anchor_kind`` + ``anchor_id``) is required.
    Both may be supplied; anchor expansion runs first so the anchor's
    related entities take priority over query-only matches.

    Args:
        store: domain store to read from.
        query: optional free-text query; entities are scored with the
            same ranker as :func:`innerwork.search.search_domain`.
        anchor_kind: ``"work_item"`` or ``"page"``.
        anchor_id: id of the anchor entity.
        token_budget: cap on approximate tokens included.
        max_items: hard upper bound on number of entries.

    Raises:
        AIContextError: on invalid input.
    """

    if query is None and anchor_kind is None and anchor_id is None:
        raise AIContextError("either query or (anchor_kind + anchor_id) is required")
    if (anchor_kind is None) != (anchor_id is None):
        raise AIContextError("anchor_kind and anchor_id must be provided together")
    if anchor_kind is not None and anchor_kind not in ("work_item", "page"):
        raise AIContextError("anchor_kind must be 'work_item' or 'page'")

    budget = _validate_token_budget(token_budget)
    cap = _validate_max_items(max_items)
    effective_principal = principal  # None means "no filtering" (back-compat)

    # Permission caches (mirror search.py) so each project/space is checked once.
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
        ok = can_read(effective_principal, visibility=proj.visibility, members=proj.members)
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
        ok = can_read(effective_principal, visibility=sp.visibility, members=sp.members)
        _space_read[sid] = ok
        return ok

    def _work_item_allowed(work_item_id: str) -> bool:
        if effective_principal is None:
            return True
        try:
            item = store.get_work_item(work_item_id)
        except Exception:
            return False
        return _project_allowed(item.project_id)

    def _page_allowed(page_id: str) -> bool:
        if effective_principal is None:
            return True
        try:
            page = store.get_page(page_id)
        except Exception:
            return False
        return _space_allowed(page.space_id)

    def _entry_allowed(entry: ContextEntry) -> bool:
        if effective_principal is None:
            return True
        if entry.kind == "work_item":
            payload = entry.payload
            pid = payload.get("project_id") if isinstance(payload, Mapping) else None
            return _project_allowed(pid if isinstance(pid, str) else None)
        if entry.kind == "page":
            payload = entry.payload
            sid = payload.get("space_id") if isinstance(payload, Mapping) else None
            return _space_allowed(sid if isinstance(sid, str) else None)
        if entry.kind == "comment":
            prov = entry.provenance
            parent_kind = prov.get("parent_kind") if isinstance(prov, Mapping) else None
            parent_id = prov.get("parent_id") if isinstance(prov, Mapping) else None
            if parent_kind == "work_item" and isinstance(parent_id, str):
                return _work_item_allowed(parent_id)
            if parent_kind == "page" and isinstance(parent_id, str):
                return _page_allowed(parent_id)
            return False
        if entry.kind == "transition":
            prov = entry.provenance
            parent_id = prov.get("parent_id") if isinstance(prov, Mapping) else None
            if isinstance(parent_id, str):
                return _work_item_allowed(parent_id)
            return False
        if entry.kind == "link":
            payload = entry.payload
            wi = payload.get("work_item_id") if isinstance(payload, Mapping) else None
            pg = payload.get("page_id") if isinstance(payload, Mapping) else None
            wi_ok = _work_item_allowed(wi) if isinstance(wi, str) else True
            pg_ok = _page_allowed(pg) if isinstance(pg, str) else True
            return wi_ok and pg_ok
        return True

    cleaned_query: str | None = None
    if query is not None:
        cleaned_query = query.strip()
        if not cleaned_query:
            cleaned_query = None
        elif len(cleaned_query) > 200:
            raise AIContextError("query is too long (max 200 characters)")
        else:
            # Reuse the search tokenizer for empty-token detection so the
            # contract matches /v1/search.
            if not tokenize(cleaned_query):
                cleaned_query = None

    candidates: list[ContextEntry] = []
    seen: set[tuple[str, str]] = set()

    def _add(entry: ContextEntry) -> None:
        key = (entry.kind, entry.entity_id)
        if key in seen:
            return
        if not _entry_allowed(entry):
            return
        seen.add(key)
        candidates.append(entry)

    # 1) Anchor expansion (deterministic order from store list_* methods).
    if anchor_kind == "work_item" and anchor_id is not None:
        if not _work_item_allowed(anchor_id):
            raise AIContextError("anchor work item is not readable")
        _add(_entry_for_work_item(store, anchor_id, reason="anchor"))
        for entry in _expand_work_item(store, anchor_id):
            _add(entry)
    elif anchor_kind == "page" and anchor_id is not None:
        if not _page_allowed(anchor_id):
            raise AIContextError("anchor page is not readable")
        _add(_entry_for_page(store, anchor_id, reason="anchor"))
        for entry in _expand_page(store, anchor_id):
            _add(entry)

    # 2) Query expansion via the search ranker.
    if cleaned_query is not None:
        try:
            result = search_domain(
                store,
                query=cleaned_query,
                limit=cap,
                principal=effective_principal,
            )
        except SearchQueryError as exc:
            raise AIContextError(str(exc)) from exc
        for hit in result.hits:
            if hit.kind == "work_item":
                _add(
                    _entry_for_work_item(
                        store,
                        hit.entity_id,
                        reason="query_match",
                        source_kind=None,
                        source_id=None,
                    )
                )
            elif hit.kind == "page":
                _add(
                    _entry_for_page(
                        store,
                        hit.entity_id,
                        reason="query_match",
                        source_kind=None,
                        source_id=None,
                    )
                )
            elif hit.kind == "comment":
                # The search hit gives us the parent, so reload through
                # the store for a canonical comment payload.
                if hit.parent_kind == "work_item" and hit.parent_id is not None:
                    for comment in store.list_work_item_comments(hit.parent_id):
                        if comment.comment_id == hit.entity_id:
                            _add(
                                _entry_for_comment(
                                    comment,
                                    parent_kind="work_item",
                                    parent_id=hit.parent_id,
                                    reason="query_match",
                                )
                            )
                            break
                elif hit.parent_kind == "page" and hit.parent_id is not None:
                    for comment in store.list_page_comments(hit.parent_id):
                        if comment.comment_id == hit.entity_id:
                            _add(
                                _entry_for_comment(
                                    comment,
                                    parent_kind="page",
                                    parent_id=hit.parent_id,
                                    reason="query_match",
                                )
                            )
                            break

    # 3) Budget + cap.
    included: list[ContextEntry] = []
    approx_tokens = 0
    truncated = False
    for entry in candidates:
        if len(included) >= cap:
            truncated = True
            break
        if approx_tokens + entry.approx_tokens > budget:
            truncated = True
            continue
        included.append(entry)
        approx_tokens += entry.approx_tokens

    omitted = len(candidates) - len(included)
    return ContextBundle(
        query=cleaned_query,
        anchor_kind=anchor_kind,
        anchor_id=anchor_id,
        token_budget=budget,
        approx_tokens=approx_tokens,
        truncated=truncated,
        entries=tuple(included),
        omitted_candidates=omitted,
    )


__all__: Iterable[str] = (
    "AIContextError",
    "CHARS_PER_TOKEN",
    "CONTEXT_KINDS",
    "ContextBundle",
    "ContextEntry",
    "DEFAULT_TOKEN_BUDGET",
    "build_ai_context",
)
