# Contributing

This repository is a reference architecture, so changes should preserve two standards:

1. Keep tenant-facing APIs narrow and intent-based.
2. Add tests for executable behavior before changing implementation.

## Local verification

```bash
uvx ruff check .
uvx pytest -q
git diff --check
```

## Documentation changes

For architecture changes, update at least one of:

- `docs/grand-design.md`
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
