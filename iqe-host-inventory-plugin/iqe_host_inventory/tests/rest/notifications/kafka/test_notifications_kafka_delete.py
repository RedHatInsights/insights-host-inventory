from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import DeleteNotificationWrapper
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.modeling.wrappers import KafkaMessageNotFoundError
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.api_utils import temp_headers
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.notifications_utils import check_delete_notifications_data
from iqe_host_inventory.utils.notifications_utils import check_delete_notifications_headers
from iqe_host_inventory.utils.notifications_utils import create_host_data_for_notification_tests

pytestmark = [pytest.mark.backend, pytest.mark.kafka]

logger = logging.getLogger(__name__)


@pytest.fixture(params=["minimal-rhel", "complete-rhel", "complete-centos"])
def prepare_host_for_delete_notification(
    request, host_inventory: ApplicationHostInventory
) -> HostWrapper:
    host_data = create_host_data_for_notification_tests(host_inventory, *request.param.split("-"))
    return host_inventory.kafka.create_host(
        host_data=host_data,
        field_to_match=HostWrapper.provider_id,
    )


@pytest.fixture(scope="module")
def prepare_host_for_negative_test(host_inventory: ApplicationHostInventory) -> HostWrapper:
    return host_inventory.kafka.create_host(cleanup_scope="module")


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "grouped, with_request_id",
    [(True, True), (False, True), (False, False)],
    ids=["grouped with request_id", "ungrouped with request_id", "ungrouped without request_id"],
)
def test_notifications_kafka_delete_by_id(
    host_inventory: ApplicationHostInventory,
    prepare_host_for_delete_notification: HostWrapper,
    grouped: bool,
    with_request_id: bool,
):
    """
    https://issues.redhat.com/browse/RHINENG-7911

    metadata:
        requirements: inv-notifications-system-deleted
        assignee: fstavela
        importance: high
        title: Deleting hosts via DELETE /hosts/<hosts_ids> endpoint triggers a delete notification
    """
    host = prepare_host_for_delete_notification
    group = (
        host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)
        if grouped
        else None
    )

    request_id = generate_uuid() if with_request_id else None
    new_headers = {"x-rh-insights-request-id": request_id} if with_request_id else None
    with temp_headers(host_inventory.apis.hosts.raw_api, new_headers):
        host_inventory.apis.hosts.delete_by_id_raw(host)

    msg = host_inventory.kafka.wait_for_filtered_delete_notification_message(
        DeleteNotificationWrapper.inventory_id, host.id
    )
    logger.info(f"Received delete notification: {msg.value}")

    check_delete_notifications_data(msg, host, group)
    check_delete_notifications_headers(msg.headers, request_id)

    host_inventory.apis.hosts.wait_for_deleted(host)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "grouped, with_request_id",
    [(True, True), (False, True), (False, False)],
    ids=["grouped with request_id", "ungrouped with request_id", "ungrouped without request_id"],
)
def test_notifications_kafka_delete_filtered(
    host_inventory: ApplicationHostInventory,
    prepare_host_for_delete_notification: HostWrapper,
    grouped: bool,
    with_request_id: bool,
):
    """
    https://issues.redhat.com/browse/RHINENG-7911

    metadata:
        requirements: inv-notifications-system-deleted
        assignee: fstavela
        importance: high
        title: Deleting hosts via DELETE /hosts endpoint triggers a system-delete notification
    """
    host = prepare_host_for_delete_notification
    group = (
        host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)
        if grouped
        else None
    )

    request_id = generate_uuid() if with_request_id else None
    new_headers = {"x-rh-insights-request-id": request_id} if with_request_id else None
    with temp_headers(host_inventory.apis.hosts.raw_api, new_headers):
        host_inventory.apis.hosts.delete_filtered(provider_id=host.provider_id)

    msg = host_inventory.kafka.wait_for_filtered_delete_notification_message(
        DeleteNotificationWrapper.inventory_id, host.id
    )

    check_delete_notifications_data(msg, host, group)
    check_delete_notifications_headers(msg.headers, request_id)

    host_inventory.apis.hosts.wait_for_deleted(host)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "grouped, with_request_id",
    [(True, True), (False, True), (False, False)],
    ids=["grouped with request_id", "ungrouped with request_id", "ungrouped without request_id"],
)
def test_notifications_kafka_delete_all(
    host_inventory: ApplicationHostInventory,
    prepare_host_for_delete_notification: HostWrapper,
    grouped: bool,
    with_request_id: bool,
):
    """
    https://issues.redhat.com/browse/RHINENG-7911

    metadata:
        requirements: inv-notifications-system-deleted
        assignee: fstavela
        importance: high
        title: Deleting hosts via DELETE /hosts/all endpoint triggers a system-delete notification
    """
    host = prepare_host_for_delete_notification
    group = (
        host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)
        if grouped
        else None
    )

    request_id = generate_uuid() if with_request_id else None
    new_headers = {"x-rh-insights-request-id": request_id} if with_request_id else None
    with temp_headers(host_inventory.apis.hosts.raw_api, new_headers):
        host_inventory.apis.hosts.confirm_delete_all()

    msg = host_inventory.kafka.wait_for_filtered_delete_notification_message(
        DeleteNotificationWrapper.inventory_id, host.id
    )

    check_delete_notifications_data(msg, host, group)
    check_delete_notifications_headers(msg.headers, request_id)

    host_inventory.apis.hosts.wait_for_deleted(host)


