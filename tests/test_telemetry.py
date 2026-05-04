"""Tests for OpenTelemetry helpers in app.telemetry."""

import importlib
from unittest.mock import MagicMock

from flask import Flask
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.telemetry import _outbound_request_hook


def test_outbound_request_hook_updates_span_name():
    span = MagicMock()
    span.is_recording.return_value = True
    request = MagicMock()
    request.method = "GET"
    request.path_url = "/api/client/features"

    _outbound_request_hook(span, request)

    span.update_name.assert_called_once_with("GET /api/client/features")


def test_outbound_request_hook_strips_query_from_path_url():
    span = MagicMock()
    span.is_recording.return_value = True
    request = MagicMock()
    request.method = "GET"
    request.path_url = "/api/client/features?env=prod&limit=10"

    _outbound_request_hook(span, request, extra_kw=1)

    span.update_name.assert_called_once_with("GET /api/client/features")


def test_outbound_request_hook_noop_when_not_recording():
    span = MagicMock()
    span.is_recording.return_value = False
    request = MagicMock()

    _outbound_request_hook(span, request)

    span.update_name.assert_not_called()


def test_outbound_request_hook_uses_slash_when_path_empty():
    span = MagicMock()
    span.is_recording.return_value = True
    request = MagicMock()
    request.method = "GET"
    request.path_url = ""

    _outbound_request_hook(span, request)

    span.update_name.assert_called_once_with("GET /")


def test_instrument_flask_app_excludes_ops_urls_but_traces_other_routes(monkeypatch):
    """Regression: excluded_urls must match full request URLs (incl. query)."""
    monkeypatch.setenv("OTEL_ENABLED", "true")
    import app.telemetry as telemetry_mod

    importlib.reload(telemetry_mod)

    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    app = Flask(__name__)

    @app.route("/health")
    def health():
        return "ok"

    @app.route("/metrics")
    def metrics():
        return "ok"

    @app.route("/version")
    def version():
        return "ok"

    @app.route("/ping")
    def ping():
        return "pong"

    excluded_paths = [
        "/health",
        "/health?verbose=1",
        "/metrics",
        "/metrics?format=prom",
        "/version",
        "/version?foo=bar",
    ]

    try:
        telemetry_mod.instrument_flask_app(app)
        client = app.test_client()
        for path in excluded_paths:
            exporter.clear()
            client.get(path)
            assert not exporter.get_finished_spans(), f"expected no spans for {path!r}"
        exporter.clear()
        client.get("/ping")
        assert len(exporter.get_finished_spans()) == 1
    finally:
        FlaskInstrumentor().uninstrument_app(app)
        provider.shutdown()
        monkeypatch.setenv("OTEL_ENABLED", "false")
        importlib.reload(telemetry_mod)
