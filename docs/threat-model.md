# Threat Model

## Scope

The platform exposes a broad product suite through shared cloud and edge infrastructure. The highest-risk assets are domain ownership, routing configuration, TLS material, identity decisions, sidecar policies, control-plane snapshots, cross-product permissions, marketplace/extension permissions, AI-agent actions, and audit trails.

This model covers the reference architecture, not Atlassian's private implementation.

## Trust boundaries

1. Product/developer config to broker API.
2. Broker API to worker queue.
3. Workers to cloud provider APIs.
4. Durable state to control-plane renderer.
5. Control plane to Envoy fleet over xDS.
6. Envoy to local sidecars.
7. Envoy to product backends.
8. Products to shared platform services: identity, teams, goals, search, chat, analytics, admin.
9. Rovo/Studio/agent actions to product APIs.
10. Marketplace apps and integrations to product/platform APIs.

## Assets

- Public domains and certificates.
- Tenant route ownership.
- Control-plane signing/deployment credentials.
- xDS snapshots.
- Sidecar policy and identity configuration.
- Audit logs and operation history.
- Customer request metadata.
- Cross-product graph links: work, knowledge, team, delivery, service, asset, feedback, and strategy graphs.
- Search indexes and AI retrieval context.
- Marketplace app manifests, tokens, and granted scopes.

## Threats and mitigations

### Tenant claims another team's domain

Risk: traffic hijack or accidental exposure.

Mitigations:

- strong uniqueness constraint on domain ownership;
- DNS/TLS proof or pre-approved domain registry for first claims;
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

### Product-profile mismatch

Risk: a product receives the wrong edge profile: e.g. media upload path treated like a simple web page, admin path treated like a normal route, or status-page traffic coupled to a failing product backend.

Mitigations:

- product-family profiles are explicit in durable state;
- high-risk profiles require approval;
- tests assert expected filters, limits, cache behavior, and auth mode per profile;
- rollout dashboards segment by product family.

### Malicious or broken sidecar policy

Risk: fail-open authorization, excessive latency, or inconsistent decisions.

Mitigations:

- explicit route-level failure mode;
- fail closed for authn/authz;
- sidecar latency budgets and circuit breakers;
- signed sidecar artifacts;
- decision logs correlated with request id, tenant id, product family, and snapshot version.

### Cross-product permission leak

Risk: search, analytics, Rovo, or linked-object views expose data from a product where the user lacks permission.

Mitigations:

- permission filtering at indexing and query time;
- source-product authorization checks for object expansion;
- tenant/site boundary tests;
- audit for cross-product reads;
- deny-by-default when permission state is stale or ambiguous.

### AI-agent overreach

Risk: Rovo/Rovo Dev/Studio-like agents perform actions outside user scope, use stale context, or cross data boundaries invisibly.

Mitigations:

- tool-call scopes bound to user, site, product, and marketplace app permissions;
- human approval for high-impact actions;
- prompt/data provenance in audit records;
- replayable agent action logs;
- rate/cost limits;
- kill switch for agent classes.

### Marketplace or Studio extension abuse

Risk: third-party or custom extensions exfiltrate data, over-request scopes, or weaken product workflows.

Mitigations:

- reviewed manifests and scoped OAuth grants;
- per-app rate limits and anomaly detection;
- tenant admin approval flows;
- extension sandboxing where possible;
- clear audit trails for app reads/writes.

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
- per-tenant and per-product-family rate limiting;
- circuit breakers and outlier detection;
- capacity buffers per region;
- graceful degradation and backpressure.

### Audit-log tampering

Risk: loss of accountability for public exposure changes, permission changes, or AI/extension actions.

Mitigations:

- append-only audit sink;
- restricted write path;
- periodic export to immutable storage;
- correlation between broker operations, worker actions, snapshots, cloud audit events, product API calls, and agent/tool actions.

## Security invariants

- Unknown hostnames are denied by default.
- Public exposure requires explicit owner and domain ownership.
- TLS is required for public routes.
- Access logging cannot be disabled by tenants.
- Authn/authz failures default to deny.
- Cross-product reads use source-product permissions.
- AI agents and marketplace apps act only through scoped, audited permissions.
- Last-known-good config is preserved on control-plane failure.
- Every published snapshot is attributable, diffable, and reversible.
