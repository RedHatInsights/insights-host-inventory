import json
from collections.abc import Callable
from copy import deepcopy
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
from app.models import HostInventoryMetadata
from app.models import Staleness
from app.models import db
from jobs.generate_stale_host_notifications import run as run_stale_host_notification
from jobs.host_reaper import run as host_reaper_run
from tests.culling.test_custom_staleness import CUSTOM_STALENESS_HOST_BECAME_STALE
from tests.culling.test_custom_staleness import CUSTOM_STALENESS_NO_HOSTS_TO_DELETE
from tests.helpers.api_utils import STALENESS_URL
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import do_request
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import MockEventProducer
from tests.helpers.mq_utils import assert_stale_notification_is_valid
from tests.helpers.mq_utils import assert_system_registered_notification_is_valid
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host

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


@pytest.fixture
def notification_writes(notification_event_producer_mock, inventory_config, mocker):
    mocker.patch("app.queue.notifications.hostname", return_value="host-inventory-notification-test")
    mocker.patch.object(inventory_config, "base_ui_url", "https://localhost/insights/inventory")
    return notification_event_producer_mock.events


def _assert_notification_envelope(write, event_type, org_id, request_id):
    event = json.loads(write.event)
    assert set(event) == {"timestamp", "event_type", "org_id", "application", "bundle", "context", "events"}
    assert event["event_type"] == event_type
    assert event["org_id"] == org_id
    assert event["application"] == "inventory"
    assert event["bundle"] == "rhel"
    timestamp = datetime.fromisoformat(event["timestamp"])
    assert timestamp.utcoffset() == timedelta(0)
    assert abs((datetime.now(UTC) - timestamp).total_seconds()) < 10
    assert len(event["events"]) == 1
    assert set(event["events"][0]) == {"metadata", "payload"}
    assert event["events"][0]["metadata"] == {}
    assert isinstance(event["events"][0]["payload"], dict)
    headers = {
        "event_type": event_type,
        "producer": "host-inventory-notification-test",
        "rh-message-id": write.headers["rh-message-id"],
    }
    assert str(UUID(headers["rh-message-id"])) == headers["rh-message-id"]
    if request_id is not None:
        headers["request_id"] = request_id
    assert write.headers == headers
    assert write.key is None
    assert write.wait is True
    return event


def _notification_host_data(data_class):
    # Provider-only identity deliberately omits insights_id, profile, names, tags and other IDs.
    host = minimal_host(provider_id=generate_uuid(), provider_type="aws", reporter="puptoo")
    if data_class != "minimal":
        host.data().update(
            provider_type="azure" if data_class == "RHEL" else "gcp",
            insights_id=generate_uuid(),
            subscription_manager_id=generate_uuid(),
            satellite_id=generate_uuid(),
            fqdn=f"{data_class.lower().replace(' ', '-')}.example.com",
            display_name=f"notification-{data_class}",
            tags={"inventory": {"role": ["database", "web"], "unvalued": []}},
            system_profile={"operating_system": {"name": data_class, "major": 8, "minor": 6}},
        )
    return host


def _assert_host_notification(write, host, data_class, event_type, request_id):
    """Validate inventory notification values without using production serializers."""
    event = _assert_notification_envelope(write, event_type, host["org_id"], request_id)
    context = {
        "inventory_id": host["id"],
        "hostname": host.get("fqdn") or "",
        "display_name": host["display_name"],
        "rhel_version": "8.6" if data_class == "RHEL" else "",
        "tags": {} if data_class == "minimal" else {"inventory": {"role": ["database", "web"], "unvalued": []}},
    }
    if event_type != "system-deleted":
        context["host_url"] = f"https://localhost/insights/inventory/{host['id']}"
    assert event["context"] == context
    payload = {
        "insights_id": host.get("insights_id") or "",
        "subscription_manager_id": host.get("subscription_manager_id") or "",
        "satellite_id": host.get("satellite_id") or "",
        "groups": [{"id": group["id"], "name": group["name"]} for group in host["groups"]],
    }
    if event_type == "new-system-registered":
        payload.update(reporter="puptoo", system_check_in=host["created"])
    assert event["events"][0]["payload"] == payload


