# Documentation Index

This repo builds **Innerwork**, a clean-room, self-hostable work-and-knowledge
application inspired by the public roles of Jira and Confluence. The
authoritative scope and naming rules live in `product-scope.md`. Everything
else either describes what currently runs or what is planned next.

## Start here

1. `product-scope.md` — exact product boundary: Innerwork = Jira/Confluence-inspired work + knowledge only.
2. `overview.md` — short, current explanation of the repo and where the build is.
3. `live-application.md` — how to run the app (Python, Docker), HTTP endpoints, CLI.
4. `docker-poc.md` — Docker Compose proof of concept and smoke tests.

## Product-domain reference

These document the currently implemented MVP slices under `/v1/`.

- `work-graph-domain.md` — projects, work items, workflow transitions (Phase B slice 1).
- `knowledge-graph-domain.md` — spaces, pages, immutable page versions, cross-graph WorkItem ↔ Page links (Phase B slice 2).
- `comments-and-idempotency.md` — work-item / page comments and the `X-Idempotency-Key` contract on all `/v1/` mutations (Phase B slice 3).
- `collaboration.md` — Phase F slice: `@handle` mentions, in-process notification dispatch (quiet hours + token-bucket rate limit), and deterministic JSON import/export round-trip.
- `production-grade-roadmap.md` — phased roadmap from PoC to production.

## Archive

Earlier exploratory documents that described a broader Atlassian-suite
broker/edge-platform vision now live in `archive/`. They are kept for
historical context only and **must not** drive new implementation work;
the product scope is locked to Innerwork (work graph + knowledge graph).

- `archive/grand-design.md`, `archive/product-system-map.md`,
  `archive/production-oss-grand-design.md` — the original Atlassian-suite
  reconstruction documents.
- `archive/operations-runbook.md`, `archive/threat-model.md`,
  `archive/production-readiness-checklist.md` — operations/security/readiness
  docs aimed at the broker/edge platform, not the Innerwork product-domain
  surface. They will be rewritten against the product-domain API once Phase D
  (identity/permission/audit) lands.
- `archive/autonomous-kanban-playbook.md`,
  `archive/adr-001-edge-platform-shape.md`, `archive/architecture.html` —
  historical execution playbook and edge ADR; superseded by the current
  roadmap and the product-domain ADR work to come.
