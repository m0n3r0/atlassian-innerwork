"""Field-level ACL hook for phase 7.

A deliberately small, flat policy table — no role hierarchy, no group
inheritance. Each policy entry names ``(entity_kind, field)`` and an allowed
set of ``actor_kind`` values for read/write.

Default behavior: when no policy exists for a field, both read and write are
allowed for all actor kinds (no regression vs phase 6). Default actor
``"system"`` always bypasses ACLs so internal callers (CLI, scripts) keep
working without explicit grants.

This module is documentation-as-code: the privacy-relevant fields enumerated
in ``docs/threat-model.md`` §3.4 are seeded below. Adding a new
privacy-relevant field without updating the policy table is a tested
regression (see ``tests/test_field_acl.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = (
    "DEFAULT_POLICY",
    "FieldACL",
    "FieldPolicy",
    "PRIVACY_FIELDS",
    "redact_for",
)


ActorKind = Literal["system", "user", "service", "anonymous"]


@dataclass(frozen=True)
class FieldPolicy:
    """Per-field policy. ``readable_by``/``writable_by`` are actor_kind sets."""

    readable_by: frozenset[str] = frozenset({"system", "user", "service"})
    writable_by: frozenset[str] = frozenset({"system", "user", "service"})
    redact_with: Any = None  # value substituted when read is denied


# Privacy-relevant fields per docs/threat-model.md §3.4. Adding a new one
# requires updating this dict (the test enforces parity).
PRIVACY_FIELDS: tuple[tuple[str, str], ...] = (
    ("User", "email"),
    ("User", "display_name"),
    ("Comment", "author"),
    ("Comment", "body"),
    ("AuditEvent", "actor"),
    ("Page", "version_author"),
    ("MentionEvent", "mentioned_user"),
    ("MentionEvent", "context_snippet"),
)


DEFAULT_POLICY: Mapping[tuple[str, str], FieldPolicy] = {
    ("User", "email"): FieldPolicy(
        readable_by=frozenset({"system", "service"}),
        writable_by=frozenset({"system", "user"}),
        redact_with="[redacted-email]",
    ),
    ("User", "display_name"): FieldPolicy(),  # defaults — open
    ("Comment", "author"): FieldPolicy(),
    ("Comment", "body"): FieldPolicy(),
    ("AuditEvent", "actor"): FieldPolicy(
        readable_by=frozenset({"system", "service"}),
        writable_by=frozenset({"system"}),
        redact_with="[redacted-actor]",
    ),
    ("Page", "version_author"): FieldPolicy(),
    ("MentionEvent", "mentioned_user"): FieldPolicy(
        readable_by=frozenset({"system", "service", "user"}),
        writable_by=frozenset({"system", "service"}),
        redact_with="[redacted-user]",
    ),
    ("MentionEvent", "context_snippet"): FieldPolicy(
        readable_by=frozenset({"system", "service", "user"}),
        writable_by=frozenset({"system", "service"}),
        redact_with="[redacted-snippet]",
    ),
}


@dataclass
class FieldACL:
    """Look up read/write permission for ``(actor_kind, entity_kind, field)``.

    ``policy`` defaults to :data:`DEFAULT_POLICY`; tests may inject a custom
    table to assert truth-table behavior.
    """

    policy: Mapping[tuple[str, str], FieldPolicy] = field(default_factory=lambda: DEFAULT_POLICY)

    def is_readable(self, actor_kind: str, entity_kind: str, field: str) -> bool:
        if actor_kind == "system":
            return True
        policy = self.policy.get((entity_kind, field))
        if policy is None:
            return True
        return actor_kind in policy.readable_by

    def is_writable(self, actor_kind: str, entity_kind: str, field: str) -> bool:
        if actor_kind == "system":
            return True
        policy = self.policy.get((entity_kind, field))
        if policy is None:
            return True
        return actor_kind in policy.writable_by

    def redact_for(
        self,
        actor_kind: str,
        entity_kind: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return a shallow copy of ``payload`` with denied fields replaced.

        Use this in the serialization layer (``domain_api.py``,
        ``knowledge.py``) so the redaction truth table is visible at the
        boundary. Engineering must not call this deep inside the store.
        """

        out: dict[str, Any] = dict(payload)
        for key in list(out.keys()):
            if not self.is_readable(actor_kind, entity_kind, key):
                policy = self.policy.get((entity_kind, key))
                out[key] = policy.redact_with if policy is not None else None
        return out


def redact_for(
    actor_kind: str,
    entity_kind: str,
    payload: Mapping[str, Any],
    *,
    acl: FieldACL | None = None,
) -> dict[str, Any]:
    """Convenience wrapper using the default ACL when none is supplied."""

    return (acl or FieldACL()).redact_for(actor_kind, entity_kind, payload)
