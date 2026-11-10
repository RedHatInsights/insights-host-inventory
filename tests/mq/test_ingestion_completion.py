"""Completion evidence follows the DB commit and the actual Kafka acknowledgement."""

import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import SpanLimits
from opentelemetry.trace import SpanKind
from opentelemetry.trace import StatusCode

from app.logging import threadctx
from app.queue import event_producer
from app.queue import host_mq
from app.queue.events import EventType
from app.telemetry import _build_rh_attribute_span_processor


@pytest.fixture
def completion_consumer(monkeypatch, otel_provider):
    provider, exporter = otel_provider(
        span_processors=[_build_rh_attribute_span_processor()],
        span_limits=SpanLimits(max_events=1),
    )
    monkeypatch.setattr(host_mq, "tracer", provider.get_tracer(__name__))
    monkeypatch.setattr(host_mq, "OTEL_MQ_ENABLED", True)
    monkeypatch.setattr(host_mq, "OTEL_MQ_MESSAGE_SPANS_ENABLED", True)
    monkeypatch.setattr(host_mq, "db", SimpleNamespace(session=MagicMock()))
    monkeypatch.setattr(host_mq, "StalenessCache", nullcontext)
    monkeypatch.setattr(host_mq, "UngroupedGroupCache", nullcontext)
    monkeypatch.setattr(host_mq, "parse_operation_message", lambda message, *_args, **_kwargs: json.loads(message))
    monkeypatch.setattr(host_mq, "metrics", MagicMock())
    monkeypatch.setattr(threadctx, "request_id", "previous-request", raising=False)
    monkeypatch.setattr(threadctx, "org_id", "previous-org", raising=False)
    consumer = host_mq.HostAppMessageConsumer(MagicMock(), MagicMock(), MagicMock(), MagicMock())

    def process_message(_application, message):
        with host_mq.tracer.start_as_current_span(f"SQL {message['org_id']}"):
            pass
        result = host_mq.OperationResult(None, None, None, None, lambda: None)
        result.persisted_host_ids = message["persisted_host_ids"]
        return result

    monkeypatch.setattr(consumer, "process_message", process_message)
    return consumer, exporter


def message(host_ids, *, application="advisor", request_id="request-A", org_id="org-A", index=1):
    msg = MagicMock()
    msg.headers.return_value = [
        ("application", application.encode()),
        ("traceparent", f"00-{index:032x}-{index:016x}-01".encode()),
    ]
    if request_id is not None:
        msg.headers.return_value.append(("request_id", request_id.encode()))
    msg.value.return_value = json.dumps({"org_id": org_id, "persisted_host_ids": host_ids})
    msg.topic.return_value = "platform.inventory.host-apps"
    msg.partition.return_value = 0
    return msg


def completions(exporter):
    return [
        (span, event)
        for span in exporter.get_finished_spans()
        for event in span.events
        if event.name == "rh.ingestion.completed"
    ]


@pytest.mark.parametrize("application,commit_fails", [("advisor", False), ("compliance", False), ("advisor", True)])
def test_views_completion_and_success_metrics_follow_commit(completion_consumer, application, commit_fails):
    consumer, exporter = completion_consumer
    host_id = str(uuid4())

    def commit():
        assert not consumer.processed_rows[0].otel_span.events
        host_mq.metrics.host_app_data_processing_success.labels.assert_not_called()
        if commit_fails:
            raise RuntimeError("commit failed")

    host_mq.db.session.commit.side_effect = commit
    if commit_fails:
        with pytest.raises(RuntimeError, match="commit failed"):
            consumer._run_batch([message([host_id], application=application)])
        assert completions(exporter) == []
        host_mq.db.session.rollback.assert_called_once()
        consumer.consumer.commit.assert_not_called()
        host_mq.metrics.host_app_data_processing_success.labels.assert_not_called()
        host_mq.metrics.host_app_data_last_processed_timestamp.labels.assert_not_called()
        span = next(span for span in exporter.get_finished_spans() if span.name.startswith("mq.process"))
        assert span.status.status_code == StatusCode.ERROR
    else:
        consumer._run_batch([message([host_id], application=application)])
        span, event = completions(exporter)[0]
        assert span.context.trace_id == 1
        assert dict(event.attributes) == {
            "rh.ingestion.application": application,
            "rh.ingestion.milestone": "inventory_views",
            "rh.ingestion.outcome": "processed",
            "rh.request_id": "request-A",
            "rh.org_id": "org-A",
            "rh.host_id": host_id,
        }
        assert event.timestamp == consumer.processed_rows[0].committed_at_ns
        host_mq.metrics.host_app_data_processing_success.labels.assert_called_once_with(application=application)
        host_mq.metrics.host_app_data_processing_success.labels.return_value.inc.assert_called_once_with(1)


