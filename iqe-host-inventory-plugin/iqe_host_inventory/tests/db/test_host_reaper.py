import logging
from time import sleep

import pytest
from iqe.base.datafiles import get_data_path_for_plugin
from ocdeployer.utils import oc
from sqlalchemy.orm import Session

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.modeling.wrappers import DeleteNotificationWrapper
from iqe_host_inventory.modeling.wrappers import HostMessageWrapper
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.db_utils import query_hosts_by_ids
from iqe_host_inventory.utils.notifications_utils import check_delete_notifications_data
from iqe_host_inventory.utils.notifications_utils import check_delete_notifications_headers
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale_stalewarning_culled
from iqe_host_inventory.utils.staleness_utils import create_hosts_in_state

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def execute_reaper():
    reaper_file = str(get_data_path_for_plugin("host_inventory").joinpath("start-reaper.yaml"))  # type: ignore[union-attr]
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
@pytest.mark.parametrize("host_type", ["conventional", "edge"])
def test_reaper_script(
    inventory_db_session: Session,
    host_inventory: ApplicationHostInventory,
    is_kessel_phase_1_enabled: bool,
    host_type: str,
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

    fresh_hosts_data = host_inventory.datagen.create_n_hosts_data(amount, host_type=host_type)
    stale_hosts_data = host_inventory.datagen.create_n_hosts_data(amount, host_type=host_type)
    stale_warning_hosts_data = host_inventory.datagen.create_n_hosts_data(
        amount, host_type=host_type
    )
    culled_hosts_data = host_inventory.datagen.create_n_hosts_data(amount, host_type=host_type)

    hosts = create_hosts_fresh_stale_stalewarning_culled(
        host_inventory,
        fresh_hosts_data,
        stale_hosts_data,
        stale_warning_hosts_data,
        culled_hosts_data,
        host_type=host_type,
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
            with raises_apierror(403):
                host_inventory.apis.hosts.get_hosts_by_id(host_id)
        else:
            response = host_inventory.apis.hosts.get_hosts_by_id(host_id)
            assert len(response) == 0


@pytest.mark.reaper_script
@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_reaper_script_grouped_hosts(
    host_inventory: ApplicationHostInventory, inventory_db_session
):
    """
    https://issues.redhat.com/browse/RHINENG-2303
    https://issues.redhat.com/browse/RHINENG-6037

    metadata:
        requirements: inv-host-reaper, inv-staleness-hosts, inv-groups-get-by-id, inv-groups-delete
        assignee: fstavela
        importance: high
        title: Test that host reaper correctly deletes grouped hosts
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    hosts_ids = [host.id for host in hosts]

    groups_data = [GroupData(hosts=hosts[0]), GroupData(hosts=hosts[1])]
    groups = host_inventory.apis.groups.create_groups(groups_data)

    create_hosts_in_state(
        host_inventory,
        hosts_data,
        host_state="culling",
        deltas=(1, 2, 10),
    )

    # Test that I can't get culled hosts, even if they are not deleted yet
    response_hosts = host_inventory.apis.hosts.get_hosts_by_id(hosts)
    assert len(response_hosts) == 0

    # Test that I can delete a group with culled hosts
    response_group = host_inventory.apis.groups.get_group_by_id(groups[0])
    assert response_group.host_count == 0
    host_inventory.apis.groups.delete_groups(groups[0], wait_for_deleted=False)
    host_inventory.apis.groups.verify_deleted(groups[0])

    # Remove the sleep when https://issues.redhat.com/browse/RHINENG-11171 is fixed
    sleep(10)

    execute_reaper()

    logger.info("Retrieving hosts from the database")
    hosts_in_db = query_hosts_by_ids(inventory_db_session, hosts_ids)
    logger.info(f"{len(hosts_in_db)} hosts retrieved from the database")
    assert len(hosts_in_db) == 0

    # Test that I can delete a group with deleted culled hosts
    response_group = host_inventory.apis.groups.get_group_by_id(groups[1])
    assert response_group.host_count == 0
    host_inventory.apis.groups.delete_groups(groups[1], wait_for_deleted=False)
    host_inventory.apis.groups.verify_deleted(groups[1])


@pytest.mark.reaper_script
@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_reaper_script_rhsm_sp_bridge_host(
    inventory_db_session: Session,
    host_inventory: ApplicationHostInventory,
) -> None:
    """A temporary test for a temporary workaround for culling of rhsm-system-profile-bridge hosts.
    Hosts which are reported only by this reporter should never get culled. To achieve this, every
    time a host reaper runs it updates the "updated" and "last_check_in" timestamps of these hosts.

    https://issues.redhat.com/browse/RHINENG-16934

    metadata:
        requirements: inv-host-reaper-rhsm-sp-bridge-bandaid
        assignee: fstavela
        importance: high
        title: Test that rhsm-system-profile-bridge hosts will not get culled
    """
    # These hosts shouldn't be deleted
    hosts_data = host_inventory.datagen.create_n_hosts_data(
        5, reporter="rhsm-system-profile-bridge", display_name="rhsm-bridge-test"
    )

    # These hosts should be deleted
    hosts_data += host_inventory.datagen.create_n_hosts_data(
        5, reporter="puptoo", display_name="rhsm-bridge-test"
    )

    hosts = create_hosts_in_state(
        host_inventory,
        hosts_data,
        host_state="culling",
        deltas=(40, 50, 60),
    )
    rhsm_host_ids = [host.id for host in hosts[:5]]
    rhsm_hosts_by_ids = {host.id: host for host in hosts[:5]}
    puptoo_host_ids = [host.id for host in hosts[5:]]

    execute_reaper()

    # Check that all puptoo hosts were deleted
    logger.info("Retrieving puptoo hosts from the database")
    puptoo_hosts_in_db = query_hosts_by_ids(inventory_db_session, puptoo_host_ids)
    logger.info(f"{len(puptoo_hosts_in_db)} culled hosts retrieved from the database")
    assert len(puptoo_hosts_in_db) == 0

    # Check that all rhsm bridge hosts are still in the DB
    logger.info("Retrieving rhsm-system-profile-bridge hosts from the database")
    rhsm_hosts_in_db = query_hosts_by_ids(inventory_db_session, rhsm_host_ids)
    logger.info(f"{len(rhsm_hosts_in_db)} hosts retrieved from the database")
    assert len(rhsm_hosts_in_db) == len(rhsm_host_ids)

    # Check that all rhsm bridge hosts are retrievable by API
    response_hosts = host_inventory.apis.hosts.get_hosts(display_name="rhsm-bridge-test")
    assert len(response_hosts) == len(rhsm_host_ids)
    response_ids = {host.id for host in response_hosts}
    assert response_ids == set(rhsm_host_ids)

    # Check that the "updated" and "last_check_in" timestamps stayed the same
    for response_host in response_hosts:
        assert response_host.updated == rhsm_hosts_by_ids[response_host.id].updated
        assert response_host.last_check_in == rhsm_hosts_by_ids[response_host.id].last_check_in


@pytest.mark.reaper_script
@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_reaper_script_rhsm_sp_bridge_host_with_other_reporters(
    inventory_db_session: Session,
    host_inventory: ApplicationHostInventory,
) -> None:
    """A temporary test for a temporary workaround for culling of rhsm-system-profile-bridge hosts.
    The workaround shouldn't apply to hosts which have been reported by rhsm-sp-bridge and other
    reporters as well.

    https://issues.redhat.com/browse/RHINENG-16934

    metadata:
        requirements: inv-host-reaper-rhsm-sp-bridge-bandaid
        assignee: fstavela
        importance: high
        title: Test that hosts with rhsm-sp-bridge and other reporters will get culled and deleted
    """
    # Create hosts with a different reporter
    hosts_data = host_inventory.datagen.create_n_hosts_data(
        5, reporter="rhsm-conduit", display_name="rhsm-bridge-test"
    )
    hosts = host_inventory.kafka.create_hosts(hosts_data)
    host_ids = {host.id for host in hosts}

    # Update the hosts with rhsm-system-profile-bridge reporter and make them culled
    for host_data in hosts_data:
        host_data["reporter"] = "rhsm-system-profile-bridge"
    create_hosts_in_state(
        host_inventory,
        hosts_data,
        host_state="culling",
        deltas=(40, 50, 60),
    )

    execute_reaper()

    # Check that the hosts are deleted from the DB
    logger.info("Retrieving the hosts from the database")
    hosts_in_db = query_hosts_by_ids(inventory_db_session, list(host_ids))
    logger.info(f"{len(hosts_in_db)} hosts retrieved from the database")
    assert len(hosts_in_db) == 0

    # Check that the hosts are not retrievable by API
    response_hosts = host_inventory.apis.hosts.get_hosts(display_name="rhsm-bridge-test")
    assert len(response_hosts) == 0


@pytest.mark.reaper_script
@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_reaper_script_uses_last_check_in(
    inventory_db_session: Session,
    host_inventory: ApplicationHostInventory,
    is_kessel_phase_1_enabled: bool,
) -> None:
    """
    Ensure that the host reaper script is using 'last_check_in' timestamp to determine culled hosts

    https://issues.redhat.com/browse/RHINENG-17845

    metadata:
        requirements: inv-host-reaper, inv-staleness-hosts
        assignee: fstavela
        importance: high
        title: Test that host reaper uses 'last_check_in' timestamp to determine culled hosts
    """
    culled_hosts = host_inventory.kafka.create_random_hosts(10)
    sleep(60)

    # Patch hosts to update their 'updated' timestamp, but 'last_check_in' stays the same
    patched_hosts = culled_hosts[:5]
    host_inventory.apis.hosts.patch_hosts(patched_hosts, display_name=generate_display_name())

    # Go through all the host events, otherwise updating staleness won't find correct events
    host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, [host.insights_id for host in patched_hosts]
    )

    host_inventory.apis.account_staleness.create_staleness(
        conventional_time_to_stale=58,
        conventional_time_to_stale_warning=59,
        conventional_time_to_delete=60,
    )
    fresh_hosts = host_inventory.kafka.create_random_hosts(5)

    fresh_hosts_ids = {host.id for host in fresh_hosts}
    patched_hosts_ids = {host.id for host in patched_hosts}
    culled_hosts_ids = {host.id for host in culled_hosts[5:]}

    all_hosts_ids = fresh_hosts_ids | patched_hosts_ids | culled_hosts_ids

    execute_reaper()

    logger.info("Retrieving culled hosts from the database")
    culled_hosts_in_db = query_hosts_by_ids(inventory_db_session, list(culled_hosts_ids))
    logger.info(f"{len(culled_hosts_in_db)} culled hosts retrieved from the database")
    assert len(culled_hosts_in_db) == 0

    logger.info("Retrieving culled hosts with fresh 'updated' timestamp from the database")
    updated_hosts_in_db = query_hosts_by_ids(inventory_db_session, list(patched_hosts_ids))
    logger.info(f"{len(updated_hosts_in_db)} updated culled hosts retrieved from the database")
    assert len(updated_hosts_in_db) == 0

    logger.info("Retrieving fresh hosts from the database")
    fresh_hosts_in_db = query_hosts_by_ids(inventory_db_session, list(fresh_hosts_ids))
    logger.info(f"{len(fresh_hosts_in_db)} fresh hosts retrieved from the database")
    assert len(fresh_hosts_in_db) == len(fresh_hosts_ids)

    not_deleted_hosts_ids = all_hosts_ids - culled_hosts_ids - patched_hosts_ids
    response = host_inventory.apis.hosts.get_hosts_by_id(list(not_deleted_hosts_ids))
    response_ids = {host.id for host in response}
    assert response_ids == not_deleted_hosts_ids

    for host_id in culled_hosts_ids.union(patched_hosts_ids):
        if is_kessel_phase_1_enabled:
            with raises_apierror(403):
                host_inventory.apis.hosts.get_hosts_by_id(host_id)
        else:
            response = host_inventory.apis.hosts.get_hosts_by_id(host_id)
            assert len(response) == 0
