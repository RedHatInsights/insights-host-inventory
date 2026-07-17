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
OTEL_HTTP_INBOUND_ENABLED = os.getenv("OTEL_HTTP_INBOUND_ENABLED", "true").lower() == "true"
OTEL_HTTP_OUTBOUND_ENABLED = os.getenv("OTEL_HTTP_OUTBOUND_ENABLED", "true").lower() == "true"
OTEL_MQ_ENABLED = os.getenv("OTEL_MQ_ENABLED", "true").lower() == "true"
OTEL_BOTOCORE_ENABLED = os.getenv("OTEL_BOTOCORE_ENABLED", "true").lower() == "true"


def _parse_sampling_rate(env_var: str, default: str = "1.0") -> float:
    """Parse a sampling-rate env var, clamping to [0.0, 1.0] and falling back on bad values."""
    raw = os.getenv(env_var, default)
    try:
        rate = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; falling back to %s", env_var, raw, default)
        rate = float(default)
    return min(max(rate, 0.0), 1.0)


OTEL_SAMPLING_RATE = _parse_sampling_rate("OTEL_SAMPLING_RATE")
# Host-ingress MQ only (mq-pmin / mq-p1). Default 1.0 for Payload Tracker parity.
OTEL_HOST_INGESTION_SAMPLING_RATE = _parse_sampling_rate("OTEL_HOST_INGESTION_SAMPLING_RATE")

OTEL_BSP_MAX_QUEUE_SIZE = int(os.getenv("OTEL_BSP_MAX_QUEUE_SIZE", "8192"))
OTEL_BSP_MAX_EXPORT_BATCH_SIZE = int(os.getenv("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", "256"))
OTEL_BSP_SCHEDULE_DELAY = int(os.getenv("OTEL_BSP_SCHEDULE_DELAY", "2000"))
OTEL_BSP_EXPORT_TIMEOUT = int(os.getenv("OTEL_BSP_EXPORT_TIMEOUT", "10000"))

OTEL_EXPORTER_OTLP_COMPRESSION = os.getenv("OTEL_EXPORTER_OTLP_COMPRESSION", "gzip").lower()
OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT = int(os.getenv("OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT", "64"))
OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT = int(os.getenv("OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT", "1024"))

# MQ per-message span controls
# Default True to preserve full visibility in stage; set to "false" in production.
OTEL_MQ_MESSAGE_SPANS_ENABLED = os.getenv("OTEL_MQ_MESSAGE_SPANS_ENABLED", "true").lower() == "true"
# Threshold in ms: when message spans are disabled, still emit a span for messages slower than this.
# 0 means disabled (no slow-message spans).
OTEL_MQ_SLOW_MESSAGE_MS = int(os.getenv("OTEL_MQ_SLOW_MESSAGE_MS", "0"))

_RH_PROPAGATED_ATTRS = ("rh.org_id", "rh.request_id")

_otel_initialized_pid = None


