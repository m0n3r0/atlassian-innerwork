# Atlassian Innerwork Grand Design

> Clean-room reconstruction from public sources: the video at https://www.youtube.com/watch?v=55pTFVoclvE and the software homepage at https://www.atlassian.com/software. This document describes an Atlassian-style platform pattern, not Atlassian proprietary implementation.

## Executive summary

Atlassian's public portfolio now reads as a single system of work: Jira, Confluence, Loom, Trello, Rovo, Jira Service Management, Bitbucket, Jira Product Discovery, Focus, Talent, Align, and more sit on a connected cloud platform. The video explains one critical platform pattern needed to operate that breadth safely: a self-service edge platform that lets product teams expose services through a common broker, control plane, and regional Envoy data plane.

The production-grade design has six layers:

1. Product experiences: the apps and collections visible to customers.
2. Shared system-of-work platform: identity, teams, goals, search, chat, analytics, admin, marketplace, and AI agents.
3. Developer-facing service intent: product teams declare exposure and policy needs through a narrow model.
4. Broker and workers: Open Service Broker-style API, async execution, durable state, audit, and operation polling.
5. Envoy control plane: validated product/service intent rendered into deterministic xDS snapshots.
6. Regional edge data plane: CDN/NLB, Envoy proxy fleets, sidecars, logs, metrics, rollout/rollback.

The edge platform is not the whole Atlassian platform, but it is a keystone: without common exposure, auth, logging, rate limiting, DDoS protection, compliance evidence, and rollout safety, each product would need to rebuild high-risk infrastructure independently.

---

## Public-source reconstruction

### From the video

The video describes this evolution:

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

### From the software homepage

The homepage shows the product surface this kind of platform must support:

- Teamwork: Jira, Confluence, Loom, Trello, Rovo.
- Software delivery: Bitbucket, Pipelines, Rovo Dev, DX.
- Service: Jira Service Management, Customer Service Management, Assets, Statuspage, Guard.
- Product discovery: Jira Product Discovery, Feedback, Rovo.
- Strategy: Focus, Talent, Jira Align / Align.
- Atlassian Cloud Platform: Home, Goals, Teams, Studio, Search, Chat, Analytics, Admin.
- Ecosystem: Marketplace, Community, Partners, Developer resources.

`product-system-map.md` provides the full product-by-product reconstruction.

---

## Reference architecture

```text
Customers / users / integrations
        |
        v
Product experiences
Jira | Confluence | Loom | Trello | JSM | CSM | Assets | Statuspage | Bitbucket | Rovo | Focus | Talent | Align
        |
        v
Atlassian Cloud Platform
Identity | Teams | Goals | Home | Search | Chat | Studio | Analytics | Admin | Marketplace
        |
        v
Product and service graph
work | knowledge | people | code | builds | services | assets | incidents | feedback | strategy
        |
        v
Self-service edge platform
Broker API -> async workers -> durable state -> xDS renderer -> rollout controller
        |
        v
Regional edge data plane
CloudFront/NLB -> Envoy fleet -> auth/authz/rate-limit/policy sidecars -> product backends
```

### Key graphs

The integrated product suite depends on shared graph-like primitives:

| Graph | Objects | Main consumers |
| --- | --- | --- |
| Work graph | issues, projects, plans, tasks, requests, incidents | Jira, JSM, Trello, Align, Focus |
| Knowledge graph | pages, videos, decisions, comments, artifacts | Confluence, Loom, Rovo |
| Team graph | users, groups, teams, ownership, expertise | Admin, Teams, Guard, all products |
| Delivery graph | repos, PRs, builds, deployments, services | Bitbucket, Pipelines, Rovo Dev, DX |
| Service graph | assets, CIs, incidents, status, customer requests | JSM, CSM, Assets, Statuspage |
| Strategy graph | goals, investments, funds, capacity, outcomes | Focus, Talent, Jira Align, Analytics |

---

## Product-suite architecture

### Teamwork core

Products: Jira, Confluence, Loom, Trello, Rovo.

Responsibilities:

- capture work;
- create durable knowledge;
- enable async updates;
- provide lightweight and heavyweight planning surfaces;
- make work searchable and actionable through Rovo.

Platform dependencies:

- shared identity and permissions;
- comments, mentions, notifications;
- object linking between issues, pages, videos, and boards;
- search indexing with permission filtering;
- AI context retrieval and audit.

### Software delivery

Products: Bitbucket, Pipelines, Rovo Dev, DX.

Responsibilities:

- store source code;
- review changes;
- run CI/CD;
- map software components and owners;
- measure developer productivity, quality, and delivery flow;
- let AI agents assist inside permissioned SDLC boundaries.

