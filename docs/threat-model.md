# Threat Model

## Scope

The platform exposes product services to the public internet through a shared edge. The highest-risk assets are domain ownership, routing configuration, TLS material, identity decisions, sidecar policies, and control-plane snapshots.

## Trust boundaries

1. Developer config to broker API.
2. Broker API to worker queue.
3. Workers to cloud provider APIs.
4. Durable state to control-plane renderer.
5. Control plane to Envoy fleet over xDS.
6. Envoy to local sidecars.
7. Envoy to product backends.

## Assets

- Public domains and certificates.
- Tenant route ownership.
- Control-plane signing/deployment credentials.
- xDS snapshots.
- Sidecar policy and identity configuration.
- Audit logs and operation history.
- Customer request metadata.

## Threats and mitigations

### Tenant claims another team's domain

Risk: traffic hijack or accidental exposure.

Mitigations:

- strong uniqueness constraint on domain ownership;
- approval workflow for domain transfer;
- broker admission checks before worker execution;
- audit log for every ownership mutation.

### Raw proxy config injection

Risk: tenant bypasses platform policy, routes to unauthorized clusters, disables logs, or weakens TLS.

Mitigations:

- tenants submit narrow intent only;
- typed xDS builders instead of raw templates for untrusted input;
- policy-as-code admission;
- Envoy validation plus snapshot diff review for high-risk changes.

### Malicious or broken sidecar policy

Risk: fail-open authorization, excessive latency, or inconsistent decisions.

Mitigations:

- explicit route-level failure mode;
- fail closed for authn/authz;
- sidecar latency budgets and circuit breakers;
- signed sidecar artifacts;
- decision logs correlated with request id and snapshot version.

### Control-plane compromise

Risk: attacker publishes malicious routing or disables controls globally.

Mitigations:

- least-privilege deployment credentials;
- signed snapshots or mutually authenticated xDS;
- separation between render, approval, and publish roles;
- append-only audit log;
- canary rollout with automated rollback;
- emergency freeze switch.

### Worker credential abuse

Risk: cloud resources, DNS, certificates, or CDN settings are mutated outside intended scope.

Mitigations:

- per-worker IAM roles with resource constraints;
- short-lived credentials;
- operation-scoped audit;
- dry-run diff for high-risk mutations;
- cloud audit log monitoring.

### Stale or inconsistent proxy config

Risk: some regions serve old policy or route traffic incorrectly.

Mitigations:

- version-skew dashboard;
- xDS ACK/NACK tracking;
- max staleness alert;
- regional rollout records;
- forced drain/restart workflow for stuck proxies.

### Data-plane overload

Risk: request storm, DDoS, or backend failure cascades through shared proxy fleet.

Mitigations:

- CDN/DDoS layer before Envoy;
- Envoy overload manager;
- per-tenant rate limiting;
- circuit breakers and outlier detection;
- capacity buffers per region;
- graceful degradation and backpressure.

### Audit-log tampering

Risk: loss of accountability for public exposure changes.

Mitigations:

- append-only audit sink;
- restricted write path;
- periodic export to immutable storage;
- correlation between broker operations, worker actions, snapshots, and cloud audit events.

## Security invariants

- Unknown hostnames are denied by default.
- Public exposure requires explicit owner and domain ownership.
- TLS is required for public routes.
- Access logging cannot be disabled by tenants.
- Authn/authz failures default to deny.
- Last-known-good config is preserved on control-plane failure.
- Every published snapshot is attributable, diffable, and reversible.
