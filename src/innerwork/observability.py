"""In-process observability primitives for Phase 8.

This module is intentionally stdlib-only. It exposes three primitives that
the FastAPI app and CLI can use to emit structured logs, in-process metrics,
and contextvar-based traces:

1. ``get_json_logger(name)`` — returns a ``logging.Logger`` configured with
   a JSON formatter so log lines are machine-parseable.
2. ``MetricsRegistry`` — a tiny counter + histogram registry that renders
   Prometheus 0.0.4 text exposition format. The registry is process-local;
   no scraper is shipped. Operators wire it into ``/metrics`` if they want
   Prometheus scraping, otherwise it remains a debug surface.
3. ``trace_span(name)`` — a context manager that pushes a span onto a
   contextvar stack. Spans carry a request id correlation header so logs
   emitted inside a span automatically include the request id.

The module deliberately avoids OpenTelemetry, prometheus_client, ddtrace,
or any other dependency. That decision is logged in
``docs/observability.md``; if a managed backend is wired later, the
primitives here become the bridge layer.
"""

from __future__ import annotations

import contextvars
import json
import logging
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "JsonLogFormatter",
    "MetricsRegistry",
    "configure_json_logging",
    "current_request_id",
    "get_json_logger",
    "new_request_id",
    "registry",
    "trace_span",
]


# ---------------------------------------------------------------------------
# Request id correlation
# ---------------------------------------------------------------------------

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "innerwork_request_id", default=None
)
_span_stack_var: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "innerwork_span_stack", default=()
)


def new_request_id() -> str:
    """Generate a fresh request id and bind it to the current context."""
    rid = uuid.uuid4().hex
    _request_id_var.set(rid)
    return rid


def current_request_id() -> str | None:
    """Return the current request id, if one has been bound."""
    return _request_id_var.get()


# ---------------------------------------------------------------------------
# JSON logging
# ---------------------------------------------------------------------------


class JsonLogFormatter(logging.Formatter):
    """Format log records as single-line JSON.

    Output keys: ``ts``, ``level``, ``logger``, ``msg``, plus ``request_id``
    and ``spans`` when bound, plus any ``extra={...}`` fields the caller
    attached via ``logger.info("...", extra={"key": value})``.
    """

    _RESERVED = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "asctime",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = current_request_id()
        if rid is not None:
            payload["request_id"] = rid
        spans = _span_stack_var.get()
        if spans:
            payload["spans"] = list(spans)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in self._RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                value = repr(value)
            payload[key] = value
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


_configured_lock = threading.Lock()
_configured = False