Platform dependencies:

- Git/API edge paths;
- webhook ingress and delivery;
- artifact/log access;
- integration with Jira work items and Confluence docs;
- service ownership metadata;
- analytics and governance.

### Service management

Products: Jira Service Management, Customer Service Management, Assets, Statuspage, Guard.

Responsibilities:

- internal and customer service workflows;
- incident, change, request, and support processes;
- asset/CMDB context;
- external status communication;
- security and policy controls across Atlassian Cloud.

Platform dependencies:

- customer/user identity boundaries;
- public portal routing;
- strong tenant isolation;
- asset and service graph links;
- incident and status-page availability;
- audit trails and admin policy enforcement.

### Product discovery

Products: Jira Product Discovery, Feedback, Rovo.

Responsibilities:

- collect ideas and feedback;
- synthesize and prioritize;
- produce roadmaps;
- connect discovery to Jira delivery.

Platform dependencies:

- feedback ingestion;
- roadmap/work-item links;
- Confluence/Loom context;
- Rovo summarization and search;
- analytics over ideas, outcomes, and delivery.

### Strategy and leadership

Products: Focus, Talent, Jira Align / Align.

Responsibilities:

- connect goals, work, people, funds, and outcomes;
- plan workforce/capacity;
- align enterprise planning with delivery.

Platform dependencies:

- goal graph;
- team/capacity graph;
- delivery rollups from Jira/Bitbucket/DX;
- portfolio analytics;
- executive-level permissioning and audit.

---

## Edge platform component design

### 1. Developer intent layer

Product teams should not submit raw Envoy YAML. They submit a narrow, policy-aware resource model:

```yaml
apiVersion: edge.platform/v1
kind: EdgeService
metadata:
  name: jira-web
  owner: jira-platform
spec:
  service_id: jira-web
  owner: jira-platform
  domains:
    - jira.example.com
  routes:
    - prefix: /
      backend:
        name: jira
        port: 8080
  features:
    - external_auth
    - rate_limit
    - access_logs
```

Production requirements:

- schema validation at CI and API admission time;
- ownership checks for domains, backends, certificates, and paths;
- explicit public-exposure signal; no accidental public ingress;
- safe defaults: TLS required, access logs on, deny unknown hosts, bounded timeouts;
- compatibility versioning so templates can evolve without breaking tenants;
- product-specific routing profiles without product-specific edge stacks.

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
- audit entries record actor, diff, validation result, worker actions, and final state;
- service-scoped operation lookup only.

### 3. Async worker layer

Provisioning touches slow and failure-prone APIs: DNS, certificates, CloudFront, NLBs, IAM, secrets, service discovery, webhooks, and customer/tenant configuration. The API should enqueue work and return immediately.

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

- `edge_services`: tenant intent, schema version, owner, lifecycle state, product family;
- `domain_ownership`: domain -> service id, certificate id, validation state, ownership-proof status;
- `route_ownership`: host/path -> service id, priority, policy profile;
- `operations`: operation id, type, status, actor, started/finished timestamps;
- `rendered_snapshots`: control-plane version, hash, validation result;
- `rollouts`: region, fleet, canary percentage, health gates;
- `audit_log`: append-only event stream.

Production requirements:

- optimistic concurrency control on service specs;
- strong uniqueness on domain and route ownership;
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

- deterministic rendering: same canonical input produces same resource hashes;
- type-checked templates or generated builders instead of stringly YAML;
- Envoy config validation before publication;
- snapshot diffing and blast-radius estimation;
- most-specific-prefix-first route rendering;
- canary rollout by region/fleet;
- automatic rollback if proxy NACKs, 5xx, latency, auth failures, or traffic drops exceed thresholds;
- stale-proxy detection and version-skew dashboards.

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
- request enrichment or external processing;
- AI-agent/tool-call guard for Rovo-like actions.

Production requirements:

- sidecar APIs are versioned and benchmarked;
- failure mode is explicit per route: fail closed for auth, bounded fail open only when business-approved;
- sidecar config is delivered through the same safe rollout pipeline;
- resource budgets prevent sidecars from starving Envoy;
- logs correlate request id, tenant id, sidecar decision, upstream cluster, product family, and actor.

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

1. Product team commits an edge-service config or triggers a platform deployment.
2. Platform deploy system submits a broker request.
3. Broker validates schema, ownership, product-family policy, and route/domain conflicts.
4. Broker creates an operation row and queues worker task.
5. Worker creates/updates DNS, certificates, CDN/NLB bindings, service discovery, and durable intent.
6. Control plane detects new state and renders a candidate snapshot.
7. Candidate snapshot is validated, diffed, and canaried.
8. Envoy fleet ACKs the new snapshot.
9. Broker last-operation returns success.
10. Audit and metrics become visible to product team and platform operators.

