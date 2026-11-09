from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.utils.api_utils import is_ungrouped_host
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_single_host(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      assignee: fstavela
      importance: high
      title: Test removing one host from group by using DELETE /groups/hosts/<host_ids> endpoint
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    host_inventory.apis.groups.remove_hosts_from_multiple_groups(hosts[0], wait_for_removed=False)
    host_inventory.apis.groups.verify_updated(group, hosts=hosts[1:])
    host_inventory.apis.hosts.verify_not_deleted(hosts)


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_same_group(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      assignee: fstavela
      importance: high
      title: Test removing hosts from the same group by using
             DELETE /groups/hosts/<host_ids> endpoint
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    host_inventory.apis.groups.remove_hosts_from_multiple_groups(hosts[:2], wait_for_removed=False)
    host_inventory.apis.groups.verify_updated(group, hosts=hosts[2])


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_different_groups(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      assignee: fstavela
      importance: high
      title: Test removing hosts from different groups by using
             DELETE /groups/hosts/<host_ids> endpoint
    """
    hosts = host_inventory.kafka.create_random_hosts(4)

    groups_data = [GroupData(hosts=hosts[:2]), GroupData(hosts=hosts[2:])]
    groups = host_inventory.apis.groups.create_groups(groups_data)

    host_inventory.apis.groups.remove_hosts_from_multiple_groups(
        [hosts[0], hosts[2]], wait_for_removed=False
    )
    host_inventory.apis.groups.verify_updated(groups[0], hosts=hosts[1])
    host_inventory.apis.groups.verify_updated(groups[1], hosts=hosts[3])


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_ungrouped_host(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      assignee: fstavela
      importance: medium
      negative: true
      title: Test removing ungrouped host from group by using
             DELETE /groups/hosts/<host_ids> endpoint
    """
    host = host_inventory.kafka.create_host()

    code = 400
    message = "The provided hosts cannot be removed from the ungrouped-hosts group."

    with raises_apierror(code, message):
        host_inventory.apis.groups.remove_hosts_from_multiple_groups(host, wait_for_removed=False)
    host_inventory.apis.hosts.verify_not_deleted(host)

    response_host = host_inventory.apis.hosts.get_host_by_id(host)
    assert is_ungrouped_host(response_host)


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      assignee: fstavela
      importance: critical
      negative: true
      title: Test host ID from a different account on DELETE /groups/hosts/<host_ids> endpoint
    """
    host_secondary = host_inventory_secondary.kafka.create_host()

    group_secondary = host_inventory_secondary.apis.groups.create_group(
        generate_display_name(), hosts=host_secondary
    )

    with raises_apierror(404, match_message="One or more hosts not found."):
        host_inventory.apis.groups.remove_hosts_from_multiple_groups(
            host_secondary, wait_for_removed=False
        )

    host_inventory_secondary.apis.groups.verify_not_updated(group_secondary, hosts=host_secondary)


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_my_and_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      assignee: fstavela
      importance: critical
      title: Test host ID from my and different account on DELETE /groups/hosts/<host_ids> endpoint
    """
    host_primary = host_inventory.kafka.create_host()
    host_secondary = host_inventory_secondary.kafka.create_host()

    group_primary = host_inventory.apis.groups.create_group(
        generate_display_name(), hosts=host_primary
    )
    group_secondary = host_inventory_secondary.apis.groups.create_group(
        generate_display_name(), hosts=host_secondary
    )

    with raises_apierror(404):
        host_inventory.apis.groups.remove_hosts_from_multiple_groups(
            [host_primary, host_secondary], wait_for_removed=False
        )

    host_inventory.apis.groups.verify_not_updated(group_primary, hosts=host_primary)
    host_inventory_secondary.apis.groups.verify_not_updated(group_secondary, hosts=host_secondary)
