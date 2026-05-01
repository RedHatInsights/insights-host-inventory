"""OpenTelemetry initialization for HBI services.

Provides centralized tracing setup for all HBI entry points (web API, MQ service,
export service). Controlled by the OTEL_ENABLED environment variable.

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

OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
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
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        attributes={
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "deployment.environment": os.getenv("NAMESPACE", "development"),
        }
    )

    provider = TracerProvider(resource=resource)

    # OTLP exporter — picks up endpoint from OTEL_EXPORTER_OTLP_ENDPOINT
    # (falls back to OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, then default localhost:4318)
    exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _otel_initialized_pid = os.getpid()
    logger.info("OpenTelemetry initialized for service=%s version=%s", service_name, service_version)


def instrument_flask_app(flask_app):
    """Instrument a Flask app with OpenTelemetry request tracing.

    Each HTTP request becomes a span with method, path, status code,
    plus HBI-specific attributes (org_id, request_id).
    """
    if not OTEL_ENABLED:
        return

    from opentelemetry.instrumentation.flask import FlaskInstrumentor

    # Patterns match flask.request.url (full URL), not path-only; do not anchor with ^.
    FlaskInstrumentor().instrument_app(
        flask_app,
        excluded_urls="/health$,/metrics$,/version$",
        request_hook=_request_hook,
        response_hook=_response_hook,
    )
    logger.info("Flask instrumented with OpenTelemetry")


def instrument_sqlalchemy(engine):
    """Instrument a SQLAlchemy engine with OpenTelemetry query tracing.

    Every SQL query becomes a child span of the request that triggered it,
    with the query text and duration. SQLCommenter adds traceparent to SQL
    comments so queries are visible in pg_stat_activity.
    """
    if not OTEL_ENABLED:
        return

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        enable_commenter=True,
        commenter_options={
            "db_framework": True,
            "db_driver": True,
        },
    )
    logger.info("SQLAlchemy engine instrumented with OpenTelemetry")


def instrument_outbound_http():
    """Instrument outbound HTTP calls (e.g., RBAC) with OpenTelemetry.

    Automatically creates spans for all requests made via the `requests` library,
    including trace context propagation to downstream services.
    """
    if not OTEL_ENABLED:
        return

    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    RequestsInstrumentor().instrument(request_hook=_outbound_request_hook)
    logger.info("Outbound HTTP (requests library) instrumented with OpenTelemetry")


def _outbound_request_hook(span, request):
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