def test_views_reports_every_persisted_host_without_sdk_event_truncation(completion_consumer):
    consumer, exporter = completion_consumer
    host_ids = [str(uuid4()), str(uuid4())]
    consumer._run_batch([message(host_ids)])
    events = completions(exporter)
    assert len(events) == len(host_ids)
    assert {event.attributes["rh.host_id"] for _, event in events} == set(host_ids)
    parent = next(span for span in exporter.get_finished_spans() if span.name.startswith("mq.process"))
    for span, event in events:
        assert span.parent.span_id == parent.context.span_id
        assert span.context.trace_id == parent.context.trace_id
        assert event.timestamp == consumer.processed_rows[0].committed_at_ns


@pytest.mark.parametrize("upstream", [True, False])
def test_batch_preserves_message_and_sql_identity(completion_consumer, upstream):
    consumer, exporter = completion_consumer
    identities = [("advisor", "A"), ("vulnerability", "B"), ("patch", "C"), ("advisor", None)]
    hosts = [str(uuid4()) for _ in identities]
    messages = [
        message([host], application=app, request_id=request, org_id=f"org-{index}", index=index)
        for index, ((app, request), host) in enumerate(zip(identities, hosts, strict=True), 1)
    ]
    invalid = message([], index=5)
    invalid.value.return_value = "invalid JSON"
    messages.append(invalid)
    if not upstream:
        for msg in messages:
            msg.headers.return_value = [(key, value) for key, value in msg.headers() if key != "traceparent"]
    batch = (
        nullcontext()
        if upstream
        else host_mq.tracer.start_as_current_span(
            "batch", kind=SpanKind.CONSUMER, attributes={"rh.request_id": "old-request", "rh.org_id": "old-org"}
        )
    )
    with batch:
        consumer._run_batch(messages)
    spans = exporter.get_finished_spans()
    parents = {span.attributes.get("rh.org_id"): span for span in spans if span.name.startswith("mq.process")}
    assert len(parents) == len(identities) + 1
    for index, (_app, request) in enumerate(identities, 1):
        span = parents[f"org-{index}"]
        sql = next(child for child in spans if child.name == f"SQL org-{index}")
        assert sql.parent.span_id == span.context.span_id
        for observed in (span, sql):
            assert observed.attributes.get("rh.request_id") == request
            assert observed.attributes["rh.org_id"] == f"org-{index}"
        if upstream:
            assert span.context.trace_id == index
    assert parents[None].status.status_code == StatusCode.ERROR
    assert "rh.request_id" not in parents[None].attributes
    assert "rh.org_id" not in parents[None].attributes
    assert {
        (
            event.attributes["rh.ingestion.application"],
            event.attributes["rh.request_id"],
            event.attributes["rh.host_id"],
        )
        for span, event in completions(exporter)
    } == {(app, request, host) for (app, request), host in zip(identities[:3], hosts[:3], strict=True)}


