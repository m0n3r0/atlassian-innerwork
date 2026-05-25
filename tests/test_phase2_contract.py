from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from innerwork.app import create_app
from innerwork.broker import EdgeBroker
from innerwork.model import EDGE_POLICY_PROFILES
from innerwork.sql_state_store import SqliteStateStore

PAYLOAD = {
    "service_id": "ignored-by-path",
    "owner": "jira-platform",
    "product_family": "teamwork_core",
    "edge_profile": "web_app_api",
    "domains": ["jira.example.com"],
    "routes": [{"prefix": "/", "backend": {"name": "jira", "port": 8080}}],
    "features": ["rate_limit"],
}


def test_put_requires_idempotency_key_and_replays_original_operation(tmp_path: Path):
    db_path = tmp_path / "innerwork.db"
    client = TestClient(create_app(database_url=f"sqlite:///{db_path}"))

    missing = client.put("/v2/service_instances/jira-web", json=PAYLOAD)
    assert missing.status_code == 428
    assert "X-Idempotency-Key" in missing.json()["detail"]

    first = client.put(
        "/v2/service_instances/jira-web",
        json=PAYLOAD,
        headers={"X-Idempotency-Key": "phase2-key-000001"},
    )
    replay = client.put(
        "/v2/service_instances/jira-web",
        json=PAYLOAD,
        headers={"X-Idempotency-Key": "phase2-key-000001"},
    )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json() == first.json()

    operation = first.json()["operation"]
    restarted = TestClient(create_app(database_url=f"sqlite:///{db_path}"))
    last = restarted.get(f"/v2/service_instances/jira-web/last_operation?operation={operation}")
    assert last.status_code == 200
    assert last.json()["state"] == "succeeded"


def test_sqlite_store_persists_services_operations_and_idempotency(tmp_path: Path):
    db_path = tmp_path / "innerwork.db"
    first_store = SqliteStateStore(db_path)
    first_broker = EdgeBroker(state_store=first_store)
    operation = first_broker.provision_from_payload(
        "jira-web",
        PAYLOAD,
        idempotency_key="phase2-key-000002",
    )
    result = first_broker.last_operation(operation.operation_id)
    assert result.state == "succeeded"

    restarted_broker = EdgeBroker(state_store=SqliteStateStore(db_path))
    assert restarted_broker.get_service("jira-web") is not None
    assert restarted_broker.last_operation(operation.operation_id).state == "succeeded"
    replayed = restarted_broker.provision_from_payload(
        "jira-web",
        PAYLOAD,
        idempotency_key="phase2-key-000002",
    )
    assert replayed.operation_id == operation.operation_id

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {"services", "operations", "idempotency_keys"}.issubset(tables)


def test_profile_policy_contract_is_exposed_and_enforced():
    profile = EDGE_POLICY_PROFILES[("teamwork_core", "web_app_api")]
    assert profile.required_features == ("access_logs",)
    assert "rate_limit" in profile.allowed_features

    invalid = dict(PAYLOAD)
    invalid["edge_profile"] = "git_code"
    client = TestClient(create_app())
    response = client.put(
        "/v2/service_instances/jira-web",
        json=invalid,
        headers={"X-Idempotency-Key": "phase2-key-000003"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "failed"
    assert "not allowed for teamwork_core" in body["description"]


def test_openapi_documents_idempotency_operation_schema_and_profile_policy():
    client = TestClient(create_app())
    openapi = client.get("/openapi.json").json()

    put_operation = openapi["paths"]["/v2/service_instances/{instance_id}"]["put"]
    assert any(param["name"] == "X-Idempotency-Key" for param in put_operation["parameters"])
    assert "428" in put_operation["responses"]
    assert "EdgeServicePayload" in openapi["components"]["schemas"]
    assert "OperationResponse" in openapi["components"]["schemas"]
    assert "EdgePolicyProfile" in openapi["components"]["schemas"]

    policies = client.get("/v2/policy-profiles").json()
    assert policies["profiles"][0]["product_family"]
    assert any(
        policy["product_family"] == "teamwork_core" and policy["edge_profile"] == "web_app_api"
        for policy in policies["profiles"]
    )
