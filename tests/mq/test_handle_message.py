from __future__ import annotations

import json
import logging
from copy import deepcopy
from types import SimpleNamespace
from unittest import mock
from unittest.mock import ANY

import marshmallow
import pytest
from sqlalchemy.exc import OperationalError

from app.auth.identity import Identity
from app.auth.identity import create_mock_identity_with_org_id
from app.queue.events import EventType
from app.queue.host_mq import IngressMessageConsumer
from lib.host_repository import AddHostResult
from tests.helpers.mq_utils import expected_headers
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import OWNER_ID
from tests.helpers.test_utils import SATELLITE_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_encoded_idstr
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host


def test_handle_message_failure_invalid_json_message(mocker, ingress_message_consumer_mock):
    invalid_message = "failure {} "

    mock_event_producer = mocker.Mock()
    mock_notification_event_producer = mocker.Mock()

    with pytest.raises(json.decoder.JSONDecodeError):
        ingress_message_consumer_mock.handle_message(invalid_message)

    mock_event_producer.assert_not_called()
    mock_notification_event_producer.assert_not_called()


def test_handle_message_failure_invalid_message_format(mocker, ingress_message_consumer_mock):
    invalid_message = json.dumps({"operation": "add_host", "NOTdata": {}})  # Missing data field

    mock_event_producer = mocker.Mock()
    mock_notification_event_producer = mocker.Mock()

    with pytest.raises(marshmallow.exceptions.ValidationError):
        ingress_message_consumer_mock.handle_message(invalid_message)

    mock_event_producer.assert_not_called()
    mock_notification_event_producer.assert_not_called()


@pytest.mark.usefixtures("flask_app")
@pytest.mark.parametrize("identity", (SYSTEM_IDENTITY, SATELLITE_IDENTITY, USER_IDENTITY))
@pytest.mark.parametrize("existing_ungrouped", (True, False))
def test_handle_message_happy_path(
    identity, existing_ungrouped, mocker, ingress_message_consumer_mock, db_create_group
):
    expected_insights_id = generate_uuid()
    host = minimal_host(org_id=identity["org_id"], insights_id=expected_insights_id)
    existing_group_name = "test group"
    if existing_ungrouped:
        db_create_group(existing_group_name, identity=identity, ungrouped=existing_ungrouped)

    mock_notification_event_producer = mocker.Mock()
    message = wrap_message(host.data(), "add_host", get_platform_metadata(identity))
    result = ingress_message_consumer_mock.handle_message(json.dumps(message))

    assert result.event_type == EventType.created
    assert str(result.row.insights_id) == expected_insights_id
    assert len(result.row.groups) == 1
    assert result.row.groups[0]["name"] == existing_group_name if existing_ungrouped else "Ungrouped Hosts"
    assert result.row.groups[0]["ungrouped"] is True

    mock_notification_event_producer.write_event.assert_not_called()


@pytest.mark.usefixtures("flask_app")
@pytest.mark.usefixtures("enable_kessel")
@pytest.mark.parametrize("identity", (SYSTEM_IDENTITY, SATELLITE_IDENTITY, USER_IDENTITY))
def test_handle_message_kessel_private_endpoint(identity, mocker, ingress_message_consumer_mock, db_create_group):
    from uuid import UUID

    mock_access_token = "mock_sa_token_12345"
    workspace_uuid = generate_uuid()
    get_rbac_mock = mocker.patch(
        "lib.middleware.rbac_get_request_using_endpoint_and_headers", return_value={"id": str(workspace_uuid)}
    )
    mocker.patch(
        "lib.middleware.inventory_config",
        return_value=SimpleNamespace(
            bypass_kessel=False,
            kessel_auth_enabled=True,
            rbac_endpoint="fake-rbac-endpoint:8080",
            rbac_endpoint_ca_certificate=None,
            rbac_endpoint_authenticated=False,
        ),
    )
    mocker.patch("lib.middleware._get_rbac_access_token", return_value=mock_access_token)

    # Simulate the MQ consumer creating the group in the DB while we wait.
    def wait_and_create(workspace_id_str, *args, **kwargs):
        db_create_group("Ungrouped Hosts", identity=identity, ungrouped=True, group_id=UUID(workspace_id_str))

    wait_mock = mocker.patch("lib.group_repository.wait_for_workspace_event", side_effect=wait_and_create)

    host = minimal_host(org_id=identity["org_id"])

    message = wrap_message(host.data(), "add_host", get_platform_metadata(identity))
    result = ingress_message_consumer_mock.handle_message(json.dumps(message))

    assert result.event_type == EventType.created
    assert "/_private/_s2s/workspaces/ungrouped/" in get_rbac_mock.call_args_list[0][0][0]
    assert get_rbac_mock.call_args_list[0][0][1] == {
        "Authorization": f"Bearer {mock_access_token}",
        "X-RH-RBAC-CLIENT-ID": "inventory",
        "X-RH-RBAC-ORG-ID": "test",
    }
    wait_mock.assert_called_once_with(
        str(workspace_uuid),
        EventType.created,
        org_id=identity["org_id"],
        timeout=ANY,
    )