@pytest.mark.parametrize("with_request_id", [True, False], ids=["request-id", "no-request-id"])
def test_registered_notification_contracts(
    mq_create_or_update_host, db_get_host, notification_writes, with_request_id
):
    request_id = generate_uuid() if with_request_id else None
    metadata = get_platform_metadata()
    metadata.pop("request_id")
    if with_request_id:
        metadata["request_id"] = request_id
    hosts = {}
    for data_class in ("minimal", "RHEL", "CentOS Linux"):
        host_data = _notification_host_data(data_class)
        host = mq_create_or_update_host(host_data, platform_metadata=metadata).data()
        assert host["provider_id"] == host_data.provider_id
        assert host["provider_type"] == host_data.provider_type
        assert host["created"] == db_get_host(host["id"]).created_on.isoformat()
        if data_class == "minimal":
            assert host["insights_id"] == "00000000-0000-0000-0000-000000000000"
        else:
            for field in ("insights_id", "subscription_manager_id", "satellite_id", "display_name", "fqdn"):
                assert host[field] == host_data.data()[field]
        hosts[host["id"]] = (host, data_class)

    # Exact cardinality/type across ALL writes also excludes a preceding validation error.
    assert len(notification_writes) == 3
    assert {json.loads(write.event)["context"]["inventory_id"] for write in notification_writes} == set(hosts)
    assert len({write.headers["rh-message-id"] for write in notification_writes}) == 3
    for write in notification_writes:
        host, data_class = hosts[json.loads(write.event)["context"]["inventory_id"]]
        _assert_host_notification(write, host, data_class, "new-system-registered", request_id)


@pytest.mark.parametrize("endpoint", ["ids", "provider-filter", "all"])
@pytest.mark.parametrize(
    "grouped,with_request_id",
    [(True, True), (False, True), (False, False)],
    ids=["grouped-request-id", "ungrouped-request-id", "ungrouped-no-request-id"],
)
def test_deleted_notification_contracts(
    mq_create_or_update_host,
    db_create_group,
    api_add_hosts_to_group,
    db_get_host,
    api_delete_host,
    api_delete_filtered_hosts,
    api_delete_all_hosts,
    notification_writes,
    endpoint,
    grouped,
    with_request_id,
):
    request_id = generate_uuid() if with_request_id else None
    headers = {"x-rh-insights-request-id": request_id} if with_request_id else {}
    group = db_create_group("notification-group") if grouped else None
    hosts = {}
    for data_class in ("minimal", "RHEL", "CentOS Linux"):
        host = mq_create_or_update_host(_notification_host_data(data_class)).data()
        if group:
            host["groups"] = [{"id": str(group.id), "name": group.name}]
        hosts[host["id"]] = (host, data_class)
    if group:
        # Use the real move operation: MQ creation already assigned the ungrouped workspace.
        assert api_add_hosts_to_group(str(group.id), list(hosts))[0] == 200

    assert len(notification_writes) == 3  # Consume only the creation phase.
    notification_writes.clear()
    if endpoint == "ids":
        status, _ = api_delete_host(",".join(hosts), extra_headers=headers)
        assert status == 200
    elif endpoint == "all":
        status, body = api_delete_all_hosts({"confirm_delete_all": True}, extra_headers=headers)
        assert status == 202
        assert body["hosts_found"] == body["hosts_deleted"] == 3
    else:
        # A nonmatching provider remains present, so a broad/unfiltered delete cannot pass.
        survivor = mq_create_or_update_host(_notification_host_data("minimal"))
        notification_writes.clear()
        for host, _ in hosts.values():
            status, body = api_delete_filtered_hosts({"provider_id": host["provider_id"]}, extra_headers=headers)
            assert status == 202
            assert body["hosts_found"] == body["hosts_deleted"] == 1
        assert db_get_host(survivor.id) is not None

    assert len(notification_writes) == 3
    assert {json.loads(write.event)["context"]["inventory_id"] for write in notification_writes} == set(hosts)
    assert len({write.headers["rh-message-id"] for write in notification_writes}) == 3
    for write in notification_writes:
        host, data_class = hosts[json.loads(write.event)["context"]["inventory_id"]]
        _assert_host_notification(write, host, data_class, "system-deleted", request_id)
        assert db_get_host(host["id"]) is None


