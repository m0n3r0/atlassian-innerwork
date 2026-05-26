"""Tests for the /v1/ work-graph FastAPI surface."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from innerwork.app import create_app


def _make_client(tmp_path: Path) -> TestClient:
    db = tmp_path / "innerwork.db"
    return TestClient(create_app(database_url=f"sqlite:///{db}"))


def _idem_headers() -> dict[str, str]:
    return {"X-Idempotency-Key": uuid.uuid4().hex}


def test_workflow_endpoint_returns_default_workflow(tmp_path: Path):
    client = _make_client(tmp_path)
    body = client.get("/v1/workflow").json()
    assert body["initial_state"] == "todo"
    assert "todo" in body["states"]
    pairs = {(t["from_state"], t["to_state"]) for t in body["transitions"]}
    assert ("todo", "in_progress") in pairs
    assert ("done", "in_progress") in pairs  # reopen


def test_project_and_work_item_lifecycle_end_to_end(tmp_path: Path):
    client = _make_client(tmp_path)

    created = client.post(
        "/v1/projects",
        json={"key": "ENG", "name": "Engineering", "owner": "eml"},
        headers=_idem_headers(),
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["key"] == "ENG"
    project_id = project["project_id"]

    listed = client.get("/v1/projects").json()
    assert [p["key"] for p in listed["projects"]] == ["ENG"]

    wi = client.post(
        "/v1/work_items",
        json={"project_id": project_id, "title": "Set up CI", "description": "with pytest"},
        headers=_idem_headers(),
    )
    assert wi.status_code == 201, wi.text
    item = wi.json()
    assert item["key"] == "ENG-1"
    assert item["state"] == "todo"
    wid = item["work_item_id"]

    # Filtered list
    by_project = client.get(f"/v1/projects/{project_id}/work_items").json()
    assert [i["key"] for i in by_project["work_items"]] == ["ENG-1"]

    # Valid transition
    transitioned = client.post(
        f"/v1/work_items/{wid}/transitions",
        json={"to_state": "in_progress", "actor": "eml"},
        headers=_idem_headers(),
    )
    assert transitioned.status_code == 201, transitioned.text
    assert transitioned.json()["work_item"]["state"] == "in_progress"

    history = client.get(f"/v1/work_items/{wid}/transitions").json()
    assert [(t["from_state"], t["to_state"]) for t in history["transitions"]] == [
        ("todo", "in_progress"),
    ]


def test_create_project_rejects_duplicate_key_with_409(tmp_path: Path):
    client = _make_client(tmp_path)
    payload = {"key": "ENG", "name": "Engineering", "owner": "eml"}
    assert client.post("/v1/projects", json=payload, headers=_idem_headers()).status_code == 201
    second = client.post("/v1/projects", json=payload, headers=_idem_headers())
    assert second.status_code == 409


def test_create_project_rejects_invalid_key_with_400(tmp_path: Path):
    client = _make_client(tmp_path)
    # lowercase key violates the validate_project_key rule
    bad = client.post(
        "/v1/projects",
        json={"key": "eng", "name": "Engineering", "owner": "eml"},
        headers=_idem_headers(),
    )
    assert bad.status_code == 400


def test_invalid_transition_returns_409(tmp_path: Path):
    client = _make_client(tmp_path)
    project = client.post(
        "/v1/projects",
        json={"key": "ENG", "name": "Engineering", "owner": "eml"},
        headers=_idem_headers(),
    ).json()
    item = client.post(
        "/v1/work_items",
        json={"project_id": project["project_id"], "title": "Skip-state attempt"},
        headers=_idem_headers(),
    ).json()
    # todo -> done is not allowed by the default workflow
    response = client.post(
        f"/v1/work_items/{item['work_item_id']}/transitions",
        json={"to_state": "done", "actor": "eml"},
        headers=_idem_headers(),
    )
    assert response.status_code == 409
    # Item must remain in todo after the rejection.
    refetched = client.get(f"/v1/work_items/{item['work_item_id']}").json()
    assert refetched["state"] == "todo"


def test_unknown_state_filter_returns_400(tmp_path: Path):
    client = _make_client(tmp_path)
    assert client.get("/v1/work_items", params={"state": "bogus"}).status_code == 400


def test_missing_project_create_work_item_returns_404(tmp_path: Path):
    client = _make_client(tmp_path)
    response = client.post(
        "/v1/work_items",
        json={"project_id": "nope", "title": "x"},
        headers=_idem_headers(),
    )
    assert response.status_code == 404


def test_domain_state_persists_across_app_restarts(tmp_path: Path):
    db = tmp_path / "innerwork.db"
    url = f"sqlite:///{db}"
    first = TestClient(create_app(database_url=url))
    project = first.post(
        "/v1/projects",
        json={"key": "ENG", "name": "Engineering", "owner": "eml"},
        headers=_idem_headers(),
    ).json()
    item = first.post(
        "/v1/work_items",
        json={"project_id": project["project_id"], "title": "Set up CI"},
        headers=_idem_headers(),
    ).json()
    first.post(
        f"/v1/work_items/{item['work_item_id']}/transitions",
        json={"to_state": "in_progress", "actor": "eml"},
        headers=_idem_headers(),
    )

    second = TestClient(create_app(database_url=url))
    reopened = second.get(f"/v1/work_items/{item['work_item_id']}").json()
    assert reopened["state"] == "in_progress"
    assert reopened["key"] == "ENG-1"
    listing = second.get("/v1/projects").json()
    assert [p["key"] for p in listing["projects"]] == ["ENG"]


def test_openapi_advertises_v1_endpoints(tmp_path: Path):
    client = _make_client(tmp_path)
    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"].keys())
    assert "/v1/projects" in paths
    assert "/v1/work_items" in paths
    assert "/v1/work_items/{work_item_id}/transitions" in paths
    assert "/v1/workflow" in paths


def test_broker_endpoints_still_work_with_domain_router(tmp_path: Path):
    """Regression: adding /v1/ must not break the v2 broker surface."""

    client = _make_client(tmp_path)
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/v2/catalog").json()["services"][0]["id"] == "innerwork-edge-service"


def test_v1_mutations_require_idempotency_key(tmp_path: Path):
    client = _make_client(tmp_path)
    response = client.post(
        "/v1/projects",
        json={"key": "ENG", "name": "Engineering", "owner": "eml"},
    )
    assert response.status_code == 428


def test_v1_idempotent_replay_returns_same_response_without_side_effects(tmp_path: Path):
    client = _make_client(tmp_path)
    headers = _idem_headers()
    payload = {"key": "ENG", "name": "Engineering", "owner": "eml"}

    first = client.post("/v1/projects", json=payload, headers=headers)
    assert first.status_code == 201
    second = client.post("/v1/projects", json=payload, headers=headers)
    assert second.status_code == 201
    assert first.json() == second.json()
    listing = client.get("/v1/projects").json()
    assert len(listing["projects"]) == 1


def test_v1_idempotency_key_conflict_for_different_body_returns_409(tmp_path: Path):
    client = _make_client(tmp_path)
    headers = _idem_headers()
    assert (
        client.post(
            "/v1/projects",
            json={"key": "ENG", "name": "Engineering", "owner": "eml"},
            headers=headers,
        ).status_code
        == 201
    )
    response = client.post(
        "/v1/projects",
        json={"key": "DOC", "name": "Docs", "owner": "eml"},
        headers=headers,
    )
    assert response.status_code == 409
