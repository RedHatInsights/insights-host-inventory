"""Async audit records follow actual database and receiver outcomes."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from datagen_utils import generate_host_app_data
from opentelemetry import propagate
from opentelemetry.propagators.composite import CompositePropagator
from requests.exceptions import ConnectionError

from app import audit
from app.models import db
from app.queue import export_service
from app.queue import export_service_mq
from app.queue import host_mq
from app.queue.enums import ConsumerApplication
from lib import host_app_repository
from tests.helpers import export_service_utils
from tests.helpers.test_utils import USER_IDENTITY

pytestmark = pytest.mark.usefixtures("restore_thread_context")

APPLICATIONS = ("advisor", "vulnerability", "patch", "compliance", "malware", "remediations")
INVALID_FIELD = {
    "advisor": "recommendations",
    "vulnerability": "total_cves",
    "patch": "advisories_rhsa_applicable",
    "compliance": "policies",
    "malware": "last_matches",
    "remediations": "remediations_plans",
}


def records(output):
    return [json.loads(line) for line in output.getvalue().splitlines()]


def message(app, org_id, hosts, *, index=1):
    msg = MagicMock()
    msg.value.return_value = json.dumps({"org_id": org_id, "timestamp": "2026-11-19T10:00:00Z", "hosts": hosts})
    msg.headers.return_value = [
        ("application", app.encode()),
        ("request_id", f"request-{index}".encode()),
        ("traceparent", f"00-{index:032x}-{index:016x}-00".encode()),
    ]
    msg.topic.return_value = "platform.inventory.host-apps"
    msg.error.return_value = None
    return msg


def assert_processor(event, *, org_id, index=1, spans=True):
    assert event["principal"] == "host-app-data-consumer"
    assert event["principal_type"] == "SystemActor"
    assert event["org_id"] == org_id
    assert event["request_id"] == f"request-{index}"
    assert event["trace_id"] == f"{index:032x}"
    assert bool(event["span_id"]) == spans
    assert event["logger"] == "inventory.audit"
    assert event["timestamp"].endswith("+00:00")


@pytest.mark.parametrize(
    "app,tracing,spans,commit_fails",
    [(app, True, True, False) for app in APPLICATIONS]
    + [("advisor", True, False, False), ("advisor", False, False, False), ("advisor", True, True, True)],
)
def test_projection_partial_validation_fk_skip_and_commit(
    app, tracing, spans, commit_fails, flask_app, db_create_host, audit_output, monkeypatch, otel_provider
):
    provider, _ = otel_provider()
    monkeypatch.setattr(host_mq, "tracer", provider.get_tracer(__name__))
    monkeypatch.setattr(host_mq, "OTEL_MQ_ENABLED", tracing)
    monkeypatch.setattr(host_mq, "OTEL_MQ_MESSAGE_SPANS_ENABLED", spans)
    consumer = host_mq.HostAppMessageConsumer(MagicMock(), flask_app, MagicMock(), MagicMock())
    host = db_create_host()
    host_id, org_id, missing_id, invalid_id = str(host.id), host.org_id, str(uuid4()), str(uuid4())
    data = generate_host_app_data(app)
    invalid_data = {**data, INVALID_FIELD[app]: {"private-invalid-field": "private-payload"}}
    msg = message(
        app,
        org_id,
        [
            {"id": host_id, "data": data},
            {"id": missing_id, "data": data},
            {"id": invalid_id, "data": invalid_data},
        ],
    )
    original = type(db.session()).commit

    def commit(session):
        assert not [event for event in records(audit_output) if event["outcome"] == "success"]
        if commit_fails:
            raise RuntimeError("private-commit-error")
        original(session)

    monkeypatch.setattr(type(db.session()), "commit", commit)
    if commit_fails:
        with pytest.raises(RuntimeError, match="private-commit-error"):
            consumer._run_batch([msg])
    else:
        consumer._run_batch([msg])
    events = records(audit_output)
    assert len(events) == 3
    by_id = {event["resource_id"]: event for event in events}
    assert by_id[f"{app}:{host_id}"]["outcome"] == ("failure" if commit_fails else "success")
    assert by_id[f"{app}:{missing_id}"]["reason"] == "host_not_found"
    assert by_id[f"{app}:{invalid_id}"]["reason"] == "invalid_host_data"
    for event in events:
        assert_processor(event, org_id=org_id, spans=spans)
        assert event["action"] == "UPSERT" and event["resource_type"] == "host_app_data"
    model, _ = host_mq.HostAppMessageConsumer.APPLICATION_MAP[ConsumerApplication(app)]
    assert db.session.query(model).count() == (0 if commit_fails else 1)
    assert "private-" not in audit_output.getvalue()


@pytest.mark.parametrize("app", APPLICATIONS)
def test_projection_exact_replay_has_no_mutation_event(app, flask_app, db_create_host, audit_output):
    host = db_create_host()
    msg = message(app, host.org_id, [{"id": str(host.id), "data": generate_host_app_data(app)}])
    consumer = host_mq.HostAppMessageConsumer(MagicMock(), flask_app, MagicMock(), MagicMock())
    consumer._run_batch([msg])
    assert len(records(audit_output)) == 1
    consumer.processed_rows = []  # The production event loop resets results for each batch.
    audit_output.seek(0)
    audit_output.truncate()
    consumer._run_batch([msg])
    assert records(audit_output) == []
    assert consumer.processed_rows[0].persisted_host_ids == [host.id]


def test_projection_error_after_write_rolls_back_only_failed_message(
    flask_app, db_create_host, audit_output, monkeypatch, otel_provider
):
    provider, _ = otel_provider()
    monkeypatch.setattr(host_mq, "tracer", provider.get_tracer(__name__))
    monkeypatch.setattr(host_mq, "OTEL_MQ_ENABLED", True)
    monkeypatch.setattr(host_mq, "OTEL_MQ_MESSAGE_SPANS_ENABLED", True)
    consumer = host_mq.HostAppMessageConsumer(MagicMock(), flask_app, MagicMock(), MagicMock())
    messages = []
    for index, app in enumerate(("malware", "remediations"), 1):
        host = db_create_host(extra_data={"org_id": f"org-{index}"})
        messages.append(
            message(app, host.org_id, [{"id": str(host.id), "data": generate_host_app_data(app)}], index=index)
        )
    original = host_app_repository.upsert_host_app_data

    def upsert(**kwargs):
        result = original(**kwargs)
        if kwargs["org_id"] == "org-2":
            raise RuntimeError("private-error-after-write")
        return result

    monkeypatch.setattr(host_app_repository, "upsert_host_app_data", upsert)
    consumer.consumer.consume.return_value = messages
    consumer.event_loop(MagicMock(side_effect=[False, True]))
    events = records(audit_output)
    assert len(events) == 2
    for event in events:
        index = int(event["org_id"].removeprefix("org-"))
        assert_processor(event, org_id=f"org-{index}", index=index)
        assert event["outcome"] == ("success" if index == 1 else "failure")
    for app in ("malware", "remediations"):
        model, _ = consumer.APPLICATION_MAP[ConsumerApplication(app)]
        assert db.session.query(model).count() == (1 if app == "malware" else 0)
    consumer.consumer.commit.assert_called_once_with(asynchronous=False)
    assert "private-" not in audit_output.getvalue()


@pytest.mark.parametrize("bad_only", [False, True])
def test_projection_data_error_is_rejected_without_blocking_offsets(flask_app, db_create_host, audit_output, bad_only):
    host = db_create_host()
    healthy = db_create_host()
    data = generate_host_app_data("advisor")
    messages = [message("advisor", host.org_id, [{"id": str(host.id), "data": {**data, "recommendations": 2**40}}])]
    if not bad_only:
        messages.append(message("advisor", healthy.org_id, [{"id": str(healthy.id), "data": data}], index=2))
    kafka = MagicMock()
    kafka.consume.return_value = messages
    consumer = host_mq.HostAppMessageConsumer(kafka, flask_app, MagicMock(), MagicMock())

    consumer.event_loop(MagicMock(side_effect=[False, True]))

    model, _ = consumer.APPLICATION_MAP[ConsumerApplication.ADVISOR]
    assert [str(row.host_id) for row in db.session.query(model).all()] == ([] if bad_only else [str(healthy.id)])
    events = records(audit_output)
    assert events[0]["outcome"] == "failure"
    assert len(events) == (1 if bad_only else 2)
    if not bad_only:
        assert events[1]["outcome"] == "success"
    kafka.commit.assert_called_once_with(asynchronous=False)


@pytest.fixture
def export_env(monkeypatch):
    config = SimpleNamespace(
        export_service_endpoint="https://export.invalid",
        export_service_endpoint_ca_certificate=None,
        export_service_endpoint_authenticated=False,
        export_service_token="private-service-token",
        export_svc_batch_size=100,
    )
    session = MagicMock()
    monkeypatch.setattr(export_service, "Session", lambda: session)
    monkeypatch.setattr(export_service, "resolve_permission", lambda *_args, **_kwargs: (True, None))
    monkeypatch.setattr(
        export_service,
        "get_hosts_to_export",
        lambda *_args, **_kwargs: iter(
            [
                {"host_id": str(uuid4()), "display_name": "private-host-value"},
            ]
        ),
    )

    def post(*_args, **kwargs):
        if kwargs["url"].endswith("/upload"):
            b"".join(kwargs["data"])
        return export_service_utils.make_response(202, "")

    session.post.side_effect = post
    payload = export_service_mq.parse_export_service_message(export_service_utils.create_export_message_mock())
    return config, session, payload


@pytest.mark.parametrize(
    "kind,fmt",
    [(kind, "json") for kind in ("accepted", "duplicate", "rejected", "network", "stream", "no_data", "headers")]
    + [("accepted", "csv"), ("stream", "csv")],
)
def test_export_results_are_distinct(kind, fmt, export_env, audit_output, monkeypatch):
    config, session, payload = export_env
    payload["data"]["resource_request"]["format"] = fmt
    if kind == "duplicate":
        session.post.side_effect = None
        session.post.return_value = export_service_utils.make_response(400, "This resource has already been processed")
    elif kind == "rejected":
        session.post.side_effect = None
        session.post.return_value = export_service_utils.make_response(500, "private-server-error")
    elif kind == "network":
        session.post.side_effect = ConnectionError("private-network-error")
    elif kind == "stream":

        def hosts(*_args, **_kwargs):
            yield {"host_id": str(uuid4()), "display_name": "private-host-value"}
            raise RuntimeError("private-query-error")

        monkeypatch.setattr(export_service, "get_hosts_to_export", hosts)
    elif kind == "no_data":
        monkeypatch.setattr(export_service, "get_hosts_to_export", lambda *_args, **_kwargs: iter([]))
    elif kind == "headers":

        def headers(*_args):
            raise RuntimeError("private-token-error")

        monkeypatch.setattr(export_service, "build_headers", headers)
    if kind in ("network", "stream"):
        with pytest.raises((ConnectionError, RuntimeError)):
            export_service.create_export(payload, config)
    else:
        assert export_service.create_export(payload, config) == (kind in ("accepted", "duplicate"))
    (event,) = records(audit_output)
    assert event["resource_type"] == "export"
    assert event["resource_id"] == str(payload["data"]["resource_request"]["export_request_uuid"])
    assert event["request_id"] == event["resource_id"]
    assert event["org_id"] == USER_IDENTITY["org_id"]
    assert event["principal"] == USER_IDENTITY["user"]["user_id"]
    assert event["principal_type"] == "User"
    assert event["action"] == {"accepted": "EXPORT_UPLOAD", "duplicate": "EXPORT_REPLAY"}.get(kind, "EXPORT")
    assert event["outcome"] == ("success" if kind in ("accepted", "duplicate") else "failure")
    assert "private-" not in audit_output.getvalue()
    session.close.assert_called_once()


@pytest.mark.parametrize(
    "kind,tracing,spans",
    [
        ("upload", True, True),
        ("upload", True, False),
        ("upload", False, False),
        ("invalid_credentials", False, False),
        ("invalid_schema", False, False),
    ],
)
def test_export_consumer_retains_original_trace_and_trusted_actor(
    tracing, spans, kind, flask_app, export_env, audit_output, monkeypatch, otel_provider
):
    config, _, _ = export_env
    provider, _ = otel_provider()
    monkeypatch.setattr(host_mq, "tracer", provider.get_tracer(__name__))
    monkeypatch.setattr(host_mq, "OTEL_MQ_ENABLED", tracing)
    monkeypatch.setattr(host_mq, "OTEL_MQ_MESSAGE_SPANS_ENABLED", spans)
    monkeypatch.setattr(export_service_mq, "inventory_config", lambda: config)
    payload = json.loads(export_service_utils.create_export_message_mock())
    payload["redhatorgid"] = "private-untrusted-tenant"
    resource = payload["data"]["resource_request"]
    if kind == "invalid_credentials":
        resource["x-rh-identity"] = "private-credential"
    elif kind == "invalid_schema":
        resource["filters"] = {"view_id": "private-invalid-uuid"}
    msg = MagicMock()
    msg.value.return_value = json.dumps(payload)
    msg.headers.return_value = [("traceparent", b"00-00000000000000000000000000000042-0000000000000042-00")]
    msg.topic.return_value = "platform.export.requests"
    consumer = export_service_mq.ExportServiceConsumer(MagicMock(), flask_app, MagicMock(), MagicMock())
    consumer._run_batch([msg])
    (event,) = records(audit_output)
    assert event["trace_id"] == "00000000000000000000000000000042"
    assert bool(event["span_id"]) == spans
    assert event["resource_id"] == resource["export_request_uuid"]
    assert event["request_id"] == resource["export_request_uuid"]
    assert event["principal"] == (None if kind == "invalid_credentials" else USER_IDENTITY["user"]["user_id"])
    assert event["org_id"] == (None if kind == "invalid_credentials" else USER_IDENTITY["org_id"])
    assert event["outcome"] == ("success" if kind == "upload" else "failure")
    assert (
        event["action"]
        == {
            "upload": "EXPORT_UPLOAD",
            "invalid_credentials": "AUTHENTICATE",
            "invalid_schema": "EXPORT",
        }[kind]
    )
    assert "private-" not in audit_output.getvalue()


def test_export_acceptance_is_not_relabeled_by_later_db_failure(flask_app, export_env, audit_output, monkeypatch):
    config, _, _ = export_env
    monkeypatch.setattr(export_service_mq, "inventory_config", lambda: config)
    msg = MagicMock()
    msg.value.return_value = export_service_utils.create_export_message_mock()
    msg.headers.return_value = []
    msg.topic.return_value = "platform.export.requests"

    def commit(_session):
        raise RuntimeError("private-later-db-error")

    monkeypatch.setattr(type(db.session()), "commit", commit)
    consumer = export_service_mq.ExportServiceConsumer(MagicMock(), flask_app, MagicMock(), MagicMock())
    with pytest.raises(RuntimeError, match="private-later-db-error"):
        consumer._run_batch([msg])
    (event,) = records(audit_output)
    assert (event["action"], event["outcome"]) == ("EXPORT_UPLOAD", "success")


@pytest.mark.parametrize("headers", [{}, {"traceparent": "private-invalid-trace"}])
def test_missing_producer_trace_does_not_inherit_batch_trace(headers, otel_provider):
    provider, _ = otel_provider()
    with provider.get_tracer(__name__).start_as_current_span("unrelated batch"):
        context = audit.with_message_audit_trace(audit.capture_audit_context(), headers, local_span=False)
    assert context.trace_id is None and context.span_id is None


def test_message_audit_trace_honors_configured_propagator():
    previous = propagate.get_global_textmap()
    try:
        propagate.set_global_textmap(CompositePropagator([]))
        context = audit.with_message_audit_trace(
            audit.capture_audit_context(),
            {"traceparent": "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"},
            local_span=False,
        )
    finally:
        propagate.set_global_textmap(previous)
    assert context.trace_id is None and context.span_id is None
