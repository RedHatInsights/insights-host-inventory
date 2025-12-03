import logging

import pytest
from iqe.base.datafiles import get_data_path_for_plugin
from ocdeployer.utils import oc
from sqlalchemy.orm import Session

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import DeleteNotificationWrapper
from iqe_host_inventory.modeling.wrappers import HostMessageWrapper
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.db_utils import query_hosts_by_ids
from iqe_host_inventory.utils.notifications_utils import check_delete_notifications_data
from iqe_host_inventory.utils.notifications_utils import check_delete_notifications_headers
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale_stalewarning_culled

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def execute_reaper():
    reaper_file = str(get_data_path_for_plugin("host_inventory").joinpath("start-reaper.yaml"))
    logger.info("Executing the host reaper...")
    job_invocation = oc("apply", "-f", reaper_file, "-o", "name").stdout.decode("utf-8").strip()
    logger.info("Getting the host reaper job name")
    reaper_job = oc("get", "job", "-o", "name").stdout.decode("utf-8").split("\n")
    reaper_job = next(job for job in reaper_job if "host-inventory-reaper" in job)
    logger.info("Waiting for the host reaper job to finish")
    oc("wait", "--for=condition=complete", "--timeout=3m", reaper_job)
    logger.info("Deleting the host reaper job")
    oc("delete", reaper_job)
    oc("delete", job_invocation)


def check_events_and_notifications(
    host_inventory: ApplicationHostInventory, hosts: dict[str, list[HostWrapper]]
) -> None:
    logger.info("Searching deletion events and notifications")
    all_hosts_ids = {host.id for staleness in hosts.keys() for host in hosts[staleness]}
    found_host_events = set()
    found_notifications = set()

    # Get all host event messages and notifications
    for msg in host_inventory.kafka.walk_messages(timeout=5):
        if isinstance(msg, HostMessageWrapper) and msg.host.id in all_hosts_ids:
            found_host_events.add(msg)
        elif isinstance(msg, DeleteNotificationWrapper) and msg.inventory_id in all_hosts_ids:
            found_notifications.add(msg)

    # Check host event messages
    culled_hosts_ids = {host.id for host in hosts["culled"]}
    assert {host_message.value.get("id") for host_message in found_host_events} == culled_hosts_ids
    assert all(host_message.value.get("type") == "delete" for host_message in found_host_events)

    # Check notifications
    assert {notification.inventory_id for notification in found_notifications} == culled_hosts_ids
    for notification in found_notifications:
        check_delete_notifications_data(
            notification,
            next(host for host in hosts["culled"] if host.id == notification.inventory_id),
        )
        check_delete_notifications_headers(notification.headers, None)


@pytest.mark.reaper_script
@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_reaper_script(
    inventory_db_session: Session,
    host_inventory: ApplicationHostInventory,
    is_kessel_phase_1_enabled: bool,
) -> None:
    """
    Ensure that the host reaper script is removing the culled hosts from the database

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-3755

    1. Create 5 hosts in fresh state.
    2. Create 5 hosts in stale state.
    3. Create 5 hosts in stale_warning state.
    4. Create 5 hosts in culled state.
    5. Make sure that all of 20 hosts were created successfully
    6. Make sure that the culled hosts were removed by the reaper script from the database
    7. Make sure that the fresh, stale and stale_warning hosts
       are still in the database after the reaper script exec
    8. Make sure that the proper deletion messages are being sent to the events kafka topic

    metadata:
        requirements: inv-host-reaper, inv-staleness-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Confirm the culled hosts being removed by the host reaper
    """
    amount = 5

    fresh_hosts_data = host_inventory.datagen.create_n_hosts_data(amount)
    stale_hosts_data = host_inventory.datagen.create_n_hosts_data(amount)
    stale_warning_hosts_data = host_inventory.datagen.create_n_hosts_data(amount)
    culled_hosts_data = host_inventory.datagen.create_n_hosts_data(amount)

    hosts = create_hosts_fresh_stale_stalewarning_culled(
        host_inventory,
        fresh_hosts_data,
        stale_hosts_data,
        stale_warning_hosts_data,
        culled_hosts_data,
        deltas=(60, 120, 180),
    )

    fresh_hosts_ids = {host.id for host in hosts["fresh"]}
    stale_hosts_ids = {host.id for host in hosts["stale"]}
    stale_warning_hosts_ids = {host.id for host in hosts["stale_warning"]}
    culled_hosts_ids = {host.id for host in hosts["culled"]}

    all_hosts_ids = fresh_hosts_ids | stale_hosts_ids | stale_warning_hosts_ids | culled_hosts_ids

    execute_reaper()

    logger.info("Retrieving culled hosts from the database")
    culled_hosts_in_db = query_hosts_by_ids(inventory_db_session, list(culled_hosts_ids))
    logger.info(f"{len(culled_hosts_in_db)} culled hosts retrieved from the database")
    assert len(culled_hosts_in_db) == 0

    logger.info("Retrieving fresh hosts from the database")
    fresh_hosts_in_db = query_hosts_by_ids(inventory_db_session, list(fresh_hosts_ids))
    logger.info(f"{len(fresh_hosts_in_db)} fresh hosts retrieved from the database")
    assert len(fresh_hosts_in_db) == len(fresh_hosts_ids)

    logger.info("Retrieving stale hosts from the database")
    stale_hosts_in_db = query_hosts_by_ids(inventory_db_session, list(stale_hosts_ids))
    logger.info(f"{len(stale_hosts_in_db)} stale hosts retrieved from the database")
    assert len(stale_hosts_in_db) == len(stale_hosts_ids)

    logger.info("Retrieving stale_warning hosts from the database")
    stale_warning_hosts_in_db = query_hosts_by_ids(
        inventory_db_session, list(stale_warning_hosts_ids)
    )
    logger.info(
        f"{len(stale_warning_hosts_in_db)} stale_warning hosts retrieved from the database"
    )
    assert len(stale_warning_hosts_in_db) == len(stale_warning_hosts_ids)

    check_events_and_notifications(host_inventory, hosts)

    non_culled_hosts_ids = all_hosts_ids - culled_hosts_ids
    response = host_inventory.apis.hosts.get_hosts_by_id(list(non_culled_hosts_ids))
    response_ids = {host.id for host in response}
    assert response_ids == non_culled_hosts_ids

    for host_id in culled_hosts_ids:
        if is_kessel_phase_1_enabled:
            with raises_apierror(404):
                host_inventory.apis.hosts.get_hosts_by_id(host_id)
        else:
            response = host_inventory.apis.hosts.get_hosts_by_id(host_id)
            assert len(response) == 0
