from fastapi.testclient import TestClient

from innerwork.app import create_app


def test_create_app_is_reexported_from_innerwork_app_module():
    assert callable(create_app)


def test_live_app_health_catalog_and_openapi_are_available():
    client = TestClient(create_app())

    assert client.get("/healthz").json()["status"] == "ok"
    catalog = client.get("/v2/catalog").json()
    assert catalog["services"][0]["id"] == "innerwork-edge-service"
    openapi = client.get("/openapi.json").json()
    assert openapi["info"]["title"] == "Atlassian Innerwork"


def test_live_app_provisions_service_and_renders_snapshot():
    client = TestClient(create_app())
    payload = {
        "service_id": "ignored-by-path",
        "owner": "jira-platform",
        "product_family": "teamwork_core",
        "edge_profile": "web_app_api",
        "domains": ["Jira.Example.Com"],
        "routes": [{"prefix": "/", "backend": {"name": "jira", "port": 8080}}],
        "features": ["rate_limit"],
    }

    accepted = client.put("/v2/service_instances/jira-web", json=payload)

    assert accepted.status_code == 202
    body = accepted.json()
    assert body["state"] == "succeeded"
    assert body["service_id"] == "jira-web"
    operation = body["operation"]
    assert client.get(
        f"/v2/service_instances/jira-web/last_operation?operation={operation}"
    ).json()[
        "state"
    ] == "succeeded"
    service = client.get("/v2/service_instances/jira-web").json()
    assert service["domains"] == ["jira.example.com"]
    snapshot = client.get("/v2/control-plane/snapshot").json()
    assert snapshot["clusters"] == [{"name": "jira", "port": 8080}]
    assert snapshot["virtual_hosts"][0]["filters"] == ["access_logs", "rate_limit"]


def test_live_app_conflicts_are_safe_and_do_not_persist_failed_service():
    client = TestClient(create_app())
    first = {
        "service_id": "jira-web",
        "owner": "jira-platform",
        "product_family": "teamwork_core",
        "edge_profile": "web_app_api",
        "domains": ["shared.example.com"],
        "routes": [{"prefix": "/jira", "backend": {"name": "jira", "port": 8080}}],
        "features": [],
    }
    second = {
        "service_id": "confluence-web",
        "owner": "confluence-platform",
        "product_family": "teamwork_core",
        "edge_profile": "web_app_api",
        "domains": ["shared.example.com"],
        "routes": [{"prefix": "/wiki", "backend": {"name": "confluence", "port": 8090}}],
        "features": [],
    }

    assert client.put("/v2/service_instances/jira-web", json=first).json()["state"] == "succeeded"
    conflict = client.put("/v2/service_instances/confluence-web", json=second).json()

    assert conflict["state"] == "failed"
    assert "already owned" in conflict["description"]
    assert client.get("/v2/service_instances/confluence-web").status_code == 404
