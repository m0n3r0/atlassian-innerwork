from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .broker import EdgeBroker
from .catalog import broker_catalog, product_catalog, production_oss_phases
from .control_plane import ControlPlane
from .serialization import (
    operation_result_to_dict,
    operation_to_dict,
    snapshot_to_dict,
    spec_from_dict,
    spec_to_dict,
)


class BackendPayload(BaseModel):
    name: str
    port: int = Field(ge=1, le=65535)


class RoutePayload(BaseModel):
    prefix: str
    backend: BackendPayload


class EdgeServicePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: str
    owner: str
    product_family: str
    edge_profile: str
    domains: list[str] = Field(min_length=1)
    routes: list[RoutePayload] = Field(min_length=1)
    features: list[str] = Field(default_factory=list)


class AppState:
    def __init__(self) -> None:
        self.broker = EdgeBroker()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Atlassian Innerwork",
        version="0.1.0",
        description=(
            "Open-source reference application for a Jira/Confluence-inspired "
            "self-service edge broker."
        ),
    )
    state = AppState()

    @app.get("/", include_in_schema=False)
    def home() -> HTMLResponse:
        return HTMLResponse(_home_html())

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "service_count": len(state.broker.list_services()),
            "snapshot_version": ControlPlane(state.broker).snapshot().version,
        }

    @app.get("/v2/catalog", tags=["broker"])
    def catalog() -> dict[str, Any]:
        return broker_catalog()

    @app.get("/v2/products", tags=["catalog"])
    def products() -> dict[str, Any]:
        return product_catalog()

    @app.get("/v2/production-oss-phases", tags=["catalog"])
    def phases() -> dict[str, Any]:
        return production_oss_phases()

    @app.get("/v2/service_instances", tags=["broker"])
    def list_service_instances() -> dict[str, Any]:
        return {"services": [spec_to_dict(spec) for spec in state.broker.list_services()]}

    @app.put(
        "/v2/service_instances/{instance_id}",
        tags=["broker"],
        status_code=status.HTTP_202_ACCEPTED,
    )
    def provision_service_instance(instance_id: str, payload: EdgeServicePayload) -> dict[str, Any]:
        spec_payload = payload.model_dump()
        spec_payload["service_id"] = instance_id
        try:
            spec = spec_from_dict(spec_payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        operation = state.broker.provision(spec)
        result = state.broker.last_operation(operation.operation_id)
        body = operation_to_dict(operation)
        body["state"] = result.state
        body["description"] = result.description
        return body

    @app.get("/v2/service_instances/{instance_id}", tags=["broker"])
    def get_service_instance(instance_id: str) -> dict[str, Any]:
        spec = state.broker.get_service(instance_id)
        if spec is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="service not found")
        return spec_to_dict(spec)

    @app.get("/v2/service_instances/{instance_id}/last_operation", tags=["broker"])
    def last_operation(
        instance_id: str,
        response: Response,
        operation: str = Query(..., min_length=1),
    ) -> dict[str, Any]:
        result = state.broker.last_operation_for_service(instance_id, operation)
        if result.state == "failed" and result.description.startswith("operation not found"):
            response.status_code = status.HTTP_404_NOT_FOUND
        return operation_result_to_dict(result)

    @app.get("/v2/control-plane/snapshot", tags=["control-plane"])
    def control_plane_snapshot() -> dict[str, Any]:
        return snapshot_to_dict(ControlPlane(state.broker).snapshot())

    return app


def _home_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Atlassian Innerwork</title>
  <style>
    body {
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
      margin: 0;
      background: #0f172a;
      color: #e2e8f0;
    }
    main { max-width: 980px; margin: 0 auto; padding: 56px 24px; }
    .card {
      background: #111827;
      border: 1px solid #334155;
      border-radius: 18px;
      padding: 28px;
      box-shadow: 0 24px 80px rgba(0,0,0,.25);
    }
    h1 { font-size: clamp(2rem, 4vw, 4rem); margin: 0 0 12px; }
    p { color: #cbd5e1; line-height: 1.6; }
    code, a { color: #93c5fd; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-top: 24px;
    }
    .tile {
      background: #0b1220;
      border: 1px solid #1e293b;
      border-radius: 14px;
      padding: 18px;
    }
  </style>
</head>
<body>
<main>
  <section class="card">
    <h1>Innerwork Edge Broker</h1>
    <p>
      A live, open-source reference app for a Jira/Confluence-inspired platform.
      Product teams request domain and route intent; the broker validates ownership;
      the control plane renders deterministic proxy snapshots.
    </p>
    <div class="grid">
      <div class="tile">
        <strong>Explore API</strong>
        <p><a href="/docs">/docs</a> and <a href="/openapi.json">/openapi.json</a></p>
      </div>
      <div class="tile"><strong>Health</strong><p><code>GET /healthz</code></p></div>
      <div class="tile"><strong>Catalog</strong><p><code>GET /v2/catalog</code></p></div>
      <div class="tile">
        <strong>Snapshot</strong>
        <p><code>GET /v2/control-plane/snapshot</code></p>
      </div>
    </div>
  </section>
</main>
</body>
</html>"""


app = create_app()
