# Release Pipeline

This document describes the release process for `atlassian-innerwork`.
The source of truth is `.github/workflows/release.yml`; this doc explains
the intent and how an operator drives it.

## Cadence

There is no fixed cadence. A release is cut when `main` is green and a
maintainer has walked the SLO doc and the operations runbook.

## Pre-release checklist

Run locally from a clean checkout of `main`:

```sh
uv run pytest -q
uv run ruff check .
uv run pyright
uv run python scripts/validate_openapi_contract.py
uv run python scripts/rollback_drill.py --workdir /tmp/innerwork-drill
```

All five must pass. The rollback drill exits non-zero on any failure and
prints a JSON summary the on-call can paste into a retro.

Then walk:

- `docs/slos.md` — confirm no target has drifted relative to what the
  code actually emits. Update the table or the code, not both
  silently.
- `docs/operations-runbook.md` — confirm every documented procedure
  still maps to a real command in the repo.
- `docs/threat-model.md` — confirm no new endpoint has been added
  without a row.

## Cutting the release

```sh
git fetch --tags
git checkout main
git pull --ff-only
git tag -s vMAJOR.MINOR.PATCH -m "vMAJOR.MINOR.PATCH"
git push origin vMAJOR.MINOR.PATCH
```

The push of the tag triggers `.github/workflows/release.yml`, which:

1. Re-runs lint, type-check, OpenAPI contract validation, tests.
2. Executes the rollback drill against an ephemeral SQLite DB in
   `${RUNNER_TEMP}`.
3. Builds the wheel and sdist via `uv build`.
4. Generates `CHANGELOG_RELEASE.md` from the git log between the
   previous tag and the new one.
5. Creates a GitHub release with the wheel, sdist, and changelog
   attached. The job fails if either artifact is missing
   (`fail_on_unmatched_files: true`).

## Rolling back

If a release surfaces a regression in production:

1. Confirm the regression reproduces against the released artifact
   (not just against `main`).
2. Roll the deployment back to the previous tag using whatever the
   environment-specific mechanism is (Docker tag, Helm rollback,
   systemd unit revert, etc.). None of those mechanisms ship in this
   repo.
3. If the regression involves a destructive data mutation, restore the
   most recent good backup per the runbook's Backup & restore
   section, then re-run the rollback drill against the restored DB to
   confirm the procedure still works on the rolled-back code.
4. File a follow-up branch that fixes the regression on top of the
   rolled-back tag, ship it, and cut a new patch release.

## What this pipeline does NOT do

- It does not push to any package index (PyPI, internal Artifactory).
  Operators consume the wheel directly from the GitHub release.
- It does not sign artifacts with sigstore or cosign. Signing was
  scoped out of Phase 8 (decision flag 1.4-A in the PM scoping doc)
  pending a key-custody decision.
- It does not deploy. The reference repo ships an artifact; the
  operator deploys it.
- It does not call out to any external observability vendor. The
  observability primitives in `src/innerwork/observability.py` are
  stdlib-only by design.
