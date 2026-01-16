import json
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Any
from unittest import mock
from unittest.mock import patch
from uuid import UUID

import pytest
from connexion import FlaskApp

from app.config import Config
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.exceptions import ValidationException
from app.logging import threadctx
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.models import Staleness
from app.models import db
from jobs.generate_stale_host_notifications import run as run_stale_host_notification
from jobs.host_reaper import run as host_reaper_run
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import MockEventProducer
from tests.helpers.mq_utils import assert_stale_notification_is_valid
from tests.helpers.mq_utils import assert_system_registered_notification_is_valid
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.test_custom_staleness import CUSTOM_STALENESS_HOST_BECAME_STALE
from tests.test_custom_staleness import CUSTOM_STALENESS_NO_HOSTS_TO_DELETE

OWNER_ID = SYSTEM_IDENTITY["system"]["cn"]

# Custom staleness configurations for testing
# Makes hosts stale in 1 second and stale_warning after 2 seconds
CUSTOM_STALENESS_STALE_WARNING = {
    "conventional_time_to_stale": 1,
    "conventional_time_to_stale_warning": 2,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
}


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
def test_host_did_not_became_stale(
    notification_event_producer_mock: MockEventProducer,
    db_create_staleness_culling: Callable[..., Staleness],
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID | str], Host | None],
) -> None:
    db_create_staleness_culling(**CUSTOM_STALENESS_NO_HOSTS_TO_DELETE)

    with patch("app.models.utils.datetime") as models_datetime:
        job_start_time = datetime.now(UTC)
        models_datetime.now.return_value = job_start_time - timedelta(minutes=5)

        host = minimal_db_host(reporter="some reporter")
        created_host = db_create_host(host=host)
        assert db_get_host(created_host.id)

        threadctx.request_id = None
        run_stale_host_notification(
            mock.Mock(),
            db.session,
            notification_event_producer=notification_event_producer_mock,
            application=flask_app,
            job_start_time=job_start_time,
        )

        assert notification_event_producer_mock.event is None


