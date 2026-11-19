"""Audit records describe committed host operations, including batch rollback."""

import json
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from api import host as host_api
from app.exceptions import ValidationException
from app.logging import threadctx
from app.models import Host
from app.models import db
from app.queue import host_mq
from jobs.host_reaper import run as host_reaper_run
from lib import host_delete
from tests.helpers.api_utils import build_facts_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.db_utils import DB_FACTS
from tests.helpers.db_utils import DB_FACTS_NAMESPACE
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host

pytestmark = pytest.mark.usefixtures("restore_thread_context")


def records(output):
    return [json.loads(line) for line in output.getvalue().splitlines()]


def assert_user_event(event, *, action, resource_type, resource_id, outcome="success"):
    assert event["logger"] == "inventory.audit"
    assert event["action"] == action
    assert event["resource_type"] == resource_type
    assert event["resource_id"] == resource_id
    assert event["outcome"] == outcome
    assert event["principal"] == USER_IDENTITY["user"]["user_id"]
    assert event["principal_type"] == "User"
    assert event["org_id"] == USER_IDENTITY["org_id"]
    assert event["timestamp"].endswith("+00:00")


@pytest.fixture
def culled_audit_hosts(db_create_host):
    with patch("app.models.utils.datetime") as clock:
        clock.now.return_value = datetime(2023, 4, 2, tzinfo=UTC)
        return {
            str(host.id): host.org_id
            for org_id in ("1234567", "7654321", "3333333")
            for host in [db_create_host(host=minimal_db_host(org_id=org_id, reporter="puptoo"))]
        }


@pytest.fixture
def run_audited_reaper(
    flask_app, inventory_config, event_producer_mock, notification_event_producer_mock, monkeypatch
):
    monkeypatch.setattr(threadctx, "request_id", None, raising=False)

    def run(shutdown_handler=None):
        host_reaper_run(
            inventory_config,
            MagicMock(),
            db.session,
            event_producer_mock,
            notification_event_producer_mock,
            shutdown_handler or MagicMock(**{"shut_down.return_value": False}),
            flask_app,
        )

    return run


def assert_reaper_event(event, hosts, *, outcome):
    assert event["logger"] == "inventory.audit"
    assert event["action"] == "DELETE"
    assert event["resource_type"] == "host"
    assert event["resource_id"] in hosts
    assert event["org_id"] == hosts[event["resource_id"]]
    assert event["principal"] == "host-delete:REAPER"
    assert event["principal_type"] == "SystemActor"
    assert event["outcome"] == outcome
    assert event["timestamp"].endswith("+00:00")


def test_reaper_audits_each_committed_host_with_its_tenant(
    run_audited_reaper, culled_audit_hosts, db_create_host, inventory_config, audit_output, monkeypatch
):
    fresh_host_id = db_create_host().id
    inventory_config.host_delete_chunk_size = 10
    original_commit = type(db.session()).commit

    def commit(session):
        assert records(audit_output) == []
        original_commit(session)

    monkeypatch.setattr(type(db.session()), "commit", commit)
    run_audited_reaper()
    events = records(audit_output)
    assert len(events) == len(culled_audit_hosts)
    assert {event["resource_id"] for event in events} == set(culled_audit_hosts)
    for event in events:
        assert_reaper_event(event, culled_audit_hosts, outcome="success")
    assert [host.id for host in Host.query.all()] == [fresh_host_id]


@pytest.mark.parametrize("failure", ["flush", "kafka_unavailable"])
def test_reaper_failed_chunk_has_only_failure_audit(
    run_audited_reaper, culled_audit_hosts, inventory_config, audit_output, monkeypatch, failure
):
    inventory_config.host_delete_chunk_size = 1

    def fail(*_args, **_kwargs):
        assert records(audit_output) == []
        raise RuntimeError("private-reaper-error")

    with monkeypatch.context() as operation_patch:
        if failure == "flush":
            original_delete = host_delete._delete_host

            def delete_with_failed_flush(*args, **kwargs):
                with monkeypatch.context() as flush_patch:
                    flush_patch.setattr(type(db.session()), "flush", fail)
                    return original_delete(*args, **kwargs)

            operation_patch.setattr(host_delete, "_delete_host", delete_with_failed_flush)
        else:
            operation_patch.setattr(host_delete, "kafka_available", lambda: False)

        expected_exception = host_delete.KafkaException if failure == "kafka_unavailable" else RuntimeError
        with pytest.raises(expected_exception):
            run_audited_reaper()

    (event,) = records(audit_output)
    assert_reaper_event(event, culled_audit_hosts, outcome="failure")
    assert event["reason"] == ("publication_unavailable" if failure == "kafka_unavailable" else "delete_failed")
    assert {str(host.id) for host in Host.query.all()} == set(culled_audit_hosts)
    assert "private-reaper-error" not in audit_output.getvalue()


