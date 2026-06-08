from __future__ import annotations

import json
from copy import deepcopy

import pytest

from app.exceptions import ValidationException
from app.queue.host_mq import IngressMessageConsumer
from app.queue.host_mq import write_add_update_event_message
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_encoded_idstr
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import valid_system_profile

OWNER_ID = SYSTEM_IDENTITY["system"]["cn"]


# --- Positive: system identity with correct owner_id ---


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_owner_id(mq_create_or_update_host, db_get_host):
    """
    Tests that owner_id in the system profile is ingested properly
    """
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile={"owner_id": OWNER_ID})
    created_host_from_event = mq_create_or_update_host(host)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert str(created_host_from_db.static_system_profile.owner_id) == OWNER_ID


# --- Positive: RHSM reporter ---


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

    assert event["host"]["system_profile"]["owner_id"] == "09152341-475c-4671-a376-df609374c349"


@pytest.mark.usefixtures("flask_app")
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_reporter_and_no_platform_metadata(rhsm_reporter, ingress_message_consumer_mock):
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=generate_uuid(),
        reporter=rhsm_reporter,
        subscription_manager_id=OWNER_ID,
    )

    message = wrap_message(host.data(), "add_host")

    ingress_message_consumer_mock.handle_message(json.dumps(message))


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_reporter_and_no_identity(mocker, rhsm_reporter):
    expected_insights_id = generate_uuid()
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

    consumer = IngressMessageConsumer(
        mocker.Mock(), mocker.Mock(), mock_event_producer, mock_notification_event_producer
    )

    result = consumer.handle_message(json.dumps(message))
    write_add_update_event_message(mock_event_producer, mock_notification_event_producer, result)

    mock_event_producer.write_event.assert_called_once()
    mock_notification_event_producer.assert_not_called()


# --- Negative: wrong owner_id / wrong CN ---


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
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    with pytest.raises(ValidationException) as ve:
        consumer.handle_message(json.dumps(message))

    assert ve.value.detail == "The owner in host does not match the owner in identity"
    mock_notification_event_producer.write_event.assert_called_once()


# --- Negative: owner_id format ---


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


# --- Negative: no identity / no metadata ---


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
def test_no_identity_and_no_rhsm_reporter(mocker):
    expected_insights_id = generate_uuid()
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=expected_insights_id)

    platform_metadata = get_platform_metadata()
    platform_metadata.pop("b64_identity")

    message = wrap_message(host.data(), "add_host", platform_metadata)
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    with pytest.raises(ValidationException):
        consumer.handle_message(json.dumps(message))
    mock_notification_event_producer.write_event.assert_called()


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
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)
    with pytest.raises(ValidationException):
        consumer.handle_message(json.dumps(message))
    mock_notification_event_producer.write_event.assert_called()


# --- Negative: invalid identity ---


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
