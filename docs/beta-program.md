# Beta Program

Status: draft for Phase 10 launch readiness.

This document defines how external participants join the `innerwork` public
beta, what they should expect from the maintainers, and how their feedback
flows back into the project. The beta program is intentionally small in scope:
it is a way to surface bugs and rough edges in real-world usage, not a
commercial offering.

Companion documents:

- `docs/launch-plan.md` — cutover sequence, rollback, comms.
- `docs/operations-runbook.md` — day-2 ops for self-hosted operators.
- `docs/governance.md` — decision making, maintainership, code of conduct.
- `docs/post-launch-iteration.md` — release cadence and feedback triage.

This document makes no claim about how many participants are enrolled. No
participant counts, conversion metrics, or pricing/commercial claims appear
anywhere in `innerwork`.

---

## 1. Goals

The beta program exists to:

1. Validate that `innerwork` runs end-to-end against documented setup steps
   on common host operating systems (Linux, macOS, WSL).
2. Surface defects the test suite did not catch — workflow ergonomics,
   confusing error messages, missing CLI affordances.
3. Stress-test the operations runbook (`docs/operations-runbook.md`) by
   having real operators follow it instead of the maintainers.
4. Build a public record of how the project is being used so future
   contributors can scope features against real needs.

Non-goals:

- The beta is **not** a sales channel. No pricing, billing, contracts, or
  service-level agreements are offered.
- The beta is **not** a guarantee of future feature delivery. The roadmap
  (`docs/roadmap.md`) is directional, not contractual.
- The beta does **not** import data from hosted Jira or Confluence. The
  only importer shipped in Phase 10 is the synthetic fixture used to
  exercise the migration code path (see `docs/migration-guide.md`).

---

## 2. Signup channel

The single signup channel is a GitHub issue template:

- Template: `.github/ISSUE_TEMPLATE/beta_signup.md`
- Title prefix: `[beta] <short description of intended use>`
- Label applied automatically: `beta`

The template asks for:

- Host OS and Python version.
- Whether the operator intends to self-host or evaluate locally.
- A one-paragraph description of the use case.
- Any timing constraints the operator wants the maintainers to know about.

Participants do **not** submit personal contact information through this
template. All correspondence happens on the public issue thread. Operators
who prefer private channels are explicitly told in the template to wait for
a maintainer to propose a channel.

If a signup is for a use case the maintainers cannot reasonably support
(e.g. depends on a hosted Jira importer that does not exist), the issue is
closed with a polite explanation and a pointer to the roadmap.

---

## 3. Participant expectations

Beta participants should expect:

- **No SLA.** Maintainers respond to beta issues on best-effort and triage
  on the cadence documented in `docs/post-launch-iteration.md`.
- **Public-by-default.** All bug reports, feature requests, and discussion
  happen on public GitHub issues unless the maintainers explicitly move a
  thread elsewhere for a stated reason (e.g. a security report — see
  `SECURITY.md`).
- **Self-hosted only.** There is no managed `innerwork` deployment. Each
  participant runs their own instance per `docs/operations-runbook.md`.
- **Breaking changes possible.** The portability format
  (`PORTABILITY_FORMAT_VERSION`) and CLI surface are stable enough for a
  beta but may evolve before a 1.0 release. Every breaking change is
  called out in `CHANGELOG.md` and `docs/migration-guide.md`.
- **No data import from Jira or Confluence.** Operators can exercise
  the export/import path against the synthetic fixture documented in
  `docs/migration-guide.md` to confirm round-trip behaviour.

Maintainers commit to:

- Responding to every `beta`-labelled issue within the triage window
  defined in `docs/post-launch-iteration.md` (currently one week).
- Keeping the CHANGELOG honest: every behaviour change that affects
  beta operators is listed under the relevant version block.
- Publishing a short post-mortem on any incident that affects the
  beta program's documented expectations (for example, a regression
  that breaks the synthetic round-trip).

---

## 4. Feedback loop

Beta feedback enters the project through one of three labelled paths:

| Label | What it means | Triage window |
|---|---|---|
| `beta` | Generic beta-program issue (signup, question, observation) | 7 days |
| `bug` | Defect: behaviour does not match documentation | 7 days |
| `enhancement` | Concrete feature/UX suggestion | 14 days |

Triage:

1. A maintainer reads the issue, applies the `triaged` label, and either:
   - asks a clarifying question on-thread, or
   - moves the issue into the relevant roadmap section
     (`docs/roadmap.md`), or
   - closes the issue with a stated reason.
2. Triage outcomes are summarised in the periodic iteration note
   (`docs/post-launch-iteration.md`) so beta participants can see how
   their input is being processed in aggregate.

Maintainers will not promise delivery dates on beta-sourced enhancements.
The roadmap document is the only place where directional commitments live,
and even there the language is explicitly non-binding.

---

## 5. Beta exit / offboarding

A beta participant can exit the program at any time by:

- Closing their open `beta`-labelled issues with a short note, or
- Opening a new issue titled `[beta] offboard <handle>` so the
  maintainers can mark the prior threads as inactive.

There is nothing to uninstall on the maintainers' side — `innerwork` is
self-hosted, so offboarding is purely about closing the feedback loop.
Operators who stop running `innerwork` are encouraged (not required) to
leave a one-paragraph note on their original signup issue saying what
worked and what did not. Those notes feed directly into the roadmap.

Re-onboarding is supported: opening a new signup issue is sufficient.

---

## 6. What the beta does NOT do

Documented here so participants do not infer anything we did not promise:

- No marketing channels, mailing lists, or telemetry are introduced by
  the beta program. `innerwork` ships no telemetry of any kind.
- No revenue, pricing, paid tier, or commercial offering is associated
  with the beta. The project is open-source under the licence noted in
  the repository root.
- No service-level agreements, uptime guarantees, or response-time
  guarantees beyond the best-effort triage windows above.
- No managed onboarding calls, professional services, or paid support
  are offered through the beta channel.

If a beta participant asks for any of the above, the maintainers will
politely decline and point them back to this document.

---

## 7. Graduation criteria

The beta program graduates (rolls into normal operation) when:

1. The CI parity gate (`pytest -x`, `ruff check .`, `pyright`) has been
   green for the entire window documented in
   `docs/post-launch-iteration.md`.
2. The synthetic-fixture migration round-trip (`docs/migration-guide.md`)
   has been re-validated against the most recent release.
3. The maintainers have triaged every open `beta`-labelled issue at
   least once.

Graduation does not require a specific participant count, retention
metric, or commercial milestone — the project intentionally does not
track those numbers.

---

## 8. Cross-references

- `docs/launch-plan.md` — launch cutover and rollback.
- `docs/migration-guide.md` — synthetic import/export round-trip.
- `docs/operations-runbook.md` — day-2 operator playbook.
- `docs/post-launch-iteration.md` — triage cadence and review notes.
- `docs/roadmap.md` — directional, non-binding feature direction.
- `docs/governance.md` — maintainership and decision making.
- `SECURITY.md` — private channel for security reports.
