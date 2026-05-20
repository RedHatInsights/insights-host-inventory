"""Tests for MQ per-message span controls (OTEL_MQ_MESSAGE_SPANS_ENABLED / OTEL_MQ_SLOW_MESSAGE_MS)."""

import importlib
from unittest.mock import MagicMock

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.queue.host_mq import HBIMessageConsumerBase
from app.queue.host_mq import OperationResult
from tests.helpers.mq_utils import FakeMessage


@pytest.fixture
def otel_spans(monkeypatch):
    """Set up an in-memory exporter and patch the module-level tracer."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr("app.queue.host_mq.tracer", provider.get_tracer("test"))
    yield exporter
    provider.shutdown()


@pytest.fixture
def consumer():
    """A minimal HBIMessageConsumerBase subclass for testing span behavior."""

    class _TestConsumer(HBIMessageConsumerBase):
        def __init__(self):
            self.consumer = MagicMock()
            self.flask_app = MagicMock()
            self.event_producer = MagicMock()
            self.notification_event_producer = MagicMock()
            self.processed_rows = []
            self._is_retry = False
            self._handler = MagicMock(return_value=OperationResult(None, None, None, None, None, lambda: None))

        def handle_message(self, message, headers=None):
            return self._handler(message, headers=headers)

    return _TestConsumer()


def test_span_emitted_when_enabled(otel_spans, consumer, monkeypatch):
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_MESSAGE_SPANS_ENABLED", True)
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_SLOW_MESSAGE_MS", 0)

    consumer._process_single_message(FakeMessage())

    spans = otel_spans.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name.startswith("mq.process")


def test_no_span_when_disabled(otel_spans, consumer, monkeypatch):
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_MESSAGE_SPANS_ENABLED", False)
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_SLOW_MESSAGE_MS", 0)

    consumer._process_single_message(FakeMessage())

    assert len(otel_spans.get_finished_spans()) == 0
    assert len(consumer.processed_rows) == 1


def test_error_emits_span_when_disabled(otel_spans, consumer, monkeypatch):
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_MESSAGE_SPANS_ENABLED", False)
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_SLOW_MESSAGE_MS", 0)
    consumer._handler.side_effect = ValueError("boom")

    consumer._process_single_message(FakeMessage())

    spans = otel_spans.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code == trace.StatusCode.ERROR
    assert spans[0].attributes["hbi.error"] is True


def test_retry_emits_span_when_disabled(otel_spans, consumer, monkeypatch):
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_MESSAGE_SPANS_ENABLED", False)
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_SLOW_MESSAGE_MS", 0)
    consumer._is_retry = True

    consumer._process_single_message(FakeMessage())

    spans = otel_spans.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes["hbi.retry"] is True


def test_slow_message_emits_span(otel_spans, consumer, monkeypatch):
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_MESSAGE_SPANS_ENABLED", False)
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_SLOW_MESSAGE_MS", 30)

    start_ns = 1_000_000_000_000
    end_ns = start_ns + 40_000_000  # 40ms > 30ms threshold
    call_count = {"n": 0}

    def fake_time_ns():
        call_count["n"] += 1
        return start_ns if call_count["n"] == 1 else end_ns

    monkeypatch.setattr("app.queue.host_mq.time.time_ns", fake_time_ns)

    consumer._process_single_message(FakeMessage())

    spans = otel_spans.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes["hbi.slow_message"] is True
    assert spans[0].attributes["hbi.duration_ms"] >= 30


def test_fast_message_no_slow_span(otel_spans, consumer, monkeypatch):
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_MESSAGE_SPANS_ENABLED", False)
    monkeypatch.setattr("app.queue.host_mq.OTEL_MQ_SLOW_MESSAGE_MS", 5000)

    consumer._process_single_message(FakeMessage())

    assert len(otel_spans.get_finished_spans()) == 0


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("OTEL_MQ_MESSAGE_SPANS_ENABLED", raising=False)
    monkeypatch.delenv("OTEL_MQ_SLOW_MESSAGE_MS", raising=False)

    import app.telemetry as telemetry_mod

    importlib.reload(telemetry_mod)

    assert telemetry_mod.OTEL_MQ_MESSAGE_SPANS_ENABLED is True
    assert telemetry_mod.OTEL_MQ_SLOW_MESSAGE_MS == 0

    # Clean up
    importlib.reload(telemetry_mod)
