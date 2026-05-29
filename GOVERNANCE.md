# Governance

`atlassian-innerwork` follows a **minimalist BDFL (Benevolent Dictator For Life) governance model**. This document describes how decisions are made, who has authority, and how that can change.

## 1. Project status

This is a small open-source reference project. It has no foundation affiliation, no corporate sponsor, and no full-time staff. Treat this document accordingly: it favors *clarity about who has the final word* over committees and process.

## 2. Roles

### 2.1 Contributor

Anyone who opens an issue, comments on a pull request, or sends a pull request is a contributor. No paperwork. No CLA. Contributions are made under the [MIT license](LICENSE) by virtue of being submitted to this repository (DCO; see §6.4).

### 2.2 Maintainer

A maintainer is a human listed in [`MAINTAINERS.md`](MAINTAINERS.md). Maintainers can:

- merge pull requests,
- cut releases (tag and run `release.yml`),
- triage and label issues,
- amend governance documents via the procedure in §7.

Today there is one maintainer, `m0n3r0`, who is also the BDFL (§2.3).

### 2.3 BDFL

The BDFL is the maintainer who breaks ties when consensus among maintainers cannot be reached. Today, with one maintainer, the BDFL and the maintainer are the same person (`m0n3r0`). When a second maintainer is added, the BDFL remains the original until they hand off in writing in this file.

## 3. Decision-making

### 3.1 Lazy consensus

Routine changes (bug fixes, docs, refactors, additive features that don't change a documented contract) merge under **lazy consensus**:

1. A maintainer opens or reviews the PR.
2. If no other maintainer objects within **24 hours** of the request for review, and CI is green, the PR may be merged.
3. Any maintainer may veto a merge by leaving a "Request changes" review with a written reason. Vetoes are lifted by the vetoing maintainer.

### 3.2 BDFL tiebreak

When maintainers disagree and the conflict cannot be resolved by discussion within a reasonable time, the BDFL decides. The decision is recorded as a comment on the relevant issue or PR so the reasoning is durable.

### 3.3 Non-trivial changes

Changes to a documented contract — public API shape, CLI surface, on-disk state format, configuration keys, the cross-graph extension surfaces in §5, or any item from §4 below — require:

- a written rationale in the PR description,
- explicit acknowledgement that this is a contract change,
- a corresponding `CHANGELOG.md` entry,
- the deprecation handling described in §4 if the change is breaking.

## 4. Breaking changes and versioning

The project follows [Semantic Versioning](https://semver.org/) with `MAJOR.MINOR.PATCH`.

### 4.1 Pre-1.0 (current)

The project is currently at `0.1.0` (no tag cut yet).

- **MINOR bumps may include breaking changes** while pre-1.0. Each breaking change MUST be called out in `CHANGELOG.md` under the minor that introduces it.
- **PATCH bumps are strictly bug fixes.** No behavioral changes, no API additions.

### 4.2 Post-1.0

Once `v1.0.0` ships:

- Breaking changes require a **one-minor-version deprecation window**. The deprecation must be announced in `CHANGELOG.md` under the minor *before* the removal under the next minor.
- For runtime contracts, the deprecation should ideally include a runtime warning where feasible.

### 4.3 Cross-graph contract surfaces

The following surfaces are explicitly part of the public contract. Changing them is a breaking change and triggers the rules above:

- **`LINK_KINDS` and `validate_link_kind`** in `src/innerwork/knowledge.py`. Adding a kind is breaking (downstream consumers may not know it). Removing or renaming a kind is breaking.
- **`ContextEntry` and `ContextBundle` shape** in `src/innerwork/ai_context.py`. Field names, types, and presence are part of the AI-context contract. Adding required fields is breaking; adding optional fields is additive.
- **Workflow state names and transition table** in `src/innerwork/domain.py`. Adding a new terminal state, renaming an existing state, or removing a transition is breaking.
- **`WorkItem.kind` vocabulary** (currently implicit, single kind). Once `kind` is exposed in the public API, the accepted values are a breaking surface.
- **`PageVersion.body` size cap and shape** in `src/innerwork/knowledge.py`. Adding `body_format` later is additive; tightening the size cap is breaking.

### 4.4 Tag format

- Tags are `vMAJOR.MINOR.PATCH` (e.g. `v0.1.0`).
- Tags should be **signed** (`git tag -s`) per [`docs/release.md`](docs/release.md).
- No alpha/beta/rc tag conventions until needed.

## 5. Extension policy

`atlassian-innerwork` does not currently ship plug-in registries for work-item types or page macros. See [`docs/contributor-guide.md`](docs/contributor-guide.md) §4 for the honest list of module seams a future registry would live behind. Any work to introduce such a registry is a documented contract change (§3.3) and gets called out under §4.

## 6. Becoming a maintainer

There is no quota and no committee. The procedure:

1. You are an active contributor (one or more merged non-trivial PRs).
2. You **personally** open a PR that adds your row to [`MAINTAINERS.md`](MAINTAINERS.md), with your GitHub handle and your intended scope.
3. The PR's description explains your prior contributions and why you want to maintain.
4. An existing maintainer (or the BDFL) reviews. Lazy consensus applies — 24 hours for an existing maintainer to object, then merge.
5. After merge, you have maintainer permissions.

Self-nomination only. No one else may add your name. No bots, no AI agents, no organizational handles.

## 7. Amending these documents

Amendments to `GOVERNANCE.md`, `MAINTAINERS.md`, `SECURITY.md`, or `CODE_OF_CONDUCT.md` follow the same rules as a non-trivial change (§3.3) and additionally require explicit BDFL sign-off in the PR review (a "LGTM" comment is sufficient).

## 8. Conflict resolution

Disagreements between contributors that cannot be resolved on the issue or PR thread should be escalated, in order:

1. Ping a maintainer in a comment on the relevant issue or PR.
2. If still unresolved, request BDFL adjudication explicitly (`@m0n3r0` with a one-paragraph summary of the disagreement).
3. The BDFL's adjudication is recorded as a comment and is final.

Code of Conduct concerns follow the path in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md), not this section.

## 9. Affiliation and grounding

`atlassian-innerwork` has no foundation affiliation. It is not an Atlassian project. It does not claim to mirror Atlassian's private architecture. It is grounded in public product positioning and clean-room reference design. Anyone documenting the project externally is asked to preserve that framing.
