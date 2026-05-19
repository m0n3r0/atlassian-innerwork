# Product Scope

This repository builds a clean-room, open-source product named **Innerwork**. It is inspired by the public roles of **Jira** and **Confluence**, not by private Atlassian internals and not by Atlassian branding or UI.

## What we are building

Innerwork is a self-hostable work-and-knowledge application:

- a work graph inspired by Jira's public role as a work tracking and workflow engine;
- a knowledge graph inspired by Confluence's public role as durable team documentation and decision memory;
- one shared identity, permission, search, audit, and linking model across both graphs;
- a platform backend that exposes these capabilities through documented APIs and deterministic operational workflows.

The current executable app is the platform/broker proof of concept for that direction. It validates product-service intent, persists local state, exposes an OpenAPI backend, and renders deterministic control-plane snapshots. It does not yet implement the full work-item/page UI.

## What we are not building

Not building Bitbucket, Trello, Loom, Jira Service Management, Statuspage, Guard, Jira Align, or the rest of the Atlassian portfolio.

Those products stay in the research catalog only so the repo can explain where this app deliberately stops. They are not MVP scope and should not drive implementation tasks unless the roadmap is explicitly expanded later.

## Naming rule

User-facing product language should use `Innerwork`, `work graph`, `knowledge graph`, `project`, `space`, `work item`, `page`, and `link`.

Use `Jira` and `Confluence` only when describing public-source inspiration or catalog grounding. Do not use Atlassian product names in the app's own product surface.
