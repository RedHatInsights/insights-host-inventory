import json
import logging
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from functools import partial
from types import SimpleNamespace
from unittest.mock import patch

import marshmallow
import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from app.auth.identity import Identity
from app.auth.identity import create_mock_identity_with_org_id
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.logging import threadctx
from app.queue.events import EventType
from app.queue.host_mq import _validate_json_object_for_utf8
from app.queue.host_mq import event_loop
from app.queue.host_mq import handle_message
from app.queue.host_mq import update_system_profile
from app.queue.host_mq import write_add_update_event_message
from app.utils import Tag
from lib.host_repository import AddHostResult
from tests.helpers.db_utils import create_reference_host_in_db
from tests.helpers.mq_utils import FakeMessage
from tests.helpers.mq_utils import assert_mq_host_data
from tests.helpers.mq_utils import expected_headers
from tests.helpers.mq_utils import wrap_message
from tests.helpers.system_profile_utils import INVALID_SYSTEM_PROFILES
from tests.helpers.system_profile_utils import mock_system_profile_specification
from tests.helpers.system_profile_utils import system_profile_specification
from tests.helpers.test_utils import SATELLITE_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import YUM_REPO2
from tests.helpers.test_utils import base_host
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_encoded_idstr
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now
from tests.helpers.test_utils import valid_system_profile

OWNER_ID = SYSTEM_IDENTITY["system"]["cn"]


def test_event_loop_exception_handling(mocker, event_producer, flask_app):
    """
    Test to ensure that an exception in message handler method does not cause the
    event loop to stop processing messages
    """
    fake_consumer = mocker.Mock()
    fake_consumer.consume.return_value = [FakeMessage()]

    fake_notification_event_producer = None
    handle_message_mock = mocker.Mock(
        return_value=None,
        side_effect=(
            None,
            KeyError("blah"),
            None,
        ),
    )
    event_loop(
        fake_consumer,
        flask_app.app,
        event_producer,
        fake_notification_event_producer,
        handler=handle_message_mock,
        interrupt=mocker.Mock(side_effect=(False, False, False, True)),
    )
    assert handle_message_mock.call_count == 3


def test_event_loop_with_error_message_handling(mocker, event_producer, flask_app):
    """
    Test to ensure that event loop does not stop processing messages when
    consumer.poll() gets an error in message handler method.
    """
    fake_consumer = mocker.Mock(**{"consume.side_effect": [[FakeMessage()], [FakeMessage("oops")], [FakeMessage()]]})
    fake_notification_event_producer = None

    handle_message_mock = mocker.Mock(return_value=None, side_effect=None)
    event_loop(
        fake_consumer,
        flask_app.app,
        event_producer,
        fake_notification_event_producer,
        handler=handle_message_mock,
        interrupt=mocker.Mock(side_effect=(False, False, False, True)),
    )

    assert handle_message_mock.call_count == 2


def test_handle_message_failure_invalid_json_message(mocker):
    invalid_message = "failure {} "

    mock_event_producer = mocker.Mock()
    mock_notification_event_producer = mocker.Mock()

    with pytest.raises(json.decoder.JSONDecodeError):
        handle_message(invalid_message, mock_event_producer, mock_notification_event_producer)

    mock_event_producer.assert_not_called()
    mock_notification_event_producer.assert_not_called()


def test_handle_message_failure_invalid_message_format(mocker):
    invalid_message = json.dumps({"operation": "add_host", "NOTdata": {}})  # Missing data field

    mock_event_producer = mocker.Mock()
    mock_notification_event_producer = mocker.Mock()

    with pytest.raises(marshmallow.exceptions.ValidationError):
        handle_message(invalid_message, mock_event_producer, mock_notification_event_producer)

    mock_event_producer.assert_not_called()
    mock_notification_event_producer.assert_not_called()


@pytest.mark.usefixtures("flask_app")
@pytest.mark.parametrize("identity", (SYSTEM_IDENTITY, SATELLITE_IDENTITY))
@pytest.mark.parametrize("kessel_migration", (True, False))
def test_handle_message_happy_path(identity, kessel_migration, mocker):
    with mocker.patch("app.queue.host_mq.get_flag_value", return_value=kessel_migration):
        expected_insights_id = generate_uuid()
        host = minimal_host(account=identity["account_number"], insights_id=expected_insights_id)

        mock_notification_event_producer = mocker.Mock()

        message = wrap_message(host.data(), "add_host", get_platform_metadata(identity))
        result = handle_message(json.dumps(message), mock_notification_event_producer)

        assert result.event_type == EventType.created
        assert result.host_row.canonical_facts["insights_id"] == expected_insights_id
        if kessel_migration:
            assert len(result.host_row.groups) == 1
        else:
            assert result.host_row.groups == []

        mock_notification_event_producer.write_event.assert_not_called()


@pytest.mark.usefixtures("flask_app")
def test_handle_message_existing_ungrouped_workspace(mocker, db_create_group):
    with mocker.patch("app.queue.host_mq.get_flag_value", return_value=True):
        expected_insights_id = generate_uuid()
        host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=expected_insights_id)
        group_id = db_create_group("kessel-test", ungrouped=True).id
        mock_notification_event_producer = mocker.Mock()

        message = wrap_message(host.data(), "add_host", get_platform_metadata(SYSTEM_IDENTITY))
        result = handle_message(json.dumps(message), mock_notification_event_producer)

        assert result.event_type == EventType.created
        assert result.host_row.canonical_facts["insights_id"] == expected_insights_id
        assert result.host_row.groups[0]["name"] == "kessel-test"
        assert result.host_row.groups[0]["id"] == str(group_id)

        mock_notification_event_producer.write_event.assert_not_called()


def test_request_id_is_reset(mocker, flask_app, db_create_host):
    with flask_app.app.app_context():
        mock_event_producer = mocker.Mock()
        mock_notification_event_producer = mocker.Mock()
        metadata = get_platform_metadata()
        add_host_mock = mocker.patch(
            "app.queue.host_mq.add_host",
            return_value=(
                db_create_host(),
                AddHostResult.created,
                Identity(SYSTEM_IDENTITY),
                mocker.MagicMock(),
            ),
        )

        message = wrap_message(minimal_host().data(), "add_host", metadata)
        result = handle_message(json.dumps(message), mock_notification_event_producer, add_host_mock)
        write_add_update_event_message(mock_event_producer, mock_notification_event_producer, result)
        assert json.loads(mock_event_producer.write_event.call_args[0][0])["metadata"]["request_id"] == metadata.get(
            "request_id"
        )
        assert threadctx.request_id == metadata.get("request_id")

        metadata["request_id"] = None
        message = wrap_message(minimal_host().data(), "add_host", metadata)
        result = handle_message(json.dumps(message), mock_notification_event_producer, add_host_mock)

        assert threadctx.request_id is None


def test_shutdown_handler(mocker, flask_app):
    fake_consumer = mocker.Mock()
    fake_consumer.consume.return_value = [FakeMessage(), FakeMessage()]

    fake_event_producer = None
    fake_notification_event_producer = None
    handle_message_mock = mocker.Mock(return_value=None, side_effect=[None, None])
    event_loop(
        fake_consumer,
        flask_app.app,
        fake_event_producer,
        fake_notification_event_producer,
        handler=handle_message_mock,
        interrupt=mocker.Mock(side_effect=(False, True)),
    )
    fake_consumer.consume.assert_called_once()

    assert handle_message_mock.call_count == 2


# Leaving this in as a reminder that we need to impliment this test eventually
# when the problem that it is supposed to test is fixed
# https://projects.engineering.redhat.com/browse/RHCLOUD-3503
# def test_handle_message_verify_threadctx_request_id_set_and_cleared(self):
#     # set the threadctx.request_id
#     # and clear it
#     pass