@pytest.mark.ephemeral
def test_notifications_kafka_delete_multiple_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-7911

    metadata:
        requirements: inv-notifications-system-deleted
        assignee: fstavela
        importance: high
        title: Deleting multiple hosts triggers multiple system-delete notifications
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    request_id = generate_uuid()
    new_headers = {"x-rh-insights-request-id": request_id}
    with temp_headers(host_inventory.apis.hosts.raw_api, new_headers):
        host_inventory.apis.hosts.delete_by_id(hosts, wait_for_deleted=False)

    msgs = host_inventory.kafka.wait_for_filtered_delete_notification_messages(
        DeleteNotificationWrapper.inventory_id, [host.id for host in hosts]
    )
    assert len(msgs) == 3
    assert {msg.inventory_id for msg in msgs} == {host.id for host in hosts}

    hosts_by_ids = {host.id: host for host in hosts}
    for msg in msgs:
        check_delete_notifications_data(msg, hosts_by_ids[msg.inventory_id])
        check_delete_notifications_headers(msg.headers, request_id)

    host_inventory.apis.hosts.wait_for_deleted(hosts)


@pytest.mark.ephemeral
def test_notifications_kafka_delete_by_id_dont_produce(
    host_inventory: ApplicationHostInventory, is_kessel_phase_1_enabled: bool
):
    """
    https://issues.redhat.com/browse/RHINENG-7911

    metadata:
        requirements: inv-notifications-system-deleted
        assignee: fstavela
        importance: high
        negative: true
        title: Unsuccessful deletion via DELETE /hosts/<hosts_ids> doesn't trigger a notification
    """
    host_id = generate_uuid()
    with raises_apierror(403 if is_kessel_phase_1_enabled else 404):
        with temp_headers(
            host_inventory.apis.hosts.raw_api, {"x-rh-insights-request-id": generate_uuid()}
        ):
            host_inventory.apis.hosts.delete_by_id_raw(host_id)

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_delete_notification_message(
            DeleteNotificationWrapper.inventory_id, host_id, timeout=3
        )


