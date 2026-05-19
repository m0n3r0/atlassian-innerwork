from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .model import EdgeServiceSpec, OperationResult
from .serialization import operation_result_to_dict, spec_from_dict, spec_to_dict
from .state_store_base import IdempotencyRecord

SQLITE_SCHEMA_VERSION = 1


class SqliteStateStore:
    """SQLite-backed Phase 2 state store for local, durable broker runs.

    This is intentionally small and single-process friendly, but it persists the
    three records Phase 2 needs before worker execution exists: service intents,
    operation state, and idempotency-key bindings.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def load_services(self) -> tuple[EdgeServiceSpec, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM services ORDER BY service_id"
            ).fetchall()
        return tuple(spec_from_dict(_loads(row[0])) for row in rows)

    def save_services(self, services: tuple[EdgeServiceSpec, ...]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM services")
            connection.executemany(
                """
                INSERT INTO services(service_id, payload_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                [
                    (service.service_id, _dumps(spec_to_dict(service)))
                    for service in sorted(services, key=lambda item: item.service_id)
                ],
            )

    def load_operations(self) -> tuple[OperationResult, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT operation_id, service_id, state, description
                FROM operations
                ORDER BY created_at, operation_id
                """
            ).fetchall()
        return tuple(
            OperationResult(
                operation_id=row[0],
                service_id=row[1],
                state=row[2],
                description=row[3],
            )
            for row in rows
        )

    def save_operation(self, result: OperationResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO operations(operation_id, service_id, state, description, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(operation_id) DO UPDATE SET
                    service_id = excluded.service_id,
                    state = excluded.state,
                    description = excluded.description,
                    payload_json = excluded.payload_json
                """,
                (
                    result.operation_id,
                    result.service_id,
                    result.state,
                    result.description,
                    _dumps(operation_result_to_dict(result)),
                ),
            )

    def get_idempotency_record(self, key: str) -> IdempotencyRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT key, request_hash, operation_id
                FROM idempotency_keys
                WHERE key = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return IdempotencyRecord(key=row[0], request_hash=row[1], operation_id=row[2])

    def save_idempotency_record(self, record: IdempotencyRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO idempotency_keys(key, request_hash, operation_id)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    request_hash = excluded.request_hash,
                    operation_id = excluded.operation_id
                """,
                (record.key, record.request_hash, record.operation_id),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS services (
                    service_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN (
                        'in_progress', 'succeeded', 'failed', 'requires_attention'
                    )),
                    description TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key TEXT PRIMARY KEY,
                    request_hash TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(operation_id) REFERENCES operations(operation_id)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO meta(key, value) VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(SQLITE_SCHEMA_VERSION),),
            )


def _dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _loads(payload: str) -> dict[str, Any]:
    import json

    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        raise ValueError("stored payload must be a JSON object")
    return loaded
