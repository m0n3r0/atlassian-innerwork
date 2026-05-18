# Production OSS Grand Design

> Status: phase 0 deliverable — product thesis and lifecycle phase specification for a clean-room work + knowledge open-source application inspired by the public Atlassian Jira + Confluence pairing.
>
> This document is **not** a Jira or Confluence clone, not a description of Atlassian-internal architecture, and not a trademarked-product proposal. Every claim about the source inspiration is grounded in the repository's public-source catalog and reference docs.

## 1. Source grounding

This phase 0 output relies only on the following repository sources:

- `data/product_catalog.json` — canonical public-source product catalog.
- `docs/product-system-map.md` — reverse-engineered product/platform map.
- `docs/grand-design.md` — existing edge/control-plane reference design.
- `docs/production-grade-roadmap.md` — existing production roadmap for the reference platform.
- `research/video-transcript.md`, `research/software-page-extract.md` — public source notes.

All Atlassian product references in this design map back to `data/product_catalog.json`. Where evidence is insufficient we write "not supported by current public sources" instead of guessing.

## 2. Selected product pair

The selected inspiration pair is **Jira + Confluence**, exactly as required by the plan. The catalog roles used here are quoted directly from `data/product_catalog.json`:

| Product | Catalog family | Catalog system role | Catalog dependencies |
| --- | --- | --- | --- |
| `jira` | `teamwork_core` | Primary work graph and workflow engine. | identity, teams, goals, search, analytics, rovo |
| `confluence` | `teamwork_core` | Knowledge graph and durable decision memory. | identity, teams, search, analytics, rovo |

Both products live in the same catalog family (`teamwork_core`) and share five of six platform dependencies. That overlap is exactly what makes the pair the smallest high-leverage exercise of the system-of-work loop: identity, permissions, search, analytics, and AI-readiness are forced to be unified across two distinct graphs.

## 3. Product thesis

The open-source application we are designing is a **work-and-knowledge operating system**: a work graph (issues, projects, transitions) and a knowledge graph (pages, spaces, versions) sharing a single identity, permission, link, search, and audit model. The placeholder internal name is `innerwork-os`. No vendor brand is used in the product surface.

### 3.1 Target users

- Small-to-mid engineering and product teams that want self-hostable work tracking plus durable documents under one identity and permission model.
- OSS maintainers and platform teams that need a transparent reference implementation of a system-of-work surface, with API-first contracts and clear governance.
- Operators who need to deploy, monitor, back up, and audit the system without proprietary lock-in.

### 3.2 Non-goals

- Cloning Jira, Confluence, or any other vendor product surface, branding, schema, or private APIs.
- Reimplementing every Atlassian feature; the scope is the two graphs and the integration surface between them.
- Multi-cloud and enterprise-portfolio features before the single-cloud, single-tenant production posture is stable.
- Building an LLM/agent platform before the deterministic data, API, permission, and audit layers are sound.

### 3.3 Clean-room rules

- Use the public Atlassian software-homepage product catalog only for inspiration about *responsibilities*, not for any private-architecture claims.
- Do not invent Atlassian-internal services, schemas, team names, metrics, or compliance certifications.
- Avoid trademarked product names, logos, and slogans in the application surface and in user-facing documentation.

## 4. Architecture stance

The product blueprint sits on top of the existing edge/control-plane reference in this repository (`docs/grand-design.md`, `docs/production-grade-roadmap.md`, `src/innerwork/`). The work graph and knowledge graph are modeled as two domains under one identity, one permission, one search, and one audit pipeline. Cross-graph links are first-class entities, not free-text references.

Allowed platform-capability vocabulary (drawn from `docs/product-system-map.md` and `data/product_catalog.json`):

`home, goals, teams, studio, search, chat, analytics, admin, identity, audit`

Any design statement that references a capability outside that list must either add it to the vocabulary with a source citation or be rewritten.

## 5. Lifecycle phase model (0–10)

The phase catalog is encoded in `data/production_oss_phases.json`. Every phase carries:

- `objective`
- `jira_inspired_requirements`
- `confluence_inspired_requirements`
- `cross_product_integration_requirements`
- `build_artifacts`
- `acceptance_gates`
- `anti_hallucination_checks`
- `kanban_child_task_shape`
- `exit_criteria`

### 5.1 Phases at a glance

| # | Name | Headline objective |
| --- | --- | --- |
| 0 | Idea and public-source grounding | Lock thesis to repo-grounded sources; declare scope and non-scope. |
| 1 | Product thesis, target users, non-goals | One paragraph + three lists; no vendor-clone language. |
| 2 | Domain model and information architecture | Minimum durable domain across both graphs under shared identity. |
| 3 | API contract and permission model | OpenAPI surface, RBAC, idempotency, audit events per endpoint. |
| 4 | MVP vertical slice | End-to-end: create work item, create page, link them, permission-filtered list. |
| 5 | Collaboration, notifications, import/export | Comments, mentions, notifications, round-trippable JSON portability. |
| 6 | Search, analytics, AI-ready context | Permission-respecting search; explicit AI context boundary with redaction. |
| 7 | Reliability, security, privacy, compliance | Threat model, audit completeness, backup drills, privacy fields. |
| 8 | Deployment, operations, SLOs, observability | Reproducible deployment, SLOs, signed releases, rollback drills. |
| 9 | OSS governance, contributor experience, packaging, docs | License, CoC, security policy, governance, tagged releases. |
| 10 | Beta, migration, launch, post-launch iteration | Beta program, migration tooling, post-launch metrics loop. |

### 5.2 How to read a phase

For phase N, the `data/production_oss_phases.json` entry is the source of truth. This markdown summary exists for human readability; tests in `tests/test_production_oss_phases.py` (added in the engineering phase of this task graph) validate the JSON against the same structural requirements documented above.

Every phase ends with `block_reason_on_finish: review-required` so the orchestrator gates progression rather than auto-completing work that still needs human or reviewer judgment.

## 6. Anti-hallucination checklist (cross-phase)

These checks apply to every phase and every downstream Kanban child task. The phase catalog encodes phase-specific variants in `anti_hallucination_checks`.

- Reject any product reference outside `selected_products` ∪ `allowed_platform_capabilities`.
- Reject any architectural claim that names an Atlassian-internal service, schema, or team.
- Reject any compliance, certification, customer, revenue, or benchmark claim that is not backed by a reproducible artifact in the repo.
- When evidence is insufficient, write "not supported by current public sources" instead of guessing.
- Verify, with `grep` or equivalent, that every changed file actually contains the changes a Kanban worker claims to have made.

## 7. Pointers

- Machine-readable phase catalog: `data/production_oss_phases.json`.
- Public-source catalog: `data/product_catalog.json`.
- Reverse-engineered product/platform map: `docs/product-system-map.md`.
- Existing production roadmap for the underlying edge/control-plane platform: `docs/production-grade-roadmap.md`.
- Existing grand design for the underlying platform: `docs/grand-design.md`.

The autonomous Kanban execution playbook (`docs/autonomous-kanban-playbook.md`) and the validation tests (`tests/test_production_oss_phases.py`) are produced by downstream tasks in this stack.
