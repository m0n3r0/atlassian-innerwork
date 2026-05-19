from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .model import EdgeServiceSpec, OperationResult


@dataclass(frozen=True)
class IdempotencyRecord:
    key: str
    request_hash: str
    operation_id: str


class StateStore(Protocol):
    """Persistence boundary required by the Phase 2 broker contract."""

    def load_services(self) -> tuple[EdgeServiceSpec, ...]: ...

    def save_services(self, services: tuple[EdgeServiceSpec, ...]) -> None: ...

    def load_operations(self) -> tuple[OperationResult, ...]:
        return ()

    def save_operation(self, result: OperationResult) -> None:
        return None

    def get_idempotency_record(self, key: str) -> IdempotencyRecord | None:
        return None

    def save_idempotency_record(self, record: IdempotencyRecord) -> None:
        return None


def services_tuple(services: Iterable[EdgeServiceSpec]) -> tuple[EdgeServiceSpec, ...]:
    return tuple(services)
