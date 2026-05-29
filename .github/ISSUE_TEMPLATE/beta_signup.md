---
name: Beta signup
about: Volunteer to try atlassian-innerwork during the public beta.
title: "beta: <your handle or org>"
labels: beta-signup
---

<!--
Phase 10 public beta intake. This template is the only supported way to
join the beta. Please do not include credentials, customer data, or
anything you would not want stored in a public GitHub issue.

The maintainers do not publish beta participant counts; expect a short
acknowledgement comment when your signup is accepted.
-->

**Handle / org (public is fine)**

<!-- e.g. @octocat, or "Internal platform team at Example Corp" -->

**Primary use case**

<!--
One or two sentences. Examples:
- "Replace an internal work-graph spreadsheet for ~10 engineers."
- "Evaluate the EdgeService manifest format for a control-plane spike."
- "Migrate a synthetic dataset to test the portability envelope."
-->

**Which surfaces are you planning to use?**

<!-- check what applies -->

- [ ] CLI (`innerwork ...` subcommands)
- [ ] FastAPI service (`innerwork serve`)
- [ ] Work-graph domain store (`projects`, `work-items`, transitions)
- [ ] Portability envelope (`export` / `import` / `migrate --source synthetic`)
- [ ] Analytics rollup (`metrics`)
- [ ] EdgeService manifest validation / render

**Deployment shape**

<!-- e.g. "single SQLite file on a workstation", "containerised in our k8s
sandbox", "uv-managed local install on macOS". -->

**Feedback channel preference**

- [ ] GitHub issues only (default)
- [ ] Happy to be tagged on related PRs for review
- [ ] Willing to file structured iteration notes (see
      `docs/post-launch-iteration.md`)

**Anything we should know before onboarding?**

<!--
Optional. Hard constraints, regulatory context, integrations you care
about, or specific phase-10 docs you've read (launch-plan, beta-program,
migration-guide, roadmap, post-launch-iteration, metrics-dashboard).
-->

---

By opening this issue you confirm that:

- You will not paste secrets, customer data, or proprietary code into this
  thread.
- You understand the beta has no commercial commitments, SLAs, or
  pricing — see `docs/beta-program.md`.
- You will report issues via the bug-report template, not by editing this
  signup issue.
