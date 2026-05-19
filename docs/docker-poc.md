# Docker Proof of Concept

The Docker proof of concept runs the current Innerwork backend as a single container with a local SQLite database mounted from the host.

It is intentionally small:

- one FastAPI process;
- one SQLite file at `.innerwork/innerwork.db`;
- no external database, reverse proxy, queue, or worker yet;
- no secrets required;
- no production hardening claims.

## Run with Docker Compose

```bash
docker compose up --build
```

Open:

- app landing page: http://127.0.0.1:8000/
- interactive API docs: http://127.0.0.1:8000/docs
- OpenAPI contract: http://127.0.0.1:8000/openapi.json
- health check: http://127.0.0.1:8000/healthz

Stop:

```bash
docker compose down
```

The SQLite file remains on the host under `.innerwork/` and is mounted into the container at `/tmp/innerwork`, so a restart preserves broker service intent, operations, and idempotency-key bindings.

## Smoke test the API

After `docker compose up --build`, create a demo service intent:

```bash
curl -sS -X PUT http://127.0.0.1:8000/v2/service_instances/jira-web \
  -H 'content-type: application/json' \
  -H 'X-Idempotency-Key: docker-demo-jira-web-0001' \
  -d '{
    "service_id": "jira-web",
    "owner": "jira-platform",
    "product_family": "teamwork_core",
    "edge_profile": "web_app_api",
    "domains": ["jira.example.com"],
    "routes": [{"prefix": "/", "backend": {"name": "jira", "port": 8080}}],
    "features": ["external_auth", "rate_limit"]
  }'
```

Inspect the stored state and rendered snapshot:

```bash
curl -sS http://127.0.0.1:8000/v2/service_instances
curl -sS http://127.0.0.1:8000/v2/control-plane/snapshot
```

## What this proves

The Docker PoC proves that a contributor can run the app from a clean container image, exercise the backend API, persist local state across process restarts, and inspect the generated OpenAPI/control-plane output.

## What it does not prove yet

This is not a production deployment. It does not include:

- a dedicated frontend SPA;
- real work-item/page domain APIs;
- async workers or retry queues;
- authn/authz or tenant isolation;
- Postgres migrations;
- Envoy sidecars or real xDS serving;
- observability dashboards;
- signed release artifacts.

Those items are phased in the production roadmap.
