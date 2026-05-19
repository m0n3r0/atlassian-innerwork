# Live application guide

The app can run in memory, persist service intent to a local JSON file for restart-safe demos, or use a local SQLite database for the Phase 2 API/schema gate. The SQLite store persists services, operations, and idempotency-key bindings so local broker API runs survive process restarts. It is still a single-process local store; worker queues, auth, tenant isolation, and production multi-writer database operations remain later roadmap work.

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
  In-memory / JSON / SQLite service registry
        |
        |  records idempotent operation state
        v
  Control-plane snapshot
```

The app intentionally keeps the default mode in memory for easy contributor review. Use `INNERWORK_STATE_PATH` for JSON demo persistence, or `INNERWORK_DATABASE_URL=sqlite:///.innerwork/innerwork.db` for the Phase 2 durable local API contract with persisted operations and idempotency keys.

## HTTP endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Human-friendly project landing page. |
| `GET /healthz` | Process health and current snapshot version. |
| `GET /v2/catalog` | OSB-shaped service catalog. |
| `GET /v2/products` | Public product catalog grounding data. |
| `GET /v2/production-oss-phases` | Production OSS phase plan. |
| `GET /v2/policy-profiles` | Product-family/profile policy matrix used by validation and rendering. |
| `GET /v2/service_instances` | List stored service intents. |
| `PUT /v2/service_instances/{instance_id}` | Validate and store service intent; requires `X-Idempotency-Key`. |
| `GET /v2/service_instances/{instance_id}` | Fetch stored service intent. |
| `GET /v2/service_instances/{instance_id}/last_operation?operation=...` | Poll operation state. |
| `GET /v2/control-plane/snapshot` | Render deterministic proxy snapshot. |

## Run

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
git diff --check
```

The app is ready for local demos and contributor review, including the Phase 2 schema/API gate. It now has OpenAPI/Pydantic contracts, CLI config validation, reviewed profile policies, required idempotency keys for mutating requests, persisted operation state, and a local SQLite durable state option. Before production traffic, add authentication/authorization, tenant isolation, async worker queues, retry/backoff/poison queues, operational migrations, and deployment manifests.
