"""Tests for the Phase 6 FastAPI surface: /v1/search, /v1/ai_context, /v1/analytics/*."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from innerwork.app import create_app
from innerwork.domain_store import DomainStore


def _seed_store(path: Path) -> DomainStore:
    store = DomainStore(path=path)
    store.create_project(
        project_id="pp",
        key="PUB",
        name="Public",
        owner="eml",
        visibility="public",
    )
    store.create_project(
        project_id="pr",
        key="RES",
        name="Restricted",
        owner="eml",
        visibility="restricted",
        members=("alice",),
    )
    store.create_space(
        space_id="sp",
        key="SPUB",
        name="SPub",
        owner="eml",
        visibility="public",
    )
    store.create_work_item(
        work_item_id="wa",
        project_id="pp",
        title="Login bug",
        description="users cannot log in via SSO",
        assignee="eml",
    )
    store.create_work_item(
        work_item_id="wr",
        project_id="pr",
        title="Secret login work",
        description="restricted SSO planning",
        assignee="alice",
    )
    store.create_page(
        page_id="pg1",
        space_id="sp",
        title="SSO Runbook",
        body="how to debug SSO login flows",
        author="eml",
    )
    return store


def _make_client(tmp_path: Path) -> TestClient:
    db = tmp_path / "innerwork.db"
    # Pre-seed the database before constructing the app so the router sees the data.
    _seed_store(db)
    return TestClient(create_app(database_url=f"sqlite:///{db}"))


# ----------------------------------------------------------------- /v1/search/kinds


def test_search_kinds_endpoint(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get("/v1/search/kinds")
    assert r.status_code == 200
    assert r.json() == {"kinds": ["work_item", "page", "comment"]}


# ----------------------------------------------------------------- /v1/search


def test_search_query_returns_hits(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get("/v1/search", params={"q": "SSO login"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "hits" in body
    kinds = {h["kind"] for h in body["hits"]}
    assert kinds <= {"work_item", "page", "comment"}


def test_search_principal_header_filters_restricted(tmp_path: Path):
    client = _make_client(tmp_path)
    # Anonymous (no header) cannot see internal/restricted projects.
    r = client.get("/v1/search", params={"q": "login"})
    ids = {h["entity_id"] for h in r.json()["hits"]}
    assert "wr" not in ids
    # Public project work item is visible.
    assert "wa" in ids


def test_search_member_can_see_restricted(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get(
        "/v1/search",
        params={"q": "login"},
        headers={"X-Innerwork-Principal": "alice"},
    )
    assert r.status_code == 200
    ids = {h["entity_id"] for h in r.json()["hits"]}
    assert "wr" in ids


def test_search_bad_principal_header_returns_400(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get(
        "/v1/search",
        params={"q": "login"},
        headers={"X-Innerwork-Principal": "bad id"},
    )
    assert r.status_code == 400


def test_search_invalid_kinds_returns_400(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get("/v1/search", params={"q": "login", "kinds": ","})
    assert r.status_code == 400


def test_search_unknown_kind_returns_400(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get("/v1/search", params={"q": "login", "kinds": "garbage"})
    assert r.status_code == 400


def test_search_missing_query_returns_422(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get("/v1/search")
    assert r.status_code == 422


# ----------------------------------------------------------------- /v1/ai_context


def test_ai_context_query_only(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.post("/v1/ai_context", json={"query": "SSO login"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "entries" in body
    assert body["anchor_kind"] is None


def test_ai_context_anchor_mode(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.post(
        "/v1/ai_context",
        json={"anchor_kind": "work_item", "anchor_id": "wa"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["anchor_id"] == "wa"
    assert body["entries"][0]["entity_id"] == "wa"


def test_ai_context_anchor_missing_returns_404_or_400(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.post(
        "/v1/ai_context",
        json={"anchor_kind": "work_item", "anchor_id": "no-such-id"},
    )
    # ai_context normalizes "missing anchor" to AIContextError (400). The
    # endpoint also has a 404 path for WorkItemNotFoundError; both are valid
    # negative responses for callers.
    assert r.status_code in (400, 404)


def test_ai_context_invalid_args_returns_400(tmp_path: Path):
    client = _make_client(tmp_path)
    # Neither query nor anchor.
    r = client.post("/v1/ai_context", json={})
    assert r.status_code == 400


def test_ai_context_bad_principal_returns_400(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.post(
        "/v1/ai_context",
        json={"query": "login"},
        headers={"X-Innerwork-Principal": "bad id"},
    )
    assert r.status_code == 400


def test_ai_context_restricted_anchor_denied_for_anonymous(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.post(
        "/v1/ai_context",
        json={"anchor_kind": "work_item", "anchor_id": "wr"},
    )
    assert r.status_code == 400  # AIContextError "not readable"


def test_ai_context_restricted_anchor_allowed_for_member(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.post(
        "/v1/ai_context",
        json={"anchor_kind": "work_item", "anchor_id": "wr"},
        headers={"X-Innerwork-Principal": "alice"},
    )
    assert r.status_code == 200, r.text


# ----------------------------------------------------------------- /v1/analytics/*


def test_analytics_domain_anonymous_sees_public_only(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get("/v1/analytics/domain")
    assert r.status_code == 200, r.text
    body = r.json()
    keys = {p["key"] for p in body["projects"]}
    assert keys == {"PUB"}


def test_analytics_domain_member_sees_restricted(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get(
        "/v1/analytics/domain",
        headers={"X-Innerwork-Principal": "alice"},
    )
    keys = {p["key"] for p in r.json()["projects"]}
    assert "RES" in keys


def test_analytics_project_endpoint(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get("/v1/analytics/projects/pp")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == "pp"
    assert body["work_item_count"] == 1


def test_analytics_project_restricted_denied_anon(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get("/v1/analytics/projects/pr")
    assert r.status_code == 404


def test_analytics_project_missing_returns_404(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get("/v1/analytics/projects/nope")
    assert r.status_code == 404


def test_analytics_space_endpoint(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get("/v1/analytics/spaces/sp")
    assert r.status_code == 200
    body = r.json()
    assert body["space_id"] == "sp"


def test_analytics_bad_principal_returns_400(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.get(
        "/v1/analytics/domain",
        headers={"X-Innerwork-Principal": "bad id"},
    )
    assert r.status_code == 400
