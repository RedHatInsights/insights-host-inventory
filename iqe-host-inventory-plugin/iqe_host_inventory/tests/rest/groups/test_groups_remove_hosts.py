import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def test_groups_remove_host(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      assignee: zabikeno
      importance: high
      title: Remove single host from group
    """
    hosts = host_inventory.upload.create_hosts(2)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    response = (
        host_inventory.apis.groups.raw_api.api_host_group_delete_hosts_from_group_with_http_info(
            group.id, [hosts[0].id]
        )
    )
    assert response[1] == 204
    # ensure host was removed and another 3 stay in group
    host_inventory.apis.groups.verify_updated(group, hosts=hosts[1:])
    # ensure hosts wasn't deleted from db
    host_inventory.apis.hosts.verify_not_deleted(hosts)


@pytest.mark.ephemeral
def test_groups_remove_multiple_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      assignee: zabikeno
      importance: high
      title: Remove multiple hosts from group
    """
    hosts = host_inventory.kafka.create_random_hosts(4)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    host_inventory.apis.groups.remove_hosts_from_group(group, hosts[:2], wait_for_removed=False)
    # ensure first 2 hosts were removed and another 2 stay in group
    host_inventory.apis.groups.verify_updated(group, hosts=hosts[2:])


@pytest.mark.ephemeral
def test_groups_remove_all_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      assignee: zabikeno
      importance: high
      title: Remove all hosts from group
    """
    hosts = host_inventory.kafka.create_random_hosts(4)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    host_inventory.apis.groups.remove_hosts_from_group(group, hosts, wait_for_removed=False)
    # ensure first hosts were removed and group is empty
    host_inventory.apis.groups.verify_updated(group, hosts=[])


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    metadata:
        assignee: zabikeno
        importance: critical
        negative: true
        title: Inventory: Confirm removing host from different account does not remove
            a host from a group"
    """
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group_secondary = host_inventory_secondary.apis.groups.create_group(
        group_name, hosts=hosts_secondary
    )
    group_primary = host_inventory.apis.groups.create_group(group_name)

    # TODO: Switch the next 2 lines when https://issues.redhat.com/browse/RHINENG-17234 is done
    # with raises_apierror(404, match_message="Hosts not found."):
    with raises_apierror(404):
        host_inventory.apis.groups.remove_hosts_from_group(
            group_primary, hosts_secondary, wait_for_removed=False
        )

    # hosts weren't removed from group
    host_inventory_secondary.apis.groups.verify_not_updated(group_secondary, hosts=hosts_secondary)
    host_inventory.apis.groups.verify_not_updated(group_primary, hosts=[])


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_group_with_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    metadata:
        assignee: zabikeno
        importance: critical
        negative: true
        title: Inventory: Confirm removing host from group with different account does not remove
            a host"
    """
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group_secondary = host_inventory_secondary.apis.groups.create_group(
        group_name, hosts=hosts_secondary
    )
    group_primary = host_inventory.apis.groups.create_group(group_name)

    with raises_apierror(404):
        host_inventory.apis.groups.remove_hosts_from_group(
            group_secondary, hosts_secondary, wait_for_removed=False
        )

    # hosts weren't removed from group
    host_inventory_secondary.apis.groups.verify_not_updated(group_secondary, hosts=hosts_secondary)
    host_inventory.apis.groups.verify_not_updated(group_primary, hosts=[])
