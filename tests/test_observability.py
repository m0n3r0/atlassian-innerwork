"""Tests for the Phase 8 observability primitives + middleware wiring."""

from __future__ import annotations

import json
import logging
import re

from fastapi.testclient import TestClient

from innerwork.app import create_app
from innerwork.observability import (
    JsonLogFormatter,
    MetricsRegistry,
    current_request_id,
    get_json_logger,
    new_request_id,
    registry,
    trace_span,
)


def test_metrics_registry_counter_inc_and_render() -> None:
    reg = MetricsRegistry()
    reg.counter("test_total", "help text")
    reg.inc("test_total", labels={"a": "1"})
    reg.inc("test_total", labels={"a": "1"})
    reg.inc("test_total", labels={"a": "2"}, value=3.5)
    text = reg.render()
    assert "# HELP test_total help text" in text
    assert "# TYPE test_total counter" in text
    assert 'test_total{a="1"} 2.0' in text
    assert 'test_total{a="2"} 3.5' in text


def test_metrics_registry_histogram_bucket_counts() -> None:
    reg = MetricsRegistry()
    reg.histogram("h_ms", "h help", buckets=(10.0, 100.0))
    for v in (5.0, 8.0, 50.0, 200.0):
        reg.observe("h_ms", v, labels={"endpoint": "x"})
    text = reg.render()
    assert 'h_ms_bucket{endpoint="x",le="10"} 2.0' in text
    assert 'h_ms_bucket{endpoint="x",le="100"} 3.0' in text
    assert 'h_ms_bucket{endpoint="x",le="+Inf"} 4.0' in text
    assert 'h_ms_sum{endpoint="x"} 263.0' in text
    assert 'h_ms_count{endpoint="x"} 4.0' in text


def test_metrics_registry_rejects_negative_counter_increment() -> None:
    reg = MetricsRegistry()
    reg.counter("c")
    try:
        reg.inc("c", value=-1.0)
    except ValueError:
        return
    raise AssertionError("expected ValueError on negative inc")


def test_json_log_formatter_emits_required_fields_and_request_id() -> None:
    fmt = JsonLogFormatter()
    new_request_id()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.user_id = "u-42"
    payload = json.loads(fmt.format(record))
    assert payload["msg"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "t"
    assert payload["user_id"] == "u-42"
    assert re.fullmatch(r"[0-9a-f]{32}", payload["request_id"])


def test_trace_span_records_duration_and_decorates_logs(caplog) -> None:
    registry.reset()
    logger = get_json_logger("trace.test")
    with caplog.at_level(logging.INFO, logger="trace.test"):
        with trace_span("outer"):
            with trace_span("inner"):
                logger.info("inside")
    assert any("inside" in r.message for r in caplog.records)
    text = registry.render()
    assert 'span_duration_ms_count{span="outer"} 1.0' in text
    assert 'span_duration_ms_count{span="inner"} 1.0' in text


def test_app_middleware_emits_request_id_and_records_metrics() -> None:
    registry.reset()
    app = create_app()
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    rid = r.headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", rid)
    text = client.get("/metrics").text
    assert 'http_requests_total{endpoint="/healthz",method="GET",status="200"}' in text
    assert "http_request_duration_ms_bucket" in text


def test_app_middleware_honors_upstream_request_id() -> None:
    registry.reset()
    app = create_app()
    client = TestClient(app)
    upstream = "trace-from-edge-001"
    r = client.get("/v1/system/request-id", headers={"x-request-id": upstream})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == upstream
    assert r.json() == {"request_id": upstream}


def test_metrics_endpoint_uses_route_template_not_raw_path() -> None:
    registry.reset()
    app = create_app()
    client = TestClient(app)
    # Hit a parameterized route twice with different ids; bucket should
    # collapse to the route template, not two distinct labels.
    created = client.post(
        "/v1/projects",
        json={"key": "AAA", "name": "alpha", "owner": "eml"},
        headers={"X-Idempotency-Key": "obs-test-idempotency-0001"},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["project_id"]
    client.get(f"/v1/projects/{project_id}")
    text = client.get("/metrics").text
    # Distinct labels for the two endpoints; the path-parameter route
    # collapses to its template.
    assert 'endpoint="/v1/projects/{project_id}"' in text
    assert (
        text.count('endpoint="/v1/projects/{project_id}"')
        >= 2  # at least requests_total + duration_count rows
    )
    # Make sure no row leaked the literal id.
    assert project_id not in text


def test_current_request_id_isolated_between_requests() -> None:
    registry.reset()
    # Clear any residual id bound by an earlier test in this thread.
    from innerwork.observability import _request_id_var

    _request_id_var.set(None)
    app = create_app()
    client = TestClient(app)
    r1 = client.get("/healthz")
    r2 = client.get("/healthz")
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]
    # Outside any request, no id is bound on the test thread.
    assert current_request_id() is None
