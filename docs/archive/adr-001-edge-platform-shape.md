# ADR-001: Use Product-Suite Map + Broker + Envoy Control Plane + Regional Proxy Fleets

## Status

Accepted for this reference design.

## Context

The source video describes a platform that replaced manual or enterprise-load-balancer-oriented workflows with self-service broker provisioning and an Envoy-based regional data plane.

The Atlassian software homepage shows why this kind of shared platform matters: Atlassian exposes many products and collections that need common identity, permissions, routing, search, analytics, AI, admin, observability, and operational controls.

The design must therefore explain both sides:

1. the product suite and shared system-of-work platform;
2. the edge/control-plane mechanism that safely exposes product services.

## Decision

Use a layered reference architecture:

1. Product-suite map grounded in public homepage data.
2. Shared Atlassian Cloud Platform primitives: Home, Goals, Teams, Studio, Search, Chat, Analytics, Admin.
3. Product/service graph connecting work, knowledge, teams, code, services, assets, incidents, feedback, and strategy.
4. OSB-inspired broker for self-service edge intent.
5. Durable state and async workers for provisioning.
6. Envoy xDS control plane for deterministic runtime config.
7. Regional proxy fleets with sidecars for cross-cutting controls.

## Consequences

Positive:

- The repo is easier to read because product context appears before infrastructure mechanics.
- Product-specific edge profiles can be discussed without inventing private implementation details.
- The executable model remains small while docs cover the broader system-of-work architecture.
- Future build phases can add structured product taxonomy and policy profiles.

Trade-offs:

- The product map is inferred from public positioning, not private service boundaries.
- The repo intentionally stays a reference architecture, not a clone of Atlassian products.
- Some product capabilities are modeled as platform dependencies even when their exact internal implementation is unknown.

## Rejected alternatives

### Edge-only architecture

Rejected because it made the repo look like a load-balancer project and did not explain how the public product suite fits together.

### Product clone

Rejected because the goal is architecture reverse engineering, not recreating Atlassian applications.

### Raw Envoy configuration as tenant API

Rejected because it makes tenants responsible for unsafe low-level details and makes policy enforcement harder.

### Single monolithic product service

Rejected because the public product suite clearly spans many jobs-to-be-done and requires a shared platform plus product-specific surfaces.
