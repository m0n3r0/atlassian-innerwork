from __future__ import annotations

from typing import Any

from .model import (
    Backend,
    EdgeServiceSpec,
    EnvoyCluster,
    EnvoyListener,
    EnvoySnapshot,
    EnvoyVirtualHost,
    Operation,
    OperationResult,
    RouteRule,
)


def spec_from_dict(payload: dict[str, Any]) -> EdgeServiceSpec:
    """Build and validate an EdgeServiceSpec from API/CLI-shaped data."""

    routes = tuple(
        RouteRule(
            prefix=str(route["prefix"]),
            backend=Backend(
                name=str(route["backend"]["name"]),
                port=int(route["backend"]["port"]),
            ),
        )
        for route in payload.get("routes", ())
    )
    return EdgeServiceSpec(
        service_id=str(payload["service_id"]),
        owner=str(payload["owner"]),
        product_family=str(payload["product_family"]),
        edge_profile=str(payload["edge_profile"]),
        domains=tuple(str(domain) for domain in payload.get("domains", ())),
        routes=routes,
        features=tuple(str(feature) for feature in payload.get("features", ())),
    ).canonicalized()


def spec_to_dict(spec: EdgeServiceSpec) -> dict[str, Any]:
    return {
        "service_id": spec.service_id,
        "owner": spec.owner,
        "product_family": spec.product_family,
        "edge_profile": spec.edge_profile,
        "domains": list(spec.domains),
        "routes": [route_to_dict(route) for route in spec.routes],
        "features": list(spec.features),
    }


def route_to_dict(route: RouteRule) -> dict[str, Any]:
    return {
        "prefix": route.prefix,
        "backend": {
            "name": route.backend.name,
            "port": route.backend.port,
        },
    }


def operation_to_dict(operation: Operation) -> dict[str, Any]:
    return {
        "operation": operation.operation_id,
        "service_id": operation.service_id,
    }


def operation_result_to_dict(result: OperationResult) -> dict[str, Any]:
    return {
        "operation": result.operation_id,
        "service_id": result.service_id,
        "state": result.state,
        "description": result.description,
    }


def snapshot_to_dict(snapshot: EnvoySnapshot) -> dict[str, Any]:
    return {
        "version": snapshot.version,
        "clusters": [cluster_to_dict(cluster) for cluster in snapshot.clusters],
        "virtual_hosts": [virtual_host_to_dict(host) for host in snapshot.virtual_hosts],
        "listeners": [listener_to_dict(listener) for listener in snapshot.listeners],
    }


def cluster_to_dict(cluster: EnvoyCluster) -> dict[str, Any]:
    return {"name": cluster.name, "port": cluster.port}


def virtual_host_to_dict(host: EnvoyVirtualHost) -> dict[str, Any]:
    return {
        "name": host.name,
        "domains": list(host.domains),
        "routes": [route_to_dict(route) for route in host.routes],
        "filters": list(host.filters),
    }


def listener_to_dict(listener: EnvoyListener) -> dict[str, Any]:
    return {"name": listener.name, "filters": list(listener.filters)}