@pytest.mark.usefixtures("flask_app")
@pytest.mark.usefixtures("enable_kessel")
@pytest.mark.parametrize("identity", (SYSTEM_IDENTITY, SATELLITE_IDENTITY, USER_IDENTITY))
def test_handle_message_kessel_rbac_v2_uses_db_group_without_request_context(
    identity, mocker, ingress_message_consumer_mock, db_create_group
):
    """MQ ingest has no Flask request. After the ungrouped workspace is created via S2S RBAC
    and the workspace event lands in the DB, host association must use that local Group row
    even when hbi.rbac-v2 is enabled — not get_rbac_workspace_by_id(), which reads request headers.
    """
    from uuid import UUID

    mock_access_token = "mock_sa_token_12345"
    workspace_uuid = generate_uuid()
    get_rbac_mock = mocker.patch(
        "lib.middleware.rbac_get_request_using_endpoint_and_headers", return_value={"id": str(workspace_uuid)}
    )
    mocker.patch(
        "lib.middleware.inventory_config",
        return_value=SimpleNamespace(
            bypass_kessel=False,
            kessel_auth_enabled=True,
            rbac_endpoint="fake-rbac-endpoint:8080",
            rbac_endpoint_ca_certificate=None,
            rbac_endpoint_authenticated=False,
        ),
    )
    mocker.patch("lib.middleware._get_rbac_access_token", return_value=mock_access_token)
    mocker.patch("lib.group_repository.is_rbac_v2_enabled", return_value=True)
    rbac_http = mocker.patch("lib.middleware._execute_rbac_http_request")

    def wait_and_create(workspace_id_str, *args, **kwargs):
        db_create_group("Ungrouped Hosts", identity=identity, ungrouped=True, group_id=UUID(workspace_id_str))

    mocker.patch("lib.group_repository.wait_for_workspace_event", side_effect=wait_and_create)

    host = minimal_host(org_id=identity["org_id"])
    message = wrap_message(host.data(), "add_host", get_platform_metadata(identity))
    result = ingress_message_consumer_mock.handle_message(json.dumps(message))

    assert result.event_type == EventType.created
    assert result.row.groups[0]["ungrouped"] is True
    assert result.row.groups[0]["id"] == str(workspace_uuid)
    assert result.row.groups[0]["name"] == "Ungrouped Hosts"
    assert "/_private/_s2s/workspaces/ungrouped/" in get_rbac_mock.call_args_list[0][0][0]
    rbac_http.assert_not_called()


@pytest.mark.usefixtures("flask_app")
@pytest.mark.usefixtures("enable_kessel")
def test_handle_message_kessel_workspace_timeout(mocker, ingress_message_consumer_mock, caplog):
    """TimeoutError from wait_for_workspace_event is logged with context and re-raised with a clear metric label."""

    mocker.patch(
        "lib.middleware.rbac_get_request_using_endpoint_and_headers",
        return_value={"id": str(generate_uuid())},
    )
    mocker.patch(
        "lib.middleware.inventory_config",
        return_value=SimpleNamespace(
            bypass_kessel=False,
            kessel_auth_enabled=True,
            rbac_endpoint="fake-rbac-endpoint:8080",
            rbac_endpoint_ca_certificate=None,
            rbac_endpoint_authenticated=False,
        ),
    )
    mocker.patch("lib.middleware._get_rbac_access_token", return_value="mock_token")
    mocker.patch(
        "lib.group_repository.wait_for_workspace_event",
        side_effect=TimeoutError("No workspace creation message consumed in time."),
    )
    mock_add_host_failure = mocker.patch("app.queue.host_mq.metrics.add_host_failure")

    host = minimal_host(reporter="test_reporter")
    message = wrap_message(host.data(), "add_host", get_platform_metadata(SYSTEM_IDENTITY))

    with caplog.at_level(logging.ERROR), pytest.raises(TimeoutError):
        ingress_message_consumer_mock.handle_message(json.dumps(message))

    assert any(
        "Timed out waiting for RBAC workspace creation while adding host" in record.message
        for record in caplog.records
        if record.levelno == logging.ERROR
    )
    mock_add_host_failure.labels.assert_called_once_with("TimeoutError", "test_reporter")
    mock_add_host_failure.labels.return_value.inc.assert_called_once()


@pytest.mark.usefixtures("flask_app")
def test_handle_message_existing_ungrouped_workspace(mocker, db_create_group):
    expected_insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=expected_insights_id)
    group_id = db_create_group("kessel-test", ungrouped=True).id
    mock_notification_event_producer = mocker.Mock()
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    message = wrap_message(host.data(), "add_host", get_platform_metadata(SYSTEM_IDENTITY))
    result = consumer.handle_message(json.dumps(message))

    assert result.event_type == EventType.created
    assert str(result.row.insights_id) == expected_insights_id

    assert result.row.groups[0]["name"] == "kessel-test"
    assert result.row.groups[0]["id"] == str(group_id)

    mock_notification_event_producer.write_event.assert_not_called()


