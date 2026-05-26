# Product System Map

> Source: https://www.atlassian.com/software, extracted from the public homepage text and navigation. This is a product-architecture reconstruction, not a claim about private Atlassian internals.

## Executive summary

The software homepage presents Atlassian as a connected system of work. Its public surface is not just a list of apps; it is a layered operating model:

1. product experiences for teams;
2. curated collections for end-to-end jobs;
3. role-based entry points for developers, product managers, IT, business teams, and leaders;
4. a cloud platform foundation: Home, Goals, Teams, Studio, Search, Chat, Analytics, Admin;
5. ecosystem surfaces: Marketplace, Community, Partners, Developer resources.

The most important reverse-engineered design point is that the platform must maintain shared graphs across products:

- work graph: issues, projects, goals, plans, incidents, tasks;
- knowledge graph: pages, videos, decisions, comments, artifacts;
- team graph: people, groups, ownership, permissions, expertise;
- delivery graph: repositories, pull requests, builds, deployments, services;
- service graph: requests, incidents, assets, status, customers;
- strategy graph: goals, investments, teams, capacity, delivery outcomes.

Rovo and the Atlassian Cloud Platform then sit across those graphs as a search/chat/agent layer.

## Public catalog: products, capabilities, and ecosystem surfaces

| Surface | Homepage positioning | Reverse-engineered role in the system |
| --- | --- | --- |
| Jira | Flexible project management; AI-powered project management; plan, track, deliver ideas. | Primary work graph: issues, projects, planning, execution state, workflow automation. |
| Confluence | Knowledge, all in one place; docs, discussion, organized work. | Knowledge graph and decision memory: pages, plans, requirements, project context. |
| Loom | Quick async video updates; video messages and AI-powered meeting recaps. | Rich communication and meeting-memory layer attached to work and knowledge. |
| Trello | Visual boards for organizing projects and tasks. | Lightweight task/kanban surface for teams that do not need full Jira workflows. |
| Rovo | AI-powered Search, Chat, Agents, Studio-built agents/apps. | Cross-product AI layer over work, knowledge, people, and service graphs. |
| Jira Service Management | AI-powered service at scale. | ITSM/ESM workflow engine: requests, incidents, changes, service operations. |
| Customer Service Management | AI-powered customer service with context. | Customer-facing service workflows connected to product and support context. |
| Assets | Visibility into dependencies, assets, configuration items, incident troubleshooting, change risk. | CMDB/asset graph for service management and operational risk. |
| Statuspage | Incident communication that reduces support floods. | External service-status and incident communication surface. |
| Guard | Company-wide visibility, security policies, and cloud control. | Organization-wide security/control plane for Atlassian Cloud. |
| Bitbucket | Git repositories, pull requests, inline comments. | Source-code system and code-review graph. |
| Pipelines | CI/CD automation in Bitbucket. | Build/deploy execution graph connected to source and service ownership. Modeled separately because the homepage presents it as a software-collection item and product card. |
| Rovo Dev | Agentic AI for developers; productivity and quality across SDLC. | Developer-agent layer over repos, issues, builds, docs, and service context. |
| DX | Measures and improves productivity, quality, and speed with AI-native SDLC. | Engineering metrics and developer-experience intelligence. |
| Jira Product Discovery | Capture feedback, prioritize ideas, roadmaps tied to Jira delivery. | Product-intake and prioritization layer linking discovery to delivery. |
| Feedback | Listed with Jira Product Discovery and Rovo. | Feedback intake/synthesis capability that feeds product discovery; modeled as a homepage capability. |
| Focus | Enterprise-scale strategic planning; connects strategy to goals, work, people, and funds. | Strategy execution layer tying investments and goals to work and outcomes. |
| Talent | Knowledge workforce planning. | Workforce/capacity planning layer for strategic execution. |
| Jira Align / Align | Enterprise-wide work planning and value; planning/delivery aligned to strategy. | Enterprise agile planning and portfolio alignment. |
| Bamboo | Continuous integration, deployment, release management. | Legacy/alternate CI/CD and release management path. |
| SourceTree | Git/Mercurial desktop client. | Local developer workflow client for repositories. |
| Marketplace | Connect thousands of apps to Atlassian products. | Ecosystem/resource surface for extension and partner apps. |
| Community | Learn, connect, grow. | Ecosystem/resource surface for adoption, support, and knowledge-sharing. |
| Partners | Consulting, training, customization support. | Ecosystem/resource surface for enterprise adoption and services. |
| Developer resources | Developer resources and documentation. | Ecosystem/resource surface for APIs, SDKs, integration docs, and extension guidance. |

