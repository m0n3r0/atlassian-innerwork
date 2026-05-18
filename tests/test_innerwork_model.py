from innerwork.broker import EdgeBroker
from innerwork.control_plane import ControlPlane
from innerwork.model import Backend, EdgeServiceSpec, RouteRule


def test_broker_provision_returns_operation_then_succeeds():
    broker = EdgeBroker()
    spec = EdgeServiceSpec(
        service_id="jira-web",
        owner="jira-platform",
        domains=("jira.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="jira", port=8080)),),
    )

    operation = broker.provision(spec)

    assert operation.operation_id.startswith("op_")
    assert len(operation.operation_id) > 20
    assert broker.last_operation(operation.operation_id).state == "succeeded"
    assert broker.get_service("jira-web") == spec


def test_domain_uniqueness_is_enforced_across_services():
    broker = EdgeBroker()
    first = EdgeServiceSpec(
        service_id="jira-web",
        owner="jira-platform",
        domains=("shared.example.com",),
        routes=(RouteRule(prefix="/jira", backend=Backend(name="jira", port=8080)),),
    )
    second = EdgeServiceSpec(
        service_id="confluence-web",
        owner="confluence-platform",
        domains=("shared.example.com",),
        routes=(RouteRule(prefix="/wiki", backend=Backend(name="confluence", port=8090)),),
    )

    broker.provision(first)
    operation = broker.provision(second)

    result = broker.last_operation(operation.operation_id)
    assert result.state == "failed"
    assert "already owned" in result.description
    assert broker.get_service("confluence-web") is None


def test_control_plane_renders_deterministic_envoy_resources():
    broker = EdgeBroker()
    spec = EdgeServiceSpec(
        service_id="bitbucket-web",
        owner="bitbucket-platform",
        domains=("bitbucket.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="bitbucket", port=7990)),),
        features=("access_logs", "rate_limit", "external_auth"),
    )
    broker.provision(spec)

    snapshot = ControlPlane(broker).snapshot()

    assert len(snapshot.version) == 12
    assert snapshot.version == ControlPlane(broker).snapshot().version
    assert [cluster.name for cluster in snapshot.clusters] == ["bitbucket"]
    assert snapshot.virtual_hosts[0].domains == ("bitbucket.example.com",)
    assert snapshot.listeners[0].filters == (
        "http_connection_manager",
        "access_logs",
        "external_auth",
        "rate_limit",
    )
    assert snapshot.virtual_hosts[0].filters == (
        "access_logs",
        "external_auth",
        "rate_limit",
    )


def test_invalid_route_prefix_is_rejected_before_rendering():
    broker = EdgeBroker()
    spec = EdgeServiceSpec(
        service_id="bad-service",
        owner="edge-team",
        domains=("bad.example.com",),
        routes=(RouteRule(prefix="relative", backend=Backend(name="bad", port=8080)),),
    )

    operation = broker.provision(spec)

    result = broker.last_operation(operation.operation_id)
    assert result.state == "failed"
    assert "prefix must start with '/'" in result.description
    assert ControlPlane(broker).snapshot().clusters == ()


def test_domain_ownership_is_case_insensitive_and_canonicalized():
    broker = EdgeBroker()
    first = EdgeServiceSpec(
        service_id="jira-web",
        owner="jira-platform",
        domains=("Shared.Example.Com",),
        routes=(RouteRule(prefix="/jira", backend=Backend(name="jira", port=8080)),),
    )
    second = EdgeServiceSpec(
        service_id="confluence-web",
        owner="confluence-platform",
        domains=("shared.example.com",),
        routes=(RouteRule(prefix="/wiki", backend=Backend(name="confluence", port=8090)),),
    )

    first_operation = broker.provision(first)
    second_operation = broker.provision(second)

    assert broker.last_operation(first_operation.operation_id).state == "succeeded"
    assert broker.get_service("jira-web").domains == ("shared.example.com",)
    result = broker.last_operation(second_operation.operation_id)
    assert result.state == "failed"
    assert "shared.example.com is already owned" in result.description


def test_invalid_hostname_and_unknown_feature_fail_closed():
    broker = EdgeBroker()
    invalid_domain = EdgeServiceSpec(
        service_id="bad-domain",
        owner="edge-team",
        domains=("https://bad.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="bad", port=8080)),),
    )
    unknown_feature = EdgeServiceSpec(
        service_id="bad-feature",
        owner="edge-team",
        domains=("bad-feature.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="bad", port=8080)),),
        features=("externalAuth",),
    )

    domain_operation = broker.provision(invalid_domain)
    feature_operation = broker.provision(unknown_feature)

    assert broker.last_operation(domain_operation.operation_id).state == "failed"
    assert "invalid domain" in broker.last_operation(domain_operation.operation_id).description
    assert broker.last_operation(feature_operation.operation_id).state == "failed"
    assert "unsupported feature" in broker.last_operation(feature_operation.operation_id).description


def test_backend_name_port_conflict_is_rejected():
    broker = EdgeBroker()
    spec = EdgeServiceSpec(
        service_id="conflicting-backends",
        owner="edge-team",
        domains=("conflict.example.com",),
        routes=(
            RouteRule(prefix="/a", backend=Backend(name="api", port=8080)),
            RouteRule(prefix="/b", backend=Backend(name="api", port=9090)),
        ),
    )

    operation = broker.provision(spec)

    result = broker.last_operation(operation.operation_id)
    assert result.state == "failed"
    assert "backend api cannot use multiple ports" in result.description


def test_snapshot_version_changes_when_existing_service_changes():
    broker = EdgeBroker()
    first = EdgeServiceSpec(
        service_id="jira-web",
        owner="jira-platform",
        domains=("jira.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="jira", port=8080)),),
    )
    second = EdgeServiceSpec(
        service_id="jira-web",
        owner="jira-platform",
        domains=("jira.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="jira", port=8081)),),
    )

    broker.provision(first)
    first_version = ControlPlane(broker).snapshot().version
    broker.provision(second)
    second_version = ControlPlane(broker).snapshot().version

    assert first_version != second_version


def test_access_logs_are_mandatory_even_when_tenant_omits_feature():
    broker = EdgeBroker()
    spec = EdgeServiceSpec(
        service_id="minimal-web",
        owner="edge-team",
        domains=("minimal.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="minimal", port=8080)),),
    )

    broker.provision(spec)
    snapshot = ControlPlane(broker).snapshot()

    assert snapshot.listeners[0].filters == ("http_connection_manager", "access_logs")
    assert snapshot.virtual_hosts[0].filters == ("access_logs",)


def test_owner_change_for_existing_service_requires_transfer_path():
    broker = EdgeBroker()
    first = EdgeServiceSpec(
        service_id="jira-web",
        owner="jira-platform",
        domains=("jira.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="jira", port=8080)),),
    )
    takeover = EdgeServiceSpec(
        service_id="jira-web",
        owner="different-team",
        domains=("jira.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="jira", port=8080)),),
    )

    broker.provision(first)
    operation = broker.provision(takeover)

    result = broker.last_operation(operation.operation_id)
    assert result.state == "failed"
    assert "owner transfer" in result.description
    assert broker.get_service("jira-web").owner == "jira-platform"


def test_operation_lookup_is_scoped_to_service_and_unknown_safe():
    broker = EdgeBroker()
    spec = EdgeServiceSpec(
        service_id="jira-web",
        owner="jira-platform",
        domains=("jira.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="jira", port=8080)),),
    )

    operation = broker.provision(spec)

    assert operation.operation_id.startswith("op_")
    assert len(operation.operation_id) > 20
    assert broker.last_operation_for_service("jira-web", operation.operation_id).state == "succeeded"
    assert broker.last_operation_for_service("other-service", operation.operation_id).state == "failed"
    assert broker.last_operation_for_service("jira-web", "op_missing").state == "failed"


def test_cross_service_backend_name_port_conflict_is_rejected():
    broker = EdgeBroker()
    first = EdgeServiceSpec(
        service_id="jira-web",
        owner="jira-platform",
        domains=("jira.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="api", port=8080)),),
    )
    second = EdgeServiceSpec(
        service_id="confluence-web",
        owner="confluence-platform",
        domains=("confluence.example.com",),
        routes=(RouteRule(prefix="/", backend=Backend(name="api", port=9090)),),
    )

    broker.provision(first)
    operation = broker.provision(second)

    result = broker.last_operation(operation.operation_id)
    assert result.state == "failed"
    assert "already owned" in result.description


def test_routes_are_rendered_by_most_specific_prefix_first():
    broker = EdgeBroker()
    spec = EdgeServiceSpec(
        service_id="ordered-web",
        owner="edge-team",
        domains=("ordered.example.com",),
        routes=(
            RouteRule(prefix="/", backend=Backend(name="web-root", port=8080)),
            RouteRule(prefix="/z", backend=Backend(name="web-z", port=8082)),
            RouteRule(prefix="/api/v1", backend=Backend(name="web-api", port=8081)),
        ),
    )

    broker.provision(spec)
    routes = ControlPlane(broker).snapshot().virtual_hosts[0].routes

    assert [route.prefix for route in routes] == ["/api/v1", "/z", "/"]
