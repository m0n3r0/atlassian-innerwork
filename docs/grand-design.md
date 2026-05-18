# Atlassian Innerwork Grand Design

> Reverse-engineered from the public video at https://www.youtube.com/watch?v=55pTFVoclvE. This document describes an Atlassian-style platform pattern, not Atlassian proprietary implementation.

## Executive summary

The system is a self-service edge platform. Product teams declare that a service should be reachable at the public edge; the platform validates that intent, provisions or updates shared edge resources, and serves dynamic Envoy configuration to a large regional proxy fleet. Cross-cutting concerns such as DDoS protection, authentication, authorization, rate limiting, access logging, observability, and compliance are centralized at the edge instead of being rebuilt by every product service.

The grand design has five layers:

1. Developer-facing intent: small configuration committed through normal delivery workflows.
2. Service broker: an Open Service Broker-style API that accepts provision/update/delete requests, stores state, and exposes last-operation polling.
3. Control plane: a management server that renders validated platform state into Envoy xDS resources.
4. Data plane: pre-provisioned Envoy proxy fleets across many regions, fronted by cloud networking.
5. Production substrate: AMI/image pipelines, infrastructure as code, sidecars, observability, compliance, and operational playbooks.

The production-grade version adds stricter schemas, deterministic rendering, progressive rollout, safe rollback, tenant isolation, policy-as-code, audit trails, and SLO-driven operations.

---

## Source-video reconstruction

The video describes the following progression:

- A platform application for self-service load balancers, shaped like an Open Service Broker API.
- A FastAPI web application, worker process, SQS queue, and DynamoDB state store.
- Provisioning tasks such as DNS records, CloudFront distributions, and other cloud API operations.
- An Envoy-based replacement for enterprise load balancers.
- An Envoy management server/control plane that renders templates plus context into dynamic proxy configuration.
- A data plane of many pre-provisioned proxies across many AWS regions, created by CloudFormation.
- A Packer + SaltStack AMI pipeline installing Envoy, sidecars, logging/metrics/tracing agents, security hardening, network tuning, and runtime parameters.
- Migration of major products and microservices behind this centralized edge.
- Additional platform concerns handled at or beside the proxy: DDoS protection via CloudFront, access logs via Envoy, and local sidecars for authentication, authorization, and rate limiting.
- Long-term maintenance lessons: documentation, onboarding, on-call debugging, predictable churn, decoupling, and mentoring.

---

## Reference architecture

```text
Developer config / platform deploy
        |
        v
+-------------------+       +-----------------+       +------------------+
| Open Service      | ----> | Async work      | ----> | Durable state     |
| Broker API        |       | queue/workers   |       | catalog + intent  |
+-------------------+       +-----------------+       +------------------+
        |                                                     |
        | last_operation                                      | watched/polled
        v                                                     v
+--------------------------------------------------------------------------+
| Envoy control plane                                                      |
| - validates tenant intent                                                |
| - merges broker context + external context                               |
| - renders deterministic xDS snapshots                                    |
| - gates rollout and rollback                                             |
+--------------------------------------------------------------------------+
        |
        | ADS/xDS
        v
+------------------+     +------------------+     +------------------+
| Region A edge    |     | Region B edge    | ... | Region N edge    |
| CloudFront/NLB   |     | CloudFront/NLB   |     | CloudFront/NLB   |
| Envoy + sidecars |     | Envoy + sidecars |     | Envoy + sidecars |
+------------------+     +------------------+     +------------------+
        |
        v
Product backends: Jira, Confluence, Bitbucket, Statuspage, internal services
```

---

## Component design

### 1. Developer intent layer

Developers should not submit raw Envoy YAML. They submit a narrow, policy-aware resource model:

```yaml
apiVersion: edge.platform/v1
kind: EdgeService
metadata:
  name: jira-web
  owner: jira-platform
spec:
  domains:
    - jira.example.com
  routes:
    - prefix: /
      backend:
        name: jira
        port: 8080
  features:
    externalAuth: true
    rateLimit: standard
    accessLogs: required
```

Production requirements:

- schema validation at CI and API admission time;
- ownership checks for domains, backends, certificates, and paths;
- explicit public-exposure signal; no accidental public ingress;
- safe defaults: TLS required, access logs on, deny unknown hosts, bounded timeouts;
- compatibility versioning so templates can evolve without breaking tenants.