@pytest.mark.parametrize("display_name", ("\udce2\udce2", "\\udce2\\udce2", "\udce2\udce2\\udce2\\udce2"))
def test_handle_message_failure_invalid_surrogates(mocker, display_name):
    mocker.patch("app.queue.host_mq.build_event")
    add_host = mocker.patch("app.queue.host_mq.add_host", return_value=(mocker.MagicMock(), None, mocker.MagicMock()))

    invalid_message = f'{{"operation": "", "data": {{"display_name": "hello{display_name}"}}}}'

    with pytest.raises(UnicodeError):
        handle_message(invalid_message, mocker.Mock(), add_host)

    add_host.assert_not_called()


@pytest.mark.usefixtures("flask_app")
def test_handle_message_unicode_not_damaged(mocker, db_create_host, subtests):
    mocker.patch("app.queue.host_mq.build_event")
    add_host = mocker.patch(
        "app.queue.host_mq.add_host",
        return_value=(mocker.MagicMock(), None, Identity(SYSTEM_IDENTITY), mocker.MagicMock()),
    )

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
            add_host.reset_mock()
            add_host.return_value = (
                db_create_host(),
                AddHostResult.updated,
                create_mock_identity_with_org_id(SYSTEM_IDENTITY["org_id"]),
                mocker.MagicMock(),
            )
            handle_message(message, mocker.Mock(), add_host)
            add_host.assert_called_once_with(json.loads(message)["data"], mocker.ANY, {})


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
            "canonical_facts": {"insights_id": insights_id, "subscription_manager_id": subscription_manager_id},
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

    mock_add_host = mocker.patch(
        "app.queue.host_mq.add_host",
        return_value=(db_host, add_host_result, Identity(SYSTEM_IDENTITY), mocker.MagicMock()),
    )

    _, _, headers = mq_create_or_update_host(
        host, platform_metadata={"request_id": request_id}, return_all_data=True, message_operation=mock_add_host
    )

    assert headers == expected_headers(add_host_result.name, request_id, insights_id, "rhsm-conduit")


@pytest.mark.parametrize(
    "expected_value, system_profile",
    [
        ("False", {}),
        ("False", {"bootc_status": {}}),
        ("True", {"bootc_status": {"booted": {}}}),
        ("True", {"bootc_status": {"booted": {"image": "192.168.0.1:5000/foo/foo:latest"}}}),
    ],
)
def test_verify_bootc_in_headers(expected_value, system_profile, mq_create_or_update_host):
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=generate_uuid(),
        system_profile=system_profile,
    )

    _, _, headers = mq_create_or_update_host(host, return_all_data=True)
    assert "is_bootc" in headers
    assert headers["is_bootc"] is expected_value


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_simple(mq_create_or_update_host):
    """
    Tests adding a host with some simple data
    """
    expected_insights_id = generate_uuid()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        system_profile={"owner_id": OWNER_ID},
    )

    expected_results = {"host": {**host.data()}}

    host_keys_to_check = ["display_name", "insights_id", "account"]

    key, event, _ = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_edge_host(mq_create_or_update_host, db_get_host):
    """
    Tests adding an edge host
    """
    expected_insights_id = generate_uuid()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        system_profile={"owner_id": OWNER_ID, "host_type": "edge", "system_update_method": "dnf"},
    )

    expected_results = {"host": {**host.data()}}

    host_keys_to_check = ["display_name", "insights_id", "account"]

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)

    # verify that the edge host has stale_timestamp set in year 2260, way out in the future to avoid culling.
    saved_host_from_db = db_get_host(event["host"]["id"])

    # verify that the saved host stale_timestamp is past Year 2200. The actual year should be 2260
    assert saved_host_from_db.stale_timestamp.year == 2260


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_system_profile(mq_create_or_update_host):
    """
    Tests adding a host with message containing system profile
    """
    expected_insights_id = generate_uuid()
    expected_system_profile = valid_system_profile()
    expected_system_profile["owner_id"] = OWNER_ID

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        system_profile=expected_system_profile,
    )

    expected_results = {"host": {**host.data()}}

    host_keys_to_check = ["display_name", "insights_id", "account", "system_profile"]

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_without_defer_to(models_datetime_mock, mq_create_or_update_host, db_get_host):
    """
    Tests adding (updating) a host without "defer_to" option - system profile should be updated.
    """
    expected_insights_id = generate_uuid()
    original_system_profile = valid_system_profile(owner_id=OWNER_ID)
    updated_system_profile = valid_system_profile(owner_id=OWNER_ID, additional_yum_repo=YUM_REPO2)
    puptoo_stale_timestamp = models_datetime_mock + timedelta(days=1)

    existing_host = create_reference_host_in_db(
        expected_insights_id, "puptoo", original_system_profile, puptoo_stale_timestamp
    )
    existing_host_id = existing_host.id
    returned_host = existing_host

    assert returned_host.system_profile_facts == original_system_profile

    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile=updated_system_profile,
    )

    updated_host = mq_create_or_update_host(host)
    assert str(updated_host.id) == str(existing_host_id)

    returned_host = db_get_host(existing_host_id)
    assert returned_host.system_profile_facts == updated_system_profile


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_defer_to(models_datetime_mock, mq_create_or_update_host, db_get_host):
    """
    Tests adding (updating) a host with "defer_to" option - system profile should not be updated.
    """
    expected_insights_id = generate_uuid()
    original_system_profile = valid_system_profile(owner_id=OWNER_ID)
    updated_system_profile = valid_system_profile(owner_id=OWNER_ID, additional_yum_repo=YUM_REPO2)
    puptoo_stale_timestamp = models_datetime_mock + timedelta(days=1)

    existing_host = create_reference_host_in_db(
        expected_insights_id, "puptoo", original_system_profile, puptoo_stale_timestamp
    )
    existing_host_id = existing_host.id
    returned_host = db_get_host(existing_host_id)

    assert returned_host.system_profile_facts == original_system_profile

    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile=updated_system_profile,
    )

    updated_host = mq_create_or_update_host(host, operation_args={"defer_to_reporter": "puptoo"})
    assert str(updated_host.id) == str(existing_host_id)

    returned_host = db_get_host(existing_host_id)
    assert returned_host.system_profile_facts == original_system_profile


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_defer_to_wrong_reporter(models_datetime_mock, mq_create_or_update_host, db_get_host):
    """
    Tests adding (updating) a host with "defer_to" option,
    but base host not reported by specified reporter - system profile should be updated.
    """
    expected_insights_id = generate_uuid()
    original_system_profile = valid_system_profile(owner_id=OWNER_ID)
    updated_system_profile = valid_system_profile(owner_id=OWNER_ID, additional_yum_repo=YUM_REPO2)
    stale_timestamp = models_datetime_mock + timedelta(days=1)

    existing_host = create_reference_host_in_db(
        expected_insights_id, "yupana", original_system_profile, stale_timestamp
    )
    existing_host_id = existing_host.id
    returned_host = db_get_host(existing_host_id)

    assert returned_host.system_profile_facts == original_system_profile

    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile=updated_system_profile,
    )

    updated_host = mq_create_or_update_host(host, operation_args={"defer_to_reporter": "puptoo"})
    assert str(updated_host.id) == str(existing_host_id)

    returned_host = db_get_host(existing_host_id)
    assert returned_host.system_profile_facts == updated_system_profile


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_defer_to_stale(mq_create_or_update_host, db_get_host):
    """
    Tests adding (updating) a host with "defer_to" option, but reporter stale - system profile should be updated.
    """
    expected_insights_id = generate_uuid()
    original_system_profile = valid_system_profile(owner_id=OWNER_ID)
    updated_system_profile = valid_system_profile(owner_id=OWNER_ID, additional_yum_repo=YUM_REPO2)
    puptoo_stale_timestamp = now() - timedelta(days=1)

    existing_host = create_reference_host_in_db(
        expected_insights_id, "puptoo", original_system_profile, puptoo_stale_timestamp
    )
    existing_host_id = existing_host.id

    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile=updated_system_profile,
    )

    # Make host stale here
    with patch("app.models.datetime") as models_datetime:
        models_datetime.now.return_value = now() + timedelta(days=2)
        updated_host = mq_create_or_update_host(host, operation_args={"defer_to_reporter": "puptoo"})
        assert str(updated_host.id) == str(existing_host_id)
        returned_host = db_get_host(existing_host_id)
        assert returned_host.system_profile_facts == updated_system_profile


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_wrong_owner(mocker, mq_create_or_update_host):
    """
    Tests adding a host with message containing system profile
    """
    mock_notification_event_producer = mocker.Mock()
    expected_insights_id = generate_uuid()
    expected_system_profile = valid_system_profile()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        system_profile=expected_system_profile,
    )

    with pytest.raises(ValidationException) as ve:
        mq_create_or_update_host(
            host, return_all_data=True, notification_event_producer=mock_notification_event_producer
        )
    assert ve.value.detail == "The owner in host does not match the owner in identity"
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.usefixtures("event_datetime_mock")
@pytest.mark.parametrize(
    "with_account, rhsm_reporter",
    [
        (True, "rhsm-conduit"),
        (False, "rhsm-conduit"),
        (True, "rhsm-system-profile-bridge"),
        (False, "rhsm-system-profile-bridge"),
    ],
)
def test_add_host_rhsm_conduit_without_cn(mq_create_or_update_host, with_account, rhsm_reporter):
    """
    Tests adding a host with reporter rhsm-conduit and no cn
    """
    sub_mangager_id = "09152341-475c-4671-a376-df609374c349"

    metadata_without_b64 = get_platform_metadata(identity=SYSTEM_IDENTITY)
    del metadata_without_b64["b64_identity"]

    if with_account:
        host = minimal_host(
            account=SYSTEM_IDENTITY.get("account_number"),
            reporter=rhsm_reporter,
            subscription_manager_id=sub_mangager_id,
        )
    else:
        host = minimal_host(reporter=rhsm_reporter, subscription_manager_id=sub_mangager_id)

    key, event, headers = mq_create_or_update_host(host, platform_metadata=metadata_without_b64, return_all_data=True)

    # owner_id equals subscription_manager_id with dashes
    assert event["host"]["system_profile"]["owner_id"] == "09152341-475c-4671-a376-df609374c349"


