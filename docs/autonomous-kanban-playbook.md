# Autonomous Kanban Execution Playbook

> Status: phase 1 deliverable — engineering playbook for driving the production OSS grand design (`docs/production-oss-grand-design.md`, `data/production_oss_phases.json`) from idea to launch using Hermes Kanban with minimal human intervention.
>
> This playbook is **mechanics only**. The product thesis, allowed vocabulary, and lifecycle phases are owned by the grand design and the machine-readable phase catalog; this document only specifies how to execute them safely on the Kanban board.

## 1. Source grounding for this playbook

Every rule below is grounded in repository files that already exist:

- `docs/production-oss-grand-design.md` — phase summaries and clean-room rules.
- `data/production_oss_phases.json` — machine-readable phase catalog (11 phases, ids 0-10, `selected_products = ["jira", "confluence"]`).
- `data/product_catalog.json` — public-source product/capability catalog used for all grounding checks.
- `docs/grand-design.md`, `docs/production-grade-roadmap.md` — the underlying edge/control-plane reference platform.

The Kanban worker contract referenced here matches the `kanban-worker` skill that ships with this repo's operator environment (`kanban_show`, `kanban_complete`, `kanban_block`, `kanban_comment`, `kanban_create`, `kanban_heartbeat`).

## 2. Execution mechanics

### 2.1 Serial review-gated stack

The default shape for one phase is a single stack of tasks linked by `parents=[previous_task_id]`:

```
phase N PM/spec  ->  phase N engineering  ->  phase N test/integrate  ->  phase N review/merge
       \                                                                       /
        +------------------- review-required block at each handoff ------------+
```

- Each task carries one phase id and at most one `kind` (`spec`, `engineering`, `test`, `review`).
- Tasks always end with `kanban_block(reason="review-required: ...")` after the worker writes files, unless the task is a pure review task that itself approves or rejects.
- A reviewer task (human-driven via `kanban_show` + comments, or an automated reviewer profile) is the only thing allowed to `kanban_complete` a `spec` / `engineering` / `test` predecessor by transitioning state through comments and an explicit unblock.

### 2.2 Fan-out / fan-in research

When a phase needs parallel research (for example phase 6 search vs. analytics vs. AI context boundaries), use a fan-out of sibling tasks that share the same parent and a single fan-in synthesizer:

```
phase 6 spec
  |-- phase 6 research: search           ----+
  |-- phase 6 research: analytics        ----+--> phase 6 synthesis -> phase 6 engineering
  +-- phase 6 research: ai context       ----+
```

Rules:

- Sibling research tasks must have non-overlapping file partitions and read-only access; they may only write to a single scratch artifact path agreed in the spec task.
- The synthesizer reads the prior tasks' `kanban_show` handoffs (not by re-reading every file) and produces one merged design document.
- Maximum fan-out width is 4 to keep the review surface tractable.

### 2.3 TDD discipline

For every phase whose `build_artifacts` include code or schemas:

1. The `test` task is created **before** the `engineering` task that will satisfy it, with `parents=[spec_task_id]` so it cannot run before the spec is approved.
2. The `engineering` task lists the same test file in its body and must run `uvx pytest -q` plus `uvx ruff check .` and report exit codes in its completion `metadata`.
3. The engineering task may not modify the test file; if the test is wrong, it must `kanban_block(reason="review-required: test contract appears incorrect because ...")` instead of silently rewriting the spec.

### 2.4 Review-required blocks

The default end-state for a non-review worker is **block**, not **complete**, when the task ships code or doc changes that need human or reviewer-agent eyes. Use the following block reason shapes:

- `review-required: phase N spec ready — see grand design section X` for spec tasks.
- `review-required: phase N engineering ready — N files changed, tests green, see metadata` for engineering tasks.
- `review-required: phase N tests ready — full suite green` for test tasks.

Before blocking, the worker must:

1. Post a `kanban_comment` with the structured handoff (changed files, commands run, exit codes, diff path, decisions). This is the durable record the reviewer reads.
2. Confirm with `grep` or equivalent that every file claimed in the comment actually contains the expected text on disk.

### 2.5 Completion contracts

`kanban_complete` is reserved for:

- Reviewer profiles that have just approved a predecessor through comments.
- Pure orchestration tasks that successfully fanned out children and do not themselves ship artifacts (their `metadata` lists `created_cards`).
- Test or lint tasks whose only deliverable is "the suite is green" and which have no follow-up review.

`metadata` shape used in this stack:

```json
{
  "phase": 4,
  "task_kind": "engineering",
  "changed_files": ["docs/production-oss-grand-design.md", "data/production_oss_phases.json"],
  "tests_run": 27,
  "tests_passed": 27,
  "ruff_rc": 0,
  "pytest_rc": 0,
  "diff_path": ".hermes/kanban/diffs/<task_id>.patch",
  "decisions": ["..."],
  "anti_hallucination": "all 11 phases grounded; selected_products unchanged"
}
```

