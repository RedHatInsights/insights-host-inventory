"""OpenTelemetry initialization for HBI services.

Provides centralized tracing setup for all HBI entry points (web API, MQ service,
export service). Every knob is configurable via environment variables so stage and
prod can run independent configurations without code changes.

Usage:
    from app.telemetry import init_otel, instrument_flask_app, instrument_sqlalchemy, instrument_outbound_http

    # In gunicorn.conf.py post_fork or service main():
    init_otel(service_name="host-inventory")

    # After Flask app creation:
    instrument_flask_app(flask_app)

    # After db.init_app():
    instrument_sqlalchemy(db.engine)

    # For outbound HTTP (e.g., RBAC calls):
    instrument_outbound_http()
"""

import contextlib
import os
from urllib.parse import urlparse

from app.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration — all tunables are environment-driven
# ---------------------------------------------------------------------------
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
OTEL_SQL_ENABLED = os.getenv("OTEL_SQL_ENABLED", "true").lower() == "true"
OTEL_SQL_COMMENTER_ENABLED = os.getenv("OTEL_SQL_COMMENTER_ENABLED", "false").lower() == "true"
OTEL_HTTP_ENABLED = os.getenv("OTEL_HTTP_ENABLED", "true").lower() == "true"
OTEL_SAMPLING_RATE = min(max(float(os.getenv("OTEL_SAMPLING_RATE", "1.0")), 0.0), 1.0)

OTEL_BSP_MAX_QUEUE_SIZE = int(os.getenv("OTEL_BSP_MAX_QUEUE_SIZE", "8192"))
OTEL_BSP_MAX_EXPORT_BATCH_SIZE = int(os.getenv("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", "256"))
OTEL_BSP_SCHEDULE_DELAY = int(os.getenv("OTEL_BSP_SCHEDULE_DELAY", "2000"))
OTEL_BSP_EXPORT_TIMEOUT = int(os.getenv("OTEL_BSP_EXPORT_TIMEOUT", "10000"))

OTEL_EXPORTER_OTLP_COMPRESSION = os.getenv("OTEL_EXPORTER_OTLP_COMPRESSION", "gzip").lower()
OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT = int(os.getenv("OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT", "64"))
OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT = int(os.getenv("OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT", "1024"))

_otel_initialized_pid = None


def get_tracer(name: str):
    """Get an OpenTelemetry tracer for creating custom spans.

    When init_otel() has not been called (i.e. OTEL is disabled), the SDK's
    default TracerProvider is a no-op that creates zero-overhead no-op spans.
    """
    from opentelemetry import trace

    return trace.get_tracer(name)


def init_otel(service_name: str, service_version: str = "unknown"):
    """Initialize OpenTelemetry tracing. Safe to call multiple times.

    Uses the current PID to detect fork boundaries: if run.py initializes
    in the Gunicorn master process and then post_fork calls again in a
    worker, the PID will differ and the worker will re-initialize with a
    fresh (fork-safe) TracerProvider and BatchSpanProcessor.

    For single-process services (MQ, export), the second call is a no-op.
    """
    global _otel_initialized_pid

    if _otel_initialized_pid == os.getpid():
        return

    if not OTEL_ENABLED:
        logger.info("OpenTelemetry is disabled (OTEL_ENABLED != 'true')")
        _otel_initialized_pid = os.getpid()
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import SERVICE_NAME
    from opentelemetry.sdk.resources import SERVICE_VERSION
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import SpanLimits
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

    resource = Resource.create(
        attributes={
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "deployment.environment": os.getenv("NAMESPACE", "development"),
        }
    )

    sampler = TraceIdRatioBased(OTEL_SAMPLING_RATE)
    span_limits = SpanLimits(
        max_attributes=OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT,
        max_attribute_length=OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT,
    )
    provider = TracerProvider(resource=resource, sampler=sampler, span_limits=span_limits)

    from opentelemetry.exporter.otlp.proto.http import Compression

    _compression_map = {"gzip": Compression.Gzip, "deflate": Compression.Deflate}
    compression = _compression_map.get(OTEL_EXPORTER_OTLP_COMPRESSION, Compression.NoCompression)
    exporter = OTLPSpanExporter(compression=compression)
    provider.add_span_processor(
        BatchSpanProcessor(
            exporter,
            max_queue_size=OTEL_BSP_MAX_QUEUE_SIZE,
            max_export_batch_size=OTEL_BSP_MAX_EXPORT_BATCH_SIZE,
            schedule_delay_millis=OTEL_BSP_SCHEDULE_DELAY,
            export_timeout_millis=OTEL_BSP_EXPORT_TIMEOUT,
        )
    )

    trace.set_tracer_provider(provider)
    _otel_initialized_pid = os.getpid()
    logger.info("OpenTelemetry initialized for service=%s version=%s", service_name, service_version)
    logger.info(
        "OpenTelemetry config: sampling=%.2f sql=%s commenter=%s http=%s "
        "bsp_queue=%d bsp_batch=%d bsp_delay=%dms bsp_timeout=%dms "
        "compression=%s attr_limit=%d attr_len_limit=%d",
        OTEL_SAMPLING_RATE,
        OTEL_SQL_ENABLED,
        OTEL_SQL_COMMENTER_ENABLED,
        OTEL_HTTP_ENABLED,
        OTEL_BSP_MAX_QUEUE_SIZE,
        OTEL_BSP_MAX_EXPORT_BATCH_SIZE,
        OTEL_BSP_SCHEDULE_DELAY,
        OTEL_BSP_EXPORT_TIMEOUT,
        OTEL_EXPORTER_OTLP_COMPRESSION,
        OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT,
        OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT,
    )


