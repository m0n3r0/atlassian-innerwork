## What this changes

<!-- one or two sentences -->

## Why

<!-- the user-visible or contract-level reason -->

## Tests

<!-- what tests cover this; new tests added? existing tests adjusted? -->

- [ ] `uv run pytest -q` passes locally
- [ ] `uv run ruff check .` passes
- [ ] `uv run pyright` passes
- [ ] `python scripts/validate_openapi_contract.py` passes (only if you touched `spec/openapi.yaml` or any API route)

## Docs updated

<!-- which file(s) did you update? See docs/contributor-guide.md §5 for the map. -->

- [ ] CHANGELOG.md `[Unreleased]` section updated

## Breaking change?

- [ ] No.
- [ ] Yes — see [GOVERNANCE.md §4](../GOVERNANCE.md#4-breaking-changes-and-versioning) and the cross-graph contract list in §4.3. I have flagged this in CHANGELOG.md and named the contract being broken in the PR description above.

## Sign-off

I have signed my commits with `git commit -s` per the [DCO](https://developercertificate.org/).
