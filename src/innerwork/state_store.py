from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .model import EdgeServiceSpec
from .serialization import spec_from_dict, spec_to_dict
from .state_store_base import IdempotencyRecord

STATE_SCHEMA_VERSION = 1


class JsonStateStore:
    """Small durable state store for local demos and OSS smoke deployments.

    The store is intentionally simple: one JSON file, atomic replacement writes,
    and no background workers. It gives the live app restart-safe behavior while
    keeping production database and queue choices out of the reference model.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load_services(self) -> tuple[EdgeServiceSpec, ...]:
        if not self.path.exists():
            return ()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("state file must contain a JSON object")
        if payload.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ValueError(f"unsupported state schema_version: {payload.get('schema_version')}")
        services = payload.get("services", [])
        if not isinstance(services, list):
            raise ValueError("state file services must be a list")
        return tuple(spec_from_dict(service) for service in services)

    def save_services(self, services: tuple[EdgeServiceSpec, ...]) -> None:
        payload: dict[str, Any] = {
            "schema_version": STATE_SCHEMA_VERSION,
            "services": [spec_to_dict(service) for service in services],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(encoded)
            temporary_path = Path(handle.name)
        temporary_path.replace(self.path)

    def load_operations(self) -> tuple[Any, ...]:
        return ()

    def save_operation(self, result: Any) -> None:
        return None

    def get_idempotency_record(self, key: str) -> IdempotencyRecord | None:
        return None

    def save_idempotency_record(self, record: IdempotencyRecord) -> None:
        return None
