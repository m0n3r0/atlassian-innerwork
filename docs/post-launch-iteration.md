# Post-Launch Iteration

Status: cadence for the period immediately following the Phase-10 beta
launch. This document defines how the maintainers triage feedback,
publish iteration notes, and decide what enters subsequent phases.

Companion documents:

- `docs/launch-plan.md`
- `docs/beta-program.md`
- `docs/migration-guide.md`
- `docs/roadmap.md`
- `docs/metrics-dashboard.md`
- `docs/governance.md`

This document makes no claim about participant counts, retention,
revenue, or any other commercial metric. The project does not track
those numbers and does not intend to.

---

## 1. Cadence

The post-launch iteration loop runs on a two-week tick. Each tick has
three explicit phases:

| Day | Phase | Owner |
|---|---|---|
| 1–7 | Triage incoming issues, answer beta questions | All maintainers |
| 8–11 | Pick scoped work for the tick; open PRs | Assignee per item |
| 12–14 | Review, merge mergeable PRs, draft iteration note | Maintainers |

The iteration note (`docs/iteration-notes/YYYY-MM-DD.md`) is a short
write-up summarising what was triaged, what landed, what was deferred,
and any direction changes. The first iteration note will be created
within two weeks of the Phase-10 PR merging.

If no significant activity occurred in a tick, the iteration note can
be a single paragraph saying so. Silence is acceptable; ghosting is
not.

---

## 2. Triage windows

Triage windows are the same as those documented in
`docs/beta-program.md` §4:

| Label | Triage window |
|---|---|
| `beta` | 7 days |
| `bug` | 7 days |
| `enhancement` | 14 days |
| `security` (private channel only) | 72 hours initial reply |

"Triage" means a maintainer has read the issue, applied the `triaged`
label, and either asked a clarifying question, scheduled the work,
moved it onto the roadmap, or closed it with a stated reason.

Triage does **not** mean the work is done. Delivery cadence depends on
scope and contributor bandwidth and is not promised.

---

## 3. Iteration note shape

Each iteration note follows this skeleton:

```md
# Iteration: <YYYY-MM-DD> — <YYYY-MM-DD>

## Summary
One paragraph: what landed, what slipped, what got deferred.

## Triaged
- #123 (bug) — fix landed in commit <sha>.
- #124 (enhancement) — moved to roadmap under "CLI ergonomics".
- #125 (beta) — closed: out of scope per migration-guide §6.

## Landed
- <short list of merged PRs with one-line descriptions>

## Deferred
- <items that were considered but punted, with reason>

## Direction notes
- <any changes to roadmap, governance, scope boundaries>
```

Iteration notes are checked into `docs/iteration-notes/`. They are
append-only — historical notes are never rewritten, so beta participants
can see how the project's reasoning evolved over time.

---

## 4. What gets picked up in a tick

The maintainers prefer the following picking order within a tick:

1. **Regressions** against documented behaviour. These take precedence
   because they undermine the contract the docs set with beta
   operators. Specifically: any failure of the synthetic-fixture
   round-trip documented in `docs/migration-guide.md`.
2. **Bugs in CI parity gate behaviour.** A red `pytest -x`,
   `ruff check .`, or `pyright` on `main` is treated as an incident.
3. **Bugs filed by beta participants** in scope per
   `docs/beta-program.md`.
4. **Documentation gaps surfaced by beta feedback.** Cheap fixes that
   prevent the same question being asked again next tick.
5. **Enhancements** from the roadmap "directional next" section, in
   the order maintainer bandwidth allows.

Items outside this list can still land — the order is a heuristic, not
a rule.

---

## 5. Incident handling

If a regression breaks the documented contract — for example, the
synthetic-fixture round-trip stops being byte-identical, or
`import-domain` silently overwrites a populated target — the
maintainers will:

1. Open a `bug` issue with the `regression` label and a short
   reproduction.
2. Add a failing test that captures the regression before fixing.
3. Land the fix in a PR that references the issue.
4. Mention the incident in the next iteration note, including:
   - what broke,
   - what the impact window was,
   - what changed to prevent recurrence.

Operators who depended on the broken behaviour are notified on the
original beta-signup issue if one exists. No commercial remedy is
implied or offered — see `docs/beta-program.md` §3.

---

## 6. Graduation review

At the end of each tick the maintainers check the graduation
criteria from `docs/beta-program.md` §7:

- CI parity gate green for the full window.
- Synthetic round-trip re-validated against the most recent build.
- Every open `beta`-labelled issue triaged at least once.

If all three hold, the next iteration note can propose graduating the
beta program. Graduation is not automatic — it requires a maintainer
to write up the rationale and a PR amending the beta program doc.

---

## 7. What this cadence is NOT

- It is **not** a release cadence. Releases are tag-cut when a coherent
  set of changes is ready and CI is green; the iteration cadence is
  about triage and review, not release engineering. The launch plan
  (`docs/launch-plan.md` §3) covers the release procedure.
- It is **not** a roadmap. The roadmap (`docs/roadmap.md`) is the
  directional view; the iteration note is the historical view of what
  actually happened in a given two-week window.
- It is **not** a support contract. The cadence is best-effort and can
  be slowed or paused by the maintainers with an iteration-note
  announcement.

---

## 8. Cross-references

- `docs/launch-plan.md`
- `docs/beta-program.md`
- `docs/migration-guide.md`
- `docs/roadmap.md`
- `docs/metrics-dashboard.md`
- `docs/governance.md`
- `CHANGELOG.md`