## Collections reverse-engineered from the homepage

The homepage groups products into collections. These are important because they reveal the jobs-to-be-done Atlassian is optimizing for.

| Collection | Products shown | Job-to-be-done | Platform implication |
| --- | --- | --- | --- |
| Teamwork | Jira, Confluence, Loom | Turn goals and projects into visible, documented, asynchronous work. | Requires identity, notifications, links, comments, search, and shared permissions. |
| Strategy | Focus, Talent, Align / Jira Align | Connect strategy, people, funding, and delivery. | Requires portfolio hierarchy, capacity planning, outcome metrics, and rollups. |
| Service | Jira Service Management, Customer Service Management, Assets | Deliver internal and external service with context. | Requires request channels, SLAs, assets/CMDB, incident/change workflows, customer context. |
| Software | Rovo Dev, DX, Pipelines, Bitbucket | Ship high-quality software fast. | Requires repo/build/service graph, developer agents, delivery metrics, service ownership. |
| Product | Jira Product Discovery, Feedback, Rovo | Build products with confidence. | Requires feedback intake, prioritization, roadmaps, AI synthesis, Jira delivery links. |

## Role-based entry points

| Role | Products emphasized | Architectural reading |
| --- | --- | --- |
| Developers | Jira, Bitbucket, Rovo Dev, Pipelines, DX, Rovo | Developers need work context, code, CI/CD, service ownership, and AI assistance in one loop. |
| Product managers | Jira Product Discovery, Jira, Confluence, Loom, Feedback, Rovo | PMs need feedback, prioritization, documents, roadmaps, and delivery traceability. |
| IT professionals | Jira Service Management, Guard, Rovo | IT needs service workflows, security governance, and AI-assisted knowledge/search. |
| Business teams | Jira, Confluence, Trello, Loom, JSM, Customer Service Management, Rovo | Non-engineering teams need lighter work tracking, docs, async updates, service channels, AI. |
| Leadership teams | Focus, Talent, Align, Rovo | Leaders need strategy, capacity, delivery outcomes, and cross-product synthesis. |

## Atlassian Cloud Platform foundation

The homepage explicitly calls out the Atlassian Cloud Platform as "the connected foundation of your system of work" and lists:

- Home;
- Goals;
- Teams;
- Studio;
- Search;
- Chat;
- Analytics;
- Admin.

`data/product_catalog.json` stores the structured catalog and intentionally separates products, homepage capabilities, ecosystem resources, collections, and platform capabilities so the docs do not overstate all surfaces as equivalent software products.

Reverse-engineered platform responsibilities:

| Platform capability | Responsibility | Why it matters |
| --- | --- | --- |
| Home | Personalized work entry point. | Aggregates work across products so users do not start from app silos. |
| Goals | Goal/objective graph. | Connects strategy and execution across Jira, Focus, Align, Confluence, and analytics. |
| Teams | People, groups, expertise, ownership. | Powers permissions, notifications, routing, service ownership, and Rovo context. |
| Studio | Custom agents, automations, apps. | Allows customers/teams to extend the system without changing core products. |
| Search | Cross-product search. | Requires indexing and permission filtering across work, docs, video, code, service objects. |
| Chat | Conversational interface. | Turns the graph into an interactive work assistant. |
| Analytics | Cross-product reporting. | Provides leadership, operations, productivity, and delivery insight. |
| Admin | Organization, identity, policy, security. | Controls users, products, permissions, domains, compliance, audit, and Guard policies. |

## Shared platform dependency vocabulary

`platform_capabilities` lists the eight cloud-platform surfaces named on the public homepage: Home, Goals, Teams, Studio, Search, Chat, Analytics, and Admin.

