import json

import pytest

from app.exceptions import ValidationException
from tests.helpers.mq_utils import assert_system_registered_notification_is_valid
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host

OWNER_ID = SYSTEM_IDENTITY["system"]["cn"]


# New System Registered
def test_add_basic_host_success(mq_create_or_update_host, notification_event_producer_mock):
    # Tests notification production after adding a host

    expected_insights_id = generate_uuid()

    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
    )

    mq_create_or_update_host(host, return_all_data=True)
    assert_system_registered_notification_is_valid(notification_event_producer_mock, host)


def test_new_system_notification_fields(mq_create_or_update_host, notification_event_producer_mock):
    expected_insights_id = generate_uuid()

    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile={
            "operating_system": {"name": "RHEL", "major": 8, "minor": 6},
        },
    )

    mq_create_or_update_host(host, return_all_data=True)
    notification = json.loads(notification_event_producer_mock.event)
    assert_system_registered_notification_is_valid(notification_event_producer_mock, host)

    assert notification["context"]["rhel_version"] == "8.6"
    assert notification["org_id"] == SYSTEM_IDENTITY["org_id"]


@pytest.mark.parametrize(
    "sp_data",
    (
        {"owner_id": "Mike Wazowski"},
        None,
    ),
)
def test_add_host_fail(mq_create_or_update_host, notification_event_producer_mock, sp_data):
    # Test new system notification is not produced after add host fails

    host = minimal_host(org_id=SYSTEM_IDENTITY["org_id"], system_profile=sp_data)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=notification_event_producer_mock)

    # a host validation error notification should be produced instead
    event = json.loads(notification_event_producer_mock.event)

    assert event is not None
    assert event["event_type"] == "validation-error"


# System Became Stale

# System Deleted

# Host Validation Error
