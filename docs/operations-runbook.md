# Operations Runbook

This runbook describes how to operate the production-grade version of the Atlassian Innerwork edge platform.

## Service map

- Broker API: accepts and validates tenant edge intent.
- Worker queue: executes cloud-side provisioning tasks.
- Durable state: stores service specs, domain ownership, operations, snapshots, rollouts, and audit events.
- Control plane: renders and publishes xDS snapshots.
- Data plane: regional Envoy fleets plus local sidecars.
- Image/IaC pipeline: builds and deploys proxy runtime infrastructure.

## Golden dashboards

### Broker

- request rate by endpoint;
- validation failures by reason;
- operation duration p50/p95/p99;
- operation terminal state count;
- idempotency replay count.

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
- snapshot validation failures.

### Envoy/data plane

- request rate;
- downstream and upstream error rate;
- latency p50/p95/p99;
- overload manager activation;
- circuit breaker opens;
- TLS/certificate errors;
- sidecar call latency and failures.

## Incident: bad tenant config rejected by broker

Symptoms:

- broker validation failures spike;
- tenant deploy fails before traffic changes.

Actions:

1. Inspect operation id from deploy output.
2. Read broker audit entry for the operation.
3. Return validation reason to product team.
4. Do not bypass validation unless the platform owner approves a schema/policy change.

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
6. File post-incident action item for missing rollout health gate.

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

- Schema migrations applied and reversible.
- xDS render tests pass.
- Envoy validation passes.
- Canary region selected.
- Rollback snapshot/image available.
- Dashboards and alerts updated.
- On-call handoff includes expected changes and blast radius.

## Post-incident review prompts

- Did the broker reject invalid input early enough?
- Did the control plane validate and canary the rendered config?
- Did the data plane preserve last-known-good behavior?
- Did dashboards identify the failure within the SLO detection window?
- Did operators have an obvious rollback command?
- Does the codebase need decoupling where churn concentrated?
