# Overview

This repository is a readable, production-oriented reverse engineering of Atlassian's public system-of-work architecture.

It combines two public inputs:

1. the video at https://www.youtube.com/watch?v=55pTFVoclvE, which explains a self-service edge/load-balancing platform built around a broker, workers, Envoy, xDS, regional proxy fleets, and platform sidecars;
2. the public Atlassian software homepage at https://www.atlassian.com/software, which shows the current product portfolio and how Atlassian groups products into collections, roles, and platform capabilities.

The product scope is deliberately narrower than the full portfolio: **Innerwork** is a Jira/Confluence-inspired work-and-knowledge app, plus a platform/backend proof of concept that makes it runnable. Other Atlassian products are catalog context, not implementation scope.

The result is not an exact internal Atlassian design. It is a clean-room model of the architecture pattern.

## Product scope in one sentence

Innerwork is building the Jira + Confluence lane only: a work graph plus a knowledge graph with shared identity, permissions, search, links, and audit. Bitbucket, Trello, Loom, Jira Service Management, Statuspage, Guard, Jira Align, and other cataloged products are outside the MVP and should be treated as context only.

## One-page mental model

```text
Customers and teams
        |
        v
Product experiences
Jira | Confluence | Loom | Trello | JSM | Bitbucket | Rovo | Focus | Talent | Align | ...
        |
        v
System-of-work platform
Identity | Home | Goals | Teams | Search | Chat | Studio | Analytics | Admin | Marketplace
        |
        v
Product/service mesh
Work graph | Knowledge graph | Team graph | Asset graph | Incident graph | Delivery graph
        |
        v
Self-service edge platform
Broker API | async workers | durable state | xDS renderer | rollout controller
        |
        v
Regional data plane
CloudFront/NLB | Envoy fleets | auth/rate-limit/policy sidecars | access logs | metrics
        |
        v
Product backends and internal services
```

## Why the video and product page fit together

The video focuses on the platform mechanics: how a large company can stop hand-crafting load balancers and instead give product teams a safe self-service abstraction.

The product page shows why that abstraction matters: Atlassian now exposes many product experiences, collections, and cross-product platform features. A system this broad needs common capabilities for routing, identity, observability, AI, analytics, administration, marketplace integration, compliance, and operational safety.

## Product families reconstructed from the homepage

| Family | Products | What the family contributes |
| --- | --- | --- |
| Teamwork core | Jira, Confluence, Loom, Trello, Rovo | Work items, knowledge, async video, lightweight boards, AI search/chat/agents. |
| Software delivery | Bitbucket, Pipelines, Rovo Dev, DX | Source control, CI/CD, developer agents, engineering metrics, developer intelligence. |
| Service management | Jira Service Management, Customer Service Management, Assets, Statuspage, Guard | Service workflows, customer service, CMDB/assets, incident comms, cloud security. |
| Product discovery | Jira Product Discovery, Feedback, Rovo | Ideas, feedback intake, prioritization, roadmaps, AI synthesis. |
| Strategy | Focus, Talent, Jira Align | Goals, strategic planning, workforce planning, enterprise work alignment. |
| Cloud platform | Home, Goals, Teams, Studio, Search, Chat, Analytics, Admin | Shared foundation connecting apps into a system of work. |
| Ecosystem | Marketplace, Community, Partners, Developer resources | Extensibility, support, adoption, integrations. |

See `product-system-map.md` for the full product/collection/platform reconstruction.

## Repository shape

- `product-system-map.md` explains the product surface.
- `grand-design.md` explains the shared platform and edge system.
- `architecture.html` visualizes the product/platform/edge stack.
- `production-grade-roadmap.md` turns the design into build phases.
- `operations-runbook.md`, `threat-model.md`, and `production-readiness-checklist.md` make it operational.
- `src/innerwork` and `tests` keep the architecture executable enough to catch broken invariants.

## What to copy from this design

Good patterns to copy:

- Make internal platforms product-like: stable APIs, clear docs, ownership, examples, and support.
- Give product teams intent-level abstractions, not raw proxy/networking internals.
- Centralize high-risk cross-cutting concerns: identity, authorization, rate limits, logs, compliance, rollout safety.
- Keep the data plane boring and resilient: serve last-known-good config, drain cleanly, canary every change.
- Treat product integrations as graph problems: work graph, knowledge graph, team graph, service graph, and asset graph.

What not to copy blindly:

- Do not build a multi-region edge platform before one region and one product path are stable.
- Do not let tenants submit arbitrary Envoy config.
- Do not introduce AI/agent features without permissioning, provenance, auditability, and rollback.
- Do not make a product-suite map imply private implementation details.
