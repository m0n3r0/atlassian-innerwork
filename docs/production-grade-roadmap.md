# Production-Grade Roadmap

This roadmap turns the current executable backend into a production-grade open-source application without implying that we are cloning Atlassian products or private systems.

The product being built is **Innerwork**: a clean-room work-and-knowledge application inspired by the public roles of Jira and Confluence. The MVP scope is only:

- Jira-inspired work graph: projects, work items, workflow states, comments, ownership, and audit.
- Confluence-inspired knowledge graph: spaces, pages, versions, comments, durable decisions, and audit.
- Cross-graph integration: links, shared identity, shared permissions, shared search, and shared audit.

Out of scope for the MVP: Bitbucket, Trello, Loom, Jira Service Management, Statuspage, Guard, Jira Align, Marketplace, and the rest of the Atlassian portfolio.

## Phase A — Dockerized proof of concept

Status: current/implemented by this branch.

Frontend:

- server-rendered landing page at `/`;
- generated FastAPI Swagger UI at `/docs`;
- no dedicated product UI yet.

Backend:

- FastAPI app with OpenAPI contract;
- idempotent broker API;
- local SQLite state through `INNERWORK_DATABASE_URL`;
- deterministic control-plane snapshot rendering;
- CLI validator and renderer.

Docker/local-run:

- `Dockerfile` builds a single backend image;
- `docker-compose.yml` runs it on port 8000;
- `.innerwork/innerwork.db` persists state on the host through the `/tmp/innerwork` container mount.

Exit criteria:

- `docker compose up --build` starts the app;
- `/healthz`, `/docs`, and `/openapi.json` are available;
- a demo `PUT /v2/service_instances/{id}` persists across container restarts;
- local verification suite passes.

## Phase B — Work-and-knowledge MVP domain

Build:

- project and work-item models;
- workflow states and transitions;
- space and page models;
- immutable page versions;
- comments on work items and pages;
- bidirectional links between work items and pages.

Tests:

- create/read/update work item;
- transition work item with invalid transition rejection;
- create/read/version page;
- link work item to page and enforce both ends exist;
- persist all MVP entities in SQLite.

Exit criteria:

- one Dockerized demo can create a project, create a work item, create a space, create a page, link them, restart, and read them back.

## Phase C — Product frontend

Build:

- simple web UI for projects, work items, spaces, pages, and links;
- API client layer generated or typed from OpenAPI;
- navigation between work graph and knowledge graph;
- basic forms with validation errors surfaced clearly.

Tests:

- frontend smoke test loads against Docker backend;
- create/edit flows covered by browser or component tests;
- no Atlassian branding, icons, UI copy, or trade dress.

Exit criteria:

- non-technical user can complete the MVP path without Swagger UI or curl.

## Phase D — Permission, identity, and audit

Build:

- local users/groups/teams;
- project and space permissions;
- permission checks on every read and mutation;
- append-only audit events;
- idempotency keys on every mutating product endpoint.

Tests:

- permission-denied reads and writes;
- cross-graph link requires access to both objects;
- audit event emitted for every mutation;
- audit log remains append-only.

Exit criteria:

- shared identity and permissions work across both graphs.

## Phase E — Durable worker and operations

Build:

- worker queue abstraction;
- retry/backoff/poison queue;
- operation replay tooling;
- backup and restore scripts;
- drift/reconciliation checks for persisted state.

Tests:

- duplicate queue delivery is harmless;
- worker crash resumes safely;
- backup restores into a clean Docker environment;
- failed operations remain inspectable and replayable.

Exit criteria:

- operators can recover from expected process, queue, and state failures.

## Phase F — Search, collaboration, import/export

Build:

- permission-filtered search over work items and pages;
- comments, mentions, and notifications;
- JSON import/export for projects, spaces, work items, pages, comments, links, and audit metadata;
- basic analytics for cycle time and document activity.

Tests:

- search hides unauthorized objects;
- import/export round trip is deterministic;
- notification dispatch is observable and rate-limited.

Exit criteria:

- teams can collaborate and move data in/out without lock-in.

## Phase G — AI-ready context boundary

Build:

- explicit context endpoint for assistant integrations;
- permission filtering, redaction, and token budget;
- provenance records for objects included in context;
- no default dependency on a specific LLM vendor.

Tests:

- unauthorized work items/pages are excluded;
- configured fields are redacted;
- response includes provenance and budget metadata.

Exit criteria:

- AI assistants can be integrated without bypassing identity, permission, audit, or privacy boundaries.

## Phase H — Production deployment and observability

Build:

- Postgres mode and migration tooling;
- structured logging, metrics, and traces;
- dashboards and SLO definitions;
- release artifacts, SBOM, vulnerability scan, and rollback procedure;
- deployment manifests for a staging environment.

Tests/drills:

- migrations apply and roll back in staging;
- dashboards cover critical frontend/backend paths;
- rollback drill passes;
- SLOs are measured before they are claimed.

Exit criteria:

- staging deployment is reproducible and observable.

## Phase I — OSS governance and extension model

Build:

- governance document;
- security policy;
- docs site;
- extension/plugin guidelines for work-item types and page renderers;
- release cadence and contributor workflow.

Tests/gates:

- external contributor can land a non-trivial PR using docs only;
- extension examples pass CI;
- tagged release installs cleanly.

Exit criteria:

- project is legitimately community-runnable and maintainable.

## Phase J — Beta and migration loop

Build:

- beta onboarding/offboarding;
- migration tooling for documented JSON fixtures;
- public roadmap/issues mapped to phases;
- dogfooding loop where release notes and bugs live in Innerwork itself.

Tests/gates:

- at least one synthetic migration completes end to end;
- beta feedback is triaged through the app;
- post-launch metrics are published from reproducible scripts.

Exit criteria:

- beta runs for a documented window and feeds an ongoing iteration cadence.

## Non-goals until the above is stable

- Cloning Jira, Confluence, or any other vendor product surface.
- Building Bitbucket/Trello/Loom/JSM/Statuspage/etc. equivalents.
- Claiming private Atlassian implementation fidelity.
- Adding AI/agent behavior before permissions and audit are sound.
- Multi-cloud abstraction before one deployment path is production ready.
- Letting tenants submit arbitrary Envoy or infrastructure config.
