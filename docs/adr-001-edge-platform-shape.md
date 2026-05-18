# ADR-001: Use Broker + Envoy Control Plane + Regional Proxy Fleets

## Status

Accepted for this reference design.

## Context

The source video describes a platform that replaced manual or enterprise load-balancer workflows with self-service provisioning. Developers needed simple inputs, while the platform team needed central control over routing, security, observability, and operations.

## Decision

Use a layered architecture:

1. an Open Service Broker-style API for lifecycle operations;
2. asynchronous workers for cloud-side provisioning;
3. durable state as the source of truth;
4. an Envoy xDS control plane for dynamic config;
5. pre-provisioned regional Envoy proxy fleets;
6. local sidecars for complex platform concerns.

## Consequences

Benefits:

- product teams get self-service public exposure;
- platform concerns are solved once at the edge;
- configuration is validated, diffed, canaried, and rolled back centrally;
- backends avoid duplicating authentication, rate limiting, and logging logic.

Tradeoffs:

- control-plane correctness becomes critical;
- schema design must be conservative;
- platform team owns a large operational surface;
- poor rollout gates can create global blast radius.

## Rejected alternatives

### Let teams manage their own load balancers

Rejected because it duplicates effort, creates inconsistent security posture, and makes compliance evidence difficult.

### Let teams submit raw Envoy config

Rejected because raw config is too powerful and easy to misuse. The platform should expose intent, not mechanism.

### Create proxies on demand for every service

Rejected as the default because pre-provisioned fleets reduce provisioning latency and make capacity/operations more predictable. Dedicated fleets can still exist for exceptional isolation requirements.