### Traffic lifecycle

1. Customer request reaches CDN or NLB.
2. Envoy receives TLS/HTTP traffic.
3. Listener and route config identify tenant, product family, and service.
4. Sidecars handle authentication, authorization, rate limit, tenant context, and policy checks.
5. Envoy emits access logs, metrics, and traces.
6. Envoy forwards to product backend cluster.
7. Product calls shared platform services as needed: identity, teams, search, chat, analytics, goals, marketplace.
8. Response flows back through Envoy and edge network.

---

## Product-specific edge profiles

| Product type | Edge profile |
| --- | --- |
| Jira/Confluence/Trello-style work apps | standard web/API routing, auth, rate limits, access logs, session safety. |
| Loom/media | larger payloads, streaming/CDN behavior, upload/download paths, content scanning. |
| Bitbucket/Git | Git HTTP/SSH support, webhooks, large repo operations, PR APIs. |
| Pipelines/CI | build callbacks, artifact/log access, runner egress, webhook ingress. |
| JSM/CSM service portals | customer/anonymous portal rules, stricter tenant isolation, SLA-sensitive routing. |
| Statuspage | cache-friendly public status pages that remain available during incidents. |
| Rovo/Rovo Dev/Studio agents | scoped tool calls, policy checks, prompt/data boundaries, audit and cost controls. |
| Guard/Admin | privileged routes, stronger auth, policy enforcement, high-cardinality audit. |
| Focus/Talent/Align | enterprise data access, portfolio analytics, stricter role-based permissions. |

---

## Production hardening checklist

### Safety

- Reject raw Envoy config from tenants.
- Validate domain uniqueness and route ownership.
- Validate rendered xDS with Envoy before publication.
- Canary and rollback every control-plane snapshot.
- Fail closed for identity and authorization paths.
- Keep previous known-good snapshots available per fleet.
- Keep product-specific profiles explicit and reviewed.

### Reliability

- Multi-region control plane or regional read replicas.
- Proxy continues serving last-good config if control plane is unavailable.
- Queue and worker backlog alerts.
- Synthetic probes for every public domain and every region.
- Per-tenant, per-product, and per-platform SLOs.
- Separate highly cacheable public status traffic from normal product traffic.

### Observability

Golden signals:

- request rate, error rate, duration, saturation;
- xDS ACK/NACK counts and version skew;
- sidecar latency and decision counts;
- provisioning operation duration and failure rate;
- queue age and worker retries;
- route-level 4xx/5xx and upstream connect failures;
- product-family and tenant-level SLO burn.

Required logs:

- broker request audit;
- worker action log;
- control-plane render diff;
- Envoy access log;
- sidecar decision log;
- Rovo/agent action audit where AI actions cross product boundaries;
- operator action log.

### Security/compliance

- Every public exposure has owner, purpose, and approval trail.
- TLS certificates are centrally managed and rotated.
- Secrets are delivered by a secret manager, not baked into images.
- IAM is least privilege per worker and fleet role.
- Config changes are attributable and reversible.
- Compliance evidence is generated from audit trails and rollout records.
- Cross-product search/AI always applies source-product permissions.
- Marketplace and Studio extensions run with scoped permissions and reviewable manifests.

### Maintainability

- Keep tenant model small and stable.
- Isolate high-churn feature logic behind typed modules.
- Version templates and migration steps.
- Build docs for onboarding, on-call, debugging, and common failure modes.
- Track churn hotspots and refactor before they become platform bottlenecks.
- Keep product taxonomy in sync with public product changes.

---

## Design principles

1. Intent over mechanism: developers describe exposure intent, not proxy internals.
2. One system of work: products should share identity, teams, goals, search, analytics, and graph links.
3. Centralize shared concerns: solve auth, logs, DDoS, rate limits, and compliance once at the edge.
4. Validate before render: bad tenant input never reaches Envoy.
5. Render deterministically: snapshots must be reproducible and diffable.
6. Prefer last-known-good: control-plane outages must not drop data-plane traffic.
7. Make rollout observable: every config and image change needs health gates.
8. Treat platform APIs as products: stable contracts, docs, migration paths, and empathy for internal customers.
9. AI is a platform feature, not a bypass: agents must respect permissions, provenance, audit, and rollback.

---

## What this repository implements now

The Python model in `src/innerwork` captures the core edge invariants:

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

The docs now also model the full public product suite and how it depends on a shared platform. This is intentionally not a full Atlassian clone. It is an executable architectural nucleus plus a comprehensive product/platform map that can be expanded along the production roadmap.
