"""Tests for OTel trace/span IDs in ContextualFilter."""

import logging

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.logging import ContextualFilter


def test_contextual_filter_trace_and_span_ids():
    """Injects hex trace/span IDs under an active span; None without one.

    Uses a local TracerProvider (no global set_tracer_provider) so other OTel
    tests are not poisoned by the process-wide provider singleton.
    """
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    assert ContextualFilter().filter(record) is True
    assert record.trace_id is None
    assert record.span_id is None

    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create())
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    try:
        with provider.get_tracer("test").start_as_current_span("log-span"):
            assert ContextualFilter().filter(record) is True
            assert len(record.trace_id) == 32
            assert len(record.span_id) == 16
            assert all(c in "0123456789abcdef" for c in record.trace_id + record.span_id)

        finished_spans = exporter.get_finished_spans()
        assert len(finished_spans) == 1

        span = finished_spans[0]
        assert record.trace_id == f"{span.context.trace_id:032x}"
        assert record.span_id == f"{span.context.span_id:016x}"
    finally:
        provider.shutdown()
