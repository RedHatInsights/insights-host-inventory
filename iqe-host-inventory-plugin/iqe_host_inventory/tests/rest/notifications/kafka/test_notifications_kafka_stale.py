from __future__ import annotations

import logging

import pytest
from iqe.utils.blockers import iqe_blocker

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.modeling.wrappers import KafkaMessageNotFoundError
from iqe_host_inventory.modeling.wrappers import StaleNotificationWrapper
from iqe_host_inventory.utils.notifications_utils import check_stale_notifications_data
from iqe_host_inventory.utils.notifications_utils import check_stale_notifications_headers
from iqe_host_inventory.utils.notifications_utils import create_host_data_for_notification_tests
from iqe_host_inventory.utils.notifications_utils import execute_stale_host_notification
from iqe_host_inventory.utils.staleness_utils import set_staleness
from iqe_host_inventory_api import GroupOutWithHostCount

pytestmark = [pytest.mark.backend, pytest.mark.kafka]

logger = logging.getLogger(__name__)


@pytest.fixture(params=["minimal-rhel", "complete-rhel", "complete-centos"])
def prepare_host_for_stale_notification(
    request, host_inventory: ApplicationHostInventory
) -> HostWrapper:
    host_data = create_host_data_for_notification_tests(host_inventory, *request.param.split("-"))
    return host_inventory.kafka.create_host(
        host_data=host_data,
        field_to_match=HostWrapper.provider_id,
    )


def trigger_job_validate_found(
    host_inventory: ApplicationHostInventory,
    host: HostWrapper,
    group: GroupOutWithHostCount | None = None,
    base_url: str = "https://localhost",
) -> None:
    execute_stale_host_notification()

    msg = host_inventory.kafka.wait_for_filtered_stale_notification_message(
        StaleNotificationWrapper.inventory_id, host.id
    )
    logger.info(f"Received stale notification: {msg.value}")

    check_stale_notifications_data(msg, host, group, base_url)
    check_stale_notifications_headers(msg.headers)


def trigger_job_validate_not_found(
    host_inventory: ApplicationHostInventory, host: HostWrapper
) -> None:
    execute_stale_host_notification()

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_stale_notification_message(
            StaleNotificationWrapper.inventory_id, host.id, timeout=3
        )


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_notifications_kafka_host_stale_toggle_via_refresh(
    host_inventory: ApplicationHostInventory,
):
    """
    Toggle a host's staleness from stale -> fresh -> stale and verify that
    notifications are only triggered when the host goes stale.  For this test,
    update the host to "freshen" it.

    https://issues.redhat.com/browse/RHINENG-7912

    metadata:
        requirements: inv-notifications-system-became-stale
        assignee: msager
        importance: high
        title: Staleness toggling is handled correctly
    """
    host_data = host_inventory.datagen.create_host_data()
    host = host_inventory.kafka.create_host(host_data)

    deltas = (5, 3600, 7200)

    # fresh -> stale
    set_staleness(host_inventory, deltas)
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="stale", delay=5)
    trigger_job_validate_found(host_inventory, host)

    # stale -> fresh
    host_inventory.kafka.create_host(host_data)
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="fresh")
    trigger_job_validate_not_found(host_inventory, host)

    # fresh -> stale
    set_staleness(host_inventory, deltas)
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="stale", delay=5)
    trigger_job_validate_found(host_inventory, host)


@iqe_blocker(iqe_blocker.jira("RHINENG-15789", category=iqe_blocker.PRODUCT_ISSUE))
@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_primary_groups_cleanup_function", "hbi_staleness_cleanup")
def test_notifications_kafka_host_stale_toggle_via_delete_staleness(
    host_inventory: ApplicationHostInventory,
    prepare_host_for_stale_notification: HostWrapper,
):
    """
    Toggle a host's staleness from stale -> fresh -> stale and verify that
    notifications are only triggered when the host goes stale.  For this test,
    delete the staleness record to "freshen" the host.

    https://issues.redhat.com/browse/RHINENG-7912

    metadata:
        requirements: inv-notifications-system-became-stale
        assignee: msager
        importance: low
        title: Staleness toggling is handled correctly
    """
    host = prepare_host_for_stale_notification

    deltas = (1, 3600, 7200)

    # fresh -> stale
    set_staleness(host_inventory, deltas)
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="stale")
    trigger_job_validate_found(host_inventory, host)

    # stale -> fresh
    host_inventory.apis.account_staleness.delete_staleness()
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="fresh")
    trigger_job_validate_not_found(host_inventory, host)

    # fresh -> stale
    set_staleness(host_inventory, deltas)
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="stale")
    trigger_job_validate_found(host_inventory, host)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_notifications_kafka_host_stale_retrigger(
    host_inventory: ApplicationHostInventory,
    prepare_host_for_stale_notification: HostWrapper,
):
    """
    Verify that a stale notification is only triggered once.

    https://issues.redhat.com/browse/RHINENG-7912

    metadata:
        requirements: inv-notifications-system-became-stale
        assignee: msager
        importance: high
        title: Stale notifications only trigger once
    """
    host = prepare_host_for_stale_notification

    deltas = (1, 3600, 7200)
    set_staleness(host_inventory, deltas)
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="stale")

    # Initial notification
    trigger_job_validate_found(host_inventory, host)

    # Subsequent job runs should not yield a notification
    trigger_job_validate_not_found(host_inventory, host)
