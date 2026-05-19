# Atlassian Innerwork

Atlassian Innerwork is an open-source reference application for a Jira/Confluence-inspired platform operating model. It turns public product-system research into a live, executable edge-broker service:

- product teams submit high-level domain and route intent;
- the broker validates ownership, product-family/profile compatibility, and safe defaults;
- the control plane renders deterministic Envoy-style snapshots;
- the repository includes tests, CI, docs, and a CLI so contributors can run it locally.

This is a clean-room reference design grounded in public Atlassian product positioning. It does not claim to mirror Atlassian private architecture.

## Run locally

Prerequisites: Python 3.10+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run pyright
uv run uvicorn innerwork.app:app --reload

# If you are in a plain Python CI image without uv:
python -m pip install -e . pytest ruff
python -m pytest -q
python -m ruff check .
```

Open:

- Home: <http://127.0.0.1:8000/>
- Interactive API docs: <http://127.0.0.1:8000/docs>
- OpenAPI: <http://127.0.0.1:8000/openapi.json>
- Health: <http://127.0.0.1:8000/healthz>

## CLI

```bash
uv run innerwork catalog
uv run innerwork products
uv run innerwork phases
uv run innerwork validate examples/edge-service.yaml
uv run innerwork render examples/edge-service.yaml
uv run innerwork serve --state .innerwork/state.json
```

## Minimal API example

```bash
curl -sS -X PUT http://127.0.0.1:8000/v2/service_instances/jira-web \
  -H 'content-type: application/json' \
  -d '{
    "service_id": "jira-web",
    "owner": "jira-platform",
    "product_family": "teamwork_core",
    "edge_profile": "web_app_api",
    "domains": ["jira.example.com"],
    "routes": [{"prefix": "/", "backend": {"name": "jira", "port": 8080}}],
    "features": ["external_auth", "rate_limit"]
  }'

curl -sS http://127.0.0.1:8000/v2/control-plane/snapshot
```

## What is in the repo

- `src/innerwork/model.py` — fail-closed service intent model and validation rules.
- `src/innerwork/broker.py` — in-memory OSB-inspired provisioning broker.
- `src/innerwork/control_plane.py` — deterministic xDS-style snapshot renderer.
- `src/innerwork/app.py` — FastAPI live application.
- `src/innerwork/cli.py` — local contributor CLI.
- `src/innerwork/state_store.py` — optional JSON state store for restart-safe demos.
- `data/product_catalog.json` — public product catalog grounding.
- `data/production_oss_phases.json` — phased open-source production plan.
- `spec/openapi.yaml` — hand-authored API contract reference.
- `docs/production-oss-grand-design.md` — grand design for productionizing the project.
- `docs/autonomous-kanban-playbook.md` — autonomous development playbook.

## Design docs

- [Production OSS grand design](docs/production-oss-grand-design.md)
- [Autonomous Kanban playbook](docs/autonomous-kanban-playbook.md)
- [Grand design](docs/grand-design.md)
- [Production-grade roadmap](docs/production-grade-roadmap.md)
- [Production-readiness checklist](docs/production-readiness-checklist.md)
- [Threat model](docs/threat-model.md)
- [Operations runbook](docs/operations-runbook.md)
- [Architecture HTML walkthrough](docs/architecture.html)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

1. Add or update tests first for behavior changes.
2. Run `uv run pytest -q`, `uv run ruff check .`, and `uv run pyright`.
3. Keep public-source grounding explicit; do not add claims about private Atlassian internals.