### 2. Open Service Broker-style API

The broker is the control surface. It should expose a catalog and asynchronous lifecycle operations:

- `GET /v2/catalog`
- `PUT /v2/service_instances/{id}`
- `PATCH /v2/service_instances/{id}`
- `DELETE /v2/service_instances/{id}`
- `GET /v2/service_instances/{id}/last_operation`

Production requirements:

- every operation has an idempotency key and operation id;
- writes are transactional against durable state;
- conflicting domains/routes fail before reaching the control plane;
- orphan mitigation exists for partially applied cloud resources;
- audit entries record actor, diff, validation result, worker actions, and final state.

### 3. Async worker layer

Provisioning touches slow and failure-prone APIs: DNS, certificates, CloudFront, NLBs, IAM, secrets, and service discovery. The API should enqueue work and return immediately.

Production requirements:

- queue visibility timeouts matched to operation duration;
- per-resource locks for domain/certificate mutation;
- retry with jitter for transient cloud failures;
- poison-message quarantine and operator replay;
- compensating cleanup for partially created resources;
- explicit last-operation state: `in_progress`, `succeeded`, `failed`, `requires_attention`.

### 4. Durable state model

The state store is the source of truth for declared edge intent and derived runtime metadata.

Suggested tables/collections:

- `edge_services`: tenant intent, schema version, owner, lifecycle state;
- `domain_ownership`: domain -> service id, certificate id, validation state, ownership-proof status;
- `operations`: operation id, type, status, actor, started/finished timestamps;
- `rendered_snapshots`: control-plane version, hash, validation result;
- `rollouts`: region, fleet, canary percentage, health gates;
- `audit_log`: append-only event stream.

Production requirements:

- optimistic concurrency control on service specs;
- strong uniqueness on domain ownership;
- immutable audit history;
- backup/restore drill coverage;
- snapshot export for disaster recovery.

### 5. Envoy control plane

The control plane translates validated platform state into xDS resources:

- LDS: listeners, filter chains, TLS context;
- RDS: virtual hosts and route actions;
- CDS: backend clusters;
- SDS: certificates/secrets;
- ECDS/extension config: dynamic filters when appropriate.

Production requirements:

- deterministic rendering: same input produces same resource hashes;
- type-checked templates or generated builders instead of stringly YAML;
- Envoy config validation before publication;
- snapshot diffing and blast-radius estimation;
- canary rollout by region/fleet;
- automatic rollback if proxy NACKs, 5xx, latency, auth failures, or traffic drops exceed thresholds;
- stale-proxy detection and version skew dashboards.

### 6. Data-plane proxy fleet

The video describes a large fleet of EC2-hosted Envoy proxies, deployed across many regions via CloudFormation and AMIs.

Production-grade options:

- EC2 Auto Scaling Groups for stable, high-performance edge fleets;
- Kubernetes DaemonSets/Deployments if the organization already operates regional clusters;
- NLB/CloudFront in front of Envoy for layer-4 ingress and DDoS absorption;
- blue/green AMI rollout with health gates;
- capacity models per region and tenant traffic class.

Runtime requirements:

- strict egress to control-plane and sidecar endpoints;
- local sidecar health included in Envoy readiness;
- config warming before accepting traffic;
- outlier detection and circuit breakers;
- overload manager configured to shed safely under pressure;
- graceful drain on scale-in and deploy.

### 7. Sidecar platform concerns

Not every concern belongs inside Envoy config. Some are better as local services called by Envoy filters:

- authentication sidecar;
- authorization sidecar;
- rate limiting sidecar;
- tenant context resolver;
- policy decision point;
- request enrichment or external processing.

Production requirements:

- sidecar APIs are versioned and benchmarked;
- failure mode is explicit per route: fail closed for auth, bounded fail open only when business-approved;
- sidecar config is delivered through the same safe rollout pipeline;
- resource budgets prevent sidecars from starving Envoy;
- logs correlate request id, tenant id, sidecar decision, and upstream cluster.

### 8. Image and infrastructure pipeline

The AMI/image pipeline installs and verifies the runtime bundle:

- Envoy binary and bootstrap config;
- sidecar containers/binaries;
- observability agents;
- host hardening;
- kernel/network tuning;
- runtime secret/bootstrap fetch logic.