def instrument_flask_app(flask_app):
    """Instrument a Flask app with OpenTelemetry request tracing.

    Each HTTP request becomes a span with method, path, status code,
    plus HBI-specific attributes (org_id, request_id).
    """
    if not OTEL_ENABLED:
        return

    from opentelemetry.instrumentation.flask import FlaskInstrumentor

    # Patterns match flask.request.url (full URL), not path-only; do not anchor with ^.
    # Optional (?...) allows query strings (e.g. /health?verbose=1).
    FlaskInstrumentor().instrument_app(
        flask_app,
        excluded_urls=r"/health(?:\?.*)?$,/metrics(?:\?.*)?$,/version(?:\?.*)?$",
        request_hook=_request_hook,
        response_hook=_response_hook,
    )
    logger.info("Flask instrumented with OpenTelemetry")


def instrument_sqlalchemy(engine):
    """Instrument a SQLAlchemy engine with OpenTelemetry query tracing.

    Controlled by OTEL_SQL_ENABLED (master toggle) and OTEL_SQL_COMMENTER_ENABLED
    (adds traceparent to SQL comments for pg_stat_activity visibility).
    """
    if not OTEL_ENABLED or not OTEL_SQL_ENABLED:
        return

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        enable_commenter=OTEL_SQL_COMMENTER_ENABLED,
        commenter_options={
            "db_framework": True,
            "db_driver": True,
        },
    )
    logger.info("SQLAlchemy engine instrumented with OpenTelemetry (commenter=%s)", OTEL_SQL_COMMENTER_ENABLED)


def instrument_outbound_http():
    """Instrument outbound HTTP calls (e.g., RBAC) with OpenTelemetry.

    Controlled by OTEL_HTTP_ENABLED. Automatically creates spans for all
    requests made via the `requests` library, including trace context
    propagation to downstream services.
    """
    if not OTEL_ENABLED or not OTEL_HTTP_ENABLED:
        return

    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    RequestsInstrumentor().instrument(request_hook=_outbound_request_hook)
    logger.info("Outbound HTTP (requests library) instrumented with OpenTelemetry")


def _outbound_request_hook(span, request, *_args, **_kwargs):
    """Use METHOD + path as the client span name (default is METHOD only)."""
    if not span or not span.is_recording():
        return
    parsed = urlparse(request.path_url)
    path = parsed.path or "/"
    span.update_name(f"{request.method} {path}")


def _request_hook(span, environ):  # noqa: ARG001
    """Add HBI-specific attributes to every request span.

    Adds org_id and request_id so traces can be filtered in Grafana/Tempo:
        - hbi.org_id = "12345"         → all traces for an org
        - hbi.request_id = "abc-..."   → find a specific request
    """
    if not span or not span.is_recording():
        return

    from flask import request

    # Add request_id from the x-rh-insights-request-id header
    request_id = request.headers.get("x-rh-insights-request-id", "")
    if request_id:
        span.set_attribute("hbi.request_id", request_id)

    # Add org_id from the decoded identity header
    try:
        from app.auth.identity import from_auth_header

        encoded_id = request.headers.get("x-rh-identity", "")
        if encoded_id:
            identity = from_auth_header(encoded_id)
            if identity and hasattr(identity, "org_id"):
                span.set_attribute("hbi.org_id", identity.org_id or "")
    except Exception:
        pass  # Don't break requests if identity extraction fails


def _response_hook(span, status, response_headers):  # noqa: ARG001
    """Add response-level attributes to request spans."""
    if span and span.is_recording():
        if isinstance(status, str):
            # status can be "200 OK" — extract the code
            with contextlib.suppress(ValueError, IndexError):
                span.set_attribute("http.status_code", int(status.split()[0]))
        elif isinstance(status, int):
            span.set_attribute("http.status_code", status)
