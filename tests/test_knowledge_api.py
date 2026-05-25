"""Tests for the /v1/ knowledge-graph FastAPI surface (Phase B slice 2)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from innerwork.app import create_app


class _IdemClient(TestClient):
    """TestClient that auto-injects X-Idempotency-Key on mutating /v1/ calls."""

    def request(self, method, url, *args, headers=None, **kwargs):  # type: ignore[override]
        if method.upper() in {"POST", "PUT", "DELETE", "PATCH"} and str(url).startswith("/v1/"):
            headers = dict(headers or {})
            headers.setdefault("X-Idempotency-Key", uuid.uuid4().hex)
        return super().request(method, url, *args, headers=headers, **kwargs)


def _make_client(tmp_path: Path) -> _IdemClient:
    db = tmp_path / "innerwork.db"
    return _IdemClient(create_app(database_url=f"sqlite:///{db}"))


def test_space_create_list_get(tmp_path: Path):
    client = _make_client(tmp_path)

    created = client.post(
        "/v1/spaces",
        json={"key": "DOCS", "name": "Docs", "owner": "eml"},
    )
    assert created.status_code == 201, created.text
    space = created.json()
    assert space["key"] == "DOCS"

    listed = client.get("/v1/spaces").json()
    assert [s["key"] for s in listed["spaces"]] == ["DOCS"]

    fetched = client.get(f"/v1/spaces/{space['space_id']}").json()
    assert fetched["key"] == "DOCS"


def test_duplicate_space_key_returns_409(tmp_path: Path):
    client = _make_client(tmp_path)
    payload = {"key": "DOCS", "name": "Docs", "owner": "eml"}
    assert client.post("/v1/spaces", json=payload).status_code == 201
    assert client.post("/v1/spaces", json=payload).status_code == 409


def test_invalid_space_key_returns_400(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.post(
        "/v1/spaces",
        json={"key": "docs", "name": "Docs", "owner": "eml"},
    )
    assert r.status_code == 400


def test_page_lifecycle_create_update_versions(tmp_path: Path):
    client = _make_client(tmp_path)
    space = client.post(
        "/v1/spaces",
        json={"key": "DOCS", "name": "Docs", "owner": "eml"},
    ).json()
    space_id = space["space_id"]

    create = client.post(
        "/v1/pages",
        json={
            "space_id": space_id,
            "title": "Hello",
            "body": "World",
            "author": "eml",
        },
    )
    assert create.status_code == 201, create.text
    payload = create.json()
    assert payload["page"]["current_version"] == 1
    assert payload["version"]["version_number"] == 1
    page_id = payload["page"]["page_id"]

    upd = client.put(
        f"/v1/pages/{page_id}",
        json={"title": "Hello v2", "body": "World v2", "author": "eml"},
    )
    assert upd.status_code == 201, upd.text
    assert upd.json()["page"]["current_version"] == 2

    versions = client.get(f"/v1/pages/{page_id}/versions").json()["versions"]
    assert [v["version_number"] for v in versions] == [1, 2]

    v1 = client.get(f"/v1/pages/{page_id}/versions/1").json()
    assert v1["title"] == "Hello"

    listed_pages = client.get(f"/v1/spaces/{space_id}/pages").json()["pages"]
    assert [p["page_id"] for p in listed_pages] == [page_id]


def test_page_into_missing_space_returns_404(tmp_path: Path):
    client = _make_client(tmp_path)
    r = client.post(
        "/v1/pages",
        json={
            "space_id": "ghost",
            "title": "t",
            "body": "",
            "author": "eml",
        },
    )
    assert r.status_code == 404


def test_link_lifecycle_create_list_delete(tmp_path: Path):
    client = _make_client(tmp_path)
    project = client.post(
        "/v1/projects",
        json={"key": "ENG", "name": "Eng", "owner": "eml"},
    ).json()
    item = client.post(
        "/v1/work_items",
        json={"project_id": project["project_id"], "title": "Set up CI"},
    ).json()
    space = client.post(
        "/v1/spaces",
        json={"key": "DOCS", "name": "Docs", "owner": "eml"},
    ).json()
    page = client.post(
        "/v1/pages",
        json={
            "space_id": space["space_id"],
            "title": "CI design",
            "body": "",
            "author": "eml",
        },
    ).json()["page"]

    # kinds endpoint
    kinds = client.get("/v1/links/kinds").json()
    assert "documents" in kinds["kinds"]

    create = client.post(
        "/v1/links",
        json={
            "work_item_id": item["work_item_id"],
            "page_id": page["page_id"],
            "kind": "documents",
            "created_by": "eml",
        },
    )
    assert create.status_code == 201, create.text
    link = create.json()

    # duplicate triple => 409
    dup = client.post(
        "/v1/links",
        json={
            "work_item_id": item["work_item_id"],
            "page_id": page["page_id"],
            "kind": "documents",
            "created_by": "eml",
        },
    )
    assert dup.status_code == 409

    # invalid kind => 400
    bad = client.post(
        "/v1/links",
        json={
            "work_item_id": item["work_item_id"],
            "page_id": page["page_id"],
            "kind": "bogus",
            "created_by": "eml",
        },
    )
    assert bad.status_code == 400

    # listings
    by_wi = client.get(f"/v1/work_items/{item['work_item_id']}/links").json()["links"]
    by_page = client.get(f"/v1/pages/{page['page_id']}/links").json()["links"]
    assert [link_row["link_id"] for link_row in by_wi] == [link["link_id"]]
    assert [link_row["link_id"] for link_row in by_page] == [link["link_id"]]

    # GET single
    assert client.get(f"/v1/links/{link['link_id']}").json()["kind"] == "documents"

    # DELETE
    deleted = client.delete(f"/v1/links/{link['link_id']}")
    assert deleted.status_code == 204
    assert client.get(f"/v1/links/{link['link_id']}").status_code == 404


def test_link_missing_endpoint_returns_404(tmp_path: Path):
    client = _make_client(tmp_path)
    space = client.post(
        "/v1/spaces",
        json={"key": "DOCS", "name": "Docs", "owner": "eml"},
    ).json()
    page = client.post(
        "/v1/pages",
        json={
            "space_id": space["space_id"],
            "title": "t",
            "body": "",
            "author": "eml",
        },
    ).json()["page"]

    r = client.post(
        "/v1/links",
        json={
            "work_item_id": "ghost",
            "page_id": page["page_id"],
            "kind": "documents",
            "created_by": "eml",
        },
    )
    assert r.status_code == 404
