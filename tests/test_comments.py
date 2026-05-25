"""Tests for the comments domain (Phase B slice 3)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from innerwork.app import create_app
from innerwork.comments import (
    PageComment,
    WorkItemComment,
    validate_author,
    validate_comment_body,
)
from innerwork.domain_store import (
    CommentNotFoundError,
    DomainStore,
    PageNotFoundError,
    WorkItemNotFoundError,
)

# --------------------------------------------------------------- pure domain


def test_validate_comment_body_rejects_blank_and_too_long():
    with pytest.raises(ValueError):
        validate_comment_body("")
    with pytest.raises(ValueError):
        validate_comment_body("   \n  ")
    with pytest.raises(ValueError):
        validate_comment_body("x" * 10_001)
    assert validate_comment_body("  hello  ") == "hello"


def test_validate_author_rejects_blank():
    with pytest.raises(ValueError):
        validate_author("")
    assert validate_author(" eml ") == "eml"


def test_work_item_comment_to_dict_is_deterministic():
    comment = WorkItemComment(
        comment_id="c1",
        work_item_id="w1",
        author="eml",
        body="hi",
        created_at="2026-05-26T00:00:00Z",
    )
    assert comment.to_dict() == {
        "comment_id": "c1",
        "work_item_id": "w1",
        "author": "eml",
        "body": "hi",
        "created_at": "2026-05-26T00:00:00Z",
    }


def test_page_comment_to_dict_is_deterministic():
    comment = PageComment(
        comment_id="c1",
        page_id="p1",
        author="eml",
        body="hi",
        created_at="2026-05-26T00:00:00Z",
    )
    assert comment.to_dict()["page_id"] == "p1"


# --------------------------------------------------------------- store


def _store_with_work_item_and_page(tmp_path: Path) -> tuple[DomainStore, str, str]:
    store = DomainStore(tmp_path / "innerwork.db")
    store.create_project(project_id="p1", key="ENG", name="Eng", owner="eml")
    item = store.create_work_item(
        work_item_id="w1", project_id="p1", title="t", description="", assignee=""
    )
    store.create_space(space_id="s1", key="DOCS", name="Docs", owner="eml")
    page, _ = store.create_page(page_id="pg1", space_id="s1", title="t", body="", author="eml")
    return store, item.work_item_id, page.page_id


def test_work_item_comments_create_list_get(tmp_path: Path):
    store, wid, _ = _store_with_work_item_and_page(tmp_path)
    c = store.create_work_item_comment(
        comment_id="c1", work_item_id=wid, author="eml", body="first"
    )
    assert store.get_work_item_comment("c1") == c
    listed = store.list_work_item_comments(wid)
    assert [x.comment_id for x in listed] == ["c1"]


def test_work_item_comment_missing_work_item_raises(tmp_path: Path):
    store = DomainStore(tmp_path / "innerwork.db")
    with pytest.raises(WorkItemNotFoundError):
        store.create_work_item_comment(
            comment_id="c1", work_item_id="ghost", author="eml", body="hi"
        )


def test_page_comments_create_list_get(tmp_path: Path):
    store, _, pid = _store_with_work_item_and_page(tmp_path)
    c = store.create_page_comment(comment_id="c1", page_id=pid, author="eml", body="first")
    assert store.get_page_comment("c1") == c
    assert [x.comment_id for x in store.list_page_comments(pid)] == ["c1"]


def test_page_comment_missing_page_raises(tmp_path: Path):
    store = DomainStore(tmp_path / "innerwork.db")
    with pytest.raises(PageNotFoundError):
        store.create_page_comment(comment_id="c1", page_id="ghost", author="eml", body="hi")


def test_get_unknown_comment_raises_comment_not_found(tmp_path: Path):
    store = DomainStore(tmp_path / "innerwork.db")
    with pytest.raises(CommentNotFoundError):
        store.get_work_item_comment("nope")
    with pytest.raises(CommentNotFoundError):
        store.get_page_comment("nope")


def test_comments_persist_across_store_reopen(tmp_path: Path):
    store, wid, pid = _store_with_work_item_and_page(tmp_path)
    store.create_work_item_comment(comment_id="c1", work_item_id=wid, author="eml", body="first")
    store.create_page_comment(comment_id="c2", page_id=pid, author="eml", body="second")
    reopened = DomainStore(tmp_path / "innerwork.db")
    assert reopened.get_work_item_comment("c1").body == "first"
    assert reopened.get_page_comment("c2").body == "second"


# --------------------------------------------------------------- API


class _IdemClient(TestClient):
    def request(self, method, url, *args, headers=None, **kwargs):  # type: ignore[override]
        if method.upper() in {"POST", "PUT", "DELETE", "PATCH"} and str(url).startswith("/v1/"):
            headers = dict(headers or {})
            headers.setdefault("X-Idempotency-Key", uuid.uuid4().hex)
        return super().request(method, url, *args, headers=headers, **kwargs)


def _client(tmp_path: Path) -> _IdemClient:
    return _IdemClient(create_app(database_url=f"sqlite:///{tmp_path / 'i.db'}"))


def _seed(client: _IdemClient) -> tuple[str, str]:
    project = client.post("/v1/projects", json={"key": "ENG", "name": "Eng", "owner": "eml"}).json()
    item = client.post(
        "/v1/work_items",
        json={"project_id": project["project_id"], "title": "t"},
    ).json()
    space = client.post("/v1/spaces", json={"key": "DOCS", "name": "Docs", "owner": "eml"}).json()
    page = client.post(
        "/v1/pages",
        json={
            "space_id": space["space_id"],
            "title": "t",
            "body": "",
            "author": "eml",
        },
    ).json()["page"]
    return item["work_item_id"], page["page_id"]


def test_work_item_comment_create_list_get_via_api(tmp_path: Path):
    client = _client(tmp_path)
    wid, _ = _seed(client)

    created = client.post(
        f"/v1/work_items/{wid}/comments",
        json={"author": "eml", "body": "first"},
    )
    assert created.status_code == 201, created.text
    cid = created.json()["comment_id"]

    listed = client.get(f"/v1/work_items/{wid}/comments").json()["comments"]
    assert [c["comment_id"] for c in listed] == [cid]

    fetched = client.get(f"/v1/work_item_comments/{cid}").json()
    assert fetched["body"] == "first"


def test_page_comment_create_list_get_via_api(tmp_path: Path):
    client = _client(tmp_path)
    _, pid = _seed(client)
    created = client.post(
        f"/v1/pages/{pid}/comments",
        json={"author": "eml", "body": "first"},
    )
    assert created.status_code == 201, created.text
    cid = created.json()["comment_id"]
    listed = client.get(f"/v1/pages/{pid}/comments").json()["comments"]
    assert [c["comment_id"] for c in listed] == [cid]


def test_comment_create_missing_parent_returns_404(tmp_path: Path):
    client = _client(tmp_path)
    r1 = client.post(
        "/v1/work_items/ghost/comments",
        json={"author": "eml", "body": "hi"},
    )
    assert r1.status_code == 404
    r2 = client.post(
        "/v1/pages/ghost/comments",
        json={"author": "eml", "body": "hi"},
    )
    assert r2.status_code == 404


def test_comment_create_requires_idempotency_key(tmp_path: Path):
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'i.db'}"))
    # Seed with idempotency keys
    seed = _IdemClient(client.app)
    wid, _ = _seed(seed)
    response = client.post(
        f"/v1/work_items/{wid}/comments",
        json={"author": "eml", "body": "first"},
    )
    assert response.status_code == 428


def test_comment_replay_is_idempotent(tmp_path: Path):
    client = _client(tmp_path)
    wid, _ = _seed(client)
    headers = {"X-Idempotency-Key": uuid.uuid4().hex}
    payload = {"author": "eml", "body": "first"}
    first = client.post(f"/v1/work_items/{wid}/comments", json=payload, headers=headers)
    second = client.post(f"/v1/work_items/{wid}/comments", json=payload, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["comment_id"] == second.json()["comment_id"]
    listed = client.get(f"/v1/work_items/{wid}/comments").json()["comments"]
    assert len(listed) == 1


def test_comment_replay_with_different_body_returns_409(tmp_path: Path):
    client = _client(tmp_path)
    wid, _ = _seed(client)
    headers = {"X-Idempotency-Key": uuid.uuid4().hex}
    assert (
        client.post(
            f"/v1/work_items/{wid}/comments",
            json={"author": "eml", "body": "first"},
            headers=headers,
        ).status_code
        == 201
    )
    conflict = client.post(
        f"/v1/work_items/{wid}/comments",
        json={"author": "eml", "body": "second"},
        headers=headers,
    )
    assert conflict.status_code == 409
