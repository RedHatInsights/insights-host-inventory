"""Tests for OpenTelemetry helpers in app.telemetry."""

import importlib
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
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


def _reload_telemetry(monkeypatch, env_overrides):
    """Reload the telemetry module with the given env var overrides applied."""
    for key, value in env_overrides.items():
        monkeypatch.setenv(key, value)
    import app.telemetry as telemetry_mod

    importlib.reload(telemetry_mod)
    return telemetry_mod


def _cleanup_telemetry(monkeypatch):
    """Reset the telemetry module back to disabled state."""
    monkeypatch.setenv("OTEL_ENABLED", "false")
    import app.telemetry as telemetry_mod

    importlib.reload(telemetry_mod)


def test_sampling_rate_applied_in_init_otel(monkeypatch):
    """TraceIdRatioBased sampler is created with OTEL_SAMPLING_RATE."""
    telemetry_mod = _reload_telemetry(monkeypatch, {"OTEL_ENABLED": "true", "OTEL_SAMPLING_RATE": "0.25"})

    with patch.object(telemetry_mod, "_otel_initialized_pid", None):
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        with (
            patch("opentelemetry.sdk.trace.TracerProvider") as mock_provider_cls,
            patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"),
        ):
            mock_provider_cls.return_value = MagicMock()
            telemetry_mod.init_otel(service_name="test-service")

            call_kwargs = mock_provider_cls.call_args
            sampler = call_kwargs[1]["sampler"] if "sampler" in call_kwargs[1] else call_kwargs[0][1]
            assert isinstance(sampler, TraceIdRatioBased)
            assert sampler.rate == 0.25

    _cleanup_telemetry(monkeypatch)


def test_bsp_params_passed_to_batch_span_processor(monkeypatch):
    """BatchSpanProcessor receives the env-configured queue/batch/delay/timeout values."""
    telemetry_mod = _reload_telemetry(
        monkeypatch,
        {
            "OTEL_ENABLED": "true",
            "OTEL_BSP_MAX_QUEUE_SIZE": "4096",
            "OTEL_BSP_MAX_EXPORT_BATCH_SIZE": "128",
            "OTEL_BSP_SCHEDULE_DELAY": "3000",
            "OTEL_BSP_EXPORT_TIMEOUT": "5000",
        },
    )

    with patch.object(telemetry_mod, "_otel_initialized_pid", None):
        with (
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor") as mock_bsp,
            patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"),
        ):
            mock_bsp.return_value = MagicMock()
            telemetry_mod.init_otel(service_name="test-service")

            _, kwargs = mock_bsp.call_args
            assert kwargs["max_queue_size"] == 4096
            assert kwargs["max_export_batch_size"] == 128
            assert kwargs["schedule_delay_millis"] == 3000
            assert kwargs["export_timeout_millis"] == 5000

    _cleanup_telemetry(monkeypatch)


def test_sql_instrumentation_skipped_when_disabled(monkeypatch):
    """instrument_sqlalchemy is a no-op when OTEL_SQL_ENABLED=false."""
    telemetry_mod = _reload_telemetry(monkeypatch, {"OTEL_ENABLED": "true", "OTEL_SQL_ENABLED": "false"})

    with patch("opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor") as mock_instrumentor:
        engine = MagicMock()
        telemetry_mod.instrument_sqlalchemy(engine)
        mock_instrumentor.assert_not_called()

    _cleanup_telemetry(monkeypatch)


