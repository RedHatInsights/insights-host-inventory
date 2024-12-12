import json
from datetime import datetime
from datetime import timedelta
from unittest import mock
from unittest.mock import patch

import pytest

from app.exceptions import ValidationException
from app.logging import threadctx
from app.models import db
from stale_host_notification import run as run_stale_host_notification
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import assert_stale_notification_is_valid
from tests.helpers.mq_utils import assert_system_registered_notification_is_valid
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.test_custom_staleness import CUSTOM_STALENESS_HOST_BECAME_STALE

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


def test_add_host_fail(mq_create_or_update_host, notification_event_producer_mock):
    # Test new system notification is not produced after add host fails

    owner_id = "Mike Wazowski"
    host = minimal_host(org_id=SYSTEM_IDENTITY["org_id"], system_profile={"owner_id": owner_id})

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=notification_event_producer_mock)

    # a host validation error notification should be produced instead
    event = json.loads(notification_event_producer_mock.event)

    assert event is not None
    assert event["event_type"] == "validation-error"


# System Became Stale
def test_host_became_stale(
    notification_event_producer_mock,
    db_create_staleness_culling,
    flask_app,
    event_producer_mock,
    db_create_host,
    db_get_host,
    inventory_config,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    with patch("app.models.datetime") as models_datetime, patch("app.culling.datetime") as culling_datetime:
        models_datetime.now.return_value = datetime.now() - timedelta(minutes=5)
        culling_datetime.now.return_value = datetime.now()

        host = minimal_db_host(reporter="some reporter")
        created_host = db_create_host(host=host)
        assert db_get_host(created_host.id)

        threadctx.request_id = None
        run_stale_host_notification(
            inventory_config,
            mock.Mock(),
            db.session,
            event_producer=event_producer_mock,
            notification_event_producer=notification_event_producer_mock,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
            application=flask_app,
        )

        assert_stale_notification_is_valid(
            notification_event_producer=notification_event_producer_mock, host=created_host
        )


# System Deleted

# Host Validation Error
