"""
metadata:
    requirements: inv-graceful-shutdown
"""

import logging
import multiprocessing
from time import sleep

import pytest
from ocdeployer.utils import oc
from ocdeployer.utils import wait_for_ready
from sqlalchemy.orm import Session
from urllib3.exceptions import HTTPError  # type: ignore[import-untyped]
from wait_for import wait_for

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.db_utils import query_hosts_by_ids
from iqe_host_inventory.utils.db_utils import query_hosts_by_insights_id

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.backend]


@pytest.mark.resilience
@pytest.mark.ephemeral
def test_graceful_shutdown_mq(
    host_inventory: ApplicationHostInventory,
    inventory_db_session: Session,
):
    """
    Test inventory MQ graceful shutdown

    Confirm that all hosts are created in the database and the proper "created" messages
    are produced to the events topic even if the inventory MQ goes down and then back up again

    https://projects.engineering.redhat.com/browse/RHCLOUD-6776

    1. Produce 500 messages to the platform.inventory.host-ingress topic asynchronously
    2. Stop inventory mq service
    3. Bring up the inventory mq service back up
    3. Confirm all 500 hosts are present in the inventory database
    4. Confirm all 500 messages were produced to the platform.inventory.events topic

    metadata:
        assignee: fstavela
        importance: high
        title: Inventory: confirm inventory mq service handles shutdowns gracefully
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(500)

    logger.info("Creating 500 hosts via MQ")
    host_inventory.kafka.produce_host_create_messages(hosts_data, flush=False)
    res = host_inventory.kafka._producer.flush(timeout=10)
    logger.info("flush result %s", res)
    sleep(1)

    # Take mq service down
    logger.info("Stopping Inventory MQ services")
    oc("delete", f"deployment/{host_inventory.config.inv_mq_pmin_deploy_name}")
    oc("delete", f"deployment/{host_inventory.config.inv_mq_p1_deploy_name}")
    logger.info("Ephemeral env will now bring the deployments back up automatically")

    hosts_insights_ids = [host["insights_id"] for host in hosts_data]

    # Verify all the hosts are present in the database
    assert_hosts_created_in_database(inventory_db_session, hosts_insights_ids)

    # Collect all event messages for the created hosts
    event_messages = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, values=hosts_insights_ids, timeout=30
    )

    # Check that ONLY "created" events are produced
    event_types = {msg.type for msg in event_messages}
    assert all(message.type == "created" for message in event_messages), (
        f"Expected only 'created' events, but got: {event_types}"
    )

    # Check that we received exactly one event per host
    assert len(event_messages) == len(hosts_insights_ids)
    produced_insights_ids = {message.host.insights_id for message in event_messages}
    assert produced_insights_ids == set(hosts_insights_ids)


@pytest.mark.resilience
@pytest.mark.ephemeral
@pytest.mark.parametrize("request_type", ["update", "delete"])
def test_graceful_shutdown_api(
    host_inventory: ApplicationHostInventory,
    inventory_db_session: Session,
    request_type: str,
):
    """
    Test inventory API graceful shutdown

    Confirm hosts are updated in the database and the proper "updated" messages
    are produced to the events topic even if the inventory API service goes down

    https://projects.engineering.redhat.com/browse/RHCLOUD-6776

    1. Create 300 hosts via MQ
    2. Issue async requests to update/delete the created hosts display names
    3. Stop inventory api service
    4. Confirm the hosts that have its requests processed by inventory api
       were updated/deleted in the database
    5. Confirm the hosts that have its requests processed by inventory api
       produced "updated"/"deleted" events to the events topic

    metadata:
        assignee: fstavela
        importance: high
        title: Inventory: confirm inventory api service handles shutdowns gracefully
    """
    logger.info("Creating 300 hosts via MQ")
    hosts = host_inventory.kafka.create_random_hosts(300, timeout=60)
    hosts_ids = [host.id for host in hosts]
    host_ids_first = hosts_ids[10:]
    host_ids_second = hosts_ids[:10]

    new_display_name = "test_api_graceful_shutdown"
    if request_type == "update":
        threads_first = async_patch_display_name(host_inventory, host_ids_first, new_display_name)
    else:
        threads_first = async_delete(host_inventory, host_ids_first)

    logger.info("Stopping Inventory API and MQ services")
    oc("delete", f"deployment/{host_inventory.config.inv_mq_pmin_deploy_name}")
    oc("delete", f"deployment/{host_inventory.config.inv_mq_p1_deploy_name}")
    sleep(1)
    oc("delete", f"deployment/{host_inventory.config.inv_api_deploy_name}")
    sleep(1)
    logger.info("Ephemeral env will now bring the deployments back up automatically")

    # make sure host-inventory-service is back
    wait_for_ready("deployment", host_inventory.config.inv_api_deploy_name)
    if request_type == "update":
        threads_second = async_patch_display_name(
            host_inventory, host_ids_second, new_display_name
        )
    else:
        threads_second = async_delete(host_inventory, host_ids_second)

    threads = threads_first | threads_second
    affected_host_ids = []
    refused_count = 0
    for host_id, thread in threads.items():
        try:
            thread.get()
            affected_host_ids.append(host_id)
        except HTTPError:
            refused_count += 1
            logger.info(f"Request refused for {host_id}, total refused: {refused_count}")
            # Ignore hosts that have requests refused due to inventory api being down
            pass

    logger.info(f"Number of hosts that should have been {request_type}d: {len(affected_host_ids)}")

    # Verify expected 10 hosts are affected
    assert all(host_id in affected_host_ids for host_id in host_ids_second)
    # Verify all the successful requests affected the host in the database
    if request_type == "update":
        assert_hosts_updated_in_database(inventory_db_session, affected_host_ids, new_display_name)
    else:
        assert_hosts_deleted_from_database(inventory_db_session, affected_host_ids)

    expected_message_type = "updated" if request_type == "update" else request_type

    # Collect all event messages for the affected hosts
    event_messages = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.id, values=affected_host_ids, timeout=30
    )

    # Check that ONLY correct event type is produced
    event_types = {msg.type for msg in event_messages}
    assert all(message.type == expected_message_type for message in event_messages), (
        f"Expected only '{expected_message_type}' events, but got: {event_types}"
    )

    # Check that we received exactly one event per affected host
    assert len(event_messages) == len(affected_host_ids)
    produced_host_ids = {message.host.id for message in event_messages}
    assert produced_host_ids == set(affected_host_ids)


def async_patch_display_name(
    host_inventory: ApplicationHostInventory, host_id_list: list, new_display_name
):
    logger.info("Patching hosts display names")
    host_inventory.apis.hosts.raw_api.api_client.pool_threads = multiprocessing.cpu_count()
    logger.info(f"CPU count: {multiprocessing.cpu_count()}")

    threads = {}
    for host_id in host_id_list:
        threads[host_id] = host_inventory.apis.hosts.raw_api.api_host_patch_host_by_id(
            [host_id], {"display_name": new_display_name}, async_req=True, _preload_content=False
        )
    host_inventory.apis.hosts.raw_api.api_client.pool_threads = 1
    return threads


def async_delete(host_inventory: ApplicationHostInventory, host_id_list: list):
    logger.info("Deleting hosts")
    host_inventory.apis.hosts.raw_api.api_client.pool_threads = multiprocessing.cpu_count()
    logger.info(f"CPU count: {multiprocessing.cpu_count()}")

    threads = {}
    for host_id in host_id_list:
        threads[host_id] = host_inventory.apis.hosts.raw_api.api_host_delete_host_by_id(
            host_id_list=[host_id], async_req=True, _preload_content=False
        )

    host_inventory.apis.hosts.raw_api.api_client.pool_threads = 1
    return threads


def assert_hosts_created_in_database(inventory_db_session, hosts_ids):
    def _assert_hosts_in_database():
        hosts_created_in_db = query_hosts_by_insights_id(inventory_db_session, hosts_ids)
        logger.info(
            f"Current number of hosts found in the database: {hosts_created_in_db.rowcount}"
        )
        return hosts_created_in_db.rowcount == len(hosts_ids)

    logger.info("Waiting for all hosts to be saved in the database...")
    assert wait_for(
        _assert_hosts_in_database,
        num_sec=300,
        delay=5,
        message="wait for all hosts to appear in DB",
    )[0]
    logger.info("All hosts found in the database!")


def assert_hosts_updated_in_database(inventory_db_session, host_ids, new_display_name):
    hosts_updated = query_hosts_by_ids(inventory_db_session, host_ids)
    assert all(updated_host.display_name == new_display_name for updated_host in hosts_updated)
    logger.info("All expected hosts were updated in the database!")


def assert_hosts_deleted_from_database(inventory_db_session, host_ids):
    hosts_deleted = query_hosts_by_ids(inventory_db_session, host_ids)
    assert len(hosts_deleted) == 0
    logger.info("All expected hosts were deleted from the database!")