Some catalog entries also depend on shared primitives that are not separately presented as homepage platform cards, such as identity, audit, billing, or Rovo as a cross-product AI dependency. Tests keep that allowed vocabulary explicit so it does not become an unbounded free-text field.

## Product-to-platform dependency map

| Product | Identity/Admin | Search/Knowledge | Work graph | Team graph | Analytics | AI/Rovo | Edge exposure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Jira | yes | partial | primary | yes | yes | yes | public app/API |
| Confluence | yes | primary | linked | yes | yes | yes | public app/API |
| Loom | yes | primary media | linked | yes | yes | yes | public app/API/media |
| Trello | yes | partial | primary lightweight | yes | basic | yes | public app/API |
| Rovo | yes | primary cross-product | reads/actions | yes | yes | primary | public app/API/agents |
| JSM | yes | knowledge-backed | service work | yes | yes | yes | public portal/API |
| Customer Service Management | yes | knowledge-backed | customer service work | yes | yes | yes | public portal/API |
| Assets | yes | indexed entities | service-linked | ownership | yes | yes | internal/public API |
| Statuspage | yes | incident-linked | incident comms | ownership | yes | optional | public status edge |
| Guard | yes | audit/search | policy objects | org/team scope | yes | yes | admin/security edge |
| Bitbucket | yes | code search | PR/work links | ownership | yes | yes | git/API edge |
| Pipelines | yes | logs/artifacts | build work | ownership | yes | yes | CI/CD APIs |
| Rovo Dev | yes | code/docs/search | issue/PR actions | ownership | yes | primary | agent APIs |
| DX | yes | delivery context | delivery metrics | ownership | primary | yes | analytics APIs |
| JPD/Feedback | yes | feedback/search | discovery work | yes | yes | yes | public app/API |
| Focus/Talent/Align | yes | strategy docs | plans/goals | capacity | primary | yes | enterprise app/API |

## Reverse-engineered domain model

```text
Organization
  ├─ Users / Groups / Teams
  ├─ Products / Sites / Admin policies
  ├─ Goals / Strategy / Investments
  ├─ Work Items / Projects / Plans
  ├─ Knowledge Objects / Videos / Decisions
  ├─ Repositories / Pull Requests / Builds / Deployments
  ├─ Services / Components / Assets / Incidents / Status
  ├─ Feedback / Ideas / Roadmaps
  └─ AI Agents / Automations / Marketplace Apps
```

The common platform value is that each object links to other objects without copying the whole world into every product. Jira issues can link to Confluence docs, Loom videos, Bitbucket PRs services, Assets objects, JSM incidents, Focus goals, and Rovo agent context.

## Implications for the edge/control-plane design

A product suite this broad should not require every product team to implement public exposure, auth, logging, compliance, routing, DDoS protection, and incident handling separately. The video's self-service edge platform is the infrastructure answer to the product map.

Product-specific edge requirements:

| Product type | Edge requirements |
| --- | --- |
| Work/docs apps | HTTP routing, auth, session/cookie safety, API rate limits, access logs. |
| Media/video | upload/download paths, larger payloads, streaming/CDN behavior, content scanning. |
| Git/code | Git HTTP/SSH, webhooks, repository APIs, build artifact paths. |
| CI/CD | long-running callbacks, artifact storage, webhook ingress, runner egress policy. |
| Service portals | anonymous/customer portals, strict tenant isolation, SLA-sensitive uptime. |
| Status pages | highly cacheable public pages that must remain available during incidents. |
| AI agents | scoped tool calls, audit trails, prompt/data boundaries, rate/cost governance. |
| Admin/security | privileged routes, stricter auth, policy enforcement, high audit requirements. |

## Production design principle

The product catalog tells us what the platform must optimize for:

- shared identity and permissions across every surface;
- cross-product search and graph traversal;
- consistent API and webhook behavior;
- product-specific routing profiles without product-specific edge stacks;
- unified observability and incident response;
- central policy with local product ownership;
- AI agents that act only inside permissioned, auditable boundaries.