@pytest.mark.parametrize("display_name", ("\udce2\udce2", "\\udce2\\udce2", "\udce2\udce2\\udce2\\udce2"))
def test_handle_message_failure_invalid_surrogates(mocker, display_name, ingress_message_consumer_mock):
    mocker.patch("app.queue.host_mq.build_event_and_headers", return_value=("event", {}))
    add_host = mocker.patch("lib.host_repository.add_host", return_value=(mocker.MagicMock(), mocker.MagicMock()))

    invalid_message = f'{{"operation": "", "data": {{"display_name": "hello{display_name}"}}}}'

    with pytest.raises(UnicodeError):
        ingress_message_consumer_mock.handle_message(invalid_message)

    add_host.assert_not_called()


@pytest.mark.usefixtures("flask_app")
@mock.patch.object(
    IngressMessageConsumer,
    "process_message",
    return_value=(mock.MagicMock(), None, Identity(SYSTEM_IDENTITY), mock.MagicMock()),
)
def test_handle_message_unicode_not_damaged(
    process_message_mock, mocker, db_create_host, ingress_message_consumer_mock, subtests
):
    mocker.patch("app.queue.host_mq.build_event_and_headers", return_value=("event", {}))

    operation_raw = "🧜🏿‍♂️"
    operation_escaped = json.dumps(operation_raw)[1:-1]

    names = [
        f"{operation_raw}{operation_raw}",
        f"{operation_escaped}{operation_escaped}",
        f"{operation_raw}{operation_escaped}",
    ]

    messages = []

    for name in names:
        host = minimal_host(display_name=name, system_profile={"owner_id": OWNER_ID})
        host.reporter = "me"
        msg = json.dumps(wrap_message(host.data(), "", get_platform_metadata()))
        messages.append(msg)

    messages_tuple = tuple(messages)

    for message in messages_tuple:
        with subtests.test(message=message):
            process_message_mock.reset_mock()
            process_message_mock.return_value = (
                db_create_host(),
                AddHostResult.updated,
                create_mock_identity_with_org_id(SYSTEM_IDENTITY["org_id"]),
                mocker.MagicMock(),
            )
            ingress_message_consumer_mock.handle_message(message)
            process_message_mock.assert_called_once_with(json.loads(message)["data"], mocker.ANY, {})


def test_handle_message_verify_metadata_pass_through(mq_create_or_update_host):
    host_id = generate_uuid()
    insights_id = generate_uuid()

    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], id=host_id, insights_id=insights_id)
    metadata = {
        "request_id": generate_uuid(),
        "archive_url": "https://some.url",
        "b64_identity": get_encoded_idstr(),
    }

    _, event, _ = mq_create_or_update_host(host, platform_metadata=metadata, return_all_data=True)

    assert event["platform_metadata"] == metadata


def test_handle_message_verify_org_id(mq_create_or_update_host):
    host_id = generate_uuid()
    insights_id = generate_uuid()
    org_id = "1234567890"

    org_identity = deepcopy(SYSTEM_IDENTITY)
    org_identity["org_id"] = org_id
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], org_id=org_id, id=host_id, insights_id=insights_id)
    metadata = {
        "request_id": generate_uuid(),
        "archive_url": "https://some.url",
        "b64_identity": get_encoded_idstr(identity=org_identity),
    }

    _, event, _ = mq_create_or_update_host(host, platform_metadata=metadata, return_all_data=True)

    assert event["platform_metadata"] == metadata


@pytest.mark.parametrize("add_host_result", AddHostResult)
def test_handle_message_verify_message_headers(mocker, add_host_result, mq_create_or_update_host, db_create_host):
    host_id = generate_uuid()
    insights_id = generate_uuid()
    request_id = generate_uuid()
    subscription_manager_id = generate_uuid()

    db_host = db_create_host(
        extra_data={
            "insights_id": insights_id,
            "subscription_manager_id": subscription_manager_id,
            "reporter": "rhsm-conduit",
        }
    )

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        id=host_id,
        insights_id=insights_id,
        reporter="rhsm-conduit",
        subscription_manager_id=subscription_manager_id,
    )

    mocker.patch(
        "lib.host_repository.add_host",
        return_value=(db_host, add_host_result),
    )

    _, _, headers = mq_create_or_update_host(host, platform_metadata={"request_id": request_id}, return_all_data=True)

    assert headers == expected_headers(add_host_result.name, request_id, insights_id, "rhsm-conduit", host.host_type)


@pytest.mark.usefixtures("flask_app")
def test_handle_message_side_effect(mocker, ingress_message_consumer_mock):
    fake_add_host = mocker.patch(
        "lib.host_repository.add_host", side_effect=OperationalError("DB Problem", "fake_param", "fake_orig")
    )

    expected_insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=expected_insights_id)

    fake_add_host.reset_mock()
    message = json.dumps(wrap_message(host.data(), "add_host", get_platform_metadata()))

    with pytest.raises(expected_exception=OperationalError):
        ingress_message_consumer_mock.handle_message(message)
