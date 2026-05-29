# Contributing

Thanks for helping make Innerwork a useful open-source reference app.

This repository has two standards:

1. Keep tenant-facing APIs narrow and intent-based.
2. Add tests for executable behavior before changing implementation.

## Local setup

```bash
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run pyright

# CI-compatible fallback if uv is unavailable:
python -m pip install -e . pytest ruff
python -m pytest -q
python -m ruff check .
```

To run the live app:

```bash
uv run uvicorn innerwork.app:app --reload
```

## Documentation changes

For architecture changes, update at least one of:

- `docs/grand-design.md`
- `docs/production-oss-grand-design.md`
- `docs/production-grade-roadmap.md`
- `docs/production-readiness-checklist.md`
- `docs/threat-model.md`
- `docs/operations-runbook.md`

## Code changes

Follow test-driven development for behavior changes:

1. add a failing test;
2. run it and observe the failure;
3. implement the smallest change;
4. run the full suite;
5. update docs if the platform contract changes.

## Grounding and safety rules

- This is a clean-room reference implementation based on public product positioning.
- Do not claim the design mirrors Atlassian private infrastructure.
- Keep security-sensitive behavior fail-closed: invalid ownership, domains, routes, profiles, or features must not persist service state.
- Do not commit secrets, access tokens, customer data, or private architecture notes.

## How decisions are made

See [GOVERNANCE.md](GOVERNANCE.md). Routine PRs merge under lazy consensus (24h objection window for non-trivial changes); the BDFL (`m0n3r0`) breaks ties.

## How to report a security issue

See [SECURITY.md](SECURITY.md). Use GitHub private vulnerability reporting (`Security` tab → `Report a vulnerability`) on this repository. Do **not** open a public issue or PR for a security bug.

## Code of Conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Code of Conduct concerns are reported via a GitHub issue with the `code-of-conduct` label, or — if the concern involves a maintainer or sensitive information — via GitHub private vulnerability reporting (flagged as a CoC matter).

## Release flow

Tag-driven. The full procedure is in [`docs/release.md`](docs/release.md). In short: bump `CHANGELOG.md`, tag `vX.Y.Z`, push the tag, let `.github/workflows/release.yml` build the wheel + sdist and attach them to the GitHub Release. The project does **not** currently publish to PyPI.

## Extension model — adding a new work-item type or page macro

The honest version of "how to extend without forking" is in [`docs/contributor-guide.md`](docs/contributor-guide.md) §4. Short version: there are no plug-in registries yet. Both extension surfaces are intentionally deferred, and `docs/contributor-guide.md` names the exact module seams a future registry would live behind so a contributor can size the change honestly.

## Code review expectations

- Lazy consensus on PRs (24h objection window for non-trivial changes).
- One maintainer LGTM after CI is green is sufficient.
- CI must be green before merge.
- No force-push after a review has started — add fixup commits; the maintainer will squash on merge.
- Squash merge is the default; the squashed subject becomes the changelog line, so make it descriptive.

## Sign-off — DCO, no CLA

This project uses the [Developer Certificate of Origin](https://developercertificate.org/). Sign your commits with `git commit -s`. There is **no Contributor License Agreement**.

## Project layout (1-minute map)

Source lives under `src/innerwork/`. The shortest possible map:

- `app.py`, `cli.py` — entry points (FastAPI app, CLI).
- `model.py`, `broker.py`, `control_plane.py` — edge-broker side (intent → snapshot).
- `domain.py`, `domain_store.py`, `domain_api.py` — work-graph domain (projects, work items, transitions).
- `knowledge.py` — knowledge-graph domain (spaces, pages, page versions, link kinds).
- `ai_context.py` — cross-graph AI-context bundle assembly (`ContextEntry` / `ContextBundle`).
- `search.py` — cross-graph search.
- `audit.py`, `field_acl.py` — security primitives (phase 7).
- `observability.py` — Prometheus-text metrics + structured logging.
- `state_store.py`, `sql_state_store.py` — broker-side state stores.
- `data/` — bundled JSON catalogs.

See [`docs/contributor-guide.md`](docs/contributor-guide.md) §1 for the full table.