@pytest.mark.parametrize("host_data_type", ["minimal", "complete"])
@pytest.mark.parametrize("os_name", ["RHEL", "CentOS Linux"])
@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.parametrize("grouped", [True, False], ids=["grouped", "ungrouped"])
def test_host_became_stale(
    notification_event_producer_mock: MockEventProducer,
    db_create_staleness_culling: Callable[..., Staleness],
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID | str], Host | None],
    db_create_group: Callable[..., Group],
    db_create_host_group_assoc: Callable[..., HostGroupAssoc],
    host_data_type: str,
    os_name: str,
    host_type: str,
    grouped: bool,
) -> None:
    """
    Tests that newly stale hosts trigger a system-became-stale notification.
    Parametrized for:
    - grouped/ungrouped: whether the host is in a group
    - host_type: "conventional" or "edge"
    - host_data_type: "minimal" (only required fields) or "complete" (all notification fields)
    - os_name: operating_system.name value
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    with patch("app.models.utils.datetime") as models_datetime:
        job_start_time = datetime.now(UTC)
        # Create host 5 minutes before job_start_time so it will be stale
        models_datetime.now.return_value = job_start_time - timedelta(minutes=5)

        if host_data_type == "minimal":
            # Minimal host: only required fields (insights_id is auto-generated)
            system_profile: dict[str, Any] = {"host_type": host_type} if host_type == "edge" else {}
            host = minimal_db_host(reporter="puptoo", system_profile_facts=system_profile)
        else:
            # Complete host: all fields that appear in the notification
            # Context fields: hostname (fqdn), display_name, rhel_version (operating_system), tags
            # Payload fields: insights_id, subscription_manager_id, satellite_id, groups
            system_profile = {"operating_system": {"name": os_name, "major": 8, "minor": 6}}
            if host_type == "edge":
                system_profile["host_type"] = "edge"
            host = minimal_db_host(
                reporter="puptoo",
                display_name="complete-test-host",
                insights_id=generate_uuid(),
                subscription_manager_id=generate_uuid(),
                satellite_id=generate_uuid(),
                fqdn="complete-host.example.com",
                tags={"namespace": {"key": ["value1", "value2"]}},
                system_profile_facts=system_profile,
            )

        created_host = db_create_host(host=host)
        assert db_get_host(created_host.id)

        if grouped:
            group = db_create_group("test_group")
            db_create_host_group_assoc(created_host.id, group.id)

        threadctx.request_id = None
        run_stale_host_notification(
            mock.Mock(),
            db.session,
            notification_event_producer=notification_event_producer_mock,
            application=flask_app,
            job_start_time=job_start_time,
        )

        # assert_stale_notification_is_valid validates all notification fields against host data
        assert_stale_notification_is_valid(
            notification_event_producer=notification_event_producer_mock,
            host=created_host,
        )


def test_host_stale_warning_triggers_notification(
    notification_event_producer_mock: MockEventProducer,
    db_create_staleness_culling: Callable[..., Staleness],
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID | str], Host | None],
) -> None:
    """
    Test that a host in stale_warning triggers a notification as long as one
    wasn't triggered when the host became stale.
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_STALE_WARNING)

    with patch("app.models.utils.datetime") as models_datetime:
        job_start_time = datetime.now(UTC)
        models_datetime.now.return_value = job_start_time - timedelta(minutes=5)

        host = minimal_db_host(reporter="puptoo")
        created_host = db_create_host(host=host)
        assert db_get_host(created_host.id)

        threadctx.request_id = None
        run_stale_host_notification(
            mock.Mock(),
            db.session,
            notification_event_producer=notification_event_producer_mock,
            application=flask_app,
            job_start_time=job_start_time,
        )

        # Host in stale_warning should trigger notification
        assert_stale_notification_is_valid(
            notification_event_producer=notification_event_producer_mock, host=created_host
        )


@pytest.mark.usefixtures("notification_event_producer_mock")
def test_multiple_hosts_became_stale(
    db_create_staleness_culling: Callable[..., Staleness],
    flask_app: FlaskApp,
    db_create_multiple_hosts: Callable[..., list[Host]],
) -> None:
    """
    Test that one stale host notification per host is triggered when multiple
    hosts become stale.
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    with patch("app.models.utils.datetime") as models_datetime:
        job_start_time = datetime.now(UTC)
        models_datetime.now.return_value = job_start_time - timedelta(minutes=5)

        created_hosts = db_create_multiple_hosts(how_many=3, extra_data={"reporter": "puptoo"})

        # Collect all notifications by running the job multiple times
        # The MockEventProducer only keeps the last event, so we need a different approach
        # We'll check that the job processes all hosts by mocking the producer differently
        class NotificationCollector:
            def __init__(self):
                self.events = []
                self.event = None
                self.key = None
                self.headers = None
                self.topic = None
                self.wait = None
                self._kafka_producer = mock.Mock()
                self._kafka_producer.flush = mock.Mock(return_value=True)

            def write_event(self, event, key, headers, wait=False):
                self.event = event
                self.key = key
                self.headers = headers
                self.wait = wait
                self.events.append(json.loads(event))

        collector = NotificationCollector()

        threadctx.request_id = None
        run_stale_host_notification(
            mock.Mock(),
            db.session,
            notification_event_producer=collector,
            application=flask_app,
            job_start_time=job_start_time,
        )

        # Verify 3 notifications were sent
        assert len(collector.events) == 3

        # Verify each host got its own notification
        notified_host_ids = {event["context"]["inventory_id"] for event in collector.events}
        created_host_ids = {str(host.id) for host in created_hosts}
        assert notified_host_ids == created_host_ids


def test_host_stale_retrigger(
    notification_event_producer_mock: MockEventProducer,
    db_create_staleness_culling: Callable[..., Staleness],
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID | str], Host | None],
) -> None:
    """
    Verify that a stale notification is only triggered once per stale transition.
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    with patch("app.models.utils.datetime") as models_datetime:
        job_start_time = datetime.now(UTC)
        models_datetime.now.return_value = job_start_time - timedelta(minutes=5)

        host = minimal_db_host(reporter="puptoo")
        created_host = db_create_host(host=host)
        assert db_get_host(created_host.id)

        threadctx.request_id = None

        # First run - should trigger notification
        run_stale_host_notification(
            mock.Mock(),
            db.session,
            notification_event_producer=notification_event_producer_mock,
            application=flask_app,
            job_start_time=job_start_time,
        )

        assert_stale_notification_is_valid(
            notification_event_producer=notification_event_producer_mock, host=created_host
        )

        # Reset mock
        notification_event_producer_mock.event = None

        # Second run with same host still stale - should NOT trigger
        run_stale_host_notification(
            mock.Mock(),
            db.session,
            notification_event_producer=notification_event_producer_mock,
            application=flask_app,
            job_start_time=job_start_time + timedelta(minutes=1),
        )

        # No notification on retrigger
        assert notification_event_producer_mock.event is None


