# Production Readiness Checklist

## API and schema

- [ ] EdgeService schema has versioned compatibility guarantees.
- [ ] Broker endpoints have OpenAPI documentation.
- [ ] Idempotency keys are required for mutating operations.
- [ ] Admission rejects unknown domains, duplicate domains, invalid prefixes, invalid ports, and unsupported features.
- [ ] Every rejection includes a tenant-actionable reason.

## State and workers

- [ ] Domain ownership is strongly unique.
- [ ] Operation state is durable and pollable.
- [ ] Worker retries are bounded and observable.
- [ ] Poison messages are quarantined.
- [ ] Partial cloud-side changes have compensating cleanup.

## Control plane

- [ ] Rendering is deterministic.
- [ ] Rendered xDS passes Envoy validation before publication.
- [ ] Snapshots are hashed and diffable.
- [ ] ACK/NACK is recorded by proxy, region, and version.
- [ ] Previous known-good snapshots are retained.

## Rollout

- [ ] Canary rollout is mandatory.
- [ ] Health gates include 5xx, latency, NACKs, sidecar failures, and synthetic probes.
- [ ] Rollback is one command and tested.
- [ ] High-blast-radius changes require approval.

## Data plane

- [ ] Envoy has overload manager and circuit breakers.
- [ ] Access logs include request id, tenant id, route id, and snapshot version.
- [ ] Sidecar health is part of readiness.
- [ ] Scale-in drains connections gracefully.
- [ ] Regional capacity buffers are documented.

## Security

- [ ] TLS is mandatory.
- [ ] Unknown hosts deny by default.
- [ ] Authn/authz fail closed.
- [ ] Secrets are not baked into images.
- [ ] IAM is least privilege.
- [ ] Audit log is append-only and exported to immutable storage.

## Operations

- [ ] Dashboards exist for broker, workers, control plane, Envoy, sidecars, and queue.
- [ ] Runbooks cover bad config, NACKs, control-plane outage, worker backlog, certificate expiry, and traffic regression.
- [ ] On-call onboarding includes architecture, common queries, and replay drills.
- [ ] Disaster recovery restores durable state and last-known-good snapshots.
