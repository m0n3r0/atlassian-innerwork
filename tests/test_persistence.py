from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from innerwork.app import create_app

PAYLOAD = {
    "service_id": "ignored-by-path",
    "owner": "jira-platform",
    "product_family": "teamwork_core",
    "edge_profile": "web_app_api",
    "domains": ["Jira.Example.Com"],
    "routes": [{"prefix": "/", "backend": {"name": "jira", "port": 8080}}],
    "features": ["rate_limit"],
}

CONFLUENCE_PAYLOAD = {
    "service_id": "ignored-by-path",
    "owner": "confluence-platform",
    "product_family": "teamwork_core",
    "edge_profile": "web_app_api",
    "domains": ["confluence.example.com"],
    "routes": [{"prefix": "/", "backend": {"name": "confluence", "port": 8090}}],
    "features": [],
}


def _put(client: TestClient, instance_id: str, payload: dict[str, object], key: str):
    return client.put(
        f"/v2/service_instances/{instance_id}",
        json=payload,
        headers={"X-Idempotency-Key": key},
    )


def test_app_persists_service_registry_across_restarts(tmp_path: Path):
    state_file = tmp_path / "innerwork-state.json"
    first_client = TestClient(create_app(state_path=state_file))

    accepted = _put(first_client, "jira-web", PAYLOAD, "persistence-key-000001")

    assert accepted.status_code == 202
    assert accepted.json()["state"] == "succeeded"
    assert state_file.exists()

    restarted_client = TestClient(create_app(state_path=state_file))

    service = restarted_client.get("/v2/service_instances/jira-web")
    assert service.status_code == 200
    assert service.json()["domains"] == ["jira.example.com"]
    snapshot = restarted_client.get("/v2/control-plane/snapshot").json()
    assert snapshot["clusters"] == [{"name": "jira", "port": 8080}]


def test_failed_provision_does_not_overwrite_persisted_state(tmp_path: Path):
    state_file = tmp_path / "innerwork-state.json"
    first_client = TestClient(create_app(state_path=state_file))
    result = _put(first_client, "jira-web", PAYLOAD, "persistence-key-000001").json()
    assert result["state"] == "succeeded"
    original = state_file.read_text(encoding="utf-8")

    conflict = dict(CONFLUENCE_PAYLOAD)
    conflict["domains"] = ["jira.example.com"]
    response = _put(first_client, "confluence-web", conflict, "persistence-key-000003")

    assert response.status_code == 202
    assert response.json()["state"] == "failed"
    assert state_file.read_text(encoding="utf-8") == original
    restarted_client = TestClient(create_app(state_path=state_file))
    assert restarted_client.get("/v2/service_instances/confluence-web").status_code == 404


def test_appends_successful_provisions_to_persisted_state(tmp_path: Path):
    state_file = tmp_path / "innerwork-state.json"
    first_client = TestClient(create_app(state_path=state_file))
    result = _put(first_client, "jira-web", PAYLOAD, "persistence-key-000001").json()
    assert result["state"] == "succeeded"
    assert (
        _put(
            first_client,
            "confluence-web",
            CONFLUENCE_PAYLOAD,
            "persistence-key-000002",
        ).json()["state"]
        == "succeeded"
    )

    restarted_client = TestClient(create_app(state_path=state_file))

    listed = restarted_client.get("/v2/service_instances").json()["services"]
    assert [service["service_id"] for service in listed] == ["confluence-web", "jira-web"]
    snapshot = restarted_client.get("/v2/control-plane/snapshot").json()
    assert snapshot["clusters"] == [
        {"name": "confluence", "port": 8090},
        {"name": "jira", "port": 8080},
    ]
