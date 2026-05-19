# Live application guide

The current runnable application is a backend/platform proof of concept for **Innerwork**, the clean-room work-and-knowledge app defined in `docs/product-scope.md`.

It can run in memory, persist service intent to a local JSON file for restart-safe demos, use a local SQLite database for the Phase 2 API/schema gate, or run in Docker Compose with SQLite mounted from the host. The SQLite store persists services, operations, and idempotency-key bindings so local broker API runs survive process restarts. It is still a single-process local store; worker queues, auth, tenant isolation, and production multi-writer database operations remain later roadmap work.

## Frontend in the current PoC

The frontend today is intentionally minimal:

- `GET /` returns a server-rendered HTML landing page from FastAPI.
- `GET /docs` is FastAPI's generated Swagger UI for exercising the backend.
- `GET /openapi.json` exposes the generated OpenAPI document.

There is not yet a dedicated React/Vue/Svelte/etc. product UI. The future product frontend should cover projects, work items, workflow transitions, spaces, pages, page versions, comments, links, and search. That is Phase C in the updated production roadmap.

## Backend in the current PoC

The backend today is the real executable surface:

- FastAPI app in `src/innerwork/app.py`;
- Pydantic request/response contracts for broker operations;
- idempotent `PUT /v2/service_instances/{instance_id}` operations with required `X-Idempotency-Key`;
- product-family/profile policy validation;
- in-memory, JSON, or SQLite state storage;
- deterministic control-plane snapshot rendering;
- CLI wrappers for validation, rendering, and serving.

This backend currently models the platform/broker layer, not the final work-item/page domain model. Work graph and knowledge graph APIs are planned next product phases.

## Architecture

```text
Browser / operator / contributor
        |
        |  landing page, Swagger UI, curl, YAML, or CLI
        v
  Innerwork FastAPI backend
        |
        |  validates ownership, routes, profiles, features, idempotency
        v
  In-memory / JSON / SQLite service registry
        |
        |  records idempotent operation state
        v
  Control-plane snapshot renderer
```

The app intentionally keeps the default mode in memory for easy contributor review. Use `INNERWORK_STATE_PATH` for JSON demo persistence, or `INNERWORK_DATABASE_URL=sqlite:///.innerwork/innerwork.db` for the Phase 2 durable local API contract with persisted operations and idempotency keys.

## Docker PoC

```bash
docker compose up --build
```

Open:

- landing page: http://127.0.0.1:8000/
- generated backend API UI: http://127.0.0.1:8000/docs
- OpenAPI: http://127.0.0.1:8000/openapi.json
- health: http://127.0.0.1:8000/healthz

The Compose file mounts `./.innerwork` into the container at `/tmp/innerwork` and sets `INNERWORK_DATABASE_URL=sqlite:////tmp/innerwork/innerwork.db`, so local SQLite state survives container restarts. See `docs/docker-poc.md` for smoke-test commands.

## HTTP endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Human-friendly project landing page; current frontend shell. |
| `GET /healthz` | Process health and current snapshot version. |
| `GET /v2/catalog` | OSB-shaped service catalog. |
| `GET /v2/products` | Public product catalog grounding data. |
| `GET /v2/production-oss-phases` | Historical production OSS phase plan. |
| `GET /v2/policy-profiles` | Product-family/profile policy matrix used by validation and rendering. |
| `GET /v2/service_instances` | List stored service intents. |
| `PUT /v2/service_instances/{instance_id}` | Validate and store service intent; requires `X-Idempotency-Key`. |
| `GET /v2/service_instances/{instance_id}` | Fetch stored service intent. |
| `GET /v2/service_instances/{instance_id}/last_operation?operation=...` | Poll operation state. |
| `GET /v2/control-plane/snapshot` | Render deterministic proxy snapshot. |

## Run with Python

```bash
uv sync --dev
uv run uvicorn innerwork.app:app --reload

# Restart-safe local demo state:
INNERWORK_STATE_PATH=.innerwork/state.json uv run uvicorn innerwork.app:app --reload

# Durable Phase 2 local state:
INNERWORK_DATABASE_URL=sqlite:///.innerwork/innerwork.db uv run uvicorn innerwork.app:app --reload

# Equivalent CLI wrappers:
uv run innerwork serve --state .innerwork/state.json
uv run innerwork serve --database-url sqlite:///.innerwork/innerwork.db
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
uv run python scripts/validate_openapi_contract.py
git diff --check
```

The app is ready for local Docker demos and contributor review, including the Phase 2 schema/API gate. It now has OpenAPI/Pydantic contracts, CLI config validation, reviewed profile policies, required idempotency keys for mutating requests, persisted operation state, and a local SQLite durable state option. Before production traffic, add a real product frontend, work-and-knowledge domain APIs, authentication/authorization, tenant isolation, async worker queues, retry/backoff/poison queues, operational migrations, and deployment manifests.