def test_sql_commenter_toggled_by_env(monkeypatch):
    """enable_commenter reflects the OTEL_SQL_COMMENTER_ENABLED setting."""
    telemetry_mod = _reload_telemetry(
        monkeypatch, {"OTEL_ENABLED": "true", "OTEL_SQL_ENABLED": "true", "OTEL_SQL_COMMENTER_ENABLED": "true"}
    )

    with patch("opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        engine = MagicMock()
        telemetry_mod.instrument_sqlalchemy(engine)
        _, kwargs = instance.instrument.call_args
        assert kwargs["enable_commenter"] is True

    _cleanup_telemetry(monkeypatch)

    telemetry_mod = _reload_telemetry(
        monkeypatch, {"OTEL_ENABLED": "true", "OTEL_SQL_ENABLED": "true", "OTEL_SQL_COMMENTER_ENABLED": "false"}
    )

    with patch("opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        engine = MagicMock()
        telemetry_mod.instrument_sqlalchemy(engine)
        _, kwargs = instance.instrument.call_args
        assert kwargs["enable_commenter"] is False

    _cleanup_telemetry(monkeypatch)


def test_http_instrumentation_skipped_when_disabled(monkeypatch):
    """instrument_outbound_http is a no-op when OTEL_HTTP_ENABLED=false."""
    telemetry_mod = _reload_telemetry(monkeypatch, {"OTEL_ENABLED": "true", "OTEL_HTTP_ENABLED": "false"})

    with patch("opentelemetry.instrumentation.requests.RequestsInstrumentor") as mock_instrumentor:
        telemetry_mod.instrument_outbound_http()
        mock_instrumentor.assert_not_called()

    _cleanup_telemetry(monkeypatch)


def test_http_instrumentation_runs_when_enabled(monkeypatch):
    """instrument_outbound_http instruments when OTEL_HTTP_ENABLED=true."""
    telemetry_mod = _reload_telemetry(monkeypatch, {"OTEL_ENABLED": "true", "OTEL_HTTP_ENABLED": "true"})

    with patch("opentelemetry.instrumentation.requests.RequestsInstrumentor") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        telemetry_mod.instrument_outbound_http()
        instance.instrument.assert_called_once()

    _cleanup_telemetry(monkeypatch)


def test_config_defaults_without_env_vars(monkeypatch):
    """Module-level config constants use sensible defaults when env vars are absent."""
    for var in [
        "OTEL_SQL_ENABLED",
        "OTEL_SQL_COMMENTER_ENABLED",
        "OTEL_HTTP_ENABLED",
        "OTEL_SAMPLING_RATE",
        "OTEL_BSP_MAX_QUEUE_SIZE",
        "OTEL_BSP_MAX_EXPORT_BATCH_SIZE",
        "OTEL_BSP_SCHEDULE_DELAY",
        "OTEL_BSP_EXPORT_TIMEOUT",
        "OTEL_EXPORTER_OTLP_COMPRESSION",
        "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT",
        "OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT",
    ]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OTEL_ENABLED", "false")

    import app.telemetry as telemetry_mod

    importlib.reload(telemetry_mod)

    assert telemetry_mod.OTEL_ENABLED is False
    assert telemetry_mod.OTEL_SQL_ENABLED is True
    assert telemetry_mod.OTEL_SQL_COMMENTER_ENABLED is False
    assert telemetry_mod.OTEL_HTTP_ENABLED is True
    assert telemetry_mod.OTEL_SAMPLING_RATE == 1.0
    assert telemetry_mod.OTEL_BSP_MAX_QUEUE_SIZE == 8192
    assert telemetry_mod.OTEL_BSP_MAX_EXPORT_BATCH_SIZE == 256
    assert telemetry_mod.OTEL_BSP_SCHEDULE_DELAY == 2000
    assert telemetry_mod.OTEL_BSP_EXPORT_TIMEOUT == 10000
    assert telemetry_mod.OTEL_EXPORTER_OTLP_COMPRESSION == "gzip"
    assert telemetry_mod.OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT == 64
    assert telemetry_mod.OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT == 1024


@pytest.mark.parametrize(
    "env_value,expected_compression",
    [
        ("gzip", "Gzip"),
        ("GZIP", "Gzip"),
        ("deflate", "Deflate"),
        ("none", "NoCompression"),
        ("foobar", "NoCompression"),
    ],
)
def test_exporter_compression_mapping(monkeypatch, env_value, expected_compression):
    """OTLPSpanExporter receives the correct Compression enum for each config value."""
    from opentelemetry.exporter.otlp.proto.http import Compression

    telemetry_mod = _reload_telemetry(
        monkeypatch, {"OTEL_ENABLED": "true", "OTEL_EXPORTER_OTLP_COMPRESSION": env_value}
    )

    with patch.object(telemetry_mod, "_otel_initialized_pid", None):
        with patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter") as mock_exporter:
            mock_exporter.return_value = MagicMock()
            telemetry_mod.init_otel(service_name="test-service")
            expected_enum = getattr(Compression, expected_compression)
            mock_exporter.assert_called_once_with(compression=expected_enum)

    _cleanup_telemetry(monkeypatch)


def test_span_limits_applied_to_tracer_provider(monkeypatch):
    """SpanLimits are created with env-configured attribute limits."""
    telemetry_mod = _reload_telemetry(
        monkeypatch,
        {
            "OTEL_ENABLED": "true",
            "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT": "32",
            "OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT": "512",
        },
    )

    with patch.object(telemetry_mod, "_otel_initialized_pid", None):
        with (
            patch("opentelemetry.sdk.trace.TracerProvider") as mock_provider_cls,
            patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"),
        ):
            mock_provider_cls.return_value = MagicMock()
            telemetry_mod.init_otel(service_name="test-service")

            call_kwargs = mock_provider_cls.call_args[1]
            span_limits = call_kwargs["span_limits"]
            assert span_limits.max_attributes == 32
            assert span_limits.max_attribute_length == 512

    _cleanup_telemetry(monkeypatch)
