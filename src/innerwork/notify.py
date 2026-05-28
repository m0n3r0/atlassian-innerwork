"""Notification surface for the Innerwork product-domain.

This module is the Phase 5 collaboration slice. It is intentionally a pure,
in-process module with no email/Slack/webhook side effects: the goal is to
provide a clean, observable, rate-limited dispatch primitive that higher
layers (API, CLI, background workers) can drive. Integrations with concrete
transports land in later phases and must be implemented explicitly; this
module never claims a third-party connector exists.

Capabilities
============
* ``parse_mentions(body)`` extracts ``@handle`` tokens from comment bodies and
  page bodies. Handles are validated against a small charset to keep the
  cross-graph routing deterministic.
* ``UserDirectory`` maps a handle to a stable ``user_id`` so mention
  resolution points to the same person across work items and pages.
* ``NotificationPreferences`` per ``user_id`` controls which event kinds the
  user wants and an optional UTC quiet-hours window. Notifications produced
  during quiet hours are suppressed (never queued, never delivered).
* ``Notifier`` is the dispatcher. It owns a deterministic event log
  (`dispatched`), a `suppressed` log (with reasons), and a per-user
  token-bucket rate limiter so a noisy mention burst cannot drown a user.

The dispatcher is single-threaded and synchronous: ``dispatch`` returns a
tuple of the notifications that were actually delivered for the event.
Tests and callers can introspect ``notifier.dispatched`` /
``notifier.suppressed`` for assertions.

This module does not invent email-template content or vendor-standard copy;
the ``Notification.summary`` field is a short, deterministic string built
from the event kind and the actor/target identifiers.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Mention parsing
# ---------------------------------------------------------------------------

#: ``@handle`` tokens are 2-32 chars, lowercase a-z0-9, underscore, hyphen.
#: The leading ``@`` must be preceded by start-of-string or a non-word char so
#: that email addresses (``alice@example.com``) do not trigger mentions.
_MENTION_RE = re.compile(r"(?:^|(?<=[^\w]))@([A-Za-z0-9][A-Za-z0-9_-]{1,31})")


def parse_mentions(body: str) -> tuple[str, ...]:
    """Return the ordered, deduplicated list of ``@handle`` tokens in ``body``.

    Handles are normalised to lowercase; the leading ``@`` is stripped.
    Email-like ``user@host`` substrings are not matched.
    """

    if not isinstance(body, str):
        raise TypeError("body must be a string")
    seen: dict[str, None] = {}
    for match in _MENTION_RE.finditer(body):
        handle = match.group(1).lower()
        if handle not in seen:
            seen[handle] = None
    return tuple(seen)


# ---------------------------------------------------------------------------
# Event kinds
# ---------------------------------------------------------------------------

#: Closed vocabulary of notification kinds. Keeping the set small makes
#: routing and user-preference auditing tractable.
EVENT_KINDS: frozenset[str] = frozenset(
    {
        "work_item.assigned",
        "work_item.transitioned",
        "work_item.mentioned",
        "page.mentioned",
        "page.subscribed_update",
    }
)


def validate_event_kind(kind: str) -> str:
    if not isinstance(kind, str):
        raise TypeError("event kind must be a string")
    if kind not in EVENT_KINDS:
        raise ValueError(f"unknown event kind: {kind!r}")
    return kind


# ---------------------------------------------------------------------------
# Directory and preferences
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    """A user registered in the directory."""

    user_id: str
    handle: str
    display_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id must be a non-blank string")
        if not isinstance(self.handle, str) or not _MENTION_RE.match("@" + self.handle):
            raise ValueError(f"invalid handle: {self.handle!r}")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("display_name must be non-blank")

    def to_dict(self) -> dict[str, str]:
        return {"user_id": self.user_id, "handle": self.handle, "display_name": self.display_name}


class UserDirectory:
    """In-memory mapping of ``@handle`` <-> ``user_id``.

    Real deployments will back this with a persistent store; the public
    surface (``resolve_handles``, ``register``) is intentionally narrow so
    the swap is mechanical.
    """

    def __init__(self, users: Iterable[User] = ()) -> None:
        self._by_handle: dict[str, User] = {}
        self._by_id: dict[str, User] = {}
        for user in users:
            self.register(user)

    def register(self, user: User) -> None:
        if user.handle in self._by_handle and self._by_handle[user.handle].user_id != user.user_id:
            raise ValueError(f"handle {user.handle!r} already bound to a different user")
        if user.user_id in self._by_id and self._by_id[user.user_id].handle != user.handle:
            raise ValueError(f"user_id {user.user_id!r} already bound to a different handle")
        self._by_handle[user.handle] = user
        self._by_id[user.user_id] = user

    def get(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    def get_by_handle(self, handle: str) -> User | None:
        return self._by_handle.get(handle.lower())

    def resolve_handles(self, handles: Iterable[str]) -> tuple[User, ...]:
        """Return the ordered, deduplicated list of users for ``handles``.

        Unknown handles are silently dropped: mention resolution is
        best-effort and must not raise on typos.
        """

        seen: dict[str, User] = {}
        for raw in handles:
            user = self._by_handle.get(raw.lower())
            if user is None:
                continue
            seen.setdefault(user.user_id, user)
        return tuple(seen.values())


@dataclass(frozen=True)
class QuietHours:
    """A daily quiet-hours window in UTC.

    A window where ``start_hour == end_hour`` is treated as empty (the user
    has effectively disabled quiet hours). Windows that cross midnight
    (e.g. ``22 -> 6``) are supported.
    """

    start_hour: int
    end_hour: int

    def __post_init__(self) -> None:
        for label, value in (("start_hour", self.start_hour), ("end_hour", self.end_hour)):
            if not isinstance(value, int) or not 0 <= value < 24:
                raise ValueError(f"{label} must be an integer in [0, 24)")

    def is_quiet(self, now: datetime) -> bool:
        if self.start_hour == self.end_hour:
            return False
        if now.tzinfo is None:
            raise ValueError("quiet-hours check requires a timezone-aware datetime")
        hour = now.astimezone(timezone.utc).hour
        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour
        # Wrap-around window, e.g. 22 -> 6.
        return hour >= self.start_hour or hour < self.end_hour


@dataclass(frozen=True)
class NotificationPreferences:
    """Per-user opt-in preferences for the closed ``EVENT_KINDS`` vocabulary."""

    user_id: str
    enabled_kinds: frozenset[str] = field(default_factory=lambda: frozenset(EVENT_KINDS))
    quiet_hours: QuietHours | None = None
    page_subscriptions: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id must be a non-blank string")
        unknown = set(self.enabled_kinds) - EVENT_KINDS
        if unknown:
            raise ValueError(f"unknown event kinds in enabled_kinds: {sorted(unknown)!r}")

    def wants(self, kind: str) -> bool:
        return kind in self.enabled_kinds

    def subscribes_to(self, page_id: str) -> bool:
        return page_id in self.page_subscriptions


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


@dataclass(frozen=True)
class RateLimitConfig:
    """Per-user token-bucket parameters."""

    capacity: int = 5
    refill_per_second: float = 1.0 / 30.0  # one token every 30 s

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("capacity must be >= 1")
        if self.refill_per_second <= 0:
            raise ValueError("refill_per_second must be > 0")


# ---------------------------------------------------------------------------
# Events and notifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NotificationEvent:
    """An emission from the domain that the notifier may turn into deliveries."""

    kind: str
    actor: str
    target_user_ids: tuple[str, ...]
    occurred_at: datetime
    work_item_id: str | None = None
    page_id: str | None = None
    comment_id: str | None = None
    summary: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_event_kind(self.kind)
        if not isinstance(self.actor, str) or not self.actor.strip():
            raise ValueError("actor must be a non-blank string")
        if not isinstance(self.target_user_ids, tuple):
            raise TypeError("target_user_ids must be a tuple")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True)
class Notification:
    """A delivered notification."""

    kind: str
    user_id: str
    actor: str
    occurred_at: str
    summary: str
    work_item_id: str | None = None
    page_id: str | None = None
    comment_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "user_id": self.user_id,
            "actor": self.actor,
            "occurred_at": self.occurred_at,
            "summary": self.summary,
            "work_item_id": self.work_item_id,
            "page_id": self.page_id,
            "comment_id": self.comment_id,
        }


@dataclass(frozen=True)
class SuppressedNotification:
    """A notification that was not delivered, with a stable reason code."""

    kind: str
    user_id: str
    reason: str  # one of: "disabled", "quiet_hours", "rate_limited", "self"
    occurred_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "user_id": self.user_id,
            "reason": self.reason,
            "occurred_at": self.occurred_at,
        }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _iso(occurred_at: datetime) -> str:
    return occurred_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_summary(event: NotificationEvent, target_user_id: str) -> str:
    if event.summary:
        return event.summary
    bits = [event.kind, f"by {event.actor}"]
    if event.work_item_id:
        bits.append(f"work_item={event.work_item_id}")
    if event.page_id:
        bits.append(f"page={event.page_id}")
    bits.append(f"to {target_user_id}")
    return " ".join(bits)


class Notifier:
    """In-process notification dispatcher.

    Construction takes a ``UserDirectory`` and a mapping of preferences.
    Callers drive the dispatcher with :meth:`dispatch`; results are appended
    to ``dispatched`` and ``suppressed`` for observability.
    """

    def __init__(
        self,
        directory: UserDirectory,
        preferences: Mapping[str, NotificationPreferences] | None = None,
        *,
        rate_limit: RateLimitConfig | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._directory = directory
        self._prefs: dict[str, NotificationPreferences] = dict(preferences or {})
        self._rate_limit = rate_limit or RateLimitConfig()
        self._clock = clock or (lambda: datetime.now(tz=timezone.utc))
        self._buckets: dict[str, _Bucket] = {}
        self.dispatched: list[Notification] = []
        self.suppressed: list[SuppressedNotification] = []

    # -- preferences -----------------------------------------------------
    def set_preferences(self, prefs: NotificationPreferences) -> None:
        self._prefs[prefs.user_id] = prefs

    def preferences_for(self, user_id: str) -> NotificationPreferences:
        existing = self._prefs.get(user_id)
        if existing is not None:
            return existing
        # Default: opt-in to every kind, no quiet hours, no subscriptions.
        return NotificationPreferences(user_id=user_id)

    def subscribe_page(self, user_id: str, page_id: str) -> None:
        current = self.preferences_for(user_id)
        new_subs = frozenset(current.page_subscriptions | {page_id})
        self._prefs[user_id] = replace(current, page_subscriptions=new_subs)

    def unsubscribe_page(self, user_id: str, page_id: str) -> None:
        current = self.preferences_for(user_id)
        new_subs = frozenset(current.page_subscriptions - {page_id})
        self._prefs[user_id] = replace(current, page_subscriptions=new_subs)

    def subscribers_for_page(self, page_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(uid for uid, prefs in self._prefs.items() if prefs.subscribes_to(page_id))
        )

    # -- dispatch --------------------------------------------------------
    def dispatch(self, event: NotificationEvent) -> tuple[Notification, ...]:
        delivered: list[Notification] = []
        timestamp = _iso(event.occurred_at)
        for user_id in event.target_user_ids:
            user = self._directory.get(user_id)
            if user is None:
                # Unknown user: nothing to deliver and no preferences to consult.
                self.suppressed.append(
                    SuppressedNotification(
                        kind=event.kind,
                        user_id=user_id,
                        reason="disabled",
                        occurred_at=timestamp,
                    )
                )
                continue
            if user.handle == event.actor or user.user_id == event.actor:
                self.suppressed.append(
                    SuppressedNotification(
                        kind=event.kind,
                        user_id=user_id,
                        reason="self",
                        occurred_at=timestamp,
                    )
                )
                continue
            prefs = self.preferences_for(user_id)
            if not prefs.wants(event.kind):
                self.suppressed.append(
                    SuppressedNotification(
                        kind=event.kind,
                        user_id=user_id,
                        reason="disabled",
                        occurred_at=timestamp,
                    )
                )
                continue
            if prefs.quiet_hours is not None and prefs.quiet_hours.is_quiet(event.occurred_at):
                self.suppressed.append(
                    SuppressedNotification(
                        kind=event.kind,
                        user_id=user_id,
                        reason="quiet_hours",
                        occurred_at=timestamp,
                    )
                )
                continue
            if not self._take_token(user_id, event.occurred_at):
                self.suppressed.append(
                    SuppressedNotification(
                        kind=event.kind,
                        user_id=user_id,
                        reason="rate_limited",
                        occurred_at=timestamp,
                    )
                )
                continue
            notification = Notification(
                kind=event.kind,
                user_id=user_id,
                actor=event.actor,
                occurred_at=timestamp,
                summary=_default_summary(event, user_id),
                work_item_id=event.work_item_id,
                page_id=event.page_id,
                comment_id=event.comment_id,
            )
            delivered.append(notification)
            self.dispatched.append(notification)
        return tuple(delivered)

    # -- token bucket ----------------------------------------------------
    def _take_token(self, user_id: str, when: datetime) -> bool:
        cap = float(self._rate_limit.capacity)
        refill = self._rate_limit.refill_per_second
        ts = when.astimezone(timezone.utc).timestamp()
        bucket = self._buckets.get(user_id)
        if bucket is None:
            bucket = _Bucket(tokens=cap, updated_at=ts)
            self._buckets[user_id] = bucket
        else:
            elapsed = max(0.0, ts - bucket.updated_at)
            bucket.tokens = min(cap, bucket.tokens + elapsed * refill)
            bucket.updated_at = ts
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True
        return False


# ---------------------------------------------------------------------------
# Convenience builders for common domain events
# ---------------------------------------------------------------------------


def build_assignment_event(
    *,
    actor: str,
    assignee_user_id: str,
    work_item_id: str,
    occurred_at: datetime,
) -> NotificationEvent:
    return NotificationEvent(
        kind="work_item.assigned",
        actor=actor,
        target_user_ids=(assignee_user_id,),
        occurred_at=occurred_at,
        work_item_id=work_item_id,
    )


def build_transition_event(
    *,
    actor: str,
    watcher_user_ids: tuple[str, ...],
    work_item_id: str,
    from_state: str,
    to_state: str,
    occurred_at: datetime,
) -> NotificationEvent:
    return NotificationEvent(
        kind="work_item.transitioned",
        actor=actor,
        target_user_ids=watcher_user_ids,
        occurred_at=occurred_at,
        work_item_id=work_item_id,
        payload={"from": from_state, "to": to_state},
    )


def build_mention_event_for_work_item(
    *,
    actor: str,
    mentioned_user_ids: tuple[str, ...],
    work_item_id: str,
    comment_id: str | None,
    occurred_at: datetime,
) -> NotificationEvent:
    return NotificationEvent(
        kind="work_item.mentioned",
        actor=actor,
        target_user_ids=mentioned_user_ids,
        occurred_at=occurred_at,
        work_item_id=work_item_id,
        comment_id=comment_id,
    )


def build_mention_event_for_page(
    *,
    actor: str,
    mentioned_user_ids: tuple[str, ...],
    page_id: str,
    comment_id: str | None,
    occurred_at: datetime,
) -> NotificationEvent:
    return NotificationEvent(
        kind="page.mentioned",
        actor=actor,
        target_user_ids=mentioned_user_ids,
        occurred_at=occurred_at,
        page_id=page_id,
        comment_id=comment_id,
    )


def build_page_subscription_event(
    *,
    actor: str,
    subscriber_user_ids: tuple[str, ...],
    page_id: str,
    occurred_at: datetime,
    summary: str = "",
) -> NotificationEvent:
    return NotificationEvent(
        kind="page.subscribed_update",
        actor=actor,
        target_user_ids=subscriber_user_ids,
        occurred_at=occurred_at,
        page_id=page_id,
        summary=summary,
    )


__all__: Iterable[str] = (
    "EVENT_KINDS",
    "Notification",
    "NotificationEvent",
    "NotificationPreferences",
    "Notifier",
    "QuietHours",
    "RateLimitConfig",
    "SuppressedNotification",
    "User",
    "UserDirectory",
    "build_assignment_event",
    "build_mention_event_for_page",
    "build_mention_event_for_work_item",
    "build_page_subscription_event",
    "build_transition_event",
    "parse_mentions",
    "validate_event_kind",
)
