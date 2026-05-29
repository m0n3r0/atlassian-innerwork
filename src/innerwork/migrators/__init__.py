"""Phase-10 migration helpers.

The migrators package collects portability-layer adapters that produce
:func:`innerwork.portability.import_domain`-compatible payloads from
external shapes. Phase 10 ships exactly one adapter — a synthetic
fixture used by tests and operator dry-runs — and is intentionally
scoped that narrowly. There is no Jira, Confluence, or hosted-service
importer; ``docs/migration-guide.md`` documents the policy.
"""

from __future__ import annotations

from .synthetic_fixture import (
    SYNTHETIC_FIXTURE_PATH,
    build_synthetic_fixture,
    load_synthetic_fixture,
)

__all__ = [
    "SYNTHETIC_FIXTURE_PATH",
    "build_synthetic_fixture",
    "load_synthetic_fixture",
]