def test_reaper_interruption_preserves_committed_chunk_and_rolls_back_attempt(
    run_audited_reaper, culled_audit_hosts, inventory_config, audit_output
):
    inventory_config.host_delete_chunk_size = 1
    run_audited_reaper(MagicMock(**{"shut_down.side_effect": [False, True]}))
    committed, interrupted = records(audit_output)
    assert_reaper_event(committed, culled_audit_hosts, outcome="success")
    assert_reaper_event(interrupted, culled_audit_hosts, outcome="failure")
    assert committed["resource_id"] != interrupted["resource_id"]
    assert interrupted["reason"] == "interrupted"
    assert {str(host.id) for host in Host.query.all()} == set(culled_audit_hosts) - {committed["resource_id"]}


def test_reaper_without_culled_hosts_has_no_mutation_audit(run_audited_reaper, db_create_host, audit_output):
    fresh_host_id = db_create_host().id
    run_audited_reaper()
    assert records(audit_output) == []
    assert [host.id for host in Host.query.all()] == [fresh_host_id]


def test_reaper_locks_selected_hosts_until_commit(
    run_audited_reaper, culled_audit_hosts, inventory_config, audit_output, monkeypatch
):
    inventory_config.host_delete_chunk_size = 10
    original_delete = host_delete._delete_host
    blocked = []

    def delete_with_competing_writer(session, host, identity, control_rule):
        if not blocked:
            with Session(db.engine) as other:
                other.execute(text("SET LOCAL lock_timeout = '100ms'"))
                try:
                    other.query(Host).filter_by(id=host.id, org_id=host.org_id).delete(synchronize_session=False)
                    other.commit()
                    blocked.append(False)
                except OperationalError as error:
                    assert error.orig.pgcode == "55P03"
                    other.rollback()
                    blocked.append(True)
        return original_delete(session, host, identity, control_rule)

    monkeypatch.setattr(host_delete, "_delete_host", delete_with_competing_writer)
    run_audited_reaper()
    assert blocked == [True], "Another transaction must not remove a host already selected for deletion"
    events = records(audit_output)
    assert len(events) == len(culled_audit_hosts)
    for event in events:
        assert_reaper_event(event, culled_audit_hosts, outcome="success")


@pytest.mark.usefixtures("event_producer_mock")
def test_patch_audits_each_changed_host_after_commit(api_patch, db_create_host, audit_output, monkeypatch):
    hosts = [db_create_host(), db_create_host()]
    ids = {str(host.id) for host in hosts}
    session_class = type(db.session())
    original_commit = session_class.commit
    commits = []

    def commit(session):
        assert len(records(audit_output)) == len(commits)
        original_commit(session)
        commits.append(True)

    monkeypatch.setattr(session_class, "commit", commit)
    status, _ = api_patch(
        build_hosts_url(hosts),
        {"display_name": "private-display-name"},
        extra_headers={"x-rh-insights-request-id": "patch-request"},
    )
    assert status == 200
    assert len(commits) == 2
    events = records(audit_output)
    assert {event["resource_id"] for event in events} == ids
    for event in events:
        assert_user_event(event, action="UPDATE", resource_type="host", resource_id=event["resource_id"])
        assert event["request_id"] == "patch-request"
    assert "private-display-name" not in audit_output.getvalue()
    assert USER_IDENTITY["user"]["email"] not in audit_output.getvalue()


