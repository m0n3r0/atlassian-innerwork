# Production Readiness Checklist

## Product-suite map

- [ ] Every public product/capability/resource surface has an object type, family, source URL, and public positioning.
- [ ] Every catalog surface has an explicit platform dependency profile.
- [ ] Product-family edge profiles are reviewed by platform, security, and owning product teams.
- [ ] Product taxonomy changes have audit history and docs updates.

## API and schema

- [x] EdgeService schema has versioned compatibility guarantees.
- [x] Broker endpoints have OpenAPI documentation.
- [x] Idempotency keys are required for mutating operations.
- [x] Admission rejects unknown domains, duplicate domains, invalid prefixes, invalid ports, and unsupported features.
- [x] Admission rejects unsupported product-family/profile combinations.
- [x] Every rejection includes a tenant-actionable reason.

## State and workers

- [ ] Domain ownership is strongly unique.
- [ ] Route ownership is strongly unique for host/path/profile combinations.
- [x] Operation state is durable and pollable through service-scoped lookup.
- [ ] Worker retries are bounded and observable.
- [ ] Poison messages are quarantined.
- [ ] Partial cloud-side changes have compensating cleanup.

## Control plane

- [ ] Rendering is deterministic.
- [ ] Routes render most-specific-prefix first.
- [ ] Rendered xDS passes Envoy validation before publication.
- [ ] Snapshots are hashed and diffable.
- [ ] ACK/NACK is recorded by proxy, region, and version.
- [ ] Previous known-good snapshots are retained.
- [ ] Product-family filters and limits are visible in snapshot diffs.

## Rollout

- [ ] Canary rollout is mandatory.
- [ ] Health gates include 5xx, latency, NACKs, sidecar failures, product-family SLOs, and synthetic probes.
- [ ] Rollback is one command and tested.
- [ ] High-blast-radius changes require approval.
- [ ] Status-page, admin/security, media, Git, CI/CD, and AI-agent profiles have stricter rollout gates where needed.

## Data plane

- [ ] Envoy has overload manager and circuit breakers.
- [ ] Access logs include request id, tenant id, product family, route id, and snapshot version.
- [ ] Sidecar health is part of readiness.
- [ ] Scale-in drains connections gracefully.
- [ ] Regional capacity buffers are documented by traffic class.

## Shared platform

- [ ] Identity and team graph are source-of-truth integrated.
- [ ] Search indexes enforce source-product permissions.
- [ ] Rovo/agent actions are scoped, audited, and kill-switchable.
- [ ] Marketplace and Studio extensions use reviewed manifests and scoped permissions.
- [ ] Analytics pipelines expose freshness and permission-filter metrics.
- [ ] Admin/Guard policy changes are attributable and reversible.

## Security

- [ ] TLS is mandatory.
- [ ] Unknown hosts deny by default.
- [ ] Authn/authz fail closed.
- [ ] Cross-product reads deny by default when permission state is stale.
- [ ] Secrets are not baked into images.
- [ ] IAM is least privilege.
- [ ] Audit log is append-only and exported to immutable storage.

## Operations

- [ ] Dashboards exist for product catalog, broker, workers, control plane, Envoy, sidecars, queue, shared platform services, and product-family SLOs.
- [ ] Runbooks cover bad config, product-profile mismatch, NACKs, control-plane outage, worker backlog, certificate expiry, traffic regression, and cross-product permission leaks.
- [ ] On-call onboarding includes architecture, common queries, and replay drills.
- [ ] Disaster recovery restores durable state and last-known-good snapshots.
