# Atlassian Innerwork

Production-grade reference design for an Atlassian-style self-service edge platform.

This repository reverse-engineers the grand design described in the video:

https://www.youtube.com/watch?v=55pTFVoclvE

It does not claim to contain Atlassian source code or private implementation details. It reconstructs the public architectural pattern from the talk and turns it into a buildable blueprint: self-service edge provisioning, an OSB-inspired broker, an Envoy/xDS control plane, pre-provisioned regional proxy fleets, sidecar-based platform concerns, and production hardening around validation, safety, observability, and operations.

## What is inside

- `docs/grand-design.md` — polished production architecture and operating model.
- `docs/architecture.html` — standalone dark SVG architecture diagram.
- `docs/production-grade-roadmap.md` — staged path from prototype to production.
- `docs/production-readiness-checklist.md` — launch checklist for the hardened platform.
- `docs/operations-runbook.md` — incident response and operational playbooks.
- `docs/threat-model.md` — trust boundaries, risks, and mitigations.
- `spec/openapi.yaml` — OSB-inspired broker API contract.
- `examples/edge-service.yaml` — sample developer-facing edge intent.
- `research/video-transcript.md` — timestamped transcript used as source material.
- `src/innerwork/` — executable Python model for the broker/control-plane contract.
- `tests/` — regression tests for the core invariants.

## Quick start

```bash
uvx pytest -q
```

Expected:

```text
13 passed
```

## Core idea

Developers submit a small, validated edge-service intent:

```python
EdgeServiceSpec(
    service_id="jira-web",
    owner="jira-platform",
    domains=("jira.example.com",),
    routes=(RouteRule(prefix="/", backend=Backend(name="jira", port=8080)),),
    features=("external_auth", "rate_limit", "access_logs"),
)
```

The platform turns that into:

1. durable broker state and last-operation status;
2. deterministic xDS-style snapshots;
3. Envoy listeners, virtual hosts, clusters, and filters;
4. centralized auth, authorization, rate limiting, access logging, DDoS protection, and compliance controls before traffic reaches product services.

## License

MIT