@pytest.mark.usefixtures("event_producer_mock")
@pytest.mark.parametrize("operation", ["patch", "replace_facts", "merge_facts"])
def test_update_commit_failure_rolls_back_without_success(
    operation, api_patch, api_put, db_create_host, db_get_host, audit_output, monkeypatch
):
    host = db_create_host(extra_data={"facts": deepcopy(DB_FACTS)})
    host_id, original_name, original_facts = str(host.id), host.display_name, deepcopy(host.facts)

    def fail_commit(_session):
        assert records(audit_output) == []
        raise RuntimeError("private-database-error")

    monkeypatch.setattr(type(db.session()), "commit", fail_commit)
    if operation == "patch":
        status, _ = api_patch(build_hosts_url(host_id), {"display_name": "private-change"})
        resource_type, resource_id = "host", host_id
    else:
        send = api_put if operation == "replace_facts" else api_patch
        status, _ = send(build_facts_url(host_id, DB_FACTS_NAMESPACE), {"private-key": "private-value"})
        resource_type, resource_id = "host_facts", f"{host_id}:{DB_FACTS_NAMESPACE}"
    assert status == 500
    (event,) = records(audit_output)
    assert_user_event(event, action="UPDATE", resource_type=resource_type, resource_id=resource_id, outcome="failure")
    assert event["reason"] == "mutation_failed"
    assert "private-" not in audit_output.getvalue()
    persisted = db_get_host(host_id)
    assert persisted.display_name == original_name
    assert persisted.facts == original_facts


@pytest.mark.usefixtures("event_producer_mock")
@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_facts_audit_identifies_host_and_namespace(method, api_put, api_patch, db_create_host, audit_output):
    host = db_create_host(extra_data={"facts": deepcopy(DB_FACTS)})
    host_id = str(host.id)
    send = api_put if method == "PUT" else api_patch
    status, _ = send(build_facts_url(host_id, DB_FACTS_NAMESPACE), {"private-key": "private-value"})
    assert status == 200
    (event,) = records(audit_output)
    assert_user_event(
        event, action="UPDATE", resource_type="host_facts", resource_id=f"{host_id}:{DB_FACTS_NAMESPACE}"
    )
    assert "private-" not in audit_output.getvalue()


@pytest.mark.usefixtures("event_producer_mock")
def test_post_commit_publication_failure_keeps_true_mutation_success(
    api_patch, db_create_host, db_get_host, audit_output, monkeypatch
):
    host = db_create_host()
    host_id = str(host.id)

    def fail_publication(*_args):
        assert records(audit_output)[0]["outcome"] == "success"
        raise RuntimeError("publication unavailable")

    monkeypatch.setattr(host_api, "_emit_patch_event", fail_publication)
    status, _ = api_patch(build_hosts_url(host_id), {"display_name": "committed-name"})
    assert status == 500
    (event,) = records(audit_output)
    assert_user_event(event, action="UPDATE", resource_type="host", resource_id=host_id)
    assert db_get_host(host_id).display_name == "committed-name"


@pytest.mark.usefixtures("event_producer_mock")
def test_noop_patch_has_no_mutation_event(api_patch, db_create_host, audit_output):
    host = db_create_host(extra_data={"display_name": "same-name"})
    host.display_name_reporter = "API"
    db.session.commit()
    status, _ = api_patch(build_hosts_url(str(host.id)), {"display_name": host.display_name})
    assert status == 200
    assert records(audit_output) == []


def test_bulk_tags_audits_only_changed_hosts(api_post, db_create_host, audit_output):
    changed = db_create_host()
    unchanged = db_create_host(extra_data={"tags": {"test": {"env": ["private-value"]}}})
    foreign = db_create_host(extra_data={"org_id": "another-tenant"})
    ids = [str(host.id) for host in (changed, unchanged, foreign)]
    missing = generate_uuid()
    status, data = api_post(
        "/tags",
        {
            "tags": [{"namespace": "test", "key": "env", "value": "private-value"}],
            "host_id_list": [*ids, missing],
        },
    )
    assert status == 200
    assert data["processed_hosts"] == 2
    assert set(data["not_found_hosts"]) == {ids[2], missing}
    (event,) = records(audit_output)
    assert_user_event(event, action="UPDATE", resource_type="host_tags", resource_id=ids[0])
    assert "private-value" not in audit_output.getvalue()


