# Documentation site — outline only

Phase 9 produces the **outline** of a future documentation site, not the site itself. This file exists so the next maintainer who has the time can stand the site up without re-doing the information-architecture work.

## Recommended generator: mkdocs-material

Rationale: the repo already keeps docs as flat markdown under `docs/*.md`. mkdocs-material reuses them with minimal config, has no JavaScript build toolchain, and produces a site that is browsable offline. Sphinx is also viable but adds a heavier toolchain (reStructuredText familiarity, more themes to choose between, autodoc setup). Pick mkdocs-material unless someone has a strong reason otherwise.

## Proposed `mkdocs.yml` (NOT committed)

The following stub is for reference. **It is not committed as `mkdocs.yml` in this phase**, because committing it would force a maintainer decision on hosting, build pipeline, and the `mkdocs-material` dependency that no one has signed up for yet.

```yaml
site_name: Atlassian Innerwork
site_description: Open-source reference design for a Jira/Confluence-inspired platform operating model.
site_url: https://m0n3r0.github.io/atlassian-innerwork/  # placeholder; not deployed
repo_url: https://github.com/m0n3r0/atlassian-innerwork
repo_name: m0n3r0/atlassian-innerwork
edit_uri: edit/main/

theme:
  name: material
  features:
    - navigation.sections
    - navigation.expand
    - navigation.top
    - content.code.copy
    - search.suggest

markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true
  - tables
  - toc:
      permalink: true

nav:
  - Home: README.md
  - Getting Started:
      - Run locally with Docker: docs/docker-poc.md
      - Live application guide: docs/live-application.md
  - Architecture:
      - Overview: docs/overview.md
      - Grand design: docs/grand-design.md
      - Production OSS grand design: docs/production-oss-grand-design.md
      - Product scope: docs/product-scope.md
      - Work-graph domain: docs/work-graph-domain.md
      - Knowledge-graph domain: docs/knowledge-graph-domain.md
      - Collaboration / AI context: docs/collaboration.md
      - Comments and idempotency: docs/comments-and-idempotency.md
      - Phase 6 snapshot: docs/phase-6.md
  - Operations:
      - Runbook: docs/operations-runbook.md
      - SLOs: docs/slos.md
      - Observability: docs/observability.md
      - Release flow: docs/release.md
  - Security:
      - Threat model: docs/threat-model.md
      - Security policy: SECURITY.md
  - Contributing:
      - Contributing: CONTRIBUTING.md
      - Contributor guide: docs/contributor-guide.md
      - Code of Conduct: CODE_OF_CONDUCT.md
      - Governance: GOVERNANCE.md
      - Maintainers: MAINTAINERS.md
  - Reference:
      - Production-grade roadmap: docs/production-grade-roadmap.md
      - Production-readiness checklist: docs/production-readiness-checklist.md
```

## Information architecture

Existing `docs/*.md` and the new root-level governance docs group into six IA buckets:

- **Getting Started** — `README.md`, `docs/docker-poc.md`, `docs/live-application.md`.
- **Architecture** — `docs/overview.md`, `docs/grand-design.md`, `docs/production-oss-grand-design.md`, `docs/product-scope.md`, `docs/work-graph-domain.md`, `docs/knowledge-graph-domain.md`, `docs/collaboration.md`, `docs/comments-and-idempotency.md`, `docs/phase-6.md`.
- **Operations** — `docs/operations-runbook.md`, `docs/slos.md`, `docs/observability.md`, `docs/release.md`.
- **Security** — `docs/threat-model.md`, `SECURITY.md`.
- **Contributing** — `CONTRIBUTING.md`, `docs/contributor-guide.md`, `CODE_OF_CONDUCT.md`, `GOVERNANCE.md`, `MAINTAINERS.md`.
- **Reference** — `docs/production-grade-roadmap.md`, `docs/production-readiness-checklist.md`.

`docs/autonomous-kanban-playbook.md` is intentionally not in the navigation — it documents the development workflow, not the product, and would confuse a first-time reader.

## What phase 9 explicitly does NOT do

- Does **not** commit `mkdocs.yml`.
- Does **not** add `mkdocs-material` to `pyproject.toml` (neither in `dependencies` nor in `[dependency-groups].dev`).
- Does **not** deploy a site.
- Does **not** add a GitHub Pages workflow.

These are honest deferrals, not missed deliverables. A future phase will stand the site up once the maintainer commits the build/deploy time and picks a hosting target (GitHub Pages is the obvious default but is not yet chosen).
