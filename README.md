# Atlassian Innerwork

Atlassian Innerwork is an open-source reference application for a Jira/Confluence-inspired platform operating model. It turns public product-system research into a live, executable edge-broker service:

- product teams submit high-level domain and route intent;
- the broker validates ownership, product-family/profile compatibility, and safe defaults;
- the control plane renders deterministic Envoy-style snapshots;
- the repository includes tests, CI, docs, and a CLI so contributors can run it locally.

This is a clean-room reference design grounded in public Atlassian product positioning. It does not claim to mirror Atlassian private architecture.

## Product scope

The product being built is **Innerwork**: a clean-room, Jira/Confluence-inspired work-and-knowledge application. The intended MVP combines:

- a work graph: projects, work items, workflow states, comments, and ownership;
- a knowledge graph: spaces, pages, versions, comments, and durable decisions;
- cross-graph links under one identity, permission, search, and audit model.

The current runnable app is the platform/backend proof of concept for that direction: an edge broker and control-plane API that validates service intent, persists local state, and renders deterministic snapshots. It is not a Jira clone, not a Confluence clone, and not a clone of Atlassian's UI or private architecture.

Not building Bitbucket, Trello, Loom, Jira Service Management, Statuspage, Guard, Jira Align, or the rest of the Atlassian portfolio. Those products remain catalog context only.

See [`docs/product-scope.md`](docs/product-scope.md) for the scope boundary.

## Run locally with Docker

Prerequisites: Docker with Compose support.

```bash
docker compose up --build
```

Open:

- Home / current frontend shell: <http://127.0.0.1:8000/>
- Interactive API docs: <http://127.0.0.1:8000/docs>
- OpenAPI: <http://127.0.0.1:8000/openapi.json>
- Health: <http://127.0.0.1:8000/healthz>

Stop:

```bash
docker compose down
```

The Docker PoC stores SQLite state under `.innerwork/innerwork.db` through the Compose volume mount. See [`docs/docker-poc.md`](docs/docker-poc.md) for smoke-test commands and limitations.

## Run locally with Python

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

## CLI

```bash
uv run innerwork catalog
uv run innerwork products
uv run innerwork phases
uv run innerwork validate examples/edge-service.yaml
uv run innerwork render examples/edge-service.yaml
uv run innerwork serve --state .innerwork/state.json
uv run innerwork serve --database-url sqlite:///.innerwork/innerwork.db
```

## Minimal API example

```bash
curl -sS -X PUT http://127.0.0.1:8000/v2/service_instances/jira-web \
  -H 'content-type: application/json' \
  -H 'X-Idempotency-Key: demo-jira-web-0001' \
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
- `src/innerwork/broker.py` — OSB-inspired provisioning broker with idempotent operation tracking.
- `src/innerwork/control_plane.py` — deterministic xDS-style snapshot renderer.
- `src/innerwork/app.py` — FastAPI live application.
- `src/innerwork/cli.py` — local contributor CLI.
- `Dockerfile` and `docker-compose.yml` — one-container Docker PoC with host-mounted SQLite state.
- `src/innerwork/state_store.py` — optional JSON state store for restart-safe demos.
- `src/innerwork/sql_state_store.py` — local SQLite store for durable Phase 2 services, operations, and idempotency keys.
- `data/product_catalog.json` — public product catalog grounding.
- `data/production_oss_phases.json` — phased open-source production plan.
- `spec/openapi.yaml` — hand-authored API contract reference.
- `docs/production-oss-grand-design.md` — grand design for productionizing the project.
- `docs/autonomous-kanban-playbook.md` — autonomous development playbook.

## Design docs

- [Product scope](docs/product-scope.md)
- [Docker proof of concept](docs/docker-poc.md)
- [Live application guide](docs/live-application.md)
- [Production OSS grand design](docs/production-oss-grand-design.md)
- [Autonomous Kanban playbook](docs/autonomous-kanban-playbook.md)
- [Grand design](docs/grand-design.md)
- [Production-grade roadmap](docs/production-grade-roadmap.md)
- [Production-readiness checklist](docs/production-readiness-checklist.md)
- [Threat model](docs/threat-model.md)
- [Operations runbook](docs/operations-runbook.md)
- [Architecture HTML walkthrough](docs/architecture.html)
- [Launch plan](docs/launch-plan.md)
- [Beta program](docs/beta-program.md)
- [Migration guide](docs/migration-guide.md)
- [Roadmap](docs/roadmap.md)
- [Post-launch iteration](docs/post-launch-iteration.md)
- [Metrics dashboard](docs/metrics-dashboard.md)

## Beta

Phase 10 opens a public beta of the CLI and FastAPI surface. To volunteer,
open a `beta-signup` issue from the
[beta signup template](.github/ISSUE_TEMPLATE/beta_signup.md) and read
[`docs/beta-program.md`](docs/beta-program.md) first. The maintainers do not
publish participant counts and the beta carries no commercial commitments.

The Phase 10 CLI surface adds four work-graph subcommands:

```bash
innerwork export   --database-url sqlite:///./inner.db [--out export.json]
innerwork import   --database-url sqlite:///./fresh.db export.json
innerwork migrate  --database-url sqlite:///./fresh.db --source synthetic
innerwork metrics  --database-url sqlite:///./inner.db
```

`export` / `import` use the portability envelope documented in
[`docs/migration-guide.md`](docs/migration-guide.md). `migrate --source
synthetic` populates a fresh store from the bundled synthetic fixture (the
only `--source` shipped in Phase 10; no Jira/Confluence importer exists yet).
`metrics` prints the whole-domain analytics rollup.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

1. Add or update tests first for behavior changes.
2. Run `uv run pytest -q`, `uv run ruff check .`, and `uv run pyright`.
3. Keep public-source grounding explicit; do not add claims about private Atlassian internals.

## Community

- **Code of Conduct** — [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) (Contributor Covenant 2.1).
- **Governance** — [`GOVERNANCE.md`](GOVERNANCE.md). Minimalist BDFL model; lazy consensus on PRs.
- **Maintainers** — [`MAINTAINERS.md`](MAINTAINERS.md). Self-nomination only.
- **Security** — [`SECURITY.md`](SECURITY.md). Use **GitHub private vulnerability reporting** for security bugs; do not open a public issue or PR.
- **Contributor deep-dive** — [`docs/contributor-guide.md`](docs/contributor-guide.md).
- **Changelog** — [`CHANGELOG.md`](CHANGELOG.md).
- **License** — [`LICENSE`](LICENSE) (MIT).