def configure_json_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger exactly once.

    Idempotent: callers may invoke this on every app startup. We attach a
    single ``StreamHandler`` whose formatter is the ``JsonLogFormatter``.
    """
    global _configured
    with _configured_lock:
        if _configured:
            return
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(level)
        _configured = True


def get_json_logger(name: str) -> logging.Logger:
    """Return a logger; ensure JSON logging is configured first."""
    configure_json_logging()
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Metrics registry (Prometheus text exposition, in-process)
# ---------------------------------------------------------------------------


_HIST_BUCKETS_MS: tuple[float, ...] = (
    5.0,
    10.0,
    25.0,
    50.0,
    100.0,
    250.0,
    500.0,
    1000.0,
    2500.0,
    5000.0,
)


@dataclass
class _Counter:
    name: str
    help_text: str
    samples: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)


@dataclass
class _Histogram:
    name: str
    help_text: str
    buckets: tuple[float, ...]
    # samples[label_key] = [bucket_counts..., sum, count]
    samples: dict[tuple[tuple[str, str], ...], list[float]] = field(default_factory=dict)


class MetricsRegistry:
    """In-process counter + histogram registry.

    The registry is thread-safe. It exposes a Prometheus text-format
    renderer suitable for serving from a ``/metrics`` endpoint. No scraper,
    pusher, or exporter is included; this is the emission primitive only.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, _Counter] = {}
        self._histograms: dict[str, _Histogram] = {}

    def reset(self) -> None:
        """Clear all metrics. Test-only; not exposed to HTTP."""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()

    def counter(self, name: str, help_text: str = "") -> None:
        """Declare a counter; safe to call repeatedly."""
        with self._lock:
            self._counters.setdefault(name, _Counter(name=name, help_text=help_text))

    def histogram(
        self,
        name: str,
        help_text: str = "",
        buckets: tuple[float, ...] = _HIST_BUCKETS_MS,
    ) -> None:
        """Declare a histogram; safe to call repeatedly."""
        with self._lock:
            self._histograms.setdefault(
                name, _Histogram(name=name, help_text=help_text, buckets=buckets)
            )

    def inc(self, name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        if value < 0:
            raise ValueError("counter increments must be non-negative")
        key = _label_key(labels)
        with self._lock:
            counter = self._counters.get(name)
            if counter is None:
                counter = _Counter(name=name, help_text="")
                self._counters[name] = counter
            counter.samples[key] = counter.samples.get(key, 0.0) + value

    def observe(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        key = _label_key(labels)
        with self._lock:
            hist = self._histograms.get(name)
            if hist is None:
                hist = _Histogram(name=name, help_text="", buckets=_HIST_BUCKETS_MS)
                self._histograms[name] = hist
            sample = hist.samples.get(key)
            if sample is None:
                sample = [0.0] * len(hist.buckets) + [0.0, 0.0]
                hist.samples[key] = sample
            for idx, edge in enumerate(hist.buckets):
                if value <= edge:
                    sample[idx] += 1
            sample[-2] += value  # sum
            sample[-1] += 1.0  # count

    def render(self) -> str:
        """Serialize the registry as Prometheus 0.0.4 text format."""
        lines: list[str] = []
        with self._lock:
            for counter in sorted(self._counters.values(), key=lambda c: c.name):
                if counter.help_text:
                    lines.append(f"# HELP {counter.name} {counter.help_text}")
                lines.append(f"# TYPE {counter.name} counter")
                if not counter.samples:
                    lines.append(f"{counter.name} 0")
                    continue
                for key, value in sorted(counter.samples.items()):
                    lines.append(f"{counter.name}{_render_labels(key)} {value}")
            for hist in sorted(self._histograms.values(), key=lambda h: h.name):
                if hist.help_text:
                    lines.append(f"# HELP {hist.name} {hist.help_text}")
                lines.append(f"# TYPE {hist.name} histogram")
                for key, sample in sorted(hist.samples.items()):
                    for idx, edge in enumerate(hist.buckets):
                        bucket_labels = key + (("le", _fmt(edge)),)
                        lines.append(
                            f"{hist.name}_bucket{_render_labels(bucket_labels)} {sample[idx]}"
                        )
                    inf_labels = key + (("le", "+Inf"),)
                    lines.append(
                        f"{hist.name}_bucket{_render_labels(inf_labels)} {sample[-1]}"
                    )
                    lines.append(f"{hist.name}_sum{_render_labels(key)} {sample[-2]}")
                    lines.append(f"{hist.name}_count{_render_labels(key)} {sample[-1]}")
        return "\n".join(lines) + "\n"


def _label_key(labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _render_labels(key: tuple[tuple[str, str], ...]) -> str:
    if not key:
        return ""
    parts = [f'{k}="{_escape(v)}"' for k, v in key]
    return "{" + ",".join(parts) + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _fmt(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return repr(value)


# Module-level singleton; tests may call ``registry.reset()`` between cases.
registry = MetricsRegistry()
registry.counter("http_requests_total", "Total HTTP requests processed")
registry.counter(
    "http_request_errors_total",
    "Total HTTP requests with status >= 500 or raised exception",
)
registry.histogram(
    "http_request_duration_ms",
    "Wall-clock duration of HTTP requests in milliseconds",
)
registry.counter(
    "domain_writes_total",
    "Domain mutation count (work-graph + knowledge-graph)",
)
registry.counter(
    "domain_write_conflicts_total",
    "Domain mutation rejections by reason (e.g. version_conflict, invalid_state)",
)


# ---------------------------------------------------------------------------
# Tracing (contextvar-based, in-process)
# ---------------------------------------------------------------------------


@contextmanager
def trace_span(name: str) -> Iterator[None]:
    """Push ``name`` onto the in-process span stack for the current context.

    Spans show up in JSON log lines under ``"spans"`` so an operator can
    correlate emissions inside a logical operation without wiring an
    external tracer. The span is timed and its duration is observed into
    the ``span_duration_ms`` histogram so a future operator can pick up
    span-level latency without instrumenting every callsite.
    """
    registry.histogram("span_duration_ms", "Duration of in-process trace spans in milliseconds")
    stack = _span_stack_var.get()
    token = _span_stack_var.set(stack + (name,))
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        registry.observe("span_duration_ms", elapsed_ms, labels={"span": name})
        _span_stack_var.reset(token)