@pytest.mark.parametrize("failure", ["flush", "commit"])
def test_bulk_tag_rollback_has_no_success_or_processed_count(
    failure, api_post, db_create_host, db_get_host, audit_output, monkeypatch
):
    host = db_create_host()
    host_id, original_tags = str(host.id), deepcopy(host.tags)
    original_flush = type(db.session()).flush

    def fail(session, *args, **kwargs):
        if failure == "flush" and not session.dirty:
            return original_flush(session, *args, **kwargs)
        assert records(audit_output) == []
        if failure == "flush":
            raise IntegrityError("private-query", {}, RuntimeError("private-database-error"))
        raise RuntimeError("private-database-error")

    with monkeypatch.context() as patch:
        patch.setattr(type(db.session()), failure, fail)
        status, data = api_post(
            "/tags",
            {
                "tags": [{"namespace": "test", "key": "env", "value": "private-value"}],
                "host_id_list": [host_id],
            },
        )
    assert status == (200 if failure == "flush" else 500)
    if failure == "flush":
        assert data["processed_hosts"] == 0
    (event,) = records(audit_output)
    assert_user_event(event, action="UPDATE", resource_type="host_tags", resource_id=host_id, outcome="failure")
    assert event["reason"] == "tag_update_failed"
    assert "private-" not in audit_output.getvalue()
    assert db_get_host(host_id).tags == original_tags


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_delete_audits_committed_host(api_delete_host, db_create_host, db_get_host, audit_output, monkeypatch):
    host_id = str(db_create_host().id)
    original_commit = type(db.session()).commit

    def commit(session):
        assert records(audit_output) == []
        original_commit(session)

    monkeypatch.setattr(type(db.session()), "commit", commit)
    status, _ = api_delete_host(host_id)
    assert status == 200
    (event,) = records(audit_output)
    assert_user_event(event, action="DELETE", resource_type="host", resource_id=host_id)
    assert db_get_host(host_id) is None


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
@pytest.mark.parametrize("failure", ["commit", "publication"])
def test_delete_failure_is_rolled_back(
    api_delete_host, db_create_host, db_get_host, audit_output, monkeypatch, failure
):
    host_id = str(db_create_host().id)

    def fail(*_args, **_kwargs):
        assert records(audit_output) == []
        raise RuntimeError("private-delete-error")

    if failure == "commit":
        monkeypatch.setattr(type(db.session()), "commit", fail)
    else:
        monkeypatch.setattr(host_delete, "_send_delete_messages_for_batch", fail)
    status, _ = api_delete_host(host_id)
    assert status == 500
    (event,) = records(audit_output)
    assert_user_event(event, action="DELETE", resource_type="host", resource_id=host_id, outcome="failure")
    assert event["reason"] == "delete_failed"
    assert db_get_host(host_id) is not None
    assert "private-delete-error" not in audit_output.getvalue()


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_delete_generator_yields_only_after_commit(db_create_host, db_get_host, audit_output, monkeypatch):
    monkeypatch.setattr(threadctx, "request_id", None, raising=False)
    host_id = str(db_create_host().id)
    results = host_delete.delete_hosts(
        Host.query.filter(Host.id == host_id),
        MagicMock(),
        MagicMock(),
        chunk_size=1,
        control_rule="culled",
    )
    result = next(results)
    assert str(result.row.id) == host_id
    (event,) = records(audit_output)
    assert event["principal"] == "host-delete:culled"
    assert event["principal_type"] == "SystemActor"
    assert event["org_id"] == USER_IDENTITY["org_id"]
    assert event["outcome"] == "success"
    results.close()
    assert db_get_host(host_id) is None


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
@pytest.mark.parametrize("operation", ["patch", "tags", "delete"])
def test_partial_commits_keep_per_host_outcomes(
    operation, api_patch, api_post, db_create_host, db_get_host, inventory_config, audit_output, monkeypatch
):
    hosts = [db_create_host(), db_create_host()]
    ids = {str(host.id) for host in hosts}
    original_commit = type(db.session()).commit
    commits = 0

    def commit(session):
        nonlocal commits
        commits += 1
        if commits == 2:
            raise RuntimeError("second commit failed")
        original_commit(session)

    monkeypatch.setattr(type(db.session()), "commit", commit)
    if operation == "patch":
        status, _ = api_patch(build_hosts_url(hosts), {"display_name": "changed-name"})
        assert status == 500
    elif operation == "tags":
        inventory_config.api_bulk_tag_host_batch_size = 1
        status, _ = api_post(
            "/tags",
            {
                "tags": [{"namespace": "test", "key": "env", "value": "prod"}],
                "host_id_list": list(ids),
            },
        )
        assert status == 500
    else:
        monkeypatch.setattr(threadctx, "request_id", None, raising=False)
        results = host_delete.delete_hosts(
            Host.query.filter(Host.id.in_(ids)),
            MagicMock(),
            MagicMock(),
            chunk_size=1,
        )
        first = next(results)
        assert records(audit_output)[0]["resource_id"] == str(first.row.id)
        with pytest.raises(RuntimeError, match="second commit failed"):
            next(results)
    succeeded, failed = records(audit_output)
    assert {succeeded["resource_id"], failed["resource_id"]} == ids
    assert [succeeded["outcome"], failed["outcome"]] == ["success", "failure"]
    for event in (succeeded, failed):
        persisted = db_get_host(event["resource_id"])
        if operation == "delete":
            assert (persisted is None) == (event["outcome"] == "success")
        elif operation == "patch":
            assert (persisted.display_name == "changed-name") == (event["outcome"] == "success")
        else:
            assert bool(persisted.tags) == (event["outcome"] == "success")


