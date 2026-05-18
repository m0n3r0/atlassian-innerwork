# Operations Runbook

This runbook describes how to operate the production-grade version of the Atlassian Innerwork platform: product-suite map, broker/control plane, regional edge, and shared platform surfaces.

## Service map

- Product catalog: structured source of products, homepage capabilities, ecosystem resources, collections, platform capabilities, product families, and edge profiles.
- Broker API: accepts and validates tenant/product edge intent.
- Worker queue: executes cloud-side provisioning tasks.
- Durable state: stores service specs, product profiles, domain ownership, route ownership, operations, snapshots, rollouts, and audit events.
- Control plane: renders and publishes xDS snapshots.
- Data plane: regional Envoy fleets plus local sidecars.
- Platform services: identity, teams, goals, search, chat, analytics, admin, marketplace/extension controls.
- Image/IaC pipeline: builds and deploys proxy runtime infrastructure.

## Golden dashboards

### Product-suite map

- products by family;
- products missing owner/profile/source;
- product-profile changes pending review;
- product-to-platform dependency coverage;
- stale source-review age.

### Broker

- request rate by endpoint;
- validation failures by reason;
- operation duration p50/p95/p99;
- operation terminal state count;
- idempotency replay count;
- product-family policy rejections.

### Worker queue

- oldest message age;
- retry count;
- poison queue depth;
- cloud API error rate;
- per-resource lock contention.

### Control plane

- render duration;
- snapshot version and hash;
- xDS ACK/NACK count;
- proxy version skew;
- rollback count;
- snapshot validation failures;
- product-profile filter coverage.

### Envoy/data plane

- request rate;
- downstream and upstream error rate;
- latency p50/p95/p99;
- overload manager activation;
- circuit breaker opens;
- TLS/certificate errors;
- sidecar call latency and failures;
- per-product-family SLO burn.

### Shared platform

- identity/auth failures;
- search indexing lag and permission-filter errors;
- Rovo/agent tool-call failures and denials;
- marketplace app error/rate-limit counts;
- analytics pipeline freshness;
- admin/Guard policy push status.

## Incident: bad tenant config rejected by broker

Symptoms:

- broker validation failures spike;
- tenant deploy fails before traffic changes.

Actions:

1. Inspect operation id from deploy output.
2. Read broker audit entry for the operation.
3. Return validation reason to product team.
4. Check whether the failure is schema, ownership, product-profile, or policy related.
5. Do not bypass validation unless the platform owner approves a schema/policy change.

## Incident: product-profile mismatch

Symptoms:

- media, Git, admin, status-page, or AI-agent route behaves like a generic web route;
- auth/rate-limit/cache behavior differs from expected profile;
- product-family dashboards show abnormal errors after a config change.

Actions:

1. Identify affected product family and route.
2. Compare current service profile to expected profile in the product catalog.
3. Freeze rollout for affected service/family.
4. Re-render candidate snapshot with corrected profile.
5. Canary and verify profile-specific probes before global rollout.
6. Add regression coverage for the profile mismatch.

## Incident: worker backlog grows

Symptoms:

- queue age increases;
- operations stay `in_progress`;
- no new xDS snapshots for affected services.

Actions:

1. Check cloud provider API health and rate limits.
2. Check worker error logs by operation id.
3. Scale workers only if downstream APIs are healthy.
4. Move poison messages to quarantine after retry budget is exhausted.
5. Requeue only after the root cause is fixed.

## Incident: Envoy NACKs new snapshot

Symptoms:

- control-plane NACK count increases;
- rollout gate fails;
- affected fleet remains on previous version.

Actions:

1. Stop rollout immediately.
2. Inspect NACK detail and rendered resource diff.
3. Verify the candidate snapshot with Envoy validation tooling.
4. Roll back candidate to previous known-good if any proxy accepted it.
5. Add a regression test for the invalid render path.

## Incident: traffic regression after accepted snapshot

Symptoms:

- 5xx or latency increases after snapshot ACK;
- synthetic probes fail;
- sidecar decision errors spike.

Actions:

1. Freeze rollout and identify snapshot hash.
2. Compare route/backend/filter diff from previous known-good.
3. Roll back snapshot for affected fleet or region.
4. Check backend health to distinguish platform vs product outage.
5. If sidecar-related, verify sidecar config version and failure mode.
6. Check whether only one product family is affected; if so, apply profile-specific mitigation.
7. File post-incident action item for missing rollout health gate.

## Incident: cross-product search or AI permission leak

Symptoms:

- user sees object snippets from a product/site they cannot access;
- Rovo/agent answer references hidden content;
- audit shows a tool call outside expected product scope.

Actions:

1. Disable affected search/agent connector or tool class.
2. Preserve audit records and retrieval traces.
3. Verify source-product permission checks for the object type.
4. Rebuild affected index partitions if permissions were embedded incorrectly.
5. Add a deny-by-default regression test for stale/ambiguous permissions.
6. Notify security/compliance according to severity.

## Incident: control plane unavailable

Expected behavior:

- Envoy continues serving last-known-good config.
- New provisioning operations may complete but are not published.

Actions:

1. Confirm proxies keep serving previous snapshot.
2. Stop non-urgent deploys.
3. Restore control-plane API or fail over to standby.
4. Verify snapshot cache consistency before resuming rollout.
5. Watch for proxy reconnect storm after recovery.

## Incident: certificate expiry risk

Actions:

1. Query domain ownership table for certificates expiring within 14 days.
2. Check certificate automation logs.
3. Manually renew only through the approved certificate workflow.
4. Publish SDS update through canary rollout.
5. Verify TLS probes from every region.

## Release checklist

- Product catalog/profile changes reviewed.
- Schema migrations applied and reversible.
- xDS render tests pass.
- Envoy validation passes.
- Canary region selected.
- Rollback snapshot/image available.
- Dashboards and alerts updated.
- On-call handoff includes expected changes, product family impact, and blast radius.

## Post-incident review prompts

- Did the broker reject invalid input early enough?
- Did the product profile match the route's real behavior?
- Did the control plane validate and canary the rendered config?
- Did the data plane preserve last-known-good behavior?
- Did cross-product search/AI respect source permissions?
- Did dashboards identify the failure within the SLO detection window?
- Did operators have an obvious rollback command?
- Does the codebase need decoupling where churn concentrated?