@pytest.mark.usefixtures("event_datetime_mock")
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_add_host_rhsm_conduit_owner_id(mq_create_or_update_host, rhsm_reporter):
    """
    Tests adding a host with reporter rhsm-conduit
    """
    sub_mangager_id = "09152341-475c-4671-a376-df609374c349"

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        reporter=rhsm_reporter,
        subscription_manager_id=sub_mangager_id,
        system_profile={"owner_id": OWNER_ID},
    )

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    # owner_id gets overwritten and equates to subscription_manager_id with dashes
    assert event["host"]["system_profile"]["owner_id"] == "09152341-475c-4671-a376-df609374c349"


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_tags(mq_create_or_update_host):
    """
    Tests adding a host with message containing tags
    """
    expected_insights_id = generate_uuid()
    expected_tags = [
        {"namespace": "NS1", "key": "key3", "value": "val3"},
        {"namespace": "NS3", "key": "key2", "value": "val2"},
        {"namespace": "Sat", "key": "prod", "value": None},
        {"namespace": "Sat", "key": "dev", "value": ""},
        {"namespace": "Sat", "key": "test"},
        {"namespace": None, "key": "key", "value": "val1"},
        {"namespace": "", "key": "key", "value": "val4"},
        {"namespace": "null", "key": "key", "value": "val5"},
        {"namespace": None, "key": "only_key", "value": None},
        {"key": "just_key"},
        {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"], insights_id=expected_insights_id, tags=expected_tags
    )

    expected_results = {"host": {**host.data()}}
    host_keys_to_check = ["display_name", "insights_id", "account"]

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)

    assert len(event["host"]["tags"]) == len(expected_tags)


@pytest.mark.parametrize(
    "tag",
    [
        {"namespace": "NS", "key": "", "value": "val"},
        {"namespace": "a" * 256, "key": "key", "value": "val"},
        {"namespace": "NS", "key": "a" * 256, "value": "val"},
        {"namespace": "NS", "key": "key", "value": "a" * 256},
        {"namespace": "NS", "key": None, "value": "a" * 256},
        {"namespace": "NS", "value": "a" * 256},
    ],
)
def test_add_host_with_invalid_tags(tag, mocker, mq_create_or_update_host):
    """
    Tests adding a host with message containing invalid tags
    """
    mock_notification_event_producer = mocker.Mock()
    insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=[tag])

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.system_profile
def test_add_host_empty_keys_system_profile(mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    system_profile = {"owner_id": OWNER_ID, "disk_devices": [{"options": {"": "invalid"}}]}
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile=system_profile)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.system_profile
def test_add_host_with_invalid_system_update_method(mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    system_profile = {"owner_id": OWNER_ID, "system_update_method": "Whooping-cranes"}
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile=system_profile)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.system_profile
@pytest.mark.parametrize(("system_profile",), ((system_profile,) for system_profile in INVALID_SYSTEM_PROFILES))
def test_add_host_long_strings_system_profile(mocker, mq_create_or_update_host, system_profile):
    mock_notification_event_producer = mocker.Mock()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile=system_profile)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.system_profile
@pytest.mark.parametrize(("baseurl",), (("http://www.example.com",), ("x" * 2049,)))
def test_add_host_yum_repos_baseurl_system_profile(mq_create_or_update_host, db_get_host, baseurl):
    yum_repo = {"name": "repo1", "gpgcheck": True, "enabled": True}
    host_to_create = minimal_host(
        account=SYSTEM_IDENTITY["account_number"], system_profile={"yum_repos": [{**yum_repo, "baseurl": baseurl}]}
    )
    created_host_from_event = mq_create_or_update_host(host_to_create)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert created_host_from_db.system_profile_facts.get("yum_repos") == [yum_repo]


@pytest.mark.system_profile
def test_add_host_type_coercion_system_profile(mq_create_or_update_host, db_get_host):
    host_to_create = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile={"number_of_cpus": "1"})
    created_host_from_event = mq_create_or_update_host(host_to_create)
    created_host_from_db = db_get_host(created_host_from_event.id)

    assert created_host_from_db.system_profile_facts == {"number_of_cpus": 1, "owner_id": OWNER_ID}


@pytest.mark.system_profile
def test_add_host_key_filtering_system_profile(mq_create_or_update_host, db_get_host):
    host_to_create = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        system_profile={
            "owner_id": OWNER_ID,
            "number_of_cpus": 1,
            "number_of_gpus": 2,
            "disk_devices": [{"options": {"uid": "0"}, "mount_options": {"ro": True}}],
        },
    )
    created_host_from_event = mq_create_or_update_host(host_to_create)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert created_host_from_db.system_profile_facts == {
        "number_of_cpus": 1,
        "disk_devices": [{"options": {"uid": "0"}}],
        "owner_id": OWNER_ID,
    }


def test_add_host_externalized_system_profile(mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    orig_spec = system_profile_specification()
    mock_spec = deepcopy(orig_spec)
    mock_spec["$defs"]["SystemProfile"]["properties"]["number_of_cpus"]["minimum"] = 2

    with mock_system_profile_specification(mock_spec):
        host_to_create = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile={"number_of_cpus": 1})
        with pytest.raises(ValidationException):
            mq_create_or_update_host(host_to_create, notification_event_producer=mock_notification_event_producer)
        mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_owner_id(mq_create_or_update_host, db_get_host):
    """
    Tests that owner_id in the system profile is ingested properly
    """
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile={"owner_id": OWNER_ID})
    created_host_from_event = mq_create_or_update_host(host)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert created_host_from_db.system_profile_facts == {"owner_id": OWNER_ID}