def test_host_stale_to_stale_warning_no_notification(
    notification_event_producer_mock: MockEventProducer,
    db_create_staleness_culling: Callable[..., Staleness],
    db_delete_staleness_culling: Callable[[str], None],
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID | str], Host | None],
) -> None:
    """
    Test that a notification isn't triggered when a host transitions from
    stale to stale_warning.
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    with patch("app.models.utils.datetime") as models_datetime:
        job_start_time = datetime.now(UTC)
        models_datetime.now.return_value = job_start_time - timedelta(minutes=5)

        host = minimal_db_host(reporter="puptoo")
        created_host = db_create_host(host=host)
        assert db_get_host(created_host.id)

        threadctx.request_id = None

        # First run - host goes stale, triggers notification
        run_stale_host_notification(
            mock.Mock(),
            db.session,
            notification_event_producer=notification_event_producer_mock,
            application=flask_app,
            job_start_time=job_start_time,
        )

        assert_stale_notification_is_valid(
            notification_event_producer=notification_event_producer_mock, host=created_host
        )

        # Reset mock
        notification_event_producer_mock.event = None

        # Delete old staleness and create new one with shorter warning period
        # This simulates the host moving from stale to stale_warning
        db_delete_staleness_culling(SYSTEM_IDENTITY["org_id"])
        db_create_staleness_culling(**CUSTOM_STALENESS_STALE_WARNING)

        # The host was already notified, shouldn't get another notification
        run_stale_host_notification(
            mock.Mock(),
            db.session,
            notification_event_producer=notification_event_producer_mock,
            application=flask_app,
            job_start_time=job_start_time + timedelta(minutes=1),
        )

        # No notification for stale -> stale_warning transition
        assert notification_event_producer_mock.event is None


@pytest.mark.parametrize("host_type", ["conventional", "edge"])
def test_create_host_does_not_trigger_stale_notification(
    mq_create_or_update_host: Callable[..., Any],
    notification_event_producer_mock: MockEventProducer,
    flask_app: FlaskApp,
    host_type: str,
) -> None:
    """
    Verify that a freshly created host doesn't trigger a stale notification.
    """
    system_profile = {"host_type": host_type} if host_type == "edge" else {}
    host = minimal_host(system_profile=system_profile)

    mq_create_or_update_host(host)

    # Host creation triggers new-system-registered
    event = json.loads(notification_event_producer_mock.event)
    assert event["event_type"] == "new-system-registered"

    # Reset the mock to check stale notification job
    notification_event_producer_mock.event = None

    # Run stale notification job - fresh host should not trigger stale notification
    threadctx.request_id = None
    run_stale_host_notification(
        mock.Mock(),
        db.session,
        notification_event_producer=notification_event_producer_mock,
        application=flask_app,
        job_start_time=datetime.now(UTC),
    )

    # No stale notification for fresh host
    assert notification_event_producer_mock.event is None


@pytest.mark.usefixtures("event_producer_mock")
@pytest.mark.parametrize("host_type", ["conventional", "edge"])
def test_delete_host_does_not_trigger_stale_notification(
    notification_event_producer_mock: MockEventProducer,
    db_create_staleness_culling: Callable[..., Staleness],
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID | str], Host | None],
    api_delete_host: Callable[..., tuple[int, dict]],
    flask_app: FlaskApp,
    host_type: str,
) -> None:
    """
    Verify that a deleted host doesn't trigger a stale notification.
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    with patch("app.models.utils.datetime") as models_datetime:
        job_start_time = datetime.now(UTC)
        # Create host in the past so it would be stale
        models_datetime.now.return_value = job_start_time - timedelta(minutes=5)

        system_profile_facts = {"host_type": host_type} if host_type == "edge" else {}
        host = minimal_db_host(reporter="puptoo", system_profile_facts=system_profile_facts)
        created_host = db_create_host(host=host)
        assert db_get_host(created_host.id)

    # Delete the host manually via API
    api_delete_host(str(created_host.id))

    # Host deletion triggers system-deleted
    event = json.loads(notification_event_producer_mock.event)
    assert event["event_type"] == "system-deleted"

    # Reset the mock to check stale notification job
    notification_event_producer_mock.event = None

    # Run stale notification job - deleted host should not trigger stale notification
    threadctx.request_id = None
    run_stale_host_notification(
        mock.Mock(),
        db.session,
        notification_event_producer=notification_event_producer_mock,
        application=flask_app,
        job_start_time=datetime.now(UTC),
    )

    # No stale notification for deleted host
    assert notification_event_producer_mock.event is None


