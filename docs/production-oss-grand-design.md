# Production OSS Grand Design

> Status: phase 0 deliverable — product thesis and lifecycle phase specification for a clean-room work + knowledge open-source application inspired by the public Atlassian Jira + Confluence pairing.
>
> This document is **not** a Jira or Confluence clone, not a description of Atlassian-internal architecture, and not a trademarked-product proposal. Every claim about the source inspiration is grounded in the repository's public-source catalog and reference docs.

## 1. Source grounding

This phase 0 output relies only on the following repository sources:

- `data/product_catalog.json` — canonical public-source product catalog.
- `docs/product-system-map.md` — reverse-engineered product/platform map.
- `docs/grand-design.md` — existing edge/control-plane reference design.
- `docs/production-grade-roadmap.md` — existing production roadmap for the reference platform.
- `research/video-transcript.md`, `research/software-page-extract.md` — public source notes.

All Atlassian product references in this design map back to `data/product_catalog.json`. Where evidence is insufficient we write "not supported by current public sources" instead of guessing.

## 2. Selected product pair and explicit scope

The selected inspiration pair is **Jira + Confluence**, exactly as required by the plan. The catalog roles used here are quoted directly from `data/product_catalog.json`:

| Product | Catalog family | Catalog system role | Catalog dependencies |
| --- | --- | --- | --- |
| `jira` | `teamwork_core` | Primary work graph and workflow engine. | identity, teams, goals, search, analytics, rovo |
| `confluence` | `teamwork_core` | Knowledge graph and durable decision memory. | identity, teams, search, analytics, rovo |

Both products live in the same catalog family (`teamwork_core`) and share five of six platform dependencies. That overlap is exactly what makes the pair the smallest high-leverage exercise of the system-of-work loop: identity, permissions, search, analytics, and AI-readiness are forced to be unified across two distinct graphs.

**Scope boundary:** we are building **Innerwork**, a clean-room work-and-knowledge app inspired by the public roles above. Not building Bitbucket, Trello, Loom, Jira Service Management, Statuspage, Guard, Jira Align, or any other Atlassian portfolio product. Those catalog entries remain research context only and must not be treated as MVP implementation scope.

The product shape is therefore:

- Jira-inspired work graph: projects, work items, workflow transitions, comments, ownership, and audit.
- Confluence-inspired knowledge graph: spaces, pages, version history, comments, decisions, and audit.
- Cross-graph integration: bidirectional links between work items and pages, one identity model, one permission model, one search boundary, and one audit stream.

The current executable repository is one layer below that final product: a Docker-runnable backend proof of concept for the platform/broker/control-plane layer that will host and protect the work-and-knowledge application. A full user-facing work-item/page frontend is roadmap work, not current reality.

See `docs/product-scope.md` for the concise scope statement and naming rule.

## 3. Product thesis

The open-source application we are designing is a **work-and-knowledge operating system**: a work graph (issues, projects, transitions) and a knowledge graph (pages, spaces, versions) sharing a single identity, permission, link, search, and audit model. The placeholder internal name is `innerwork-os`. No vendor brand is used in the product surface.

### 3.1 Target users

- Small-to-mid engineering and product teams that want self-hostable work tracking plus durable documents under one identity and permission model.
- OSS maintainers and platform teams that need a transparent reference implementation of a system-of-work surface, with API-first contracts and clear governance.
- Operators who need to deploy, monitor, back up, and audit the system without proprietary lock-in.

### 3.2 Non-goals

- Cloning Jira, Confluence, or any other vendor product surface, branding, schema, or private APIs.
- Reimplementing every Atlassian feature; the scope is the two graphs and the integration surface between them.
- Multi-cloud and enterprise-portfolio features before the single-cloud, single-tenant production posture is stable.
- Building an LLM/agent platform before the deterministic data, API, permission, and audit layers are sound.

### 3.3 Current frontend/backend reality

The runnable PoC today has:

- **Frontend:** a small server-rendered landing page at `/` plus FastAPI's generated API documentation at `/docs`. This is enough to inspect the backend and manually exercise APIs, but it is not the final work-item/page product UI.
- **Backend:** FastAPI endpoints, Pydantic request/response models, an idempotent broker, local SQLite persistence, product/profile validation, and deterministic control-plane snapshot rendering.
- **CLI:** `innerwork validate`, `innerwork render`, and `innerwork serve` for contributor workflows.
- **Container:** `Dockerfile` and `docker-compose.yml` run the backend PoC with host-mounted SQLite state.