@pytest.mark.parametrize(
    "failure,message_spans,tracing_enabled",
    [(None, True, True), (None, False, True), (None, False, False), ("flush", True, True), ("commit", True, True)],
)
def test_ingestion_mixed_actor_tenant_trace_and_batch_rollback(
    failure,
    message_spans,
    tracing_enabled,
    flask_app,
    event_producer_mock,
    notification_event_producer_mock,
    audit_output,
    monkeypatch,
    otel_provider,
):
    provider, _ = otel_provider()
    monkeypatch.setattr(host_mq, "tracer", provider.get_tracer(__name__))
    monkeypatch.setattr(host_mq, "OTEL_MQ_ENABLED", tracing_enabled)
    monkeypatch.setattr(host_mq, "OTEL_MQ_MESSAGE_SPANS_ENABLED", message_spans)
    consumer = host_mq.IngressMessageConsumer(
        MagicMock(), flask_app, event_producer_mock, notification_event_producer_mock
    )
    messages = []
    for index in (1, 2):
        identity = deepcopy(USER_IDENTITY)
        identity["org_id"] = f"org-{index}"
        identity["user"]["user_id"] = f"user-{index}"
        metadata = {**get_platform_metadata(identity), "request_id": f"request-{index}"}
        message = MagicMock()
        message.value.return_value = json.dumps(
            wrap_message(minimal_host(org_id=f"org-{index}").data(), platform_metadata=metadata)
        )
        message.headers.return_value = [("traceparent", f"00-{index:032x}-{index:016x}-01".encode())]
        message.topic.return_value = "platform.inventory.host-ingress"
        messages.append(message)
    original_commit = type(db.session()).commit
    original_flush = type(db.session()).flush

    def commit(session):
        assert records(audit_output) == []
        if failure == "commit":
            raise RuntimeError("batch failed")
        original_commit(session)

    def flush(session, *args, **kwargs):
        if failure == "flush" and len(consumer.processed_rows) == 2:
            raise RuntimeError("batch failed")
        original_flush(session, *args, **kwargs)

    def publish():
        assert len(records(audit_output)) == 2

    with monkeypatch.context() as patch:
        patch.setattr(type(db.session()), "commit", commit)
        patch.setattr(type(db.session()), "flush", flush)
        patch.setattr(consumer, "post_process_rows", publish)
        if failure:
            with pytest.raises(RuntimeError, match="batch failed"):
                consumer._run_batch(messages)
        else:
            consumer._run_batch(messages)
    events = records(audit_output)
    assert len(events) == 2
    for index, (event, result) in enumerate(zip(events, consumer.processed_rows, strict=True), 1):
        assert event["action"] == "CREATE"
        assert event["resource_type"] == "host"
        assert event["resource_id"] == str(result.persisted_host_ids[0])
        assert event["org_id"] == f"org-{index}"
        assert event["principal"] == f"user-{index}"
        assert event["request_id"] == f"request-{index}"
        assert event["trace_id"] == f"{index:032x}"
        assert bool(event["span_id"]) == message_spans
        assert event["outcome"] == ("failure" if failure else "success")
    assert Host.query.count() == (0 if failure else 2)


