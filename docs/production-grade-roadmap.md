# Production-Grade Roadmap

This roadmap turns the reference design into a production platform without jumping straight from diagrams to a fragile edge system.

## Phase 0 — Reference nucleus

Status: implemented in this repository.

Deliverables:

- executable broker model;
- deterministic control-plane snapshot model;
- tests for domain ownership, invalid route rejection, and feature rendering;
- grand-design documentation and architecture diagram.

Exit criteria:

- `uvx pytest -q` passes;
- architecture invariants are documented;
- repository is public and reproducible.

## Phase 1 — API contract and schema gate

Build:

- OpenAPI spec for broker endpoints;
- JSON Schema or Pydantic models for `EdgeService`;
- CLI validator for developer configs;
- idempotency-key support;
- operation state machine.

Tests:

- invalid domains rejected;
- duplicate ownership rejected;
- idempotent retries return the original operation;
- every failed operation has a useful human description.

Exit criteria:

- configs can be validated in CI before deployment;
- broker API can run locally with durable SQLite/Postgres state.

## Phase 2 — Durable state and worker execution

Build:

- database schema for services, operations, ownership, snapshots, and audit log;
- worker queue abstraction;
- retry, backoff, and poison queue;
- compensating cleanup hooks;
- operation replay tooling.

Tests:

- worker crash during provisioning resumes safely;
- duplicate queue delivery is harmless;
- partial failure records cleanup requirement;
- audit trail is append-only.

Exit criteria:

- broker can survive process restarts;
- operation history is inspectable and replayable.

## Phase 3 — Real Envoy xDS renderer

Build:

- typed xDS builders for LDS, RDS, CDS, SDS;
- Envoy bootstrap for local proxy;
- snapshot cache and ADS/gRPC server;
- Envoy validation job;
- snapshot hash and diff tooling.

Tests:

- generated resources pass Envoy validation;
- same input yields same snapshot hash;
- invalid backend/route input fails before xDS publication;
- Envoy ACK/NACK is recorded.

Exit criteria:

- local Envoy can fetch config and route to demo backends.

## Phase 4 — Progressive rollout and rollback

Build:

- fleet and region model;
- canary percentages;
- health gates using metrics;
- automatic rollback to previous known-good snapshot;
- operator approval workflow for high-blast-radius changes.

Tests:

- bad snapshot is stopped at canary;
- rollback restores previous version;
- stuck proxy version skew alerts;
- region-scoped rollout limits blast radius.

Exit criteria:

- every config change has a rollout record and rollback path.

## Phase 5 — Sidecar platform concerns

Build:

- authentication sidecar contract;
- authorization sidecar contract;
- rate limit sidecar contract;
- local config delivery to sidecars;
- correlation ids and decision logs.

Tests:

- auth sidecar fail-closed behavior;
- rate limiter latency budget;
- sidecar outage readiness behavior;
- route-level policy differences.

Exit criteria:

- shared edge concerns can be rolled out independently from product services.

## Phase 6 — Infrastructure and image pipeline

Build:

- Terraform/CloudFormation module for regional edge fleet;
- Packer image build;
- SBOM and vulnerability scan;
- signed artifact promotion;
- blue/green AMI deployment.

Tests:

- image boots and fetches a test snapshot;
- host hardening checks pass;
- rollback to previous AMI succeeds;
- capacity and drain behavior validated.

Exit criteria:

- a staging region can run real traffic safely.

## Phase 7 — Operations and compliance

Build:

- dashboards for broker, control plane, Envoy, sidecars, workers, and queue;
- runbooks for common failures;
- audit report export;
- SLO burn-rate alerts;
- ownership and approval workflows.

Tests/drills:

- control-plane outage drill;
- worker queue outage drill;
- bad config rollback drill;
- regional failover drill;
- certificate rotation drill.

Exit criteria:

- on-call engineers can diagnose and recover expected failures without original authors.

## Non-goals until the above is stable

- Letting tenants submit arbitrary Envoy config.
- Supporting every Envoy feature directly.
- Building a GUI before the API and schema are stable.
- Multi-cloud abstraction before one cloud is production ready.
- Global automated rollout without canary gates.
