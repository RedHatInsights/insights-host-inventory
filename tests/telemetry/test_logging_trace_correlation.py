"""Tests for OTel trace/span IDs in ContextualFilter."""

import logging

from app.logging import ContextualFilter


def test_contextual_filter_trace_and_span_ids(otel_provider):
    """Injects hex trace/span IDs under an active span; None without one."""
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

    provider, exporter = otel_provider()

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