@pytest.mark.parametrize("consumer_class", [host_mq.IngressMessageConsumer, host_mq.SystemProfileMessageConsumer])
@pytest.mark.parametrize("failure", [None, "commit", "publication"])
def test_ingestion_audits_actual_handles_after_batch_commit(
    consumer_class,
    failure,
    flask_app,
    event_producer_mock,
    notification_event_producer_mock,
    db_create_host,
    audit_output,
    monkeypatch,
):
    # Real handlers, repositories, SQL flush/commit and JSON formatter; fake only Kafka delivery.
    existing = db_create_host()
    existing_id = str(existing.id)
    consumer = consumer_class(MagicMock(), flask_app, event_producer_mock, notification_event_producer_mock)
    host_data = minimal_host(org_id=USER_IDENTITY["org_id"]).data()
    if consumer_class is host_mq.SystemProfileMessageConsumer:
        host_data["id"] = existing_id
        host_data["system_profile"] = {"arch": "x86_64"}
    metadata = get_platform_metadata(identity=USER_IDENTITY)
    msg = MagicMock()
    msg.value.return_value = json.dumps(wrap_message(host_data, platform_metadata=metadata))
    msg.headers.return_value = []
    msg.topic.return_value = "platform.inventory.host-ingress"
    original_commit = type(db.session()).commit

    def commit(session):
        assert records(audit_output) == []
        if failure == "commit":
            raise RuntimeError("private-ingestion-error")
        original_commit(session)

    def publish():
        assert records(audit_output)[0]["outcome"] == "success"
        if failure == "publication":
            raise RuntimeError("private-ingestion-error")

    monkeypatch.setattr(type(db.session()), "commit", commit)
    monkeypatch.setattr(consumer, "post_process_rows", publish)
    if failure:
        with pytest.raises(RuntimeError, match="private-ingestion-error"):
            consumer._run_batch([msg])
    else:
        consumer._run_batch([msg])
    (result,) = consumer.processed_rows
    (event,) = records(audit_output)
    assert event["resource_id"] == str(result.persisted_host_ids[0])
    assert event["org_id"] == USER_IDENTITY["org_id"]
    assert event["request_id"] == metadata["request_id"]
    assert event["outcome"] == ("failure" if failure == "commit" else "success")
    assert event["action"] == ("UPDATE" if consumer_class is host_mq.SystemProfileMessageConsumer else "CREATE")
    assert event["principal"] == (
        "system-profile-consumer"
        if consumer_class is host_mq.SystemProfileMessageConsumer
        else USER_IDENTITY["user"]["user_id"]
    )
    persisted = Host.query.filter(Host.id == event["resource_id"]).one_or_none()
    assert (persisted is not None) == (failure != "commit" or consumer_class is host_mq.SystemProfileMessageConsumer)
    assert "private-ingestion-error" not in audit_output.getvalue()


@pytest.mark.parametrize("consumer_class", [host_mq.IngressMessageConsumer, host_mq.SystemProfileMessageConsumer])
def test_ingestion_repository_error_before_result_is_audited(
    consumer_class, flask_app, event_producer_mock, notification_event_producer_mock, audit_output, monkeypatch
):
    consumer = consumer_class(MagicMock(), flask_app, event_producer_mock, notification_event_producer_mock)
    host_data = minimal_host(org_id=USER_IDENTITY["org_id"]).data()
    host_data["system_profile"] = {"arch": "x86_64"}
    metadata = get_platform_metadata(identity=USER_IDENTITY)

    def fail(*_args, **_kwargs):
        raise RuntimeError("private-query-and-payload")

    repository_method = "add_host" if consumer_class is host_mq.IngressMessageConsumer else "update_system_profile"
    monkeypatch.setattr(host_mq.host_repository, repository_method, fail)
    with pytest.raises(RuntimeError, match="private-query-and-payload"):
        consumer.handle_message(json.dumps(wrap_message(host_data, platform_metadata=metadata)))
    (event,) = records(audit_output)
    assert event["outcome"] == "failure"
    assert event["resource_type"] == "host"
    assert event["resource_id"] is None
    assert event["org_id"] == USER_IDENTITY["org_id"]
    assert event["request_id"] == metadata["request_id"]
    assert event["principal"] == (
        USER_IDENTITY["user"]["user_id"]
        if consumer_class is host_mq.IngressMessageConsumer
        else "system-profile-consumer"
    )
    assert consumer.processed_rows == []
    assert "private-" not in audit_output.getvalue()


