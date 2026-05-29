"""Minimal visibility/permission model for Phase 6.

Phase 6 introduces a *tag*-based read-permission model: every Project and
Space carries a ``visibility`` tag (``public``/``internal``/``restricted``)
and an explicit ``members`` set. Per-object ACLs and real authentication
are deferred to phase 7.

The model is intentionally tiny:

* :class:`Principal` — ``id`` + ``groups`` (free-text). ``AnonymousPrincipal``
  is the zero-value used when an HTTP request lacks an
  ``X-Innerwork-Principal`` header.
* :data:`Visibility` — ``"public"`` (anyone reads), ``"internal"`` (any
  named principal reads — anonymous denied), ``"restricted"`` (only listed
  members or matching groups read).
* :func:`can_read` — pure predicate, no I/O, no exceptions, returns ``bool``.

``can_read`` is the single read-gate used by ``search``, ``analytics``, and
``ai_context``. Higher layers MUST funnel reads through this function so the
gate is auditable in one place.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

__all__ = (
    "VISIBILITIES",
    "DEFAULT_VISIBILITY",
    "Visibility",
    "Principal",
    "AnonymousPrincipal",
    "can_read",
    "normalize_members",
    "parse_principal_header",
    "validate_visibility",
)


Visibility = Literal["public", "internal", "restricted"]

VISIBILITIES: tuple[str, ...] = ("public", "internal", "restricted")
DEFAULT_VISIBILITY: Visibility = "internal"


def validate_visibility(value: str) -> Visibility:
    """Return ``value`` typed as :data:`Visibility`, raising on unknown tags."""

    if value not in VISIBILITIES:
        raise ValueError(
            f"visibility must be one of {VISIBILITIES}, got {value!r}"
        )
    return value  # type: ignore[return-value]


def normalize_members(members: Iterable[str] | None) -> tuple[str, ...]:
    """Return a deterministic tuple of unique, non-blank member identifiers.

    Members may name a principal id OR a group. Read-access is granted to
    either a principal whose ``id`` appears in ``members`` or whose
    ``groups`` set intersects ``members``.
    """

    if members is None:
        return ()
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in members:
        if not isinstance(raw, str):
            raise TypeError(f"member entries must be strings, got {type(raw).__name__}")
        token = raw.strip()
        if not token:
            continue
        if token in seen:
            continue
        seen.add(token)
        cleaned.append(token)
    return tuple(sorted(cleaned))


@dataclass(frozen=True)
class Principal:
    """A read-side identity. ``id=""`` means anonymous."""

    id: str = ""
    groups: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("Principal.id must be a string")
        if not isinstance(self.groups, tuple):
            raise TypeError("Principal.groups must be a tuple")
        for g in self.groups:
            if not isinstance(g, str) or not g.strip():
                raise ValueError("Principal.groups entries must be non-blank strings")

    @property
    def is_anonymous(self) -> bool:
        return self.id.strip() == ""

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "groups": list(self.groups)}


AnonymousPrincipal = Principal(id="", groups=())


def can_read(
    principal: Principal,
    *,
    visibility: str,
    members: Iterable[str] = (),
) -> bool:
    """Return ``True`` iff ``principal`` may read an object with these tags.

    Rules (intentionally simple, auditable):

    * ``public`` — always readable, even by :data:`AnonymousPrincipal`.
    * ``internal`` — readable by any non-anonymous principal.
    * ``restricted`` — readable only when ``principal.id`` is in ``members``
      or one of ``principal.groups`` is in ``members``.

    Anonymous principals are denied for both ``internal`` and ``restricted``.
    """

    if not isinstance(principal, Principal):  # pragma: no cover — defensive
        raise TypeError("principal must be a Principal")
    try:
        tag = validate_visibility(visibility)
    except ValueError:
        return False
    if tag == "public":
        return True
    if principal.is_anonymous:
        return False
    if tag == "internal":
        return True
    # restricted
    member_set = {m for m in members if isinstance(m, str) and m.strip()}
    if principal.id in member_set:
        return True
    return any(group in member_set for group in principal.groups)


def parse_principal_header(raw: str | None) -> Principal:
    """Parse an ``X-Innerwork-Principal`` header value.

    Format::

        <principal_id>;<group1>,<group2>,...

    The ``;<groups>`` suffix is optional. An empty / missing header yields
    :data:`AnonymousPrincipal`. The parser is forgiving on whitespace and on
    the absence of a groups segment but does NOT silently swallow malformed
    tokens — blank ids with a trailing groups segment raise ``ValueError``.

    No authentication is performed: this is identity, not authorization
    proof. Phase 7 will replace it with verified principals.
    """

    if raw is None:
        return AnonymousPrincipal
    if not isinstance(raw, str):
        raise TypeError("principal header must be a string or None")
    text = raw.strip()
    if not text:
        return AnonymousPrincipal
    if ";" in text:
        ident_raw, groups_raw = text.split(";", 1)
    else:
        ident_raw, groups_raw = text, ""
    ident = ident_raw.strip()
    if not ident:
        raise ValueError("principal header has empty id")
    if any(ch.isspace() for ch in ident):
        raise ValueError("principal id must not contain whitespace")
    groups: list[str] = []
    if groups_raw.strip():
        for token in groups_raw.split(","):
            t = token.strip()
            if not t:
                continue
            if any(ch.isspace() for ch in t):
                raise ValueError("group names must not contain whitespace")
            groups.append(t)
    return Principal(id=ident, groups=tuple(groups))
