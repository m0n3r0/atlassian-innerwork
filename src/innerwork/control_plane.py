from __future__ import annotations

import hashlib
from collections.abc import Iterable

from .broker import EdgeBroker
from .model import EdgeServiceSpec, EnvoyCluster, EnvoyListener, EnvoySnapshot, EnvoyVirtualHost

_OPTIONAL_FEATURE_FILTERS = {
    "external_auth": "external_auth",
    "rate_limit": "rate_limit",
}
_MANDATORY_FILTERS = ("access_logs",)


class ControlPlane:
    """Render validated broker intent into deterministic xDS-style snapshots."""

    def __init__(self, broker: EdgeBroker) -> None:
        self._broker = broker

    def snapshot(self) -> EnvoySnapshot:
        services = self._broker.list_services()
        clusters_by_name: dict[str, EnvoyCluster] = {}
        virtual_hosts: list[EnvoyVirtualHost] = []
        enabled_optional_features: set[str] = set()

        for service in services:
            service_filters = self._filters_for_service(service.features)
            enabled_optional_features.update(service_filters)
            virtual_hosts.append(
                EnvoyVirtualHost(
                    name=service.service_id,
                    domains=service.domains,
                    routes=tuple(
                        sorted(
                            service.routes,
                            key=lambda route: (-len(route.prefix), route.prefix),
                        )
                    ),
                    filters=service_filters,
                )
            )
            for route in service.routes:
                clusters_by_name[route.backend.name] = EnvoyCluster(
                    name=route.backend.name,
                    port=route.backend.port,
                )

        clusters = tuple(clusters_by_name[name] for name in sorted(clusters_by_name))
        filters = ["http_connection_manager", *_MANDATORY_FILTERS]
        filters.extend(
            _OPTIONAL_FEATURE_FILTERS[feature]
            for feature in ("external_auth", "rate_limit")
            if feature in enabled_optional_features
        )
        listeners = (EnvoyListener(name="edge-https", filters=tuple(filters)),)

        return EnvoySnapshot(
            version=_snapshot_version(services),
            clusters=clusters,
            virtual_hosts=tuple(virtual_hosts),
            listeners=listeners,
        )

    def _filters_for_service(self, features: tuple[str, ...]) -> tuple[str, ...]:
        filters = [*_MANDATORY_FILTERS]
        filters.extend(
            _OPTIONAL_FEATURE_FILTERS[feature]
            for feature in ("external_auth", "rate_limit")
            if feature in features
        )
        return tuple(filters)


def _snapshot_version(services: Iterable[EdgeServiceSpec]) -> str:
    payload = repr(tuple(service.content_hash() for service in services)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]