def test_tag_failure_discards_partial_mutation(api_post, db_create_host, db_get_host, audit_output, monkeypatch):
    failed_id = str(db_create_host().id)
    successful_id = str(db_create_host().id)
    original_update = Host._update_tags_alt

    def update(host, tags):
        if str(host.id) == failed_id:
            raise RuntimeError("private-partial-update")
        return original_update(host, tags)

    monkeypatch.setattr(Host, "_update_tags_alt", update)
    status, data = api_post(
        "/tags",
        {
            "tags": [{"namespace": "test", "key": "env", "value": "prod"}],
            "host_id_list": [failed_id, successful_id],
        },
    )
    assert status == 200
    assert data["processed_hosts"] == 1
    events = {event["resource_id"]: event for event in records(audit_output)}
    assert events[failed_id]["outcome"] == "failure"
    assert events[successful_id]["outcome"] == "success"
    assert db_get_host(failed_id).tags == {}
    assert db_get_host(failed_id).tags_alt == []
    assert db_get_host(successful_id).tags == {"test": {"env": ["prod"]}}
    assert "private-" not in audit_output.getvalue()


@pytest.mark.parametrize("consumer_class", [host_mq.IngressMessageConsumer, host_mq.SystemProfileMessageConsumer])
@pytest.mark.parametrize("failure", [RuntimeError, ValidationException])
def test_ingestion_partial_failure_is_isolated(
    consumer_class,
    failure,
    flask_app,
    event_producer_mock,
    notification_event_producer_mock,
    db_create_host,
    db_get_host,
    audit_output,
    monkeypatch,
):
    healthy, host = [db_create_host(extra_data={"system_profile_facts": {"number_of_cpus": 1}}) for _ in range(2)]
    host_id, original_name = str(host.id), host.display_name
    consumer = consumer_class(MagicMock(), flask_app, event_producer_mock, notification_event_producer_mock)
    messages = []
    for target in (healthy, host):
        host_data = minimal_host(
            org_id=USER_IDENTITY["org_id"],
            insights_id=str(target.insights_id),
            system_profile={"number_of_cpus": 4},
        ).data()
        if consumer_class is host_mq.SystemProfileMessageConsumer:
            host_data["id"] = str(target.id)
        metadata = get_platform_metadata(identity=USER_IDENTITY)
        msg = MagicMock()
        msg.value.return_value = json.dumps(wrap_message(host_data, platform_metadata=metadata))
        msg.headers.return_value = []
        msg.topic.return_value = "platform.inventory.host-ingress"
        msg.error.return_value = None
        messages.append(msg)

    original_update = Host._add_or_update_normalized_system_profiles

    def update_persisted(profile_host, data):
        if profile_host in db.session and str(profile_host.id) == host_id:
            profile_host.display_name = "private-partial-update"
            profile_host.static_system_profile.number_of_cpus = 99
            raise failure("private-mutation-error")
        return original_update(profile_host, data)

    monkeypatch.setattr(Host, "_add_or_update_normalized_system_profiles", update_persisted)
    consumer.consumer.consume.return_value = messages
    consumer.event_loop(MagicMock(side_effect=[False, True]))

    events = records(audit_output)
    assert len(events) == 2
    (success,) = (event for event in events if event["outcome"] == "success")
    assert success["resource_id"] == str(healthy.id)
    assert db_get_host(host_id).display_name == original_name
    assert db_get_host(host_id).static_system_profile.number_of_cpus == 1
    assert db_get_host(str(healthy.id)).static_system_profile.number_of_cpus == 4
    consumer.consumer.commit.assert_called_once_with(asynchronous=False)
    assert "private-" not in audit_output.getvalue()


@pytest.mark.parametrize("message_spans", [True, False])
def test_rhsm_without_identity_uses_processing_actor(
    message_spans, flask_app, event_producer_mock, notification_event_producer_mock, audit_output, monkeypatch
):
    monkeypatch.setattr(host_mq, "OTEL_MQ_MESSAGE_SPANS_ENABLED", message_spans)
    consumer = host_mq.IngressMessageConsumer(
        MagicMock(), flask_app, event_producer_mock, notification_event_producer_mock
    )
    host_data = minimal_host(
        org_id=USER_IDENTITY["org_id"],
        reporter="rhsm-conduit",
        subscription_manager_id=generate_uuid(),
    ).data()
    msg = MagicMock()
    msg.value.return_value = json.dumps(wrap_message(host_data, platform_metadata={"request_id": "rhsm-request"}))
    msg.headers.return_value = []
    msg.topic.return_value = "platform.inventory.host-ingress"
    monkeypatch.setattr(consumer, "post_process_rows", lambda: None)
    consumer._run_batch([msg])
    (event,) = records(audit_output)
    assert event["outcome"] == "success"
    assert event["principal"] == "ingress-consumer"
    assert event["principal_type"] == "SystemActor"
    assert event["org_id"] == USER_IDENTITY["org_id"]
    assert event["request_id"] == "rhsm-request"
    assert event["resource_id"] == str(consumer.processed_rows[0].persisted_host_ids[0])