@pytest.mark.parametrize("existing_host", [False, True], ids=["create", "update"])
@pytest.mark.parametrize("with_request_id", [True, False], ids=["request-id", "no-request-id"])
def test_validation_error_notification_contracts(
    mq_create_or_update_host, notification_writes, existing_host, with_request_id
):
    # Batch the four non-mutating failures within one fixture lifecycle, rather than
    # multiplying DB setup by error kind/account presence.
    for error_kind in ("provider", "canonical", "profile", "identity"):
        host = minimal_host(
            insights_id=generate_uuid(),
            provider_id=generate_uuid(),
            provider_type="aws",
            display_name=f"invalid-{error_kind}",
            account=SYSTEM_IDENTITY["account_number"],
            system_profile={"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        )
        if existing_host:
            created = mq_create_or_update_host(host)
            assert created.display_name == host.display_name
            assert len(notification_writes) == 1
            assert json.loads(notification_writes[0].event)["event_type"] == "new-system-registered"
            notification_writes.clear()

        # Unlike the IQE datagen's False branch, this really tests omitted account.
        if error_kind in ("canonical", "identity"):
            del host.account
        identity = deepcopy(SYSTEM_IDENTITY)
        if error_kind == "provider":
            del host.provider_type
            reason_parts = ("provider_type", "provider_id", "both required")
        elif error_kind == "canonical":
            host.subscription_manager_id = "bad-uuid"
            reason_parts = ("subscription_manager_id", "bad-uuid", "invalid")
        elif error_kind == "profile":
            host.system_profile["rhc_client_id"] = "12345678-1234-1234-1234-123456"
            reason_parts = ("rhc_client_id", host.system_profile["rhc_client_id"], "match")
        else:
            identity["org_id"] = ""
            reason_parts = ("org_id", "identity", "does not match", "host")
        request_id = generate_uuid() if with_request_id else None
        metadata = get_platform_metadata(identity=identity)
        metadata.pop("request_id")
        if request_id is not None:
            metadata["request_id"] = request_id
        with pytest.raises(ValidationException):
            mq_create_or_update_host(host, platform_metadata=metadata)

        assert len(notification_writes) == 1
        event = _assert_notification_envelope(notification_writes[0], "validation-error", host.org_id, request_id)
        assert event["context"] == {"event_name": "Host Validation Error", "display_name": host.display_name}
        payload = event["events"][0]["payload"]
        assert set(payload) == {"request_id", "display_name", "canonical_facts", "error"}
        assert payload["display_name"] == host.display_name
        assert payload["request_id"] == request_id
        assert payload["canonical_facts"] == {
            field: host.data().get(field)
            for field in (
                "insights_id",
                "subscription_manager_id",
                "satellite_id",
                "bios_uuid",
                "ip_addresses",
                "fqdn",
                "mac_addresses",
                "provider_id",
                "provider_type",
            )
        }
        error = payload["error"]
        assert set(error) == {"code", "message", "stack_trace", "severity"}
        assert error["code"] == "VE001"
        assert error["stack_trace"] is None
        assert error["severity"] == "error"
        for part in reason_parts:
            assert part.lower() in error["message"].lower()
        if not existing_host:
            assert db.session.query(Host).filter_by(insights_id=UUID(host.insights_id)).count() == 0
        notification_writes.clear()


def test_failed_registration_emits_only_validation_error(mq_create_or_update_host, notification_writes):
    host = minimal_host(insights_id=generate_uuid(), display_name="missing-org")
    del host.org_id
    with pytest.raises(ValidationException):
        mq_create_or_update_host(host)
    assert db.session.query(Host).filter_by(insights_id=UUID(host.insights_id)).count() == 0
    assert len(notification_writes) == 1
    event = json.loads(notification_writes[0].event)
    assert event["event_type"] == "validation-error"
    assert event["events"][0]["payload"]["canonical_facts"]["insights_id"] == host.insights_id
    assert "org_id" in event["events"][0]["payload"]["error"]["message"]


def test_non_host_mutations_do_not_emit_notifications(
    mq_create_or_update_host,
    notification_writes,
    api_get,
    api_patch,
    api_delete_host,
    api_delete_filtered_hosts,
    api_create_group,
    api_add_hosts_to_group,
    api_delete_groups,
    api_create_staleness,
    flask_client,
    db_get_host,
    db_get_staleness_culling,
    db_get_group_by_id,
):
    host_data = minimal_host(insights_id=generate_uuid(), display_name="notification-phases")
    host = mq_create_or_update_host(host_data)
    assert len(notification_writes) == 1
    assert json.loads(notification_writes[0].event)["event_type"] == "new-system-registered"
    notification_writes.clear()
    headers = {"x-rh-insights-request-id": generate_uuid()}

    host_data.display_name = "mq-updated"
    updated = mq_create_or_update_host(host_data)
    assert updated.id == host.id
    assert db_get_host(host.id).display_name == "mq-updated"
    assert notification_writes == []

    status, body = api_get(build_hosts_url(host.id), extra_headers=headers)
    assert status == 200
    assert body["results"][0]["id"] == host.id
    assert notification_writes == []

    status, _ = api_patch(build_hosts_url(host.id), {"display_name": "api-updated"}, extra_headers=headers)
    assert status == 200
    assert db_get_host(host.id).display_name == "api-updated"
    assert notification_writes == []

    missing_id = generate_uuid()
    status, body = api_delete_host(missing_id, extra_headers=headers)
    assert status == 404
    assert "hosts not found" in body["detail"]
    assert notification_writes == []
    status, body = api_delete_filtered_hosts({"insights_id": generate_uuid()}, extra_headers=headers)
    assert status == 202
    assert body["hosts_found"] == body["hosts_deleted"] == 0
    assert db_get_host(host.id) is not None
    assert notification_writes == []

    status, group = api_create_group({"name": "notification-silence"}, extra_headers=headers)
    assert status == 201
    assert db_get_group_by_id(group["id"]) is not None
    assert notification_writes == []
    status, _ = api_add_hosts_to_group(group["id"], [host.id], extra_headers=headers)
    assert status == 200
    assert [member_group["id"] for member_group in db_get_host(host.id).groups] == [group["id"]]
    assert notification_writes == []
    status, _ = api_delete_groups([group["id"]], extra_headers=headers)
    assert status == 204
    assert db_get_group_by_id(group["id"]) is None
    assert db_get_host(host.id) is not None
    assert notification_writes == []

    status, staleness = api_create_staleness({"conventional_time_to_stale": 1000}, extra_headers=headers)
    assert status == 201
    assert staleness["id"]
    assert db_get_staleness_culling(host.org_id) is not None
    assert notification_writes == []
    # The existing delete fixture has no extra_headers argument; use its same in-process client.
    status, _ = do_request(flask_client.delete, STALENESS_URL, USER_IDENTITY, extra_headers=headers)
    assert status == 204
    assert db_get_staleness_culling(host.org_id) is None
    assert db_get_host(host.id) is not None
    assert notification_writes == []


@pytest.mark.parametrize("data_class", ["minimal", "RHEL", "CentOS Linux"])
def test_stale_refresh_notification_cycle(
    mq_create_or_update_host,
    notification_event_producer_mock,
    notification_writes,
    db_get_host,
    api_get,
    api_create_staleness,
    flask_client,
    flask_app,
    data_class,
):
    start = datetime.now(UTC)
    short_staleness = {
        "conventional_time_to_stale": 5,
        "conventional_time_to_stale_warning": 3600,
        "conventional_time_to_delete": 7200,
    }
    assert api_create_staleness(short_staleness)[0] == 201
    host_data = _notification_host_data(data_class)
    with patch("app.models.utils.datetime", wraps=datetime) as clock:
        clock.now.return_value = start - timedelta(seconds=30)
        host = mq_create_or_update_host(host_data).data()
        assert len(notification_writes) == 1
        notification_writes.clear()
        first_check_in = db_get_host(host["id"]).last_check_in
        first_run = start
        status, body = api_get(build_hosts_url(host["id"]))
        assert status == 200
        assert datetime.fromisoformat(body["results"][0]["stale_timestamp"]) <= first_run
        assert datetime.fromisoformat(body["results"][0]["stale_warning_timestamp"]) > first_run
        threadctx.request_id = None
        run_stale_host_notification(mock.Mock(), db.session, notification_event_producer_mock, flask_app, first_run)
        assert len(notification_writes) == 1
        _assert_host_notification(notification_writes[0], host, data_class, "system-became-stale", None)
        assert db.session.get(HostInventoryMetadata, ("stale_host_notification", "job")).last_succeeded == first_run
        notification_writes.clear()

        # Refresh the SAME host, preserving the job watermark and original created timestamp.
        refresh_time = start + timedelta(seconds=10)
        clock.now.return_value = refresh_time
        refreshed = mq_create_or_update_host(host_data).data()
        assert refreshed["id"] == host["id"]
        assert refreshed["created"] == host["created"]
        assert db_get_host(host["id"]).last_check_in == refresh_time > first_check_in
        assert notification_writes == []
        assert do_request(flask_client.delete, STALENESS_URL, USER_IDENTITY)[0] == 204
        status, body = api_get(build_hosts_url(host["id"]))
        assert status == 200
        fresh_job_time = refresh_time + timedelta(seconds=1)
        assert datetime.fromisoformat(body["results"][0]["stale_timestamp"]) > fresh_job_time
        threadctx.request_id = None
        run_stale_host_notification(
            mock.Mock(), db.session, notification_event_producer_mock, flask_app, fresh_job_time
        )
        assert notification_writes == []
        assert db.session.get(HostInventoryMetadata, ("stale_host_notification", "job")).last_succeeded == first_run

        assert api_create_staleness(short_staleness)[0] == 201
        later_run = refresh_time + timedelta(seconds=10)
        assert db_get_host(host["id"]).last_check_in + timedelta(seconds=5) < later_run
        clock.now.return_value = later_run
        threadctx.request_id = None
        run_stale_host_notification(mock.Mock(), db.session, notification_event_producer_mock, flask_app, later_run)
        assert len(notification_writes) == 1
        _assert_host_notification(notification_writes[0], refreshed, data_class, "system-became-stale", None)
        assert db.session.get(HostInventoryMetadata, ("stale_host_notification", "job")).last_succeeded == later_run
        notification_writes.clear()
        # Still stale is not a new transition, including after a successful refresh cycle.
        run_stale_host_notification(
            mock.Mock(), db.session, notification_event_producer_mock, flask_app, later_run + timedelta(seconds=1)
        )
        assert notification_writes == []