Production requirements:

- pinned versions and signed artifacts;
- vulnerability scan and SBOM per image;
- golden-image integration tests that boot the image and fetch a test xDS snapshot;
- staged AMI promotion: dev -> staging -> one-region canary -> global;
- fast rollback to previous AMI.

---

## Request lifecycle

### Provisioning lifecycle

1. Developer commits edge-service config.
2. Platform deploy system submits a broker request.
3. Broker validates schema, ownership, and policy.
4. Broker creates an operation row and queues worker task.
5. Worker creates/updates DNS, certificates, CDN/NLB bindings, and durable intent.
6. Control plane detects new state and renders a candidate snapshot.
7. Candidate snapshot is validated, diffed, and canaried.
8. Envoy fleet ACKs the new snapshot.
9. Broker last-operation returns success.
10. Audit and metrics become visible to product team and platform operators.

### Traffic lifecycle

1. Customer request reaches CDN or NLB.
2. Envoy receives TLS/HTTP traffic.
3. Listener and route config identify tenant/service.
4. Sidecars handle authentication, authorization, rate limit, and policy checks.
5. Envoy emits access logs and metrics.
6. Envoy forwards to product backend cluster.
7. Response flows back through Envoy and edge network.

---

## Production hardening checklist

### Safety

- Reject raw Envoy config from tenants.
- Validate domain uniqueness and route ownership.
- Validate rendered xDS with Envoy before publication.
- Canary and rollback every control-plane snapshot.
- Fail closed for identity and authorization paths.
- Keep previous known-good snapshots available per fleet.

### Reliability

- Multi-region control plane or regional read replicas.
- Proxy continues serving last-good config if control plane is unavailable.
- Queue and worker backlog alerts.
- Synthetic probes for every public domain and every region.
- Per-tenant SLOs and per-platform SLOs.

### Observability

Golden signals:

- request rate, error rate, duration, saturation;
- xDS ACK/NACK counts and version skew;
- sidecar latency and decision counts;
- provisioning operation duration and failure rate;
- queue age and worker retries;
- route-level 4xx/5xx and upstream connect failures.

Required logs:

- broker request audit;
- worker action log;
- control-plane render diff;
- Envoy access log;
- sidecar decision log;
- operator action log.

### Security/compliance

- Every public exposure has owner, purpose, and approval trail.
- TLS certificates are centrally managed and rotated.
- Secrets are delivered by a secret manager, not baked into images.
- IAM is least privilege per worker and fleet role.
- Config changes are attributable and reversible.
- Compliance evidence is generated from audit trails and rollout records.

### Maintainability

- Keep tenant model small and stable.
- Isolate high-churn feature logic behind typed modules.
- Version templates and migration steps.
- Build docs for onboarding, on-call, debugging, and common failure modes.
- Track churn hotspots and refactor before they become platform bottlenecks.

---

## Design principles

1. Intent over mechanism: developers describe exposure intent, not proxy internals.
2. Centralize shared concerns: solve auth, logs, DDoS, and rate limits once at the edge.
3. Validate before render: bad tenant input never reaches Envoy.
4. Render deterministically: snapshots must be reproducible and diffable.
5. Prefer last-known-good: control-plane outages must not drop data-plane traffic.
6. Make rollout observable: every config and image change needs health gates.
7. Treat platform APIs as products: stable contracts, docs, migration paths, and empathy for internal customers.

---

## What this repository implements now

The Python model in `src/innerwork` captures the core invariants:

- pre-approved domain registry or DNS/TLS proof for first domain claims;
- broker-style provisioning;
- service-scoped last-operation status using the public API states (`in_progress`, `succeeded`, `failed`, `requires_attention`);
- unguessable operation ids for broker lifecycle polling;
- canonical hostname validation and case-insensitive domain ownership;
- explicit owner-transfer rejection for same-service updates;
- mandatory access logging even when tenants omit optional features;
- fail-closed feature validation;
- intra-service and cross-service backend name/port conflict detection;
- most-specific-prefix-first route rendering;
- developer intent model;
- deterministic content-hash xDS-style snapshot versioning;
- feature-to-filter expansion for rate limiting and external auth.

This is intentionally small. It is not a full edge platform; it is an executable architectural nucleus that can be expanded along the production roadmap.