The roadmap now separates the containerized platform PoC from the later product MVP so contributors do not confuse the current backend shell with the final Innerwork user experience.

### 3.4 Clean-room rules

- Use the public Atlassian software-homepage product catalog only for inspiration about *responsibilities*, not for any private-architecture claims.
- Do not invent Atlassian-internal services, schemas, team names, metrics, or compliance certifications.
- Avoid trademarked product names, logos, and slogans in the application surface and in user-facing documentation.

## 4. Architecture stance

The product blueprint sits on top of the existing edge/control-plane reference in this repository (`docs/grand-design.md`, `docs/production-grade-roadmap.md`, `src/innerwork/`). The work graph and knowledge graph are modeled as two domains under one identity, one permission, one search, and one audit pipeline. Cross-graph links are first-class entities, not free-text references.

Allowed platform-capability vocabulary (drawn from `docs/product-system-map.md` and `data/product_catalog.json`):

`home, goals, teams, studio, search, chat, analytics, admin, identity, audit`

Any design statement that references a capability outside that list must either add it to the vocabulary with a source citation or be rewritten.

## 5. Lifecycle phase model (A–J)

The roadmap is split into application phases so the current Docker/backend PoC is not confused with the later work-item/page product. The machine-readable historical 0–10 phase catalog remains in `data/production_oss_phases.json`, but the active product roadmap should be read as the A–J sequence below.

### 5.1 Phases at a glance

| Phase | Name | Headline objective |
| --- | --- | --- |
| A | Dockerized platform PoC | Run the current backend in Docker with local SQLite and a visible API shell. |
| B | Work-and-knowledge MVP | Implement projects, work items, spaces, pages, and cross-links. |
| C | Product frontend | Build a real web UI for work items, pages, links, and search. |
| D | Permission, identity, and audit | Add local authn/authz, scoped permissions, and append-only audit events. |
| E | Durable worker and operations | Add async workers, retries, replay, backups, and drift/reconciliation workflows. |
| F | Search, collaboration, import/export | Add comments, mentions, notifications, permissioned search, and portable JSON import/export. |
| G | AI-ready context boundary | Add redacted, permission-filtered context endpoints for assistants without binding to a vendor LLM. |
| H | Production deployment and observability | Add Postgres mode, migrations, metrics, traces, dashboards, SLOs, release artifacts, and rollback drills. |
| I | OSS governance and extension model | Add governance, security policy, extension points, docs site, and tagged releases. |
| J | Beta and migration loop | Run beta, test migrations, dogfood the app, and publish iteration cadence. |

### 5.2 How to read a phase

Each phase must state:

- product scope: which part of Innerwork it advances;
- frontend/backend impact;
- Docker/local-run impact;
- tests and acceptance gates;
- clean-room checks proving it does not clone vendor UI, schemas, or private APIs.

Every phase remains review-gated before the next phase starts.

## 6. Anti-hallucination checklist (cross-phase)

These checks apply to every phase and every downstream Kanban child task. The phase catalog encodes phase-specific variants in `anti_hallucination_checks`.

- Reject any product reference outside `selected_products` ∪ `allowed_platform_capabilities`.
- Reject any architectural claim that names an Atlassian-internal service, schema, or team.
- Reject any compliance, certification, customer, revenue, or benchmark claim that is not backed by a reproducible artifact in the repo.
- When evidence is insufficient, write "not supported by current public sources" instead of guessing.
- Verify, with `grep` or equivalent, that every changed file actually contains the changes a Kanban worker claims to have made.

## 7. Pointers

- Machine-readable historical phase catalog: `data/production_oss_phases.json`.
- Concise product boundary: `docs/product-scope.md`.
- Docker PoC instructions: `docs/docker-poc.md`.
- Public-source catalog: `data/product_catalog.json`.
- Reverse-engineered product/platform map: `docs/product-system-map.md`.
- Existing production roadmap for the underlying edge/control-plane platform: `docs/production-grade-roadmap.md`.
- Existing grand design for the underlying platform: `docs/grand-design.md`.

The autonomous Kanban execution playbook (`docs/autonomous-kanban-playbook.md`) and the validation tests (`tests/test_production_oss_phases.py`) are produced by downstream tasks in this stack.