### 2.6 Non-hallucination checks

These checks are mandatory in every worker run and are encoded as both manual reviewer steps and (where possible) executable tests. They map directly to the cross-phase checklist in `docs/production-oss-grand-design.md` section 6.

Manual checks per task:

1. **Product reference scope.** Every product mention is in `data/production_oss_phases.json#/selected_products` or referenced via the allowed platform vocabulary in `allowed_platform_capabilities`. Anything else is rewritten or removed.
2. **Architectural claim scope.** No statement names an Atlassian-internal service, schema, team, customer, revenue figure, or compliance certification.
3. **Evidence on disk.** Every claim in the worker's completion `summary` matches a file on disk. Reviewer runs `grep -F` against `changed_files` to confirm.
4. **Insufficient-evidence policy.** Anywhere evidence is missing, the worker wrote `"not supported by current public sources"` instead of guessing.
5. **No clone language.** No trademarked product names, logos, or slogans appear in the application surface; "Jira" and "Confluence" appear only as labelled inspiration sources in the design docs.

Executable checks (added by phase 2 test task; see `tests/test_production_oss_phases.py`):

- Phase ids are exactly `0..10`.
- Every phase has non-empty `objective`, `acceptance_gates`, `anti_hallucination_checks`, `exit_criteria`, and `kanban_child_task_shape`.
- `selected_products == ["jira", "confluence"]`.
- Every product token referenced inside a phase body is in `selected_products` ∪ `allowed_platform_capabilities` ∪ the platform-dependency token set drawn from `data/product_catalog.json`.

## 3. Per-phase Kanban task templates

Each phase (0-10) maps to up to four canonical Kanban tasks. The `kanban_child_task_shape` field in `data/production_oss_phases.json` is the source of truth for the spec task; the engineering / test / review variants follow the same pattern with the assignee and deliverables adjusted per the table below.

### 3.1 Canonical task kinds

| Kind | Assignee profile | Purpose | Default ends with |
| --- | --- | --- | --- |
| `spec` | `atlassianpm` (phases 0-1, 9-10) or `atlassianeng` (phases 2-8) | Write/refresh the design and acceptance gates. | `kanban_block(review-required)` |
| `engineering` | `atlassianeng` | Implement artifacts: data, schemas, code, docs. | `kanban_block(review-required)` |
| `test` | `atlassianeng` | Add or run validation; never modifies engineering artifacts. | `kanban_block(review-required)` if changes; `kanban_complete` if pure run |
| `review` | reviewer profile (operator-driven for now) | Reads handoffs, approves or requests changes via comments. | `kanban_complete` of predecessors then `kanban_complete` of self |

### 3.2 Template body (engineering task)

```
# Phase N engineering: <short headline>

Parent task: <spec_task_id>
Phase: N (see data/production_oss_phases.json#/phases/N)

## Files

- Read: docs/production-oss-grand-design.md, data/production_oss_phases.json
- Read: <phase-specific evidence files>
- Modify or Create: <phase-specific build_artifacts>

## Steps

1. Re-read the phase entry in data/production_oss_phases.json#/phases/N.
2. Implement the listed build_artifacts; do not introduce capabilities outside allowed_platform_capabilities.
3. Run uvx ruff check . and uvx pytest -q. Capture exit codes.
4. Post a kanban_comment with changed_files, exit codes, and decisions.
5. kanban_block(reason="review-required: phase N engineering ready").

## Acceptance

- All acceptance_gates and anti_hallucination_checks for phase N pass.
- ruff and pytest exit 0.
- No claim references an Atlassian-internal service, schema, team, or undocumented capability.
```

### 3.3 Review gates per phase

Every phase has a review gate enforced by a `review` task before the next phase starts. The gate checklist below is the minimum a reviewer (human or agent) must check; phase-specific gates from `acceptance_gates` are added on top.

Universal review gate:

1. `data/production_oss_phases.json` validates (`tests/test_production_oss_phases.py` is green).
2. All `changed_files` reported in the predecessor's handoff exist on disk and contain the claimed substrings.
3. No new top-level files or directories outside what the phase's `build_artifacts` declared.
4. No reference to capabilities or products outside the catalog-grounded vocabulary.
5. No new dependencies added without an ADR-style note in `docs/`.

Phase-specific review gate examples:

- Phase 3 (API + permissions): every endpoint has an explicit permission, idempotency rule, and audit-event mapping.
- Phase 4 (MVP slice): a single linear path creates a work item, creates a page, links them, and lists them filtered by permission; the path is covered by tests.
- Phase 7 (security/privacy): a written threat model exists; backup/restore drill is described; PII fields are annotated.
- Phase 8 (deployment/SLOs): SLOs are numerical and tied to monitorable signals; rollback steps are described; releases are signed.
- Phase 9 (OSS governance): repository contains LICENSE, CODE_OF_CONDUCT, SECURITY.md, CONTRIBUTING.md, and a written governance model.
- Phase 10 (beta/launch): migration script and post-launch metric loop are described; rollback plan exists.