@pytest.mark.parametrize("failure", ["metrics", "completion"])
def test_reporting_failure_preserves_processing_and_offset_commit(completion_consumer, monkeypatch, caplog, failure):
    consumer, exporter = completion_consumer
    if failure == "metrics":
        host_mq.metrics.host_app_data_processing_success.labels.side_effect = [
            RuntimeError("reporting failed"),
            MagicMock(),
        ]
    else:
        process = consumer._process_single_message_in_batch

        def process_message(msg):
            process(msg)
            result = consumer.processed_rows[-1]
            if result.request_id == "request-A":
                monkeypatch.setattr(
                    result.otel_span, "add_event", MagicMock(side_effect=RuntimeError("reporting failed"))
                )

        monkeypatch.setattr(consumer, "_process_single_message_in_batch", process_message)
    postprocess = MagicMock()
    monkeypatch.setattr(consumer, "post_process_rows", postprocess)
    consumer._run_batch([message([str(uuid4())]), message([str(uuid4())], request_id="request-B", index=2)])
    host_mq.db.session.commit.assert_called_once()
    postprocess.assert_called_once()
    consumer.consumer.commit.assert_called_once_with(asynchronous=False)
    assert all(result.otel_span is None for result in consumer.processed_rows)
    assert len(completions(exporter)) == (2 if failure == "metrics" else 1)
    assert completions(exporter)[-1][1].attributes["rh.request_id"] == "request-B"
    assert "reporting failed" in caplog.text


@pytest.mark.parametrize("outcome", ["ack", "delivery_error", "enqueue_error", "deleted", "reporting_error"])
def test_hbi_completion_requires_commit_and_broker_ack(completion_consumer, monkeypatch, outcome):
    _consumer, exporter = completion_consumer
    producer = event_producer.EventProducer.__new__(event_producer.EventProducer)
    producer.mq_topic = "platform.inventory.events"
    producer._kafka_producer = MagicMock()
    consumer = host_mq.HostMessageConsumer(MagicMock(), MagicMock(), producer, MagicMock())
    host_id = uuid4()
    row = SimpleNamespace(id=host_id, org_id="org-A", account=None, insights_id=None, groups=[])
    result = host_mq.OperationResult(
        row, {"request_id": "request-A"}, {"stale": "test"}, EventType.updated, MagicMock()
    )
    result.persisted_host_ids = [host_id]

    def handle_message(*_args, **_kwargs):
        consumer._initialize_message_context("request-A", "org-A")
        if outcome == "reporting_error":
            monkeypatch.setattr(
                host_mq.trace_api.get_current_span(),
                "add_event",
                MagicMock(side_effect=RuntimeError("reporting failed")),
            )
        return result

    monkeypatch.setattr(consumer, "handle_message", handle_message)
    monkeypatch.setattr(host_mq, "get_payload_tracker", MagicMock())
    monkeypatch.setattr(
        host_mq, "PayloadTrackerProcessingContext", lambda *_args, **_kwargs: nullcontext(SimpleNamespace())
    )
    monkeypatch.setattr(host_mq, "serialize_host", lambda *_args: {"id": str(host_id)})
    monkeypatch.setattr(
        host_mq, "build_event_and_headers", lambda *_args, **_kwargs: ('{"host": {}}', {"request_id": "request-A"})
    )
    monkeypatch.setattr(host_mq, "host_exists", lambda *_args, **_kwargs: outcome != "deleted")
    monkeypatch.setattr(host_mq, "cache_ingested_system", MagicMock())
    monkeypatch.setattr(event_producer, "message_produced", MagicMock())
    monkeypatch.setattr(event_producer, "message_not_produced", MagicMock())

    def acknowledge():
        assert result.committed_at_ns is not None
        assert not result.otel_span.events
        error = MagicMock() if outcome == "delivery_error" else None
        producer._kafka_producer.produce.call_args.kwargs["callback"](error, MagicMock())

    producer._kafka_producer.flush.side_effect = acknowledge
    if outcome == "enqueue_error":
        producer._kafka_producer.produce.side_effect = RuntimeError("enqueue failed")
    consumer._run_batch([message([str(host_id)])])
    events = completions(exporter)
    assert len(events) == (1 if outcome == "ack" else 0)
    if outcome == "reporting_error":
        result.success_logger.assert_called_once()
        host_mq.cache_ingested_system.assert_called_once()
        consumer.consumer.commit.assert_called_once_with(asynchronous=False)
    if events:
        span, event = events[0]
        assert span.context.trace_id == 1
        assert event.timestamp >= result.committed_at_ns
        assert event.attributes["rh.ingestion.application"] == "hbi"
        assert event.attributes["rh.ingestion.milestone"] == "processing"
        assert event.attributes["rh.host_id"] == str(host_id)
        assert event.attributes["rh.request_id"] == "request-A"
