from __future__ import annotations

import secrets

from .model import EdgeServiceSpec, Operation, OperationResult
from .state_store import JsonStateStore


class EdgeBroker:
    """Small OSB-inspired broker model for self-service edge exposure.

    The production pattern is asynchronous: API requests enqueue provisioning
    work, workers validate/apply intent, and clients poll last-operation state.
    This in-memory model executes immediately but keeps the same contract.
    """

    def __init__(self, *, state_store: JsonStateStore | None = None) -> None:
        self._services: dict[str, EdgeServiceSpec] = {}
        self._operations: dict[str, OperationResult] = {}
        self._operation_counter = 0
        self._state_store = state_store
        if state_store is not None:
            for service in state_store.load_services():
                self._services[service.service_id] = service

    def provision(self, spec: EdgeServiceSpec) -> Operation:
        operation = self._next_operation(spec.service_id)
        try:
            normalized = spec.canonicalized()
            self._enforce_owner_continuity(normalized)
            self._enforce_domain_ownership(normalized)
            self._enforce_backend_consistency(normalized)
        except ValueError as exc:
            self._operations[operation.operation_id] = OperationResult(
                operation_id=operation.operation_id,
                service_id=spec.service_id,
                state="failed",
                description=str(exc),
            )
            return operation

        self._services[normalized.service_id] = normalized
        if self._state_store is not None:
            self._state_store.save_services(self.list_services())
        self._operations[operation.operation_id] = OperationResult(
            operation_id=operation.operation_id,
            service_id=normalized.service_id,
            state="succeeded",
            description="service intent stored",
        )
        return operation

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