## 4. Iteration policy

The board is allowed to loop a phase up to **three times** before requiring human escalation. The loop:

1. Reviewer rejects via comment + unblock without `kanban_complete`-ing the predecessor; the predecessor is reopened.
2. The same worker profile (or a fresh task with the same assignee) addresses the comments and re-blocks `review-required`.
3. If a third attempt still fails the gate, the reviewer escalates by `kanban_block`-ing the chain with reason `human-decision-required: phase N stuck after 3 attempts — <one-line reason>` and stops spawning children.

Fix tasks vs. rework:

- Small in-place corrections (typos, missing test cases, missed grep match) are addressed by reopening the existing task via comment + unblock.
- Larger corrections (missed requirement, wrong design choice, drift from grounding) are addressed by spawning a `kanban_create` fix task with `parents=[failing_task_id]` so the chain is auditable; the failing task stays blocked until the fix lands.

Do not advance: a phase that is still in `blocked` or `review-required` must not have its successor `engineering` task started. Reviewers enforce this by refusing to `kanban_create` the successor until the predecessor is `done`.

## 5. Production-readiness gates

These gates are the autonomous board's stop-line before declaring the open-source application "production ready". They map onto the existing `docs/production-readiness-checklist.md` and the underlying platform's `docs/production-grade-roadmap.md` rather than duplicating them.

| Gate | Source of truth | Owning phase |
| --- | --- | --- |
| Security | `docs/threat-model.md` + phase-7 anti-hallucination checks | 7 |
| Reliability | `docs/operations-runbook.md` + phase-8 SLO definitions | 8 |
| Packaging | OSS release artifacts (tagged release, signed checksums) | 9 |
| CI | `uvx ruff check .` and `uvx pytest -q` are wired into the repo's CI workflow | 9 |
| Documentation | `docs/README.md` lists every published doc, including this playbook and the grand design | 9 |
| Governance | `LICENSE`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CONTRIBUTING.md`, and a governance model exist at repo root | 9 |
| Operations | Backup/restore drill described and rehearsed; rollback documented | 8 |

A phase 10 launch task must `kanban_block(reason="release-gate")` until every gate above has a green review task on the board.

## 6. Autonomous stop conditions

The board halts itself (any task `kanban_block`s with the listed reason) when an external dependency or safety boundary appears. The worker must not attempt to bypass these:

1. **Auth wall.** Any external resource that requires non-public credentials. Block with reason `auth-wall: <resource>`.
2. **Missing public evidence.** A claim cannot be grounded in `data/product_catalog.json` or the listed `research/` files. Block with reason `evidence-missing: <claim>` and propose either deleting the claim or replacing it with `"not supported by current public sources"`.
3. **Unsafe action.** Anything that would touch a real production system, send messages on the operator's behalf, exfiltrate data, or call out to a third-party service not already configured in the repo. Block with reason `unsafe-action: <action>`.
4. **External deployment credentials.** Deploy, release-signing, container-registry, package-registry, or DNS operations that require operator credentials. Block with reason `deploy-credentials-required: <step>`.
5. **Repeated review failure.** Phase loop limit hit (3 attempts). Block with reason `human-decision-required: <phase>`.

In every halt case the worker leaves a `kanban_comment` describing exactly what would be needed to resume — never a guessed action.

## 7. Quick reference: commands and tool calls

Inside an agent run (preferred):

```python
kanban_show()  # orient on your task
kanban_heartbeat(note="phase 4 step 2/5: writing OpenAPI fragment")
kanban_comment(task_id=..., body="changed_files=... ruff_rc=0 pytest_rc=0")
kanban_block(reason="review-required: phase 4 engineering ready")
kanban_create(title="phase 4 engineering: ...", assignee="atlassianeng", parents=[spec_id])
```

CLI fallback (for operator scripts only; not for in-container agents):

```bash
hermes kanban show <id> --json
hermes kanban complete <id> --summary "..." --metadata '{...}'
hermes kanban block <id> "reason"
hermes kanban create "title" --assignee atlassianeng --parent <id>
```

## 8. Relationship to other docs

- `docs/production-oss-grand-design.md` owns the phase narrative and clean-room rules; this playbook is the execution layer that turns that narrative into Kanban tasks.
- `data/production_oss_phases.json` is the deterministic source for phase ids, requirements, gates, and child-task shape. If this playbook and the JSON disagree, the JSON wins and the playbook is updated.
- `tests/test_production_oss_phases.py` (added in the next stack task) enforces the structural invariants the playbook depends on.
