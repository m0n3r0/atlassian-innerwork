from __future__ import annotations

import secrets
from typing import Any

from .model import EdgeServiceSpec, Operation, OperationResult
from .serialization import spec_from_dict
from .state_store_base import IdempotencyRecord, StateStore


class EdgeBroker:
    """Small OSB-inspired broker model for self-service edge exposure.

    The production pattern is asynchronous: API requests enqueue provisioning
    work, workers validate/apply intent, and clients poll last-operation state.
    This in-memory model executes immediately but keeps the same contract.
    """

    def __init__(self, *, state_store: StateStore | None = None) -> None:
        self._services: dict[str, EdgeServiceSpec] = {}
        self._operations: dict[str, OperationResult] = {}
        self._operation_counter = 0
        self._state_store = state_store
        if state_store is not None:
            for service in state_store.load_services():
                self._services[service.service_id] = service
            for operation in state_store.load_operations():
                self._operations[operation.operation_id] = operation

    def provision_from_payload(
        self,
        instance_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Operation:
        request_payload = dict(payload)
        request_payload["service_id"] = instance_id
        return self.provision(spec_from_dict(request_payload), idempotency_key=idempotency_key)

    def provision(
        self,
        spec: EdgeServiceSpec,
        *,
        idempotency_key: str | None = None,
    ) -> Operation:
        try:
            normalized = spec.canonicalized()
        except ValueError as exc:
            return self._record_failure(_operation_id(), spec.service_id, str(exc))
        request_hash = normalized.content_hash()
        if idempotency_key is not None:
            existing = self._idempotency_record(idempotency_key)
            if existing is not None:
                if existing.request_hash != request_hash:
                    return self._record_failure(
                        _operation_id(),
                        normalized.service_id,
                        "idempotency key reused for a different service intent",
                    )
                return Operation(
                    operation_id=existing.operation_id,
                    service_id=normalized.service_id,
                )

        operation = self._next_operation(normalized.service_id)
        try:
            self._enforce_owner_continuity(normalized)
            self._enforce_domain_ownership(normalized)
            self._enforce_backend_consistency(normalized)
        except ValueError as exc:
            failed = self._record_failure(operation.operation_id, normalized.service_id, str(exc))
            if idempotency_key is not None:
                self._save_idempotency_record(idempotency_key, request_hash, failed.operation_id)
            return failed

        self._services[normalized.service_id] = normalized
        if self._state_store is not None:
            self._state_store.save_services(self.list_services())
        self._record_operation(
            OperationResult(
                operation_id=operation.operation_id,
                service_id=normalized.service_id,
                state="succeeded",
                description="service intent stored",
            )
        )
        if idempotency_key is not None:
            self._save_idempotency_record(idempotency_key, request_hash, operation.operation_id)
        return operation

    def record_failed_operation(self, service_id: str, description: str) -> Operation:
        return self._record_failure(_operation_id(), service_id, description)

    def last_operation(self, operation_id: str) -> OperationResult:
        result = self._operations.get(operation_id)
        if result is None:
            return OperationResult(
                operation_id=operation_id,
                service_id="",
                state="failed",
                description="operation not found",
            )
        return result

    def last_operation_for_service(self, service_id: str, operation_id: str) -> OperationResult:
        result = self.last_operation(operation_id)
        if result.service_id != service_id:
            return OperationResult(
                operation_id=operation_id,
                service_id=service_id,
                state="failed",
                description="operation not found for service",
            )
        return result

    def get_service(self, service_id: str) -> EdgeServiceSpec | None:
        return self._services.get(service_id)

    def list_services(self) -> tuple[EdgeServiceSpec, ...]:
        return tuple(self._services[service_id] for service_id in sorted(self._services))

    def _next_operation(self, service_id: str) -> Operation:
        self._operation_counter += 1
        return Operation(operation_id=_operation_id(), service_id=service_id)

    def _record_failure(self, operation_id: str, service_id: str, description: str) -> Operation:
        self._record_operation(
            OperationResult(
                operation_id=operation_id,
                service_id=service_id,
                state="failed",
                description=description,
            )
        )
        return Operation(operation_id=operation_id, service_id=service_id)

    def _record_operation(self, result: OperationResult) -> None:
        self._operations[result.operation_id] = result
        if self._state_store is not None:
            self._state_store.save_operation(result)

    def _idempotency_record(self, key: str) -> IdempotencyRecord | None:
        if self._state_store is None:
            return None
        return self._state_store.get_idempotency_record(key)

    def _save_idempotency_record(self, key: str, request_hash: str, operation_id: str) -> None:
        if self._state_store is not None:
            self._state_store.save_idempotency_record(
                IdempotencyRecord(key=key, request_hash=request_hash, operation_id=operation_id)
            )

    def _enforce_owner_continuity(self, spec: EdgeServiceSpec) -> None:
        existing = self._services.get(spec.service_id)
        if existing is not None and existing.owner != spec.owner:
            raise ValueError("owner transfer requires an explicit transfer path")

    def _enforce_domain_ownership(self, spec: EdgeServiceSpec) -> None:
        requested_domains = set(spec.domains)
        for existing in self._services.values():
            if existing.service_id == spec.service_id:
                continue
            conflict = requested_domains.intersection(existing.domains)
            if conflict:
                domain = sorted(conflict)[0]
                raise ValueError(
                    f"domain {domain} is already owned by service {existing.service_id}"
                )

    def _enforce_backend_consistency(self, spec: EdgeServiceSpec) -> None:
        existing_owners = {
            route.backend.name: service.service_id
            for service in self._services.values()
            if service.service_id != spec.service_id
            for route in service.routes
        }
        for route in spec.routes:
            existing_owner = existing_owners.get(route.backend.name)
            if existing_owner is not None:
                raise ValueError(
                    f"backend {route.backend.name} is already owned by service {existing_owner}"
                )


def _operation_id() -> str:
    return f"op_{secrets.token_urlsafe(18)}"