def _build_rh_attribute_span_processor(rh_service: str = "host-inventory"):
    """Build a SpanProcessor that sets platform rh.* attributes on every span.

    Defined as a factory so the SDK SpanProcessor base is imported only when OTel
    is actually initialized.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.sdk.trace import SpanProcessor

    from app.logging import threadctx

    class RHAttributeSpanProcessor(SpanProcessor):
        """Set rh.service on every span; copy rh.org_id / rh.request_id to children.

        Prefers org/request attrs already set on the parent span (HTTP request hook).
        Falls back to threadctx for MQ, where those values are populated mid-handle_message
        after initialize_thread_local_storage.
        """

        def on_start(self, span, parent_context=None):
            if not span or not span.is_recording():
                return

            span.set_attribute("rh.service", rh_service)

            # Tracer.start_span often passes parent_context=None even for children; in that
            # case the active span during on_start is still the parent.
            parent = trace.get_current_span(parent_context) if parent_context is not None else trace.get_current_span()
            parent_attrs = {}
            if isinstance(parent, ReadableSpan) and parent.attributes:
                parent_attrs = parent.attributes

            for attr in _RH_PROPAGATED_ATTRS:
                if attr in (span.attributes or {}):
                    continue
                value = parent_attrs.get(attr)
                if value is None:
                    thread_key = "org_id" if attr == "rh.org_id" else "request_id"
                    value = getattr(threadctx, thread_key, None)
                if value is not None:
                    span.set_attribute(attr, value)

    return RHAttributeSpanProcessor()


def get_tracer(name: str):
    """Get an OpenTelemetry tracer for creating custom spans.

    When init_otel() has not been called (i.e. OTEL is disabled), the SDK's
    default TracerProvider is a no-op that creates zero-overhead no-op spans.
    """
    from opentelemetry import trace

    return trace.get_tracer(name)


def init_otel(
    service_name: str,
    service_version: str = "unknown",
    *,
    rh_service: str = "host-inventory",
    sampling_rate: float | None = None,
):
    """Initialize OpenTelemetry tracing. Safe to call multiple times.

    Uses the current PID to detect fork boundaries: if run.py initializes
    in the Gunicorn master process and then post_fork calls again in a
    worker, the PID will differ and the worker will re-initialize with a
    fresh (fork-safe) TracerProvider and BatchSpanProcessor.

    For single-process services (MQ, export), the second call is a no-op.

    Args:
        service_name: OTel service.name resource attribute.
        service_version: OTel service.version resource attribute.
        rh_service: Platform rh.service span attribute (logical service name).
        sampling_rate: Optional override for OTEL_SAMPLING_RATE (e.g. host-ingestion path).
    """
    global _otel_initialized_pid

    if _otel_initialized_pid == os.getpid():
        return

    if not OTEL_ENABLED:
        logger.info("OpenTelemetry is disabled (OTEL_ENABLED != 'true')")
        _otel_initialized_pid = os.getpid()
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http import Compression
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

    effective_rate = sampling_rate or OTEL_SAMPLING_RATE
    sampler = TraceIdRatioBased(effective_rate)
    span_limits = SpanLimits(
        max_attributes=OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT,
        max_attribute_length=OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT,
    )
    provider = TracerProvider(resource=resource, sampler=sampler, span_limits=span_limits)

    # Set rh.* span attrs (including rh.service) before batching/export.
    provider.add_span_processor(_build_rh_attribute_span_processor(rh_service=rh_service))

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
        "OpenTelemetry config: sampling=%.2f sql=%s commenter=%s http_inbound=%s http_outbound=%s "
        "botocore=%s bsp_queue=%d bsp_batch=%d bsp_delay=%dms bsp_timeout=%dms "
        "compression=%s attr_limit=%d attr_len_limit=%d "
        "mq_enabled=%s "
        "mq_message_spans=%s mq_slow_message_ms=%d",
        effective_rate,
        OTEL_SQL_ENABLED,
        OTEL_SQL_COMMENTER_ENABLED,
        OTEL_HTTP_INBOUND_ENABLED,
        OTEL_HTTP_OUTBOUND_ENABLED,
        OTEL_BOTOCORE_ENABLED,
        OTEL_BSP_MAX_QUEUE_SIZE,
        OTEL_BSP_MAX_EXPORT_BATCH_SIZE,
        OTEL_BSP_SCHEDULE_DELAY,
        OTEL_BSP_EXPORT_TIMEOUT,
        OTEL_EXPORTER_OTLP_COMPRESSION,
        OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT,
        OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT,
        OTEL_MQ_ENABLED,
        OTEL_MQ_MESSAGE_SPANS_ENABLED,
        OTEL_MQ_SLOW_MESSAGE_MS,
    )


def instrument_flask_app(flask_app):
    """Instrument a Flask app with OpenTelemetry request tracing.

    Each HTTP request becomes a span with method, path, status code,
    plus HBI-specific attributes (org_id, request_id).
    """
    if not OTEL_ENABLED or not OTEL_HTTP_INBOUND_ENABLED:
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


def instrument_kafka_producer(producer):
    """Wrap a confluent-kafka producer with OpenTelemetry instrumentation."""
    if not OTEL_ENABLED or not OTEL_MQ_ENABLED:
        return producer

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.confluent_kafka import ConfluentKafkaInstrumentor
    except ImportError:
        logger.warning("Kafka producer instrumentation unavailable; continuing without producer spans")
        return producer

    return ConfluentKafkaInstrumentor.instrument_producer(producer, tracer_provider=trace.get_tracer_provider())


def instrument_kafka_consumer(consumer):
    """Wrap a confluent-kafka consumer with OpenTelemetry instrumentation."""
    if not OTEL_ENABLED or not OTEL_MQ_ENABLED:
        return consumer

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.confluent_kafka import ConfluentKafkaInstrumentor
    except ImportError:
        logger.warning("Kafka consumer instrumentation unavailable; continuing without consumer spans")
        return consumer

    return ConfluentKafkaInstrumentor.instrument_consumer(consumer, tracer_provider=trace.get_tracer_provider())


def instrument_outbound_http():
    """Instrument outbound HTTP calls (e.g., RBAC) with OpenTelemetry.

    Controlled by OTEL_HTTP_OUTBOUND_ENABLED. Automatically creates spans for all
    requests made via the `requests` library, including trace context
    propagation to downstream services.
    """
    if not OTEL_ENABLED or not OTEL_HTTP_OUTBOUND_ENABLED:
        return

    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    RequestsInstrumentor().instrument(request_hook=_outbound_request_hook)
    logger.info("Outbound HTTP (requests library) instrumented with OpenTelemetry")


def instrument_botocore():
    """Instrument botocore/boto3 (S3/MinIO) with OpenTelemetry.

    Controlled by OTEL_BOTOCORE_ENABLED. Automatically creates spans for AWS API calls.
    """
    if not OTEL_ENABLED or not OTEL_BOTOCORE_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
    except ImportError:
        logger.warning("Botocore instrumentation unavailable; continuing without S3 spans")
        return

    BotocoreInstrumentor().instrument()
    logger.info("Botocore instrumented with OpenTelemetry")


def _outbound_request_hook(span, request, *_args, **_kwargs):
    """Use METHOD + path as the client span name (default is METHOD only)."""
    if not span or not span.is_recording():
        return
    parsed = urlparse(request.path_url)
    path = parsed.path or "/"
    span.update_name(f"{request.method} {path}")


def _request_hook(span, environ):  # noqa: ARG001
    """Add Red Hat platform attributes to every request span.

    Adds org_id and request_id so traces can be filtered in Grafana/Tempo:
        - rh.org_id = "12345"         → all traces for an org
        - rh.request_id = "abc-..."   → find a specific request
    """
    if not span or not span.is_recording():
        return

    from flask import request

    request_id = request.headers.get("x-rh-insights-request-id", "")
    if request_id:
        span.set_attribute("rh.request_id", request_id)

    try:
        from app.auth.identity import from_auth_header

        encoded_id = request.headers.get("x-rh-identity", "")
        if encoded_id:
            identity = from_auth_header(encoded_id)
            if identity and hasattr(identity, "org_id"):
                span.set_attribute("rh.org_id", identity.org_id or "")
    except Exception:
        pass


def _response_hook(span, status, response_headers):  # noqa: ARG001
    """Add response-level attributes to request spans."""
    if span and span.is_recording():
        if isinstance(status, str):
            # status can be "200 OK" — extract the code
            with contextlib.suppress(ValueError, IndexError):
                span.set_attribute("http.status_code", int(status.split()[0]))
        elif isinstance(status, int):
            span.set_attribute("http.status_code", status)
