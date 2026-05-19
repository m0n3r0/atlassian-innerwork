# Live application guide

Innerwork is now a runnable FastAPI application and CLI in addition to a reference architecture.

## Architecture

```text
Contributor / product team
        |
        |  YAML, CLI, or HTTP intent
        v
  Innerwork Broker
        |
        |  validates ownership, routes, profiles, features
        v
  In-memory service registry
        |
        |  deterministic render
        v
  Control-plane snapshot
```

The app intentionally keeps persistence in memory for the first open-source slice. That makes the core contract easy to review and test. Production persistence, authentication, tenant isolation, and async workers remain explicit roadmap items.

## HTTP endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Human-friendly project landing page. |
| `GET /healthz` | Process health and current snapshot version. |
| `GET /v2/catalog` | OSB-shaped service catalog. |
| `GET /v2/products` | Public product catalog grounding data. |
| `GET /v2/production-oss-phases` | Production OSS phase plan. |
| `GET /v2/service_instances` | List stored service intents. |
| `PUT /v2/service_instances/{instance_id}` | Validate and store service intent. |
| `GET /v2/service_instances/{instance_id}` | Fetch stored service intent. |
| `GET /v2/service_instances/{instance_id}/last_operation?operation=...` | Poll operation state. |
| `GET /v2/control-plane/snapshot` | Render deterministic proxy snapshot. |

## Run

```bash
uv sync --dev
uv run uvicorn innerwork.app:app --reload
```

## Validate and render from CLI

```bash
uv run innerwork validate examples/edge-service.yaml
uv run innerwork render examples/edge-service.yaml
```

## Open-source readiness gates

Every pull request should pass:

```bash
uv run pytest -q
uv run ruff check .
uv run pyright
git diff --check
```

The app is ready for local demos and contributor review, not production traffic. Before production traffic, add durable storage, authentication/authorization, audit logs, rate limiting, request idempotency storage, worker queues, and deployment manifests.
