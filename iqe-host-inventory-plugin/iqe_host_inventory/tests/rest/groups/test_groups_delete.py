import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def test_groups_delete_empty_group(host_inventory: ApplicationHostInventory):
    """
    metadata:
        assignee: zabikeno
        importance: critical
        title: Inventory: Confirm deletion of group works.
    """
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)
    response = host_inventory.apis.groups.raw_api.api_group_delete_groups_with_http_info([
        group.id
    ])
    assert response[1] == 204

    host_inventory.apis.groups.verify_deleted(group)


@pytest.mark.ephemeral
def test_groups_delete_group_with_hosts(host_inventory: ApplicationHostInventory):
    """
    metadata:
        assignee: zabikeno
        importance: critical
        title: Inventory: Confirm deletion of group works with multiple hosts.
    """
    hosts = host_inventory.kafka.create_random_hosts(4)
    pre_delete_group_hosts_count = host_inventory.apis.hosts.get_hosts_response().total

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    host_inventory.apis.groups.delete_groups(group, wait_for_deleted=False)
    host_inventory.apis.groups.verify_deleted(group)

    # ensure hosts wasn't deleted from db
    host_inventory.apis.hosts.verify_not_deleted(hosts)
    response_hosts = host_inventory.apis.hosts.get_hosts_response()
    assert response_hosts.total == pre_delete_group_hosts_count


def test_groups_delete_multiple_groups(host_inventory: ApplicationHostInventory):
    """
    metadata:
        assignee: zabikeno
        importance: critical
        title: Inventory: Confirm deletion of group works.
    """
    group_name1 = generate_display_name()
    group_name2 = generate_display_name()
    group_name3 = generate_display_name()
    group1 = host_inventory.apis.groups.create_group(group_name1)
    group2 = host_inventory.apis.groups.create_group(group_name2)
    group3 = host_inventory.apis.groups.create_group(group_name3)

    groups_to_delete = [group2, group3]
    host_inventory.apis.groups.delete_groups(groups_to_delete, wait_for_deleted=False)

    host_inventory.apis.groups.verify_deleted(groups_to_delete)
    host_inventory.apis.groups.verify_not_deleted(group1)


@pytest.mark.ephemeral
def test_groups_delete_group_from_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    metadata:
        assignee: zabikeno
        importance: critical
        negative: true
        title: Inventory: Confirm deletion of group from different account does not delete
            a group"
    """
    hosts = host_inventory_secondary.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group_secondary = host_inventory_secondary.apis.groups.create_group(group_name, hosts=hosts)
    group_primary = host_inventory.apis.groups.create_group(group_name)

    with raises_apierror(404):
        host_inventory.apis.groups.raw_api.api_group_delete_groups([group_secondary.id])

    # ensure groups weren't deleted from db
    host_inventory.apis.groups.verify_not_deleted(group_primary)
    host_inventory_secondary.apis.groups.verify_not_deleted(group_secondary)