@pytest.mark.ephemeral
def test_notifications_kafka_delete_filtered_dont_produce(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-7911

    metadata:
        requirements: inv-notifications-system-deleted
        assignee: fstavela
        importance: high
        negative: true
        title: Unsuccessful deletion via DELETE /hosts doesn't trigger a delete notification
    """
    insights_id = generate_uuid()
    with temp_headers(
        host_inventory.apis.hosts.raw_api, {"x-rh-insights-request-id": generate_uuid()}
    ):
        host_inventory.apis.hosts.delete_filtered(insights_id=insights_id)

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_delete_notification_message(
            DeleteNotificationWrapper.insights_id, insights_id, timeout=3
        )


@pytest.mark.ephemeral
def test_notifications_kafka_delete_get_dont_produce(
    host_inventory: ApplicationHostInventory, prepare_host_for_negative_test: HostWrapper
):
    """
    https://issues.redhat.com/browse/RHINENG-7911

    metadata:
        requirements: inv-notifications-system-deleted
        assignee: fstavela
        importance: high
        negative: true
        title: Unsuccessful deletion via DELETE /hosts/all doesn't trigger a delete notification
    """
    host = prepare_host_for_negative_test
    with temp_headers(
        host_inventory.apis.hosts.raw_api, {"x-rh-insights-request-id": generate_uuid()}
    ):
        host_inventory.apis.hosts.get_hosts_by_id(host)

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_delete_notification_message(
            DeleteNotificationWrapper.inventory_id, host.id, timeout=3
        )


@pytest.mark.ephemeral
def test_notifications_kafka_delete_patch_dont_produce(
    host_inventory: ApplicationHostInventory, prepare_host_for_negative_test: HostWrapper
):
    """
    https://issues.redhat.com/browse/RHINENG-7911

    metadata:
        requirements: inv-notifications-system-deleted
        assignee: fstavela
        importance: high
        negative: true
        title: Test that PATCH /hosts/<host_id> doesn't trigger a system-delete notification
    """
    host = prepare_host_for_negative_test
    with temp_headers(
        host_inventory.apis.hosts.raw_api, {"x-rh-insights-request-id": generate_uuid()}
    ):
        host_inventory.apis.hosts.patch_hosts(host, display_name=generate_display_name())

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_delete_notification_message(
            DeleteNotificationWrapper.inventory_id, host.id, timeout=3
        )


@pytest.mark.ephemeral
def test_notifications_kafka_delete_group_dont_produce(
    host_inventory: ApplicationHostInventory, prepare_host_for_negative_test: HostWrapper
):
    """
    https://issues.redhat.com/browse/RHINENG-7911

    metadata:
        requirements: inv-notifications-system-deleted
        assignee: fstavela
        importance: high
        negative: true
        title: Test that DELETE /groups/<groups_ids> doesn't trigger a system-delete notification
    """
    host = prepare_host_for_negative_test
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    with temp_headers(
        host_inventory.apis.groups.raw_api, {"x-rh-insights-request-id": generate_uuid()}
    ):
        host_inventory.apis.groups.delete_groups(group)

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_delete_notification_message(
            DeleteNotificationWrapper.inventory_id, host.id, timeout=3
        )

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_delete_notification_message(
            DeleteNotificationWrapper.inventory_id, group.id, timeout=1
        )


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_notifications_kafka_delete_staleness_dont_produce(
    host_inventory: ApplicationHostInventory, prepare_host_for_negative_test: HostWrapper
):
    """
    https://issues.redhat.com/browse/RHINENG-7911

    metadata:
        requirements: inv-notifications-system-deleted
        assignee: fstavela
        importance: high
        negative: true
        title: Test that DELETE /account/staleness doesn't trigger a system-delete notification
    """
    host = prepare_host_for_negative_test
    staleness = host_inventory.apis.account_staleness.create_staleness(
        conventional_time_to_stale=1000
    )

    with temp_headers(
        host_inventory.apis.account_staleness.raw_api,
        {"x-rh-insights-request-id": generate_uuid()},
    ):
        host_inventory.apis.account_staleness.delete_staleness()

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_delete_notification_message(
            DeleteNotificationWrapper.inventory_id, host.id, timeout=3
        )

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_delete_notification_message(
            DeleteNotificationWrapper.inventory_id, staleness.id.actual_instance, timeout=1
        )
