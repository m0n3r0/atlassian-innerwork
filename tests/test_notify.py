"""Tests for the Phase F notification surface (``innerwork.notify``).

These tests exercise only the pure, in-process notify module — there are no
real email / Slack / webhook side-effects. The :class:`Notifier` is driven
with a synthetic clock and asserted against its ``dispatched`` and
``suppressed`` logs.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from innerwork.notify import (
    EVENT_KINDS,
    Notification,
    NotificationEvent,
    NotificationPreferences,
    Notifier,
    QuietHours,
    RateLimitConfig,
    SuppressedNotification,
    User,
    UserDirectory,
    build_assignment_event,
    build_mention_event_for_page,
    build_mention_event_for_work_item,
    build_page_subscription_event,
    build_transition_event,
    parse_mentions,
    validate_event_kind,
)

# --------------------------------------------------------------- parse_mentions


def test_parse_mentions_extracts_handles_in_order_and_deduplicates():
    body = "hey @alice and @bob, also @alice again, ping @carol-1"
    assert parse_mentions(body) == ("alice", "bob", "carol-1")


def test_parse_mentions_lowercases_handles():
    assert parse_mentions("ping @Alice and @BOB") == ("alice", "bob")


def test_parse_mentions_excludes_email_addresses():
    # An email-like substring must not trigger a mention.
    body = "contact alice@example.com or ping @alice on chat"
    assert parse_mentions(body) == ("alice",)


def test_parse_mentions_rejects_tokens_below_min_length():
    # Handles must be >= 2 chars; @a should not match.
    assert parse_mentions("hi @a and @bo") == ("bo",)


def test_parse_mentions_handles_blank_body():
    assert parse_mentions("") == ()


def test_parse_mentions_requires_str():
    with pytest.raises(TypeError):
        parse_mentions(None)  # type: ignore[arg-type]


# --------------------------------------------------------------- event kinds


def test_event_kinds_is_closed_vocabulary():
    assert "work_item.assigned" in EVENT_KINDS
    assert "work_item.transitioned" in EVENT_KINDS
    assert "work_item.mentioned" in EVENT_KINDS
    assert "page.mentioned" in EVENT_KINDS
    assert "page.subscribed_update" in EVENT_KINDS


def test_validate_event_kind_rejects_unknown_kind():
    with pytest.raises(ValueError):
        validate_event_kind("not.a.thing")


def test_validate_event_kind_rejects_non_string():
    with pytest.raises(TypeError):
        validate_event_kind(7)  # type: ignore[arg-type]


# --------------------------------------------------------------- UserDirectory


def _user(uid: str, handle: str, display: str | None = None) -> User:
    return User(user_id=uid, handle=handle, display_name=display or handle)


def test_user_directory_register_and_resolve():
    d = UserDirectory([_user("u1", "alice"), _user("u2", "bob")])
    user_a = d.get("u1")
    assert user_a is not None
    assert user_a.handle == "alice"
    user_by_handle = d.get_by_handle("ALICE")
    assert user_by_handle is not None
    assert user_by_handle.user_id == "u1"
    resolved = d.resolve_handles(["alice", "bob", "alice", "missing"])
    assert tuple(u.user_id for u in resolved) == ("u1", "u2")


def test_user_directory_rejects_duplicate_handle_for_different_user():
    d = UserDirectory([_user("u1", "alice")])
    with pytest.raises(ValueError):
        d.register(_user("u2", "alice"))


def test_user_directory_unknown_handle_is_silently_dropped():
    d = UserDirectory([_user("u1", "alice")])
    assert d.resolve_handles(["typo", "alice"]) == (d.get("u1"),)


def test_user_validation_rejects_invalid_handle():
    with pytest.raises(ValueError):
        User(user_id="u1", handle="!bad", display_name="x")
    with pytest.raises(ValueError):
        User(user_id="u1", handle="a", display_name="x")  # too short


# --------------------------------------------------------------- QuietHours


def test_quiet_hours_window_simple():
    qh = QuietHours(start_hour=22, end_hour=6)
    assert qh.is_quiet(datetime(2026, 5, 28, 23, 0, tzinfo=timezone.utc)) is True
    assert qh.is_quiet(datetime(2026, 5, 28, 3, 0, tzinfo=timezone.utc)) is True
    assert qh.is_quiet(datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)) is False


def test_quiet_hours_empty_window_is_never_quiet():
    qh = QuietHours(start_hour=0, end_hour=0)
    assert qh.is_quiet(datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)) is False


def test_quiet_hours_requires_tz_aware():
    qh = QuietHours(start_hour=22, end_hour=6)
    with pytest.raises(ValueError):
        qh.is_quiet(datetime(2026, 5, 28, 0, 0))  # naive


def test_quiet_hours_validates_bounds():
    with pytest.raises(ValueError):
        QuietHours(start_hour=24, end_hour=6)


# --------------------------------------------------------------- preferences


def test_preferences_default_opts_in_to_every_kind():
    p = NotificationPreferences(user_id="u1")
    for kind in EVENT_KINDS:
        assert p.wants(kind)


def test_preferences_reject_unknown_enabled_kind():
    with pytest.raises(ValueError):
        NotificationPreferences(user_id="u1", enabled_kinds=frozenset({"nope"}))


# --------------------------------------------------------------- Notifier


def _at(hour: int, day: int = 28) -> datetime:
    return datetime(2026, 5, day, hour, 0, tzinfo=timezone.utc)


def _basic_setup() -> tuple[Notifier, UserDirectory]:
    directory = UserDirectory([_user("u1", "alice"), _user("u2", "bob")])
    notifier = Notifier(directory=directory)
    return notifier, directory


def test_dispatch_delivers_to_targets():
    notifier, _ = _basic_setup()
    event = NotificationEvent(
        kind="work_item.assigned",
        actor="garry",
        target_user_ids=("u1",),
        occurred_at=_at(12),
        work_item_id="w1",
    )
    delivered = notifier.dispatch(event)
    assert len(delivered) == 1
    assert isinstance(delivered[0], Notification)
    assert delivered[0].user_id == "u1"
    assert delivered[0].kind == "work_item.assigned"
    assert delivered[0].work_item_id == "w1"
    assert notifier.dispatched == list(delivered)
    assert notifier.suppressed == []


def test_dispatch_suppresses_unknown_user():
    notifier, _ = _basic_setup()
    event = NotificationEvent(
        kind="work_item.assigned",
        actor="garry",
        target_user_ids=("missing",),
        occurred_at=_at(12),
        work_item_id="w1",
    )
    assert notifier.dispatch(event) == ()
    assert len(notifier.suppressed) == 1
    assert notifier.suppressed[0].reason == "disabled"


def test_dispatch_suppresses_self_actor():
    notifier, _ = _basic_setup()
    event = NotificationEvent(
        kind="work_item.mentioned",
        actor="alice",  # matches u1's handle
        target_user_ids=("u1",),
        occurred_at=_at(12),
        work_item_id="w1",
    )
    assert notifier.dispatch(event) == ()
    assert notifier.suppressed[0].reason == "self"


def test_dispatch_suppresses_disabled_kind():
    directory = UserDirectory([_user("u1", "alice")])
    notifier = Notifier(
        directory=directory,
        preferences={
            "u1": NotificationPreferences(
                user_id="u1",
                enabled_kinds=frozenset({"work_item.assigned"}),
            )
        },
    )
    event = NotificationEvent(
        kind="work_item.mentioned",
        actor="garry",
        target_user_ids=("u1",),
        occurred_at=_at(12),
        work_item_id="w1",
    )
    assert notifier.dispatch(event) == ()
    assert notifier.suppressed[0].reason == "disabled"


def test_dispatch_suppresses_during_quiet_hours():
    directory = UserDirectory([_user("u1", "alice")])
    notifier = Notifier(
        directory=directory,
        preferences={
            "u1": NotificationPreferences(
                user_id="u1",
                quiet_hours=QuietHours(start_hour=22, end_hour=6),
            )
        },
    )
    event = NotificationEvent(
        kind="work_item.assigned",
        actor="garry",
        target_user_ids=("u1",),
        occurred_at=_at(23),
        work_item_id="w1",
    )
    assert notifier.dispatch(event) == ()
    assert notifier.suppressed[0].reason == "quiet_hours"


def test_dispatch_rate_limited_after_capacity_exhausted():
    directory = UserDirectory([_user("u1", "alice")])
    notifier = Notifier(
        directory=directory,
        rate_limit=RateLimitConfig(capacity=3, refill_per_second=0.001),
    )
    when = _at(12)
    for i in range(5):
        notifier.dispatch(
            NotificationEvent(
                kind="work_item.assigned",
                actor="garry",
                target_user_ids=("u1",),
                occurred_at=when,
                work_item_id=f"w{i}",
            )
        )
    assert len(notifier.dispatched) == 3
    assert len(notifier.suppressed) == 2
    assert {s.reason for s in notifier.suppressed} == {"rate_limited"}


def test_dispatch_rate_limit_refills_over_time():
    directory = UserDirectory([_user("u1", "alice")])
    # 1 token/sec, capacity 1: second dispatch one second later succeeds.
    notifier = Notifier(
        directory=directory,
        rate_limit=RateLimitConfig(capacity=1, refill_per_second=1.0),
    )
    notifier.dispatch(
        NotificationEvent(
            kind="work_item.assigned",
            actor="garry",
            target_user_ids=("u1",),
            occurred_at=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
            work_item_id="w0",
        )
    )
    notifier.dispatch(
        NotificationEvent(
            kind="work_item.assigned",
            actor="garry",
            target_user_ids=("u1",),
            occurred_at=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
            work_item_id="w1",
        )
    )
    # 2 seconds later -> bucket refilled.
    notifier.dispatch(
        NotificationEvent(
            kind="work_item.assigned",
            actor="garry",
            target_user_ids=("u1",),
            occurred_at=datetime(2026, 5, 28, 12, 0, 2, tzinfo=timezone.utc),
            work_item_id="w2",
        )
    )
    assert [n.work_item_id for n in notifier.dispatched] == ["w0", "w2"]
    assert len(notifier.suppressed) == 1
    assert notifier.suppressed[0].reason == "rate_limited"


def test_dispatch_default_summary_is_deterministic():
    notifier, _ = _basic_setup()
    event = NotificationEvent(
        kind="work_item.assigned",
        actor="garry",
        target_user_ids=("u1",),
        occurred_at=_at(12),
        work_item_id="w1",
    )
    out = notifier.dispatch(event)[0]
    assert out.summary == "work_item.assigned by garry work_item=w1 to u1"
    assert out.occurred_at == "2026-05-28T12:00:00Z"


def test_dispatch_preserves_explicit_summary():
    notifier, _ = _basic_setup()
    event = NotificationEvent(
        kind="page.subscribed_update",
        actor="garry",
        target_user_ids=("u1",),
        occurred_at=_at(12),
        page_id="p1",
        summary="Roadmap doc updated",
    )
    out = notifier.dispatch(event)[0]
    assert out.summary == "Roadmap doc updated"


def test_notifier_page_subscriptions_round_trip():
    notifier, _ = _basic_setup()
    notifier.subscribe_page("u1", "p1")
    notifier.subscribe_page("u2", "p1")
    notifier.subscribe_page("u2", "p2")
    assert notifier.subscribers_for_page("p1") == ("u1", "u2")
    assert notifier.subscribers_for_page("p2") == ("u2",)
    notifier.unsubscribe_page("u2", "p1")
    assert notifier.subscribers_for_page("p1") == ("u1",)


def test_notification_to_dict_is_complete():
    notifier, _ = _basic_setup()
    event = NotificationEvent(
        kind="work_item.assigned",
        actor="garry",
        target_user_ids=("u1",),
        occurred_at=_at(12),
        work_item_id="w1",
    )
    n = notifier.dispatch(event)[0]
    d = n.to_dict()
    assert d["kind"] == "work_item.assigned"
    assert d["user_id"] == "u1"
    assert d["actor"] == "garry"
    assert d["work_item_id"] == "w1"
    assert d["page_id"] is None


def test_suppressed_to_dict_records_reason():
    notifier, _ = _basic_setup()
    event = NotificationEvent(
        kind="work_item.assigned",
        actor="garry",
        target_user_ids=("missing",),
        occurred_at=_at(12),
        work_item_id="w1",
    )
    notifier.dispatch(event)
    s = notifier.suppressed[0]
    assert isinstance(s, SuppressedNotification)
    assert s.to_dict()["reason"] == "disabled"


# --------------------------------------------------------------- builders


def test_build_assignment_event():
    e = build_assignment_event(
        actor="garry",
        assignee_user_id="u1",
        work_item_id="w1",
        occurred_at=_at(12),
    )
    assert e.kind == "work_item.assigned"
    assert e.target_user_ids == ("u1",)
    assert e.work_item_id == "w1"


def test_build_transition_event_payload_carries_state():
    e = build_transition_event(
        actor="garry",
        watcher_user_ids=("u1", "u2"),
        work_item_id="w1",
        from_state="todo",
        to_state="in_progress",
        occurred_at=_at(12),
    )
    assert e.kind == "work_item.transitioned"
    assert e.payload == {"from": "todo", "to": "in_progress"}


def test_build_mention_event_for_work_item_and_page():
    e1 = build_mention_event_for_work_item(
        actor="garry",
        mentioned_user_ids=("u1",),
        work_item_id="w1",
        comment_id="c1",
        occurred_at=_at(12),
    )
    e2 = build_mention_event_for_page(
        actor="garry",
        mentioned_user_ids=("u1",),
        page_id="p1",
        comment_id=None,
        occurred_at=_at(12),
    )
    assert e1.kind == "work_item.mentioned"
    assert e1.comment_id == "c1"
    assert e2.kind == "page.mentioned"
    assert e2.page_id == "p1"
    assert e2.comment_id is None


def test_build_page_subscription_event_preserves_summary():
    e = build_page_subscription_event(
        actor="garry",
        subscriber_user_ids=("u1",),
        page_id="p1",
        occurred_at=_at(12),
        summary="Doc bumped",
    )
    assert e.kind == "page.subscribed_update"
    assert e.summary == "Doc bumped"
