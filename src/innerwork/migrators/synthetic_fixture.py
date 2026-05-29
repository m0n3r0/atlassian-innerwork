"""Synthetic migration fixture (Phase 10).

The fixture is a deterministic, fully-synthetic
:func:`innerwork.portability.export_domain`-shaped payload. It is the
*only* migration source bundled with ``innerwork`` — no Jira,
Confluence, or hosted-service exporter ships. The fixture exists so
operators can:

* exercise the export/import round-trip end-to-end against a known
  payload before pointing the import at production data;
* verify the CLI ``migrate`` and ``import`` subcommands without
  touching their own database;
* baseline the analytics rollup shape (see
  ``tests/test_migration.py``).

All identifiers, names, timestamps, and bodies are placeholders chosen
to read as obviously synthetic (``proj-001``, ``Alice Example``,
fixed ISO-8601 timestamps in 2024-01). Nothing in this file should be
mistaken for real customer data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain_store import DOMAIN_SCHEMA_VERSION
from ..portability import PORTABILITY_FORMAT_VERSION

__all__ = [
    "SYNTHETIC_FIXTURE_PATH",
    "build_synthetic_fixture",
    "load_synthetic_fixture",
]

# Path to the on-disk JSON copy of :func:`build_synthetic_fixture`.
# Kept in lockstep with the function output by
# ``tests/test_migration.py`` (asserts byte-for-byte equality).
SYNTHETIC_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "synthetic_migration.json"
)


def build_synthetic_fixture() -> dict[str, Any]:
    """Return the canonical synthetic migration payload.

    The payload is shaped to match
    :func:`innerwork.portability.export_domain` exactly so it can be
    fed straight into :func:`innerwork.portability.import_domain`.
    Schema/format versions track the live constants — bump the on-disk
    JSON fixture when these change.
    """

    return {
        "format_version": PORTABILITY_FORMAT_VERSION,
        "schema_version": DOMAIN_SCHEMA_VERSION,
        "projects": [
            {
                "project_id": "proj-001",
                "key": "PHX",
                "name": "Phoenix",
                "owner": "alice@example.test",
                "created_at": "2024-01-01T00:00:00+00:00",
            },
            {
                "project_id": "proj-002",
                "key": "ORC",
                "name": "Orchard",
                "owner": "bob@example.test",
                "created_at": "2024-01-02T00:00:00+00:00",
            },
        ],
        "work_items": [
            {
                "work_item_id": "wi-001",
                "project_id": "proj-001",
                "key": "PHX-1",
                "title": "Bootstrap project",
                "description": "Stand up the initial Phoenix surface.",
                "state": "done",
                "assignee": "alice@example.test",
                "created_at": "2024-01-03T09:00:00+00:00",
                "updated_at": "2024-01-04T17:30:00+00:00",
            },
            {
                "work_item_id": "wi-002",
                "project_id": "proj-001",
                "key": "PHX-2",
                "title": "Draft launch checklist",
                "description": "Synthetic — used for migration round-trip tests.",
                "state": "in_progress",
                "assignee": "alice@example.test",
                "created_at": "2024-01-05T10:00:00+00:00",
                "updated_at": "2024-01-06T12:00:00+00:00",
            },
            {
                "work_item_id": "wi-003",
                "project_id": "proj-002",
                "key": "ORC-1",
                "title": "Stub the orchard surface",
                "description": "",
                "state": "todo",
                "assignee": "",
                "created_at": "2024-01-07T08:15:00+00:00",
                "updated_at": "2024-01-07T08:15:00+00:00",
            },
        ],
        "transitions": [
            {
                "transition_id": 1,
                "work_item_id": "wi-001",
                "from_state": "todo",
                "to_state": "in_progress",
                "actor": "alice@example.test",
                "occurred_at": "2024-01-03T09:30:00+00:00",
                "reason": "",
            },
            {
                "transition_id": 2,
                "work_item_id": "wi-001",
                "from_state": "in_progress",
                "to_state": "done",
                "actor": "alice@example.test",
                "occurred_at": "2024-01-04T17:30:00+00:00",
                "reason": "bootstrap complete",
            },
            {
                "transition_id": 3,
                "work_item_id": "wi-002",
                "from_state": "todo",
                "to_state": "in_progress",
                "actor": "alice@example.test",
                "occurred_at": "2024-01-06T12:00:00+00:00",
                "reason": "",
            },
        ],
        "spaces": [
            {
                "space_id": "space-001",
                "key": "DOCS",
                "name": "Docs",
                "owner": "alice@example.test",
                "created_at": "2024-01-02T00:00:00+00:00",
            },
        ],
        "pages": [
            {
                "page_id": "page-001",
                "space_id": "space-001",
                "current_version": 2,
                "created_at": "2024-01-03T11:00:00+00:00",
                "updated_at": "2024-01-04T14:00:00+00:00",
            },
        ],
        "page_versions": [
            {
                "version_id": 1,
                "page_id": "page-001",
                "version_number": 1,
                "title": "Launch checklist",
                "body": "Initial outline.",
                "author": "alice@example.test",
                "created_at": "2024-01-03T11:00:00+00:00",
            },
            {
                "version_id": 2,
                "page_id": "page-001",
                "version_number": 2,
                "title": "Launch checklist",
                "body": "Updated outline with rollback notes.",
                "author": "alice@example.test",
                "created_at": "2024-01-04T14:00:00+00:00",
            },
        ],
        "links": [
            {
                "link_id": 1,
                "work_item_id": "wi-002",
                "page_id": "page-001",
                "kind": "documents",
                "created_by": "alice@example.test",
                "created_at": "2024-01-06T12:05:00+00:00",
            },
        ],
        "work_item_comments": [
            {
                "comment_id": 1,
                "work_item_id": "wi-001",
                "author": "bob@example.test",
                "body": "Nice — green across the board.",
                "created_at": "2024-01-04T17:35:00+00:00",
            },
            {
                "comment_id": 2,
                "work_item_id": "wi-002",
                "author": "alice@example.test",
                "body": "Pulling in the rollback notes from page-001.",
                "created_at": "2024-01-06T12:10:00+00:00",
            },
        ],
        "page_comments": [
            {
                "comment_id": 1,
                "page_id": "page-001",
                "author": "bob@example.test",
                "body": "Added rollback section per review.",
                "created_at": "2024-01-04T14:05:00+00:00",
            },
        ],
    }


def load_synthetic_fixture() -> dict[str, Any]:
    """Read the JSON copy of the synthetic fixture from disk.

    Used by the CLI ``migrate --source synthetic`` path so the on-disk
    file is the authoritative payload at runtime (and the in-code
    builder is the authoritative source for tests).
    """

    raw = SYNTHETIC_FIXTURE_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(
            f"{SYNTHETIC_FIXTURE_PATH} must contain a JSON object, got "
            f"{type(payload).__name__}"
        )
    return payload
