from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from typing import Literal

OperationState = Literal["in_progress", "succeeded", "failed", "requires_attention"]
FeatureName = Literal["external_auth", "rate_limit", "access_logs"]

_ALLOWED_FEATURES: frozenset[str] = frozenset({"external_auth", "rate_limit", "access_logs"})
_DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_RESOURCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_BACKEND_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


def canonical_domain(domain: str) -> str:
    """Return a lower-case IDNA hostname or raise ValueError.

    Hostnames are case-insensitive. Canonicalizing them before persistence keeps
    ownership checks and rendered proxy config aligned with DNS semantics.
    """

    raw = domain.strip()
    if raw != domain or not raw or "://" in raw or "/" in raw or "*" in raw:
        raise ValueError(f"invalid domain: {domain}")
    try:
        ascii_domain = raw.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError(f"invalid domain: {domain}") from exc
    labels = ascii_domain.split(".")
    if len(labels) < 2 or any(not _DNS_LABEL_RE.fullmatch(label) for label in labels):
        raise ValueError(f"invalid domain: {domain}")
    if len(ascii_domain) > 253:
        raise ValueError(f"invalid domain: {domain}")
    return ascii_domain


@dataclass(frozen=True)
class Backend:
    """A backend service target reachable from the edge proxy fleet."""

    name: str
    port: int

    def validate(self) -> None:
        if not _BACKEND_NAME_RE.fullmatch(self.name):
            raise ValueError("backend name must be a DNS-safe service name")
        if not 1 <= self.port <= 65535:
            raise ValueError("backend port must be between 1 and 65535")


@dataclass(frozen=True)
class RouteRule:
    """Developer-facing route intent, not raw Envoy configuration."""

    prefix: str
    backend: Backend

    def validate(self) -> None:
        if not self.prefix.startswith("/"):
            raise ValueError("route prefix must start with '/'")
        if "//" in self.prefix:
            raise ValueError("route prefix must not contain empty path segments")
        self.backend.validate()


@dataclass(frozen=True)
class EdgeServiceSpec:
    """Self-service edge exposure request submitted by a product team."""

    service_id: str
    owner: str
    domains: tuple[str, ...]
    routes: tuple[RouteRule, ...]
    features: tuple[str, ...] = field(default_factory=tuple)

    def canonicalized(self) -> EdgeServiceSpec:
        normalized = replace(
            self,
            service_id=self.service_id.strip(),
            owner=self.owner.strip(),
            domains=tuple(canonical_domain(domain) for domain in self.domains),
            features=tuple(sorted(set(self.features))),
        )
        normalized.validate()
        return normalized

    def validate(self) -> None:
        if not _RESOURCE_NAME_RE.fullmatch(self.service_id):
            raise ValueError("service_id must match ^[a-z0-9][a-z0-9-]{1,62}$")
        if not self.owner:
            raise ValueError("owner is required")
        if not self.domains:
            raise ValueError("at least one domain is required")
        if len(set(self.domains)) != len(self.domains):
            raise ValueError("domains must be unique")
        if not self.routes:
            raise ValueError("at least one route is required")
        for domain in self.domains:
            canonical_domain(domain)
        for feature in self.features:
            if feature not in _ALLOWED_FEATURES:
                raise ValueError(f"unsupported feature: {feature}")
        backend_ports: dict[str, int] = {}
        for route in self.routes:
            route.validate()
            existing_port = backend_ports.setdefault(route.backend.name, route.backend.port)
            if existing_port != route.backend.port:
                raise ValueError(f"backend {route.backend.name} cannot use multiple ports")

    def content_hash(self) -> str:
        payload = repr(
            (
                self.service_id,
                self.owner,
                self.domains,
                tuple((route.prefix, route.backend.name, route.backend.port) for route in self.routes),
                self.features,
            )
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Operation:
    operation_id: str
    service_id: str


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    service_id: str
    state: OperationState
    description: str


@dataclass(frozen=True)
class EnvoyCluster:
    name: str
    port: int


@dataclass(frozen=True)
class EnvoyVirtualHost:
    name: str
    domains: tuple[str, ...]
    routes: tuple[RouteRule, ...]
    filters: tuple[str, ...]


@dataclass(frozen=True)
class EnvoyListener:
    name: str
    filters: tuple[str, ...]


@dataclass(frozen=True)
class EnvoySnapshot:
    version: str
    clusters: tuple[EnvoyCluster, ...]
    virtual_hosts: tuple[EnvoyVirtualHost, ...]
    listeners: tuple[EnvoyListener, ...]
