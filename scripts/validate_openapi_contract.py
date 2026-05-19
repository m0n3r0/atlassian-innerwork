from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from innerwork.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    authored = yaml.safe_load((REPO_ROOT / "spec" / "openapi.yaml").read_text(encoding="utf-8"))
    generated = TestClient(create_app()).get("/openapi.json").json()

    required_paths = [
        "/v2/catalog",
        "/v2/policy-profiles",
        "/v2/service_instances",
        "/v2/service_instances/{instance_id}",
        "/v2/service_instances/{instance_id}/last_operation",
        "/v2/control-plane/snapshot",
    ]
    missing_authored = [path for path in required_paths if path not in authored["paths"]]
    missing_generated = [path for path in required_paths if path not in generated["paths"]]
    if missing_authored or missing_generated:
        raise SystemExit(
            "OpenAPI paths missing: "
            + json.dumps(
                {"authored": missing_authored, "generated": missing_generated},
                sort_keys=True,
            )
        )

    put_authored = authored["paths"]["/v2/service_instances/{instance_id}"]["put"]
    put_generated = generated["paths"]["/v2/service_instances/{instance_id}"]["put"]
    _assert_idempotency_parameter(put_authored, "spec/openapi.yaml")
    _assert_idempotency_parameter(put_generated, "FastAPI generated schema")
    if "428" not in put_authored["responses"] or "428" not in put_generated["responses"]:
        raise SystemExit("PUT service instance must document HTTP 428 for missing idempotency keys")

    authored_schemas = authored["components"]["schemas"]
    generated_schemas = generated["components"]["schemas"]
    for schema in ["EdgePolicyProfile", "OperationResponse"]:
        if schema not in authored_schemas:
            raise SystemExit(f"spec/openapi.yaml missing schema {schema}")
        if schema not in generated_schemas:
            raise SystemExit(f"FastAPI generated schema missing {schema}")

    return 0


def _assert_idempotency_parameter(operation: dict[str, object], source: str) -> None:
    parameters = operation.get("parameters", [])
    if not isinstance(parameters, list):
        raise SystemExit(f"{source} parameters must be a list")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        if parameter.get("name") == "X-Idempotency-Key":
            return
        if parameter.get("$ref") == "#/components/parameters/IdempotencyKey":
            return
    raise SystemExit(f"{source} missing X-Idempotency-Key parameter")


if __name__ == "__main__":
    raise SystemExit(main())