@pytest.mark.parametrize("host_type", ["conventional", "edge"])
def test_reaper_delete_does_not_trigger_stale_notification(
    notification_event_producer_mock: MockEventProducer,
    event_producer_mock: MockEventProducer,
    db_create_staleness_culling: Callable[..., Staleness],
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID | str], Host | None],
    inventory_config: Config,
    host_type: str,
) -> None:
    """
    Verify that a host deleted by the reaper doesn't trigger a stale notification.
    """
    # Use a staleness config that makes hosts culled quickly
    db_create_staleness_culling(
        conventional_time_to_stale=1,
        conventional_time_to_stale_warning=2,
        conventional_time_to_delete=3,
    )

    with patch("app.models.utils.datetime") as models_datetime:
        # Create host in the past so it's culled
        culled_time = datetime.now(UTC) - timedelta(minutes=5)
        models_datetime.now.return_value = culled_time
        models_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        system_profile_facts = {"host_type": host_type} if host_type == "edge" else {}
        host = minimal_db_host(reporter="puptoo", system_profile_facts=system_profile_facts)
        created_host = db_create_host(host=host)
        assert db_get_host(created_host.id)

    # Run the reaper to delete the culled host
    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer=event_producer_mock,
        notification_event_producer=notification_event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        application=flask_app,
    )

    # Host should be deleted
    assert not db_get_host(created_host.id)

    # Host deletion triggers system-deleted
    event = json.loads(notification_event_producer_mock.event)
    assert event["event_type"] == "system-deleted"

    # Reset the mock to check stale notification job
    notification_event_producer_mock.event = None

    # Run stale notification job - deleted host should not trigger stale notification
    run_stale_host_notification(
        mock.Mock(),
        db.session,
        notification_event_producer=notification_event_producer_mock,
        application=flask_app,
        job_start_time=datetime.now(UTC),
    )

    # No stale notification for deleted host
    assert notification_event_producer_mock.event is None


# System Deleted

# Host Validation Error