@pytest.mark.usefixtures("event_datetime_mock", "db_get_host")
def test_add_host_with_owner_incorrect_format(mocker, mq_create_or_update_host):
    """
    Tests that owner_id in the system profile is rejected if it's in the wrong format
    """
    mock_notification_event_producer = mocker.Mock()
    owner_id = "Mike Wazowski"
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile={"owner_id": owner_id})
    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_operating_system(mq_create_or_update_host, db_get_host):
    """
    Tests that operating_system in the system profile is ingested properly
    """
    operating_system = {"major": 5, "minor": 1, "name": "RHEL"}
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        system_profile={"operating_system": operating_system, "owner_id": OWNER_ID},
    )
    created_host_from_event = mq_create_or_update_host(host)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert created_host_from_db.system_profile_facts.get("operating_system") == operating_system


@pytest.mark.usefixtures("event_datetime_mock", "db_get_host")
def test_add_host_with_operating_system_incorrect_format(mocker, mq_create_or_update_host):
    """
    Tests that operating_system in the system profile is rejected if it's in the wrong format
    """
    mock_notification_event_producer = mocker.Mock()
    operating_system_list = [
        {"major": "bananas", "minor": 1, "name": "RHEL"},
        {"major": 1, "minor": "oranges", "name": "RHEL"},
        {"major": 1, "minor": 1, "name": "UBUNTU"},
    ]
    for operating_system in operating_system_list:
        host = minimal_host(
            account=SYSTEM_IDENTITY["account_number"],
            system_profile={"operating_system": operating_system, "owner_id": OWNER_ID},
        )
        with pytest.raises(ValidationException):
            mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
        mock_notification_event_producer.write_event.assert_called()


@pytest.mark.parametrize(
    "facts",
    (
        [{"facts": {"": "invalid"}, "namespace": "rhsm"}],
        [{"facts": {"metadata": {"": "invalid"}}, "namespace": "rhsm"}],
    ),
)
def test_add_host_empty_keys_facts(facts, mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    insights_id = generate_uuid()
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=insights_id,
        facts=facts,
        system_profile={"owner_id": OWNER_ID},
    )

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.parametrize("stale_timestamp", ("invalid", datetime.now().isoformat()))
def test_add_host_with_invalid_stale_timestamp(stale_timestamp, mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    insights_id = generate_uuid()
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=insights_id,
        stale_timestamp=stale_timestamp,
        system_profile={"owner_id": OWNER_ID},
    )

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_sap_system(mq_create_or_update_host):
    expected_insights_id = generate_uuid()

    system_profile = valid_system_profile()
    system_profile["sap_system"] = True
    system_profile["owner_id"] = OWNER_ID

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"], insights_id=expected_insights_id, system_profile=system_profile
    )

    expected_results = {"host": {**host.data()}}

    host_keys_to_check = ["display_name", "insights_id", "account", "system_profile"]

    key, event, _ = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@pytest.mark.parametrize("tags", ({}, {"tags": []}, {"tags": {}}))
