# Atlassian Innerwork

A clean-room, public-source reconstruction of Atlassian's system-of-work architecture.

This repo started from the public video at https://www.youtube.com/watch?v=55pTFVoclvE and now folds in Atlassian's public software catalog at https://www.atlassian.com/software.

It does not contain Atlassian source code, private diagrams, private configuration, or claims of exact internal fidelity. It reconstructs the architecture pattern: an integrated product suite running on a shared Atlassian Cloud Platform, with a self-service edge/control-plane pattern for exposing product services safely.

## Read this first

1. `docs/overview.md` — the easiest end-to-end explanation.
2. `docs/product-system-map.md` — reverse-engineered map of the product suite.
3. `docs/grand-design.md` — production-grade platform architecture.
4. `docs/architecture.html` — standalone visual diagram.
5. `docs/production-oss-grand-design.md` — Jira + Confluence-inspired phases from idea to production-ready OSS.
6. `docs/autonomous-kanban-playbook.md` — autonomous Kanban execution loop with hallucination gates.

## What is inside

- `docs/overview.md` — concise repo guide and mental model.
- `docs/product-system-map.md` — public product, collection, platform, and ecosystem surfaces from the software homepage, mapped into capabilities and platform dependencies.
- `docs/grand-design.md` — polished production architecture and operating model.
- `docs/architecture.html` — standalone dark SVG architecture diagram.
- `docs/production-grade-roadmap.md` — staged path from prototype to production.
- `docs/production-oss-grand-design.md` — complete idea-to-production phase design for a clean-room work + knowledge OSS app inspired by Jira + Confluence.
- `docs/autonomous-kanban-playbook.md` — Kanban playbook for autonomous phase execution, review, iteration, and stop conditions.
- `docs/production-readiness-checklist.md` — launch checklist for the hardened platform.
- `docs/operations-runbook.md` — incident response and operational playbooks.
- `docs/threat-model.md` — trust boundaries, risks, and mitigations.
- `spec/openapi.yaml` — OSB-inspired broker API contract.
- `examples/edge-service.yaml` — sample developer-facing edge intent.
- `research/video-transcript.md` — timestamped transcript used as source material.
- `research/software-page-extract.md` — normalized extraction from the Atlassian software homepage.
- `src/innerwork/` — executable Python model for the broker/control-plane contract.
- `data/product_catalog.json` — structured product/collection/platform taxonomy used by tests and docs.
- `data/production_oss_phases.json` — machine-readable phase catalog for the production OSS grand design.
- `tests/` — regression tests for the core invariants.

## Quick start

```bash
uvx pytest -q
```

Expected:

```text
30 passed
```

## Core idea

Atlassian's public product surface reads like a single system of work rather than a set of isolated apps:

- teamwork core: Jira, Confluence, Loom, Trello, Rovo;
- software delivery: Bitbucket, Pipelines, Rovo Dev, DX;
- service: Jira Service Management, Customer Service Management, Assets, Statuspage, Guard;
- product discovery: Jira Product Discovery, Feedback, Rovo;
- strategy: Focus, Talent, Jira Align;
- platform foundation: Home, Goals, Teams, Studio, Search, Chat, Analytics, Admin.

The architecture pattern is a shared platform underneath these products:

1. product teams declare service intent instead of owning bespoke edge stacks;
2. a broker validates ownership, domains, routes, and policy;
3. a control plane renders deterministic Envoy/xDS-style snapshots;
4. regional proxy fleets enforce common security, observability, and reliability controls;
5. platform services such as identity, search, analytics, AI agents, admin, and marketplace connect the product suite into one operating system for work.

## Example edge intent

```python
EdgeServiceSpec(
    service_id="jira-web",
    owner="jira-platform",
    product_family="teamwork_core",
    edge_profile="web_app_api",
    domains=("jira.example.com",),
    routes=(RouteRule(prefix="/", backend=Backend(name="jira", port=8080)),),
    features=("external_auth", "rate_limit", "access_logs"),
)
```

The platform turns that into durable broker state, service-scoped operation status, deterministic xDS-style snapshots, Envoy listeners/routes/clusters/filters, and centralized controls before traffic reaches product services.

## License

MIT
