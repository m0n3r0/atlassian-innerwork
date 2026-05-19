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
