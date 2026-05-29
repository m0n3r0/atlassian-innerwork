# Launch plan — Atlassian Innerwork (phase 10)

> Status: phase-10 deliverable. Source-of-truth for **how** the project transitions from "internal readiness" to a public beta.
>
> Reading order: this doc → [`beta-program.md`](beta-program.md) → [`migration-guide.md`](migration-guide.md) → [`post-launch-iteration.md`](post-launch-iteration.md) → [`roadmap.md`](roadmap.md) → [`metrics-dashboard.md`](metrics-dashboard.md).

This launch plan is intentionally a *plan*, not a marketing announcement. It documents the procedure and the success criteria; it does **not** claim that a beta cohort exists, that the project has users, or that any commercial activity is contemplated.

---

## §1 Launch posture

Atlassian Innerwork is launching as a **public beta** of a clean-room, Jira/Confluence-inspired work-and-knowledge reference application. The posture is deliberately narrow:

- The project is software at version `0.1.0` (per `pyproject.toml`). No tag has been cut yet; see [`release.md`](release.md) for the tag procedure.
- Beta means: source is public, the issue tracker is open, breaking changes are permitted per [`GOVERNANCE.md`](../GOVERNANCE.md) §breaking-changes, and there is **no** SLA, response-time guarantee, or support contract.
- The project is **not** a Jira clone, **not** a Confluence clone, and **not** a drop-in replacement for any Atlassian product. It is a clean-room reference design grounded in public Atlassian product positioning.
- There is no hosted SaaS, no paid tier, no commercial relationship, and no PyPI publish at phase-10 merge time.

What "launch" means here is the moment phase 10 lands on `main`, the beta program doc goes public, and the issue tracker is wired to accept beta signups. The first `v0.1.0` tag and any subsequent announce activity are gated post-merge by the BDFL.

---

## §2 Launch checklist

The checklist below separates **pre-tag** (lands inside phase 10), **tag-cut** (a deliberate later act by the BDFL), and **post-tag** (after the tag exists) work. Phase 10 only performs the pre-tag rows.

### §2.1 Pre-tag (this PR)

| # | Item | Owner | Evidence |
|---|---|---|---|
| 1 | Beta program doc exists with §onboarding and §offboarding | impl worker | `docs/beta-program.md` |
| 2 | Migration guide exists; ≥1 synthetic fixture round-trips | impl worker | `docs/migration-guide.md` + `tests/test_migration.py` green |
| 3 | Roadmap exists; phases 0–10 cross-link merged PRs | impl worker | `docs/roadmap.md` |
| 4 | Post-launch iteration loop documented | impl worker | `docs/post-launch-iteration.md` |
| 5 | Metrics dashboard surface documented | impl worker | `docs/metrics-dashboard.md` |
| 6 | CLI wraps the existing portability + analytics modules | impl worker | `innerwork export`, `innerwork import`, `innerwork migrate`, `innerwork metrics` all expose `--help` |
| 7 | Beta signup issue template installed | impl worker | `.github/ISSUE_TEMPLATE/beta_signup.md` |
| 8 | README cross-links to all new docs | impl worker | `README.md` "Beta" + "Roadmap" sections |
| 9 | CHANGELOG `[Unreleased] → Phase 10` section added | impl worker | `CHANGELOG.md` |
| 10 | All tests pass; `ruff` and `pyright` clean | impl worker | `uv run pytest -x && uv run ruff check . && uv run pyright` exits 0 |
| 11 | Anti-hallucination greps return empty | reviewer | per §9 of `docs/phase10_scoping.md` |

### §2.2 Tag-cut (BDFL only, post-merge)

| # | Item | Notes |
|---|---|---|
| 1 | Bump `pyproject.toml` `version` to `0.1.0` (or chosen tag) | One-line PR. Reviewer must confirm CHANGELOG `[Unreleased]` is rolled into a `[0.1.0]` section before tag. |
| 2 | Create signed tag `v0.1.0` | `git tag -s v0.1.0 -m "..."`. |
| 3 | Push tag | `git push origin v0.1.0`. Triggers `.github/workflows/release.yml`. |
| 4 | Verify GitHub Release page renders | Release notes pulled from `CHANGELOG.md` [0.1.0] section. |

### §2.3 Post-tag (post-merge, beta cohort permitting)

| # | Item | Notes |
|---|---|---|
| 1 | README banner update to reflect the cut tag | One-line edit. |
| 2 | Announce in GitHub Releases page | The Release body is the announce surface. |
| 3 | Iteration loop opens its first review issue | Per `docs/post-launch-iteration.md` §1. |

The project does **not** commit to any external announce channel beyond GitHub Releases. No Twitter / X, no Hacker News, no Reddit, no mailing list, no Discord. The team may choose to surface the release elsewhere later, but phase 10 makes no claim to do so.

---

## §3 Announce channels