@pytest.mark.parametrize("tracing_enabled", [True, False])
def test_invalid_ingress_identity_keeps_trace_without_trusting_actor(
    tracing_enabled, flask_app, event_producer_mock, notification_event_producer_mock, audit_output, monkeypatch
):
    monkeypatch.setattr(host_mq, "OTEL_MQ_ENABLED", tracing_enabled)
    monkeypatch.setattr(host_mq, "OTEL_MQ_MESSAGE_SPANS_ENABLED", False)
    consumer = host_mq.IngressMessageConsumer(
        MagicMock(), flask_app, event_producer_mock, notification_event_producer_mock
    )
    msg = MagicMock()
    msg.value.return_value = json.dumps(
        wrap_message(
            minimal_host().data(),
            platform_metadata={"request_id": "rejected-request", "b64_identity": "invalid"},
        )
    )
    msg.headers.return_value = [("traceparent", b"00-00000000000000000000000000000001-0000000000000001-00")]
    msg.topic.return_value = "platform.inventory.host-ingress"
    monkeypatch.setattr(consumer, "post_process_rows", lambda: None)
    consumer._run_batch([msg])
    (event,) = records(audit_output)
    assert event["action"] == "AUTHENTICATE"
    assert event["outcome"] == "failure"
    assert event["principal"] is None
    assert event["org_id"] is None
    assert event["trace_id"] == "00000000000000000000000000000001"
    assert event["span_id"] is None
    assert event["request_id"] == "rejected-request"


def test_system_profile_noop_has_no_mutation_event(
    flask_app, event_producer_mock, notification_event_producer_mock, db_create_host, audit_output, monkeypatch
):
    host_id = str(db_create_host(extra_data={"system_profile_facts": {"arch": "x86_64"}}).id)
    consumer = host_mq.SystemProfileMessageConsumer(
        MagicMock(), flask_app, event_producer_mock, notification_event_producer_mock
    )
    msg = MagicMock()
    msg.value.return_value = json.dumps(
        wrap_message(
            {
                "id": host_id,
                "org_id": USER_IDENTITY["org_id"],
                "system_profile": {"arch": "x86_64"},
            },
            platform_metadata={"request_id": "noop-request"},
        )
    )
    msg.headers.return_value = []
    msg.topic.return_value = "platform.inventory.system-profile"
    monkeypatch.setattr(consumer, "post_process_rows", lambda: None)
    consumer._run_batch([msg])
    assert records(audit_output) == []
    consumer.consumer.commit.assert_called_once_with(asynchronous=False)


@pytest.mark.parametrize("rejection", ["not_found", "empty_profile"])
def test_system_profile_rejection_preserves_other_committed_operations(
    rejection,
    flask_app,
    event_producer_mock,
    notification_event_producer_mock,
    db_create_host,
    db_get_host,
    audit_output,
    monkeypatch,
):
    host_id = str(db_create_host(extra_data={"system_profile_facts": {"number_of_cpus": 1}}).id)
    consumer = host_mq.SystemProfileMessageConsumer(
        MagicMock(), flask_app, event_producer_mock, notification_event_producer_mock
    )
    messages = []
    for index in (1, 2, 3):
        data = {"id": host_id, "org_id": USER_IDENTITY["org_id"], "system_profile": {"number_of_cpus": index * 2}}
        if index == 2:
            if rejection == "not_found":
                data["id"] = generate_uuid()
            else:
                data["system_profile"] = {}
        msg = MagicMock()
        msg.value.return_value = json.dumps(wrap_message(data, platform_metadata={"request_id": f"request-{index}"}))
        msg.headers.return_value = []
        msg.topic.return_value = "platform.inventory.system-profile"
        messages.append(msg)
    monkeypatch.setattr(consumer, "post_process_rows", lambda: None)
    consumer._run_batch(messages)
    events = records(audit_output)
    assert len(events) == 3
    successes = [event for event in events if event["outcome"] == "success"]
    assert len(successes) == 2
    assert {event["request_id"] for event in successes} == {"request-1", "request-3"}
    assert all(event["resource_id"] == host_id for event in successes)
    assert db_get_host(host_id).static_system_profile.number_of_cpus == 6
    consumer.consumer.commit.assert_called_once_with(asynchronous=False)
