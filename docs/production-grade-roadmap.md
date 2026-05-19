# Production-Grade Roadmap

This roadmap turns the reference design into a production platform without jumping straight from diagrams to a fragile product-suite clone.

## Phase 0 — Reference nucleus

Status: implemented in this repository.

Deliverables:

- executable broker model;
- deterministic control-plane snapshot model;
- tests for domain ownership, invalid route rejection, operation safety, backend ownership, route ordering, and feature rendering;
- grand-design documentation and architecture diagram;
- public product-suite map from the Atlassian software homepage.

Exit criteria:

- `uvx pytest -q` passes;
- architecture invariants are documented;
- product-suite map is grounded in public sources;
- repository is public and reproducible.

## Phase 1 — Product taxonomy and platform graph

Build:

- canonical catalog file for Jira, Confluence, Loom, Trello, Rovo, JSM, CSM, Assets, Statuspage, Guard, Bitbucket, Pipelines, Rovo Dev, DX, JPD, Feedback, Focus, Talent, Jira Align, Bamboo, Sourcetree, Marketplace, Community, Partners, Developer Resources, collections, and Cloud Platform primitives;
- typed domain model for organization, site, user, team, goal, work item, document, video, repo, build, service, asset, incident, status, feedback, roadmap, agent, marketplace app;
- relationship map for work graph, knowledge graph, team graph, delivery graph, service graph, and strategy graph;
- docs generator that renders the product map from structured data.

Tests:

- every product has a family, source URL, public positioning, and platform dependencies;
- graph relationships are acyclic where required and explicitly many-to-many where expected;
- docs are generated deterministically.

Exit criteria:

- product docs are data-backed instead of hand-maintained prose only.

## Phase 2 — API contract and schema gate

Status: completed in this repository.

Build:

- OpenAPI spec for broker endpoints;
- JSON Schema or Pydantic models for `EdgeService`;
- CLI validator for developer configs;
- idempotency-key support;
- operation state machine;
- product-family policy profiles for web apps, media, Git/code, CI/CD, service portals, status pages, AI agents, and admin/security surfaces.

Tests:

- invalid domains rejected;
- duplicate ownership rejected;
- idempotent retries return the original operation;
- every failed operation has a useful human description;
- product profile controls are applied consistently.

Exit criteria:

- configs can be validated in CI before deployment;
- broker API can run locally with durable SQLite/Postgres state;
- product-family edge profiles are explicit and reviewed.

## Phase 3 — Durable state and worker execution

Status: next phase; not yet implemented beyond the Phase 2 local SQLite state gate.

Build:

- database schema for services, operations, ownership, snapshots, rollouts, audit log, product catalog, and product/profile mappings;
- worker queue abstraction;
- retry, backoff, and poison queue;
- compensating cleanup hooks;
- operation replay tooling;
- domain/certificate/proxy resource reconciliation.

Tests:

- worker crash during provisioning resumes safely;
- duplicate queue delivery is harmless;
- partial failure records cleanup requirement;
- audit trail is append-only;
- resource reconciliation detects drift.

Exit criteria:

- broker can survive process restarts;
- operation history is inspectable and replayable;
- cloud-resource drift is visible before customers notice.

## Phase 4 — Real Envoy xDS renderer

Build:

- typed xDS builders for LDS, RDS, CDS, SDS;
- Envoy bootstrap for local proxy;
- snapshot cache and ADS/gRPC server;
- Envoy validation job;
- snapshot hash and diff tooling;
- profile-aware route/filter generation for product classes.

Tests:

- generated resources pass Envoy validation;
- same canonical input yields same snapshot hash;
- invalid backend/route input fails before xDS publication;
- Envoy ACK/NACK is recorded;
- product profiles render expected filters and limits.

Exit criteria:

- local Envoy can fetch config and route to demo backends.

## Phase 5 — Progressive rollout and rollback

Build:

- fleet and region model;
- canary percentages;
- health gates using metrics;
- automatic rollback to previous known-good snapshot;
- operator approval workflow for high-blast-radius changes;
- product-family blast-radius controls.

Tests:

- bad snapshot is stopped at canary;
- rollback restores previous version;
- stuck proxy version skew alerts;
- region-scoped rollout limits blast radius;
- status-page and admin/security routes receive stricter gates.

Exit criteria:

- every config change has a rollout record and rollback path.

## Phase 6 — Sidecar platform concerns

Build:

- authentication sidecar contract;
- authorization sidecar contract;
- rate limit sidecar contract;
- tenant/product context resolver;
- local config delivery to sidecars;
- correlation ids and decision logs;
- AI-agent action guard for Rovo/Rovo Dev/Studio-like flows.

Tests:

- auth sidecar fail-closed behavior;
- rate limiter latency budget;
- sidecar outage readiness behavior;
- route-level policy differences;
- AI-agent action attempts are permissioned and audited.

Exit criteria:

- shared edge concerns can be rolled out independently from product services.

## Phase 7 — Infrastructure and image pipeline

Build:

- Terraform/CloudFormation module for regional edge fleet;
- Packer image build;
- SBOM and vulnerability scan;
- signed artifact promotion;
- blue/green AMI deployment;
- regional capacity model per product traffic class.

Tests:

- image boots and fetches a test snapshot;
- host hardening checks pass;
- rollback to previous AMI succeeds;
- capacity and drain behavior validated;
- large media/Git/CI traffic profiles have explicit limits.

Exit criteria:

- a staging region can run real traffic safely.

## Phase 8 — Operations and compliance

Build:

- dashboards for broker, control plane, Envoy, sidecars, workers, queue, product families, and tenant SLOs;
- runbooks for common failures;
- audit report export;
- SLO burn-rate alerts;
- ownership and approval workflows;
- product-suite taxonomy review workflow.

Tests/drills:

- control-plane outage drill;
- worker queue outage drill;
- bad config rollback drill;
- regional failover drill;
- certificate rotation drill;
- product taxonomy change drill;
- AI-agent policy incident drill.

Exit criteria:

- on-call engineers can diagnose and recover expected failures without original authors;
- compliance evidence can be generated from system records.

## Non-goals until the above is stable

- Letting tenants submit arbitrary Envoy config.
- Supporting every Envoy feature directly.
- Building a GUI before the API and schema are stable.
- Multi-cloud abstraction before one cloud is production ready.
- Global automated rollout without canary gates.
- Claiming private Atlassian implementation fidelity.
- Building a full product clone instead of a reference architecture.
