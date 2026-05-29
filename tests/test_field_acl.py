"""Tests for the phase 7 field-level ACL hook."""

from __future__ import annotations

from innerwork.field_acl import DEFAULT_POLICY, PRIVACY_FIELDS, FieldACL, redact_for


def test_system_actor_bypasses_acl() -> None:
    acl = FieldACL()
    assert acl.is_readable("system", "User", "email")
    assert acl.is_writable("system", "User", "email")


def test_default_allow_for_unknown_field() -> None:
    acl = FieldACL()
    assert acl.is_readable("anonymous", "Unknown", "whatever")
    assert acl.is_writable("anonymous", "Unknown", "whatever")


def test_email_redacted_for_user_actor() -> None:
    payload = {"email": "alice@example.com", "display_name": "Alice"}
    out = redact_for("user", "User", payload)
    assert out["email"] == "[redacted-email]"
    assert out["display_name"] == "Alice"


def test_audit_actor_redacted_for_user_actor() -> None:
    payload = {"actor": "alice", "surface": "jira_workflow"}
    out = redact_for("user", "AuditEvent", payload)
    assert out["actor"] == "[redacted-actor]"
    assert out["surface"] == "jira_workflow"


def test_service_actor_can_read_email() -> None:
    acl = FieldACL()
    assert acl.is_readable("service", "User", "email")


def test_writable_truth_table() -> None:
    acl = FieldACL()
    # AuditEvent.actor only writable by system
    assert acl.is_writable("system", "AuditEvent", "actor")
    assert not acl.is_writable("user", "AuditEvent", "actor")
    assert not acl.is_writable("service", "AuditEvent", "actor")


def test_privacy_fields_match_policy_table() -> None:
    """Adding a privacy-relevant field requires updating DEFAULT_POLICY."""
    assert set(PRIVACY_FIELDS) == set(DEFAULT_POLICY.keys())


def test_redact_does_not_mutate_input() -> None:
    payload = {"email": "x@y", "display_name": "x"}
    original = dict(payload)
    redact_for("user", "User", payload)
    assert payload == original
