import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory_api import HostOut

"""
REVISIT: Kessel still requires a special setup for the EE (see below).

To run in the EE:

1. Run insights-service-deployer:
    - Clone https://github.com/project-kessel/insights-service-deployer
    - Run deploy.sh deploy_with_hbi_demo

2. Run the tests with --kessel option
"""

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def prepare_hosts(host_inventory: ApplicationHostInventory) -> list[HostOut]:
    return host_inventory.upload.create_hosts(4, cleanup_scope="module")


def test_kessel_create_hosts(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-ungrouped
      assignee: msager
      importance: high
      title: Test that ungrouped hosts are stored in the "ungrouped" group
    """
    initial_ungrouped_count = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[
        0
    ].host_count

    hosts = host_inventory.upload.create_hosts(3)
    host_ids = [host.id for host in hosts]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    assert ungrouped_group.host_count == initial_ungrouped_count + 3

    response_hosts = host_inventory.apis.hosts.get_hosts_by_id(host_ids)
    assert all(
        host.groups[0].id == ungrouped_group.id and host.groups[0].ungrouped
        for host in response_hosts
    )


def test_kessel_delete_host(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-ungrouped
      assignee: msager
      importance: high
      title: Test that a deleted host is removed from the "ungrouped" group
    """
    host = host_inventory.upload.create_host()

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    initial_ungrouped_count = ungrouped_group.host_count

    response_host = host_inventory.apis.hosts.get_host_by_id(host.id)
    assert response_host.groups[0].id == ungrouped_group.id

    host_inventory.apis.hosts.delete_by_id(host.id)

    assert (
        host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0].host_count
        == initial_ungrouped_count - 1
    )


def test_kessel_filter_ungrouped_hosts(
    host_inventory: ApplicationHostInventory, prepare_hosts: list[HostOut]
):
    """
    metadata:
      requirements: inv-kessel-ungrouped
      assignee: msager
      importance: high
      title: Test that I can filter hosts by the "ungrouped" group
    """
    initial_ungrouped_count = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[
        0
    ].host_count

    hosts = prepare_hosts
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[2:])

    ungrouped_hosts = host_inventory.apis.hosts.get_hosts(group_name=["Ungrouped Hosts"])
    ungrouped_host_ids = {host.id for host in ungrouped_hosts}

    assert len(ungrouped_hosts) == initial_ungrouped_count - 2
    assert {hosts[0].id, hosts[1].id}.issubset(ungrouped_host_ids)


def test_kessel_get_hosts_ordering_with_ungrouped(
    host_inventory: ApplicationHostInventory, prepare_hosts: list[HostOut]
):
    """
    metadata:
      requirements: inv-kessel-ungrouped
      assignee: msager
      importance: high
      title: Test get hosts group name ordering with a mix of grouped/ungrouped hosts
    """
    hosts = prepare_hosts

    # The expectation is that ungrouped hosts come first.  Use group names that
    # would come before and after "ungrouped" alphabetically.
    host_inventory.apis.groups.create_group(name="a_group", hosts=hosts[0])
    host_inventory.apis.groups.create_group(name="z_group", hosts=hosts[1])

    # We're not validating all ordering here (should be done in the groups tests),
    # but rather that ungrouped hosts come first.  Takes into account that there
    # might be other hosts in the account.

    ungrouped_hosts = host_inventory.apis.hosts.get_hosts(group_name=["Ungrouped Hosts"])
    ungrouped_host_ids = {host.id for host in ungrouped_hosts}

    ordered_hosts = host_inventory.apis.hosts.get_hosts(order_by="group_name")[
        : len(ungrouped_host_ids)
    ]
    ordered_host_ids = {host.id for host in ordered_hosts}

    assert ordered_host_ids == ungrouped_host_ids

    ordered_hosts = host_inventory.apis.hosts.get_hosts(order_by="group_name", order_how="DESC")[
        -len(ungrouped_host_ids) :
    ]
    ordered_host_ids = {host.id for host in ordered_hosts}

    assert ordered_host_ids == ungrouped_host_ids
