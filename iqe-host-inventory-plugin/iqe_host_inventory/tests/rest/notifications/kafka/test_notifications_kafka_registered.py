from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostMessageWrapper
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.modeling.wrappers import KafkaMessageNotFoundError
from iqe_host_inventory.modeling.wrappers import RegisteredNotificationWrapper
from iqe_host_inventory.utils.api_utils import temp_headers
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.notifications_utils import check_registered_notifications_data
from iqe_host_inventory.utils.notifications_utils import check_registered_notifications_headers
from iqe_host_inventory.utils.notifications_utils import create_host_data_for_notification_tests

pytestmark = [pytest.mark.backend, pytest.mark.kafka]

logger = logging.getLogger(__name__)


def filter_notifications_by_hosts(
    notifications: list[RegisteredNotificationWrapper], hosts: list[HostWrapper]
) -> list[RegisteredNotificationWrapper]:
    hosts_ids = {host.id for host in hosts}
    return [notif for notif in notifications if notif.inventory_id in hosts_ids]


def find_host_and_notification_messages(
    host_inventory: ApplicationHostInventory, provider_ids: list[str]
) -> tuple[list[HostWrapper], list[RegisteredNotificationWrapper]]:
    """
    We can't use `create_hosts` to create the hosts (especially if we are creating multiple hosts),
    because it walks through kafka messages and finds the created/updated events for our hosts.
    When it does that, it can walk through the notifications as well, which means we are later not
    able to find these notifications, because they were already processed once. For this reason
    we have to be looking for the host events and notifications at the same time.
    """
    hosts = []
    notifications = []
    for msg in host_inventory.kafka.walk_messages():
        if isinstance(msg, HostMessageWrapper) and msg.host.provider_id in provider_ids:
            hosts.append(msg.host)
        elif isinstance(msg, RegisteredNotificationWrapper):
            notifications.append(msg)
        if len(hosts) == len(provider_ids):
            filtered_notifications = filter_notifications_by_hosts(notifications, hosts)
            if len(filtered_notifications) == len(hosts):
                return hosts, filtered_notifications
    raise KafkaMessageNotFoundError()


@pytest.fixture(scope="module")
def walk_all_messages(host_inventory: ApplicationHostInventory):
    """
    Something very strange is happening when we create the first host and start the first test.
    After creating the first host, our kafka consumer can't find the notification message, even
    though I verified it is correctly produced. We have to first walk through all the messages
    in the kafka topics to get to the end of it, and then we are able to correctly find all
    notifications. We can achieve walking through all the messages by creating a random host and
    then searching for the host event for that host.
    """
    host_inventory.kafka.create_host(timeout=30, cleanup_scope="module")


@pytest.fixture(params=[True, False], ids=["without request_id", "with request_id"])
def omit_request_id(request) -> bool:
    """
    Unfortunately, it's not possible to use @pytest.mark.parametrize on fixtures, so this is a
    workaround for that.
    """
    return request.param


@pytest.fixture(params=["minimal-rhel", "complete-rhel", "complete-centos"])
def prepare_host_for_registered_notification(
    request,
    host_inventory: ApplicationHostInventory,
    omit_request_id: bool,
    walk_all_messages,
) -> tuple[HostWrapper, str | None]:
    host_data = create_host_data_for_notification_tests(host_inventory, *request.param.split("-"))
    request_id = None if omit_request_id else generate_uuid()
    metadata = {} if omit_request_id else {"request_id": request_id}

    host = host_inventory.kafka.create_host(
        host_data=host_data,
        field_to_match=HostWrapper.provider_id,
        metadata=metadata,
        omit_request_id=omit_request_id,
    )
    return host, request_id


@pytest.mark.ephemeral
def test_notifications_kafka_registered(
    host_inventory: ApplicationHostInventory,
    prepare_host_for_registered_notification: tuple[HostWrapper, str | None],
):
    """
    https://issues.redhat.com/browse/RHINENG-7914

    metadata:
        requirements: inv-notifications-new-system-registered
        assignee: fstavela
        importance: high
        title: Creating a host triggers a new-system-registered notification
    """
    host, request_id = prepare_host_for_registered_notification

    msg = host_inventory.kafka.wait_for_filtered_registered_notification_message(
        RegisteredNotificationWrapper.inventory_id, host.id
    )
    logger.info(f"Received registered notification: {msg.value}")

    check_registered_notifications_data(msg, host, base_url="https://localhost")
    check_registered_notifications_headers(msg.headers, request_id)