The phase-10 launch surfaces are exactly these:

1. The repository's GitHub Releases page (populated by the tag-cut step in §2.2).
2. The `README.md` "Beta" section (cross-linking to this plan and to `docs/beta-program.md`).
3. The pinned issue created from `.github/ISSUE_TEMPLATE/beta_signup.md` (only once a participant opens one; not pinned at merge time).

We do **not** claim any of the following:

- Any social-media post or thread.
- Any link aggregator submission.
- Any newsletter or podcast appearance.
- Any conference talk or sponsored slot.

If a reviewer or downstream operator wishes to do any of these things, they may, and they can edit this section in a follow-up PR to reflect what actually happened. Phase 10 documents *what we promise to do*, not *what we hope someone will do for us*.

---

## §4 Rollback plan

The launch involves three irreversible-looking actions: opening the beta program, cutting a tag, and pushing it. The rollback procedure for each:

| Action | Rollback |
|---|---|
| Phase-10 PR merged on `main` | `git revert <merge sha> -m 1` opens a clean revert PR. Re-runs CI. Beta docs disappear from `main` (still in history). The new CLI subcommands and `migrators/` package are removed with the revert. |
| Beta program opened | Close the pinned signup issue; update `docs/beta-program.md` to mark the program closed with a date. Existing beta participants are notified by a comment on their own issues. |
| Tag `v0.1.0` cut | `git tag -d v0.1.0 && git push --delete origin v0.1.0`. The corresponding GitHub Release must be manually deleted from the GitHub UI. A `[0.1.0-yanked]` note is appended to `CHANGELOG.md` explaining why. |

The release procedure cross-links to [`docs/release.md`](release.md) and [`.github/workflows/release.yml`](../.github/workflows/release.yml); the rollback procedure here is in addition to, not in place of, what that doc covers.

---

## §5 Success criteria

Phase 10 is judged successful at PR-merge time when:

1. The beta program doc declares an open window and a third party can follow the §onboarding procedure end-to-end without contacting a maintainer.
2. The synthetic-fixture migration completes end-to-end in `tests/test_migration.py`, proving the import path works on a non-native JSON shape.
3. The iteration loop is documented with cadence, inputs, prioritization, and outputs (`docs/post-launch-iteration.md`).
4. All seven acceptance gates in `docs/phase10_scoping.md` §2 verify against the actual repo state.
5. All existing tests continue to pass (phase 9 baseline: 307 passed in `~28s`); phase 10 adds new tests on top of the existing suite.

Success is **not** measured by:

- Any beta participant count (we may have zero at merge time; that is fine).
- Any download, star, or fork count.
- Any external social-media engagement.
- Any commercial milestone.

These are deliberately excluded because the project has no way to claim them honestly at phase-10 merge time.

---

## §6 Explicit non-goals

The following are out of scope for phase 10 and remain out of scope until the BDFL explicitly opens them as work:

- **Service-level agreement.** None. Use is at-will, support is best-effort.
- **Paid support, consulting, or services.** None. There is no commercial offering.
- **Hosted SaaS.** None. The only way to run Innerwork is to clone the repo and run it locally (or in a container the operator stands up themselves).
- **Atlassian-compatibility claim.** None. Innerwork is a clean-room reference design; it does not consume or produce Atlassian wire formats, does not run inside Atlassian Forge, and does not interoperate with Jira or Confluence APIs.
- **Foreign-format importers.** Phase 10 ships exactly one synthetic-fixture adapter. Jira REST and Confluence Cloud importers are listed as *post-launch candidates* in `docs/roadmap.md`; they are not promises.
- **Plug-in registries for work-item types or page macros.** Deferred per [`docs/contributor-guide.md`](contributor-guide.md) §extension-points. Phase 10 does not change that posture.
- **PyPI publish.** Deferred. The first publish is a deliberate post-tag act gated by the BDFL.
- **Hosted docs site.** Deferred. [`docs/site-outline.md`](site-outline.md) describes the planned site; phase 10 does not stand it up.
- **Anything Atlassian-portfolio-adjacent that this project explicitly disclaims** (Bitbucket, Trello, Loom, JSM, Statuspage, Guard, Jira Align) per the README's "Product scope" section.

---

## §7 Open questions deferred to iteration

The phase-10 PR does **not** answer these; they belong to the post-launch iteration loop:

- Whether to enable GitHub Discussions for the repository (currently issues-only).
- Whether to add a `CITATION.cff` for academic citation.
- Whether to add `funding.yml` (none anticipated; documenting non-decision is itself a decision).
- Whether to add a project logo / mark (currently text-only).
- Whether to publish a sample Innerwork instance for read-only demoing (would require a deployment commitment we are not making).

Each of these will be opened as an issue in the iteration loop only when a maintainer is prepared to do the work; pre-emptive promises are anti-pattern here.