def test_add_host_with_no_tags(tags, mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, **tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {}


def test_add_host_with_null_tags(mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    host = minimal_host(tags=None)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


def test_add_host_with_tag_list(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    tags = [
        {"namespace": "namespace 1", "key": "key 1", "value": "value 1"},
        {"namespace": "namespace 1", "key": "key 2", "value": None},
        {"namespace": "namespace 2", "key": "key 1", "value": None},
        {"namespace": "namespace 2", "key": "key 1", "value": ""},
        {"namespace": "namespace 2", "key": "key 1", "value": "value 2"},
        {"namespace": "", "key": "key 3", "value": "value 3"},
        {"namespace": None, "key": "key 3", "value": "value 4"},
        {"namespace": "null", "key": "key 3", "value": "value 5"},
    ]

    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {
        "namespace 1": {"key 1": ["value 1"], "key 2": []},
        "namespace 2": {"key 1": ["value 2"]},
        "null": {"key 3": ["value 3", "value 4", "value 5"]},
    }


def test_add_host_with_tag_dict(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    tags = {
        "namespace 1": {"key 1": ["value 1"], "key 2": [], "key 3": None},
        "namespace 2": {"key 1": ["value 2", "", None]},
        "namespace 3": None,
        "namespace 4": {},
        "null": {"key 4": ["value 3"]},
        "": {"key 4": ["value 4"]},
    }
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {
        "namespace 1": {"key 1": ["value 1"], "key 2": [], "key 3": []},
        "namespace 2": {"key 1": ["value 2"]},
        "null": {"key 4": ["value 3", "value 4"]},
    }


@pytest.mark.parametrize(
    "tags",
    (
        "string",
        123,
        123.4,
        [["namespace", "key", "value"]],
        [{"namespace": {"key": ["value"]}}],
        {"namespace": ["key", ["value"]]},
        {"namespace": [["key", "value"]]},
        {"namespace": ["key", "value"]},
        {"namespace": "key"},
        {"namespace": {"key": "value"}},
        {"namespace": {"key": {"value": "eulav"}}},
        {"namespace": {"key": [["value"]]}},
        {"namespace": {"key": [{"value": "eulav"}]}},
        {"namespace": {"key": [123]}},
        {"namespace": {"key": [123.4]}},
        {"namespace": {"": ["value"]}},
    ),
)
def test_add_host_with_invalid_tags_2(tags, mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=tags)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


def test_update_display_name(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        display_name="test_host",
        insights_id=insights_id,
    )
    mq_create_or_update_host(host)

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        display_name="better_test_host",
        insights_id=insights_id,
    )
    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.display_name == "better_test_host"


def test_add_tags_to_host_by_list(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ([], {}),
        ([{"namespace": "namespace 1", "key": "key 1", "value": "value 1"}], {"namespace 1": {"key 1": ["value 1"]}}),
        (
            [{"namespace": "namespace 2", "key": "key 1", "value": "value 2"}],
            {"namespace 1": {"key 1": ["value 1"]}, "namespace 2": {"key 1": ["value 2"]}},
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_add_tags_to_host_by_dict(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        ({"namespace 1": {"key 1": ["value 1"]}}, {"namespace 1": {"key 1": ["value 1"]}}),
        (
            {"namespace 2": {"key 1": ["value 2"]}},
            {"namespace 1": {"key 1": ["value 1"]}, "namespace 2": {"key 1": ["value 2"]}},
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_replace_tags_of_host_by_list(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ([], {}),
        (
            [
                {"namespace": "namespace 1", "key": "key 1", "value": "value 1"},
                {"namespace": "namespace 2", "key": "key 2", "value": "value 2"},
                {"namespace": "null", "key": "key 3", "value": "value 3"},
            ],
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            [{"namespace": "namespace 1", "key": "key 4", "value": "value 4"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            [{"key": "key 5", "value": "value 5"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 5": ["value 5"]},
            },
        ),
        (
            [{"namespace": None, "key": "key 6", "value": "value 6"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 6": ["value 6"]},
            },
        ),
        (
            [{"namespace": "", "key": "key 7", "value": "value 7"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 7": ["value 7"]},
            },
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)
            structured_tags = structured_tags = [
                Tag.from_nested({ns: ns_item}) for ns, ns_item in expected_tags.items()
            ]

            assert expected_tags == record.tags
            # The more concise way of replacing tags changes the list order
            assert sorted(
                Tag.create_flat_tags_from_structured(structured_tags), key=lambda t: t["namespace"]
            ) == sorted(record.tags_alt, key=lambda t: t["namespace"])


def test_replace_host_tags_by_dict(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        (
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            {"namespace 1": {"key 4": ["value 4"]}},
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            {"": {"key 5": ["value 5"]}},
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 5": ["value 5"]},
            },
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)
            structured_tags = [Tag.from_nested({ns: ns_item}) for ns, ns_item in expected_tags.items()]

            assert expected_tags == record.tags
            # The more concise way of replacing tags changes the list order
            assert sorted(
                Tag.create_flat_tags_from_structured(structured_tags), key=lambda t: t["namespace"]
            ) == sorted(record.tags_alt, key=lambda t: t["namespace"])


def test_keep_host_tags_by_empty(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({"tags": {"namespace 1": {"key 1": ["value 1"]}}}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({"tags": []}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({"tags": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, **message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


@pytest.mark.parametrize("tags", ({}, {"tags": []}, {"tags": {}}))
def test_add_host_default_empty_dict(tags, mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, **tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {}
    assert record.tags_alt == []


def test_delete_host_tags(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        (
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "namespace 3": {"key 3": ["value 3"]},
                "null": {"key 4": ["value 4"]},
            },
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "namespace 3": {"key 3": ["value 3"]},
                "null": {"key 4": ["value 4"]},
            },
        ),
        (
            {"namespace 2": None, "namespace 3": {}},
            {"namespace 1": {"key 1": ["value 1"]}, "null": {"key 4": ["value 4"]}},
        ),
        ({"null": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({"null": {"key 5": ["value 5"]}}, {"namespace 1": {"key 1": ["value 1"]}, "null": {"key 5": ["value 5"]}}),
        ({"": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)
            structured_tags = [Tag.from_nested({ns: ns_item}) for ns, ns_item in expected_tags.items()]

            assert expected_tags == record.tags
            assert Tag.create_flat_tags_from_structured(structured_tags) == record.tags_alt


@pytest.mark.usefixtures("event_datetime_mock")
@pytest.mark.parametrize("with_last_check_in", [True, False])
def test_add_host_stale_timestamp(mq_create_or_update_host, with_last_check_in):
    """
    Tests to see if the host is successfully created with both reporter
    and stale_timestamp set.
    """
    with (
        patch("app.serialization.get_flag_value", return_value=with_last_check_in),
        patch("app.staleness_serialization.get_flag_value", return_value=with_last_check_in),
    ):
        expected_insights_id = generate_uuid()
        stale_timestamp = now()

        host = minimal_host(
            account=SYSTEM_IDENTITY["account_number"],
            insights_id=expected_insights_id,
            stale_timestamp=stale_timestamp.isoformat(),
        )

        host_keys_to_check = ["reporter", "stale_timestamp", "culled_timestamp"]

        key, event, _ = mq_create_or_update_host(host, return_all_data=True)
        if with_last_check_in:
            updated_timestamp = datetime.fromisoformat(event["host"]["last_check_in"])
        else:
            updated_timestamp = datetime.fromisoformat(event["host"]["updated"])
        host.stale_timestamp = (updated_timestamp + timedelta(seconds=104400)).isoformat()
        expected_results = {
            "host": {
                **host.data(),
                "stale_warning_timestamp": (updated_timestamp + timedelta(seconds=604800)).isoformat(),
                "culled_timestamp": (updated_timestamp + timedelta(seconds=1209600)).isoformat(),
            }
        }

        assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@pytest.mark.parametrize("field_to_remove", ["stale_timestamp", "reporter"])
def test_add_host_stale_timestamp_missing_culling_fields(mocker, field_to_remove, mq_create_or_update_host):
    """
    tests to check the API will reject a host if it doesn't have both
    culling fields. This should raise InventoryException.
    """
    mock_notification_event_producer = mocker.Mock()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"])
    delattr(host, field_to_remove)

    with pytest.raises(InventoryException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.parametrize(
    "additional_data",
    (
        {"stale_timestamp": "2019-12-16T10:10:06.754201+00:00", "reporter": ""},
        {"stale_timestamp": "2019-12-16T10:10:06.754201+00:00", "reporter": None},
        {"stale_timestamp": "not a timestamp", "reporter": "puptoo"},
        {"stale_timestamp": "", "reporter": "puptoo"},
        {"stale_timestamp": None, "reporter": "puptoo"},
    ),
)
def test_add_host_stale_timestamp_invalid_culling_fields(mocker, additional_data, mq_create_or_update_host):
    """
    tests to check the API will reject a host if it doesn’t have both
    culling fields. This should raise InventoryException.
    """
    mock_notification_event_producer = mocker.Mock()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], **additional_data)

    with pytest.raises(InventoryException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


def test_valid_string_is_ok():
    _validate_json_object_for_utf8("naïve fiancé 👰🏻")
    assert True


def test_invalid_string_raises_exception():
    with pytest.raises(UnicodeEncodeError):
        _validate_json_object_for_utf8("hello\udce2\udce2")


def test_dicts_are_traversed(mocker):
    mock = mocker.patch("app.queue.host_mq._validate_json_object_for_utf8")

    _validate_json_object_for_utf8({"first": "item", "second": "value"})

    mock.assert_has_calls(
        (mocker.call("first"), mocker.call("item"), mocker.call("second"), mocker.call("value")), any_order=True
    )


def test_lists_are_traversed(mocker):
    mock = mocker.patch("app.queue.host_mq._validate_json_object_for_utf8")

    _validate_json_object_for_utf8(["first", "second"])

    mock.assert_has_calls((mocker.call("first"), mocker.call("second")), any_order=True)


@pytest.mark.parametrize(
    "obj",
    (
        {"first": "naïve fiancé 👰🏻", "second": "hello\udce2\udce2"},
        {"first": {"subkey": "hello\udce2\udce2"}, "second": "🤷🏻‍♂️"},
        [{"first": "hello\udce2\udce2"}],
        {"deep": ["deeper", {"deepest": ["Mariana trench", {"Earth core": "hello\udce2\udce2"}]}]},
    ),
)
def test_invalid_string_is_found_in_dict_value(obj):
    with pytest.raises(UnicodeEncodeError):
        _validate_json_object_for_utf8(obj)


@pytest.mark.parametrize(
    "obj",
    (
        {"naïve fiancé 👰🏻": "first", "hello\udce2\udce2": "second"},
        {"first": {"hello\udce2\udce2": "subvalue"}, "🤷🏻‍♂️": "second"},
        [{"hello\udce2\udce2": "first"}],
        {"deep": ["deeper", {"deepest": ["Mariana trench", {"hello\udce2\udce2": "Earth core"}]}]},
    ),
)
def test_invalid_string_is_found_in_dict_key(obj):
    with pytest.raises(UnicodeEncodeError):
        _validate_json_object_for_utf8(obj)


@pytest.mark.parametrize(
    "obj",
    (
        ["naïve fiancé 👰🏻", "hello\udce2\udce2"],
        {"first": ["hello\udce2\udce2"], "second": "🤷🏻‍♂️"},
        ["first", ["hello\udce2\udce2"]],
        ["deep", {"deeper": ["deepest", {"Mariana trench": ["Earth core", "hello\udce2\udce2"]}]}],
    ),
)
def test_invalid_string_is_found_in_list_item(obj):
    with pytest.raises(UnicodeEncodeError):
        _validate_json_object_for_utf8(obj)


@pytest.mark.parametrize("value", (1.23, 0, 123, -123, True, False, None))
def test_other_values_are_ignored(value):
    _validate_json_object_for_utf8(value)
    assert True


@pytest.mark.usefixtures("api_get")
def test_host_account_using_mq(mq_create_or_update_host, db_get_host, db_get_hosts):
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], fqdn="d44533.foo.redhat.co")
    host.account = SYSTEM_IDENTITY["account_number"]

    created_host = mq_create_or_update_host(host)
    assert db_get_host(created_host.id).account == SYSTEM_IDENTITY["account_number"]

    first_batch = db_get_hosts([created_host.id])

    # verify that the two hosts vars are pointing to the same resource.
    same_host = mq_create_or_update_host(host)

    second_batch = db_get_hosts([created_host.id, same_host.id])

    assert created_host.id == same_host.id
    assert len(first_batch.all()) == len(second_batch.all())


@pytest.mark.parametrize("id_type", ("id", "insights_id", "fqdn"))
def test_update_system_profile(mq_create_or_update_host, db_get_host, id_type):
    expected_ids = {"insights_id": generate_uuid(), "fqdn": "foo.test.redhat.com"}
    input_host = base_host(**expected_ids, system_profile={"owner_id": OWNER_ID, "number_of_cpus": 1})
    first_host_from_event = mq_create_or_update_host(input_host)
    first_host_from_db = db_get_host(first_host_from_event.id)
    expected_ids["id"] = str(first_host_from_db.id)

    assert str(first_host_from_db.canonical_facts["insights_id"]) == expected_ids["insights_id"]
    assert first_host_from_db.system_profile_facts.get("number_of_cpus") == 1

    input_host = base_host(
        **{id_type: expected_ids[id_type]}, system_profile={"number_of_cpus": 4, "number_of_sockets": 8}
    )
    input_host.stale_timestamp = None
    input_host.reporter = None
    second_host_from_event = mq_create_or_update_host(input_host, message_operation=update_system_profile)
    second_host_from_db = db_get_host(second_host_from_event.id)

    # The second host should have the same ID and insights ID,
    # and the system profile should have updated with the new values.
    assert str(second_host_from_db.id) == first_host_from_event.id
    assert str(second_host_from_db.canonical_facts["insights_id"]) == expected_ids["insights_id"]
    assert second_host_from_db.system_profile_facts == {
        "owner_id": OWNER_ID,
        "number_of_cpus": 4,
        "number_of_sockets": 8,
    }


@pytest.mark.usefixtures("db_get_host")
def test_update_system_profile_not_found(mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    expected_insights_id = generate_uuid()
    input_host = base_host(
        insights_id=expected_insights_id, system_profile={"owner_id": OWNER_ID, "number_of_cpus": 1}
    )
    mq_create_or_update_host(input_host)

    input_host = base_host(insights_id=generate_uuid(), system_profile={"number_of_cpus": 4, "number_of_sockets": 8})

    # Should raise an exception due to missing host
    with pytest.raises(InventoryException):
        mq_create_or_update_host(
            input_host,
            notification_event_producer=mock_notification_event_producer,
            message_operation=update_system_profile,
        )
    mock_notification_event_producer.write_event.assert_called_once()


def test_update_system_profile_not_provided(mocker, mq_create_or_update_host, db_get_host):
    expected_ids = {"insights_id": generate_uuid(), "fqdn": "foo.test.redhat.com"}
    input_host = minimal_host(**expected_ids, system_profile={"owner_id": OWNER_ID, "number_of_cpus": 1})
    first_host_from_event = mq_create_or_update_host(input_host)
    first_host_from_db = db_get_host(first_host_from_event.id)
    mock_notification_event_producer = mocker.Mock()

    input_host = minimal_host(id=str(first_host_from_db.id), system_profile={})

    with pytest.raises(InventoryException):
        mq_create_or_update_host(
            input_host,
            notification_event_producer=mock_notification_event_producer,
            message_operation=update_system_profile,
        )
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.usefixtures("flask_app")
def test_handle_message_side_effect(mocker):
    fake_add_host = mocker.patch(
        "lib.host_repository.add_host", side_effect=OperationalError("DB Problem", "fake_param", "fake_orig")
    )

    expected_insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=expected_insights_id)

    fake_add_host.reset_mock()
    message = json.dumps(wrap_message(host.data(), "add_host", get_platform_metadata()))

    with pytest.raises(expected_exception=OperationalError):
        handle_message(message, mocker.MagicMock())


@pytest.mark.parametrize("platform_metadata", (None, {}, {"request_id": "12345"}))
def test_update_system_profile_no_identity(mocker, platform_metadata, db_create_host):
    message = wrap_message(
        minimal_host(account="foobar", system_profile={"number_of_cpus": 4}).data(), "add_host", platform_metadata
    )

    # We don't care about the values here
    mocker.patch(
        "lib.host_repository.update_system_profile",
        return_value=(
            db_create_host(),
            AddHostResult.updated,
        ),
    )

    # Just make sure it doesn't complain about missing Identity/metadata
    handle_message(json.dumps(message), mocker.Mock(), update_system_profile)


def test_update_system_profile_host_not_found(mocker, flask_app):
    message = json.dumps(
        wrap_message(
            minimal_host(org_id="nomatch", account="nomatch", system_profile={"number_of_cpus": 4}).data(),
            "add_host",
            get_platform_metadata(),
        )
    )

    fake_consumer = mocker.Mock()
    fake_consumer.consume.return_value = [FakeMessage(message=message)]

    message_handler = partial(
        handle_message,
        message_operation=update_system_profile,
        notification_event_producer=mocker.Mock(),
    )

    # Make sure the "not found" exception is properly handled
    event_loop(
        fake_consumer,
        flask_app.app,
        mocker.Mock(),
        mocker.Mock(),
        handler=message_handler,
        interrupt=mocker.Mock(side_effect=(False, True)),
    )


# Adding a host requires identity or rhsm-conduit reporter, which does not have identity
@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
def test_no_identity_and_no_rhsm_reporter(mocker):
    expected_insights_id = generate_uuid()
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=expected_insights_id)

    platform_metadata = get_platform_metadata()
    platform_metadata.pop("b64_identity")

    message = wrap_message(host.data(), "add_host", platform_metadata)

    with pytest.raises(ValidationException):
        handle_message(json.dumps(message), mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called()


# Adding a host requires identity or rhsm-conduit reporter, which does not have identity
@pytest.mark.usefixtures("flask_app")
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_reporter_and_no_platform_metadata(mocker, rhsm_reporter):
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=generate_uuid(),
        reporter=rhsm_reporter,
        subscription_manager_id=OWNER_ID,
    )

    message = wrap_message(host.data(), "add_host")

    # We just want to verify that no error gets thrown here.
    handle_message(json.dumps(message), mocker.Mock())


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_reporter_and_no_identity(mocker, rhsm_reporter, db_create_host):
    expected_insights_id = generate_uuid()

    mock_add_host = mocker.patch(
        "app.queue.host_mq.add_host",
        return_value=(
            db_create_host(),
            AddHostResult.created,
            Identity(SYSTEM_IDENTITY),
            mocker.MagicMock(),
        ),
    )

    mock_event_producer = mocker.Mock()
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        reporter=rhsm_reporter,
        subscription_manager_id=OWNER_ID,
    )

    platform_metadata = get_platform_metadata()
    platform_metadata.pop("b64_identity")
    message = wrap_message(host.data(), "add_host", platform_metadata)

    result = handle_message(json.dumps(message), mock_notification_event_producer, mock_add_host)
    write_add_update_event_message(mock_event_producer, mock_notification_event_producer, result)

    mock_event_producer.write_event.assert_called_once()
    mock_notification_event_producer.assert_not_called()


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
def test_non_rhsm_reporter_and_no_identity(mocker):
    expected_insights_id = generate_uuid()
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        reporter="yee-haw",
        subscription_manager_id=OWNER_ID,
    )

    platform_metadata = get_platform_metadata()
    platform_metadata.pop("b64_identity")
    message = wrap_message(host.data(), "add_host", platform_metadata)
    with pytest.raises(ValidationException):
        handle_message(json.dumps(message), mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called()


@pytest.mark.usefixtures("flask_app")
def test_owner_id_different_from_cn(mocker):
    expected_insights_id = generate_uuid()
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        system_profile={"owner_id": "137c9d58-941c-4bb9-9426-7879a367c23b"},
    )

    message = wrap_message(host.data(), "add_host", get_platform_metadata())

    with pytest.raises(ValidationException) as ve:
        handle_message(json.dumps(message), mock_notification_event_producer)
    assert ve.value.detail == "The owner in host does not match the owner in identity"
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.usefixtures("db_get_host")
def test_change_owner_id_of_existing_host(mq_create_or_update_host):
    expected_insights_id = generate_uuid()
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"], insights_id=expected_insights_id, fqdn="d44533.foo.redhat.co"
    )

    created_key, created_event, created_headers = mq_create_or_update_host(host, return_all_data=True)
    assert created_event["host"]["account"] == SYSTEM_IDENTITY["account_number"]
    assert created_event["host"]["system_profile"]["owner_id"] == OWNER_ID

    NEW_CN = "137c9d58-941c-4bb9-9426-7879a367c23b"
    new_id = deepcopy(SYSTEM_IDENTITY)
    new_id["system"]["cn"] = NEW_CN
    platform_metadata = get_platform_metadata(new_id)

    host = minimal_host(
        account=new_id["account_number"],
        insights_id=expected_insights_id,
        fqdn="d44533.foo.redhat.co",
        system_profile={"owner_id": NEW_CN},
    )

    updated_key, updated_event, updated_headers = mq_create_or_update_host(
        host, platform_metadata=platform_metadata, return_all_data=True
    )
    assert updated_key == created_key
    assert updated_event["host"]["system_profile"]["owner_id"] == NEW_CN


#  tests changes to owner_id and display name
@pytest.mark.usefixtures("db_get_host")
def test_owner_id_present_in_existing_host_but_missing_from_payload(mq_create_or_update_host):
    expected_insights_id = generate_uuid()
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        display_name="test_host",
        insights_id=expected_insights_id,
        system_profile={"owner_id": OWNER_ID},
        reporter="puptoo",
    )

    created_key, created_event, created_headers = mq_create_or_update_host(host, return_all_data=True)
    assert created_event["host"]["display_name"] == "test_host"
    assert created_event["host"]["system_profile"]["owner_id"] == OWNER_ID

    NEW_CN = "137c9d58-941c-4bb9-9426-7879a367c23b"

    # use new identity with a new 'CN'
    new_id = deepcopy(SYSTEM_IDENTITY)
    new_id["system"]["cn"] = NEW_CN
    platform_metadata = get_platform_metadata(new_id)

    host = minimal_host(insights_id=expected_insights_id, display_name="better_test_host", reporter="puptoo")

    updated_key, updated_event, updated_headers = mq_create_or_update_host(
        host, platform_metadata=platform_metadata, return_all_data=True
    )
    # explicitly test the posted event
    assert updated_key == created_key
    assert updated_event["host"]["system_profile"]["owner_id"] == NEW_CN
    assert updated_event["host"]["display_name"] == "better_test_host"


@pytest.mark.parametrize(
    "user",
    (
        {"user": {"email": "tuser@redhat.com", "first_name": "test"}},
        {"user": {"email": "tuser@redhat.com"}},
        {"user": {"first_name": "test"}},
        {"user": {}},
        {},
    ),
)
def test_create_host_by_user_with_missing_details(mq_create_or_update_host, db_get_host, user):
    user_id = deepcopy(USER_IDENTITY)
    del user_id["user"]
    user_id.update(user)
    input_host = minimal_host(account=user_id["account_number"])

    created_host = mq_create_or_update_host(input_host)
    # find the just created host from the DB
    host_from_db = db_get_host(created_host.id)

    assert created_host.id == str(host_from_db.id)


def test_add_host_with_canonical_facts_MAC_address_incorrect_format(mocker, mq_create_or_update_host, subtests):
    """
    Tests that a validation exception is raised when MAC address is in the wrong format.
    """
    bad_address_list = [
        "bad",  # just a random string
        "Z1:Z2:Z3:Z4:Z5:Z6",  # right length, out of range character
        "BD0DC5FB42356",  # too long
        "BD0DC5FB423",  # too short
        "BD:0D:C5:FB:42:35:66",  # too long
        "BD:0D:C5:FB:42:3",  # too short
        "1EDC.C1E7.32BA.ABCD",  # too long
        "1EDC.C1E7",  # too short
        "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33:44",  # too long
        "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22",  # too short
        "99:40:16:A9:3821",  # missing one dilimiter
        "99:40:16:A9:38::21",  # too many delimiters
    ]
    mock_notification_event_producer = mocker.Mock()

    for bad_address in bad_address_list:
        with subtests.test(bad_address=bad_address):
            host = minimal_host(mac_addresses=[bad_address])
            with pytest.raises(ValidationException):
                mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
            mock_notification_event_producer.write_event.assert_called()


def test_add_host_with_canonical_facts_MAC_address_valid_formats(mq_create_or_update_host, db_get_host):
    """
    Tests that a pyload containing a list of MAC adresses (in each of the valid formats) is excepted.
    """
    host = minimal_host(
        mac_addresses=[
            "BD0DC5FB4235",
            "d3a94b06bbdd",
            "99:40:16:A9:38:21",
            "2f:3c:00:53:8c:71",
            "58-CA-D4-5F-D6-BE",
            "d5-90-c8-e0-3b-e5",
            "1EDC.C1E7.32BA",
            "a2da.8b79.40e0",
            "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33",
            "00112233445566778899aabbccddeeff00112233",
        ]
    )
    created_host = mq_create_or_update_host(host)
    host_from_db = db_get_host(created_host.id)

    assert created_host.mac_addresses == host_from_db.canonical_facts["mac_addresses"]


@pytest.mark.usefixtures("event_datetime_mock")
def test_create_invalid_host_produces_message(mocker, mq_create_or_update_host):
    insights_id = generate_uuid()
    system_profile = valid_system_profile()
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=insights_id,
        system_profile=system_profile,
    )

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


def test_groups_empty_for_new_host(mq_create_or_update_host, db_get_host):
    expected_insights_id = generate_uuid()
    host = minimal_host(insights_id=expected_insights_id)

    created_key, created_event, _ = mq_create_or_update_host(host, return_all_data=True)
    assert db_get_host(created_key).groups == []
    assert created_event["host"]["groups"] == []


def test_groups_not_overwritten_for_existing_hosts(
    mq_create_or_update_host, db_get_hosts_for_group, db_create_group_with_hosts
):
    # Create a group with a host in it;
    # Modify one value on the host and update via MQ;
    # Assert that the modified field is changed & the "groups" field is unchanged
    group = db_create_group_with_hosts("existing_group", 1)
    host = db_get_hosts_for_group(group.id)[0]
    group_id = str(group.id)
    host_id = str(host.id)

    update_data = minimal_host(insights_id=host.canonical_facts["insights_id"], ansible_host="updated.ansible.host")
    created_key, created_event, _ = mq_create_or_update_host(update_data, return_all_data=True)

    assert created_key == host_id
    assert created_event["host"]["ansible_host"] == "updated.ansible.host"
    assert created_event["host"]["groups"][0]["id"] == group_id


@pytest.mark.usefixtures("event_datetime_mock", "db_get_host")
def test_add_host_with_invalid_identity(mocker, mq_create_or_update_host):
    """
    Tests that using an invalid identity still results in a notification message
    """
    identity = deepcopy(USER_IDENTITY)
    identity["account_number"] = -5
    metadata = {
        "request_id": "b9757340-f839-4541-9af6-f7535edf08db",
        "archive_url": "http://s3.aws.com/redhat/insights/1234567",
        "b64_identity": get_encoded_idstr(identity),
    }
    mock_notification_event_producer = mocker.Mock()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"])
    with pytest.raises(ValidationException):
        mq_create_or_update_host(
            host, notification_event_producer=mock_notification_event_producer, platform_metadata=metadata
        )

    mock_notification_event_producer.write_event.assert_called_once()


def test_batch_mq_add_host_operations(mocker, event_producer, flask_app):
    host = minimal_host(
        insights_id=generate_uuid(),
    ).data()

    msg = json.dumps(
        wrap_message(
            host,
            "add_host",
            get_platform_metadata(),
        )
    )

    # Patch batch settings in inventory_config()
    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(
            mq_db_batch_max_messages=7,
            mq_db_batch_max_seconds=1,
            culling_stale_warning_offset_delta=1,
            culling_culled_offset_delta=1,
            conventional_time_to_stale_seconds=1,
            conventional_time_to_stale_warning_seconds=1,
            conventional_time_to_delete_seconds=1,
            immutable_time_to_stale_seconds=1,
            immutable_time_to_stale_warning_seconds=1,
            immutable_time_to_delete_seconds=1,
        ),
    )
    write_batch_patch = mocker.patch("app.queue.host_mq.write_message_batch")

    fake_consumer = mocker.Mock(
        **{
            "consume.side_effect": [
                [FakeMessage(message=msg) for _ in range(5)],
                [FakeMessage(message=msg) for _ in range(3)],
                [FakeMessage(message=msg) for _ in range(4)],
                [],
                [],
                [],
                [],
            ]
        }
    )

    mock_notification_event_producer = mocker.Mock()
    message_handler = partial(handle_message, notification_event_producer=mock_notification_event_producer)

    event_loop(
        fake_consumer,
        flask_app.app,
        event_producer,
        mock_notification_event_producer,
        handler=message_handler,
        interrupt=mocker.Mock(side_effect=(False, False, False, True)),
    )

    # 12 messages were sent, but it should have only committed three times:
    # - Once after 7 messages (the batch size)
    # - Once after all messages have been produced
    # - Once after it tries to consume more messages but gets an empty array
    assert write_batch_patch.call_count == 3


def test_batch_mq_header_request_id_updates(mocker, flask_app):
    # Verifies that when messages are sent as part of the same batch,
    # the request_id used in the header is updated correctly.
    msg_list = []
    request_id_list = []
    for _ in range(5):
        metadata = get_platform_metadata()
        request_id = generate_uuid()
        metadata["request_id"] = request_id
        request_id_list.append(request_id)
        msg_list.append(
            json.dumps(
                wrap_message(
                    minimal_host().data(),
                    "add_host",
                    metadata,
                )
            )
        )

    # Patch batch settings in inventory_config()
    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(
            mq_db_batch_max_messages=7,
            mq_db_batch_max_seconds=1,
            culling_stale_warning_offset_delta=1,
            culling_culled_offset_delta=1,
            conventional_time_to_stale_seconds=1,
            conventional_time_to_stale_warning_seconds=1,
            conventional_time_to_delete_seconds=1,
            immutable_time_to_stale_seconds=1,
            immutable_time_to_stale_warning_seconds=1,
            immutable_time_to_delete_seconds=1,
        ),
    )

    fake_consumer = mocker.Mock(
        **{
            "consume.side_effect": [
                [FakeMessage(message=msg_list[i]) for i in range(5)],
                [],
                [],
                [],
                [],
            ]
        }
    )

    event_producer_mock = mocker.Mock()
    send_notification_patch = mocker.patch("app.queue.host_mq.send_notification")

    event_loop(
        fake_consumer,
        flask_app.app,
        event_producer_mock,
        mocker.Mock(),
        handler=handle_message,
        interrupt=mocker.Mock(side_effect=([False for _ in range(2)] + [True])),
    )

    # Should have been called once per host
    assert send_notification_patch.call_count == 5
    assert event_producer_mock.write_event.call_count == 5

    for i in range(5):
        headers = event_producer_mock.write_event.call_args_list[i][0][2]
        assert headers["request_id"] == request_id_list[i]


def test_batch_mq_graceful_rollback(mocker, flask_app):
    # Verifies that when the DB session runs into a StaleDataError, it's handled gracefully
    msg_list = []
    for _ in range(5):
        msg_list.append(json.dumps(wrap_message(minimal_host().data(), "add_host", get_platform_metadata())))

    # Patch batch settings in inventory_config()
    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(
            mq_db_batch_max_messages=3,
            mq_db_batch_max_seconds=1,
            culling_stale_warning_offset_delta=1,
            culling_culled_offset_delta=1,
            conventional_time_to_stale_seconds=1,
            conventional_time_to_stale_warning_seconds=1,
            conventional_time_to_delete_seconds=1,
            immutable_time_to_stale_seconds=1,
            immutable_time_to_stale_warning_seconds=1,
            immutable_time_to_delete_seconds=1,
        ),
    )

    # Make it so the commit raises a StaleDataError
    mocker.patch(
        "app.queue.host_mq.db.session.commit", side_effect=[StaleDataError("Stale data"), None, None, None, None, None]
    )
    write_batch_patch = mocker.patch("app.queue.host_mq.write_message_batch")

    fake_consumer = mocker.Mock(
        **{
            "consume.side_effect": [
                [FakeMessage(message=msg_list[i]) for i in range(3)],
                [FakeMessage(message=msg_list[i]) for i in range(3, 5)],
                [],
                [],
                [],
            ]
        }
    )
    event_producer_mock = mocker.Mock()

    event_loop(
        fake_consumer,
        flask_app.app,
        event_producer_mock,
        mocker.Mock(),
        handler=handle_message,
        interrupt=mocker.Mock(side_effect=([False for _ in range(2)] + [True])),
    )

    # Assert that the hosts that came in after the error were still processed
    # Since batch size is 3 and we're sending 5 messages,the first batch (3 messages) will get dropped,
    # but the second batch (2 messages) should have events produced.
    assert write_batch_patch.call_count == 1


@pytest.mark.usefixtures("flask_app")
@pytest.mark.parametrize("identity", (SYSTEM_IDENTITY,))
def test_add_host_logs(identity, mocker, caplog):
    caplog.at_level(logging.INFO)

    expected_insights_id = generate_uuid()
    host = minimal_host(account=identity["account_number"], insights_id=expected_insights_id)

    mock_notification_event_producer = mocker.Mock()

    message = wrap_message(host.data(), "add_host", get_platform_metadata(identity))
    result = handle_message(json.dumps(message), mock_notification_event_producer)

    assert result.event_type == EventType.created
    assert result.host_row.canonical_facts["insights_id"] == expected_insights_id
    assert caplog.records[0].input_host["system_profile"] == "{}"
    mock_notification_event_producer.write_event.assert_not_called()


@pytest.mark.parametrize("id_type", ("id", "insights_id", "fqdn"))
def test_log_update_system_profile(mq_create_or_update_host, db_get_host, id_type, caplog):
    caplog.at_level(logging.INFO)
    expected_ids = {"insights_id": generate_uuid(), "fqdn": "foo.test.redhat.com"}
    input_host = base_host(**expected_ids, system_profile={"owner_id": OWNER_ID, "number_of_cpus": 1})
    first_host_from_event = mq_create_or_update_host(input_host)
    first_host_from_db = db_get_host(first_host_from_event.id)
    expected_ids["id"] = str(first_host_from_db.id)

    assert str(first_host_from_db.canonical_facts["insights_id"]) == expected_ids["insights_id"]
    assert first_host_from_db.system_profile_facts.get("number_of_cpus") == 1

    input_host = base_host(
        **{id_type: expected_ids[id_type]}, system_profile={"number_of_cpus": 4, "number_of_sockets": 8}
    )
    input_host.stale_timestamp = None
    input_host.reporter = None
    second_host_from_event = mq_create_or_update_host(input_host, message_operation=update_system_profile)
    second_host_from_db = db_get_host(second_host_from_event.id)

    # The second host should have the same ID and insights ID,
    # and the system profile should have updated with the new values.
    assert str(second_host_from_db.id) == first_host_from_event.id
    assert str(second_host_from_db.canonical_facts["insights_id"]) == expected_ids["insights_id"]
    assert second_host_from_db.system_profile_facts == {
        "owner_id": OWNER_ID,
        "number_of_cpus": 4,
        "number_of_sockets": 8,
    }
    assert caplog.records[0].input_host["system_profile"] == "{}"


def test_add_host_subman_id(mq_create_or_update_host_subman_id, db_get_host):
    subscription_manager_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], subscription_manager_id=subscription_manager_id)

    mq_create_or_update_host_subman_id(host)

    record = db_get_host(subscription_manager_id)

    assert str(record.id) == str(subscription_manager_id)