@pytest.mark.ephemeral
def test_notifications_kafka_registered_multiple_hosts(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-7914

    metadata:
        requirements: inv-notifications-new-system-registered
        assignee: fstavela
        importance: high
        title: Creating multiple hosts triggers multiple new-system-registered notifications
    """
    hosts_data = host_inventory.datagen.create_n_complete_hosts_data(3)
    request_id = generate_uuid()
    host_inventory.kafka.produce_host_create_messages(
        hosts_data, metadata={"request_id": request_id}, flush=True
    )
    hosts, msgs = find_host_and_notification_messages(
        host_inventory, [host_data["provider_id"] for host_data in hosts_data]
    )
    host_inventory.apis.hosts.wait_for_created(hosts)

    assert len(msgs) == 3
    assert {msg.inventory_id for msg in msgs} == {host.id for host in hosts}

    hosts_by_ids = {host.id: host for host in hosts}
    for msg in msgs:
        check_registered_notifications_data(
            msg, hosts_by_ids[msg.inventory_id], base_url="https://localhost"
        )
        check_registered_notifications_headers(msg.headers, request_id)


@pytest.mark.ephemeral
def test_notifications_kafka_registered_update_dont_produce(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-7914

    metadata:
        requirements: inv-notifications-new-system-registered
        assignee: fstavela
        importance: high
        negative: true
        title: Updating a host doesn't trigger a new-system-registered notification
    """
    # Create a new host
    host_data = host_inventory.datagen.create_host_data()
    host = host_inventory.kafka.create_host(host_data=host_data)

    # Find the notification to make sure we won't later find the same message
    host_inventory.kafka.wait_for_filtered_registered_notification_message(
        RegisteredNotificationWrapper.inventory_id, host.id
    )

    # Update the host
    host_data["display_name"] = generate_display_name()
    host_inventory.kafka.create_host(host_data=host_data)
    host_inventory.apis.hosts.wait_for_updated(host, display_name=host_data["display_name"])

    # Make sure a registered notification wasn't produced
    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_registered_notification_message(
            RegisteredNotificationWrapper.inventory_id, host.id, timeout=3
        )


@pytest.mark.ephemeral
def test_notifications_kafka_registered_failed_dont_produce(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-7914

    metadata:
        requirements: inv-notifications-new-system-registered
        assignee: fstavela
        importance: high
        negative: true
        title: Unsuccessful host creation doesn't trigger a new-system-registered notification
    """
    # Attempt to create a host without org_id
    host_data = host_inventory.datagen.create_host_data()
    host_data.pop("org_id")
    host_inventory.kafka.produce_host_create_messages([host_data], flush=True)
    host_inventory.apis.hosts.verify_not_created(insights_id=host_data["insights_id"])

    # Make sure a registered notification wasn't produced
    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_registered_notification_message(
            RegisteredNotificationWrapper.insights_id, host_data["insights_id"], timeout=3
        )


@pytest.mark.ephemeral
def test_notifications_kafka_registered_patch_dont_produce(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-7914

    metadata:
        requirements: inv-notifications-new-system-registered
        assignee: fstavela
        importance: high
        negative: true
        title: Updating a host via API (PATCH) doesn't trigger a new-system-registered notification
    """
    # Create a new host
    host = host_inventory.kafka.create_host()

    # Find the notification to make sure we won't later find the same message
    host_inventory.kafka.wait_for_filtered_registered_notification_message(
        RegisteredNotificationWrapper.inventory_id, host.id
    )

    # Patch the host
    new_display_name = generate_display_name()
    host_inventory.apis.hosts.patch_hosts(host, display_name=new_display_name)
    host_inventory.apis.hosts.wait_for_updated(host, display_name=new_display_name)

    # Make sure a registered notification wasn't produced
    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_registered_notification_message(
            RegisteredNotificationWrapper.inventory_id, host.id, timeout=3
        )


@pytest.mark.ephemeral
def test_notifications_kafka_registered_create_group_dont_produce(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-7914

    metadata:
        requirements: inv-notifications-new-system-registered
        assignee: fstavela
        importance: high
        negative: true
        title: Creating a group doesn't trigger a new-system-registered notification
    """
    with temp_headers(
        host_inventory.apis.groups.raw_api, {"x-rh-insights-request-id": generate_uuid()}
    ):
        group = host_inventory.apis.groups.create_group(generate_display_name())

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_registered_notification_message(
            RegisteredNotificationWrapper.inventory_id, group.id, timeout=3
        )


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_notifications_kafka_registered_create_staleness_dont_produce(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-7914

    metadata:
        requirements: inv-notifications-new-system-registered
        assignee: fstavela
        importance: high
        negative: true
        title: Creating a staleness config doesn't trigger a new-system-registered notification
    """
    with temp_headers(
        host_inventory.apis.account_staleness.raw_api,
        {"x-rh-insights-request-id": generate_uuid()},
    ):
        staleness = host_inventory.apis.account_staleness.create_staleness(
            conventional_time_to_stale=1000
        )

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_registered_notification_message(
            RegisteredNotificationWrapper.inventory_id, staleness.id.actual_instance, timeout=3
        )
