# Work-Graph Domain (Phase B slice 1)

This document describes the first slice of the work-and-knowledge MVP:
**Project + WorkItem with workflow transitions**, durable in SQLite,
exposed via REST under `/v1/` and via the `innerwork` CLI.

## Scope

In scope for this slice:

- `Project` (uppercase key, name, owner, created_at)
- `WorkItem` (project-scoped key like `ENG-1`, title, description,
  state, assignee, timestamps)
- Default workflow `todo -> in_progress -> done` with explicit reopen edges
- Append-only `Transition` history
- SQLite persistence in the same database file as the broker store
- REST surface under `/v1/`
- CLI commands `projects`, `project-create`, `work-items`,
  `work-item-create`, `work-item-transition`, `workflow`

Out of scope for this slice (later Phase B/D):

- Spaces, Pages, PageVersions, Comments
- Cross-graph Links between work items and pages
- Real users, groups, permissions, audit log of mutations
- Custom per-project workflows

## Default workflow

```
            ┌──────────┐   start
            │  todo    │ ◄────── (initial state)
            └────┬─────┘
                 │ in_progress
                 ▼
            ┌──────────────┐
            │ in_progress  │
            └────┬─────────┘
                 │ done
                 ▼
            ┌──────────┐
            │  done    │
            └──────────┘
```

Explicit reopen edges:

- `in_progress -> todo` (deprioritise)
- `done -> in_progress` (reopen)

Any other transition raises `InvalidTransitionError` and returns
HTTP 409 from the REST surface.

## REST endpoints

All endpoints live under `/v1/` and are independent of the broker
endpoints under `/v2/`.

```
GET    /v1/workflow
GET    /v1/projects
POST   /v1/projects
GET    /v1/projects/{project_id}
GET    /v1/projects/{project_id}/work_items?state=...
GET    /v1/work_items?project_id=...&state=...
POST   /v1/work_items
GET    /v1/work_items/{work_item_id}
GET    /v1/work_items/{work_item_id}/transitions
POST   /v1/work_items/{work_item_id}/transitions
```

### Example: create a project and a work item

```bash
curl -sX POST localhost:8000/v1/projects \
  -H 'content-type: application/json' \
  -d '{"key":"ENG","name":"Engineering","owner":"eml"}'

# {"project_id":"...","key":"ENG",...}

curl -sX POST localhost:8000/v1/work_items \
  -H 'content-type: application/json' \
  -d '{"project_id":"...","title":"Set up CI"}'
# {"work_item_id":"...","key":"ENG-1","state":"todo",...}

curl -sX POST localhost:8000/v1/work_items/{id}/transitions \
  -H 'content-type: application/json' \
  -d '{"to_state":"in_progress","actor":"eml"}'
```

## CLI

```bash
# durable demo
export INNERWORK_DATABASE_URL="sqlite:///.innerwork/innerwork.db"
uv run innerwork project-create --key ENG --name Engineering --owner eml \
  --database-url "$INNERWORK_DATABASE_URL"
uv run innerwork work-item-create \
  --project-id <project_id> --title "Set up CI" \
  --database-url "$INNERWORK_DATABASE_URL"
uv run innerwork work-item-transition \
  --work-item-id <id> --to-state in_progress --actor eml \
  --database-url "$INNERWORK_DATABASE_URL"
uv run innerwork work-items --database-url "$INNERWORK_DATABASE_URL"
```

## Storage

When the app is started with `--database-url sqlite:///path.db`, all
work-graph entities are stored in the same SQLite file as the broker's
`SqliteStateStore`, in their own tables:

- `projects`
- `project_sequences` (next per-project numeric suffix)
- `work_items`
- `work_item_transitions`

When the app is started without a database URL, the work-graph uses an
ephemeral SQLite file under the OS temp directory so the `/v1/` surface
is still exercisable. Broker behavior is unchanged.

## Workflow rules (canonical)

```python
WORKFLOW_STATES = ("todo", "in_progress", "done")
INITIAL_STATE = "todo"
ALLOWED_TRANSITIONS = {
    ("todo",        "in_progress"),
    ("in_progress", "done"),
    ("in_progress", "todo"),
    ("done",        "in_progress"),
}
```

These constants live in `src/innerwork/domain.py` and are the single
source of truth used by the model, the store, the API, and the CLI.
