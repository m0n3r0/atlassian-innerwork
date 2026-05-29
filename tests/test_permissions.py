"""Tests for the Phase 6 visibility/permission model."""

from __future__ import annotations

import pytest

from innerwork.permissions import (
    DEFAULT_VISIBILITY,
    VISIBILITIES,
    AnonymousPrincipal,
    Principal,
    can_read,
    normalize_members,
    parse_principal_header,
    validate_visibility,
)

# ----------------------------------------------------------------- constants


def test_visibility_constants():
    assert VISIBILITIES == ("public", "internal", "restricted")
    assert DEFAULT_VISIBILITY == "internal"


def test_validate_visibility_accepts_known_tags():
    for tag in VISIBILITIES:
        assert validate_visibility(tag) == tag


def test_validate_visibility_rejects_unknown():
    with pytest.raises(ValueError):
        validate_visibility("secret")


# ----------------------------------------------------------------- members


def test_normalize_members_dedups_sorts_strips():
    assert normalize_members(["bob", "alice", "bob", "  alice  ", ""]) == (
        "alice",
        "bob",
    )


def test_normalize_members_none_returns_empty_tuple():
    assert normalize_members(None) == ()


def test_normalize_members_type_error_on_non_string():
    with pytest.raises(TypeError):
        normalize_members(["ok", 5])  # type: ignore[list-item]


# ----------------------------------------------------------------- Principal


def test_principal_post_init_validates_groups():
    Principal(id="eml", groups=("a", "b"))
    with pytest.raises(TypeError):
        Principal(id="eml", groups=["a", "b"])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Principal(id="eml", groups=("",))


def test_principal_is_anonymous_property():
    assert AnonymousPrincipal.is_anonymous is True
    assert Principal(id="eml").is_anonymous is False
    assert Principal(id="   ").is_anonymous is True


def test_principal_to_dict():
    p = Principal(id="eml", groups=("eng",))
    assert p.to_dict() == {"id": "eml", "groups": ["eng"]}


# ----------------------------------------------------------------- can_read matrix


def test_can_read_public_always_true():
    assert can_read(AnonymousPrincipal, visibility="public") is True
    assert can_read(Principal(id="eml"), visibility="public", members=("nobody",)) is True


def test_can_read_internal_denies_anonymous():
    assert can_read(AnonymousPrincipal, visibility="internal") is False
    assert can_read(Principal(id="eml"), visibility="internal") is True


def test_can_read_restricted_member_id_grants():
    assert can_read(
        Principal(id="eml"),
        visibility="restricted",
        members=("eml", "alice"),
    ) is True


def test_can_read_restricted_group_match_grants():
    assert can_read(
        Principal(id="eml", groups=("eng", "sec")),
        visibility="restricted",
        members=("sec",),
    ) is True


def test_can_read_restricted_no_match_denies():
    assert can_read(
        Principal(id="eml", groups=("eng",)),
        visibility="restricted",
        members=("sec",),
    ) is False


def test_can_read_restricted_anonymous_denied_even_if_listed():
    # anonymous principal has id="" which can never appear in a real members tuple.
    assert can_read(AnonymousPrincipal, visibility="restricted", members=("",)) is False


def test_can_read_unknown_visibility_returns_false():
    assert can_read(Principal(id="eml"), visibility="garbage") is False


# ------------------------------------------------------ parse_principal_header


def test_parse_principal_header_anonymous_when_none():
    assert parse_principal_header(None) == AnonymousPrincipal


def test_parse_principal_header_anonymous_when_blank():
    assert parse_principal_header("   ") == AnonymousPrincipal


def test_parse_principal_header_simple_id():
    assert parse_principal_header("eml") == Principal(id="eml", groups=())


def test_parse_principal_header_with_groups():
    p = parse_principal_header("eml;eng,sec")
    assert p.id == "eml"
    assert p.groups == ("eng", "sec")


def test_parse_principal_header_strips_whitespace_around_tokens():
    p = parse_principal_header("  eml ;  eng , sec  ")
    assert p.id == "eml"
    assert p.groups == ("eng", "sec")


def test_parse_principal_header_empty_id_with_groups_raises():
    with pytest.raises(ValueError):
        parse_principal_header(";eng,sec")


def test_parse_principal_header_whitespace_in_id_raises():
    with pytest.raises(ValueError):
        parse_principal_header("foo bar")


def test_parse_principal_header_whitespace_inside_group_raises():
    with pytest.raises(ValueError):
        parse_principal_header("eml;foo bar")


def test_parse_principal_header_skips_blank_group_tokens():
    p = parse_principal_header("eml;,eng,,sec,")
    assert p.groups == ("eng", "sec")


def test_parse_principal_header_type_error_on_non_string():
    with pytest.raises(TypeError):
        parse_principal_header(42)  # type: ignore[arg-type]
