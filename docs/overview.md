# Overview

This repository builds **Innerwork**, a clean-room, self-hostable
work-and-knowledge application inspired by the public roles of Jira (work
graph) and Confluence (knowledge graph). It is not a clone of Atlassian
products, not Atlassian-branded, and not a description of Atlassian internals.

The authoritative product boundary lives in `product-scope.md`. Everything in
this repo should be readable as "what does Innerwork do today, and what is the
next slice toward MVP".

## Product scope in one sentence

Innerwork = a work graph (projects, work items, workflow, comments) plus a
knowledge graph (spaces, pages, versions, comments) with shared identity,
permissions, search, links, and audit. Bitbucket, Trello, Loom, JSM,
Statuspage, Guard, Align, and the rest of the Atlassian portfolio are
explicitly out of scope.

## What runs today

The currently runnable surface, all behind `INNERWORK_DATABASE_URL` SQLite or
in-memory:

- FastAPI app at `src/innerwork/app.py` serving:
  - a server-rendered landing page at `/`;
  - generated Swagger UI at `/docs`;
  - the broker / control-plane API under `/v2/` (legacy from the platform PoC,
    kept idempotency-keyed and durable);
  - the Innerwork product-domain API under `/v1/`.
- Product-domain MVP slices implemented so far:
  - **Work graph (slice 1)** — projects, work items with project-scoped keys,
    workflow states (`todo`, `in_progress`, `done`), guarded transitions, and
    an append-only transition history. See `work-graph-domain.md`.
  - **Knowledge graph (slice 2)** — spaces, pages, immutable page versions,
    and typed cross-graph `WorkItem` ↔ `Page` links. See
    `knowledge-graph-domain.md`.
- CLI wrappers (`uv run innerwork ...`) for validation, rendering, serving,
  and basic work-graph operations.
- Docker Compose PoC with persistent SQLite under `.innerwork/`.

The original "broker / Envoy / xDS / regional proxies" architecture is still
present in code under `/v2/` because the work-and-knowledge MVP is being built
on top of it. New product work happens under `/v1/`.

## What is next

See `production-grade-roadmap.md`. The current focus is finishing Phase B
(comments + idempotency keys on all `/v1/` mutations), then Phase D
(identity / permissions / audit), then Phase C (product frontend).

## Repository shape

- `src/innerwork/domain.py`, `knowledge.py`, `comments.py`, `domain_store.py`,
  `domain_api.py` — product-domain models, persistence, and `/v1/` routes.
- `src/innerwork/app.py`, `broker.py`, `sql_state_store.py`, `model.py` —
  platform / broker layer kept under `/v2/`.
- `tests/` — pytest suite covering both layers.
- `docs/` — current docs; older Atlassian-suite reconstruction documents live
  under `docs/archive/` for historical context only.

## Pointers

- `product-scope.md` — locked product boundary and naming rules.
- `live-application.md` — concrete run instructions, endpoints, environments.
- `docker-poc.md` — Docker Compose proof of concept.
- `work-graph-domain.md`, `knowledge-graph-domain.md` — per-slice domain docs.
- `production-grade-roadmap.md` — phased plan.
- `archive/` — historical broker/edge platform documents, not implementation
  scope.
