# mypy: disallow-untyped-defs

import logging
import uuid
from time import sleep

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.kessel_relations import HBIKesselRelationsGRPC
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.db.test_host_reaper import execute_reaper
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.staleness_utils import set_staleness

"""
These tests test HBI -> Kessel host replication. The workflows are:

1. Create/update/delete hosts, or change group membership
2. Verify that these updates are reflected in Kessel.

Kessel stores host data in the kessel-inventory database, which consists
of multiple tables.  To facilitate validation, I've requested an interface
described here:

   https://issues.redhat.com/browse/RHCLOUD-41166

This card is being implemented by the Kessel QE team and is in-progress.  So, for
the time being, validation is done just against Kessel Relations. In the relations,
we can't validate the actual data (other than host ID and workspace ID),
but we can validate that the data is correctly replicated to Kessel from HBI.
Once the interface is implemented, validation should be added against the Kessel Inventory.

The fields currently being replicated (to Kessel Inventory) are:

(see https://github.com/project-kessel/inventory-api/blob/main/data/schema/resources/host/reporters/hbi/host.json)

    * ansible_host
    * satellite_id
    * insights_id
    * subscription_manager_id

Additonally, hosts are identified by

    * workspace_id
    * inventory_id (termed a resource_id in Kessel)


REVISIT: Kessel still requires a special setup for the EE (see below).

To run in the EE:

1. Run insights-service-deployer:
    - Clone https://github.com/project-kessel/insights-service-deployer
    - Run deploy.sh deploy_with_hbi_demo

2. Run the tests with --kessel option
"""

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.mark.ephemeral
def test_kessel_repl_create_hosts(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that host info is replicated to kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_create_minimal_host(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that empty fields aren't replicated to Kessel
    """
    host_data = host_inventory.datagen.create_minimal_host_data()
    host = host_inventory.kafka.create_host(host_data=host_data)

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
    # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "update_field,update_value",
    [
        pytest.param("ansible_host", "Updated ansible_host"),
        pytest.param("satellite_id", str(uuid.uuid4())),
        pytest.param("subscription_manager_id", str(uuid.uuid4())),
        pytest.param("insights_id", str(uuid.uuid4())),
    ],
)
def test_kessel_repl_update_host(
    host_inventory: ApplicationHostInventory,
    update_field: str,
    update_value: str,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that host updates are replicated to Kessel
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["provider_type"] = "aws"
    host_data["provider_id"] = generate_uuid()

    host = host_inventory.kafka.create_host(host_data)

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
    # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    host_update_data = host_data.copy()
    host_update_data[update_field] = update_value
    host = host_inventory.kafka.create_host(host_update_data)

    host_inventory.apis.hosts.wait_for_updated(host, **{update_field: update_value})  # type: ignore[arg-type]

    hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
    # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_update_host_multiple_fields(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that host updates are replicated to Kessel
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["provider_type"] = "aws"
    host_data["provider_id"] = generate_uuid()

    host = host_inventory.kafka.create_host(host_data)

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
    # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    updates = {
        "ansible_host": "Update ansible_host",
        "satellite_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "insights_id": generate_uuid(),
    }
    host_update_data = host_data.copy()
    for update_field, update_value in updates.items():
        host_update_data[update_field] = update_value

    host = host_inventory.kafka.create_host(host_update_data)

    host_inventory.apis.hosts.wait_for_updated(host, **updates)  # type: ignore[arg-type]

    hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
    # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_update_host_via_api(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that host updates via API are replicated to Kessel
    """
    host = host_inventory.kafka.create_host()

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
    # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    updated_ansible_host = generate_display_name()
    host_inventory.apis.hosts.patch_hosts(host, ansible_host=updated_ansible_host)

    hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
    # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
@pytest.mark.parametrize("host_count", [1, 3])
def test_kessel_repl_delete_hosts_by_id(
    host_inventory: ApplicationHostInventory,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
    host_count: int,
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that deleted hosts by ID are reflected in Kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    host_inventory.apis.hosts.delete_by_id(hosts[:host_count])

    for host in hosts[:host_count]:
        hbi_kessel_relations_grpc.verify_deleted(host)

    for host in hosts[host_count:]:
        assert (
            hbi_kessel_relations_grpc.get_host_workspace_tuple(host, ungrouped_group) is not None
        )
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
@pytest.mark.parametrize("host_count", [1, 3])
def test_kessel_repl_delete_hosts_by_filter(
    host_inventory: ApplicationHostInventory,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
    host_count: int,
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that deleted hosts by filter are reflected in Kessel
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(3)
    if host_count > 1:
        for host_data in hosts_data[1:]:
            host_data["insights_id"] = hosts_data[0]["insights_id"]
    hosts = host_inventory.kafka.create_hosts(
        hosts_data=hosts_data, field_to_match=HostWrapper.subscription_manager_id
    )

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    host_inventory.apis.hosts.delete_filtered(insights_id=hosts_data[0]["insights_id"])

    for host in hosts[:host_count]:
        hbi_kessel_relations_grpc.verify_deleted(host)

    for host in hosts[host_count:]:
        assert (
            hbi_kessel_relations_grpc.get_host_workspace_tuple(host, ungrouped_group) is not None
        )
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_create_grouped_hosts(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that grouped hosts' info is replicated to kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_add_hosts_to_group(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that addings hosts to groups are reflected correctly in kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)

    group = host_inventory.apis.groups.add_hosts_to_group(group, hosts[:2])
    assert group.host_count == 2

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts[:2]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    for host in hosts[2:]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_remove_hosts_from_group(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that deleting hosts from group is reflected correctly in kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    host_inventory.apis.groups.remove_hosts_from_group(group, hosts[:2])
    group = host_inventory.apis.groups.get_groups(name=group_name)[0]
    assert group.host_count == 1

    for host in hosts[:2]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    for host in hosts[2:]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_remove_hosts_from_multiple_groups(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that deleting hosts from multiple groups is reflected correctly in kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(5)
    group1 = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[:2])
    group2 = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[2:4])
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts[:2]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group1)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory
    for host in hosts[2:4]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group2)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    host_inventory.apis.groups.remove_hosts_from_multiple_groups(hosts[:4])

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_patch_group_add_hosts(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that adding hosts to group via PATCH is reflected correctly in kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group = host_inventory.apis.groups.create_group(generate_display_name())

    host_inventory.apis.groups.patch_group(group, hosts=hosts)

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_patch_group_remove_hosts(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that removing hosts from group via PATCH is reflected correctly in kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    host_inventory.apis.groups.patch_group(group, hosts=[])

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_patch_group_change_hosts(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that changing hosts in group via PATCH is reflected correctly in kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(8)

    # Add first 4 hosts to group
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[:4])
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts[:4]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    for host in hosts[4:]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    # Remove 2 hosts from the group and add 2 new hosts to the group at the same time
    host_inventory.apis.groups.patch_group(group, hosts=hosts[2:6])

    for host in hosts[2:6]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory

    for host in hosts[:2] + hosts[6:]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
def test_kessel_repl_delete_group(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that deleting group is reflected correctly in kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    host_inventory.apis.groups.delete_groups(group)

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
        # TODO: Verify that each replicated field (see list above) is correct in Kessel Inventory


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_kessel_repl_delete_host_reaper(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19244
    https://issues.redhat.com/browse/RHINENG-21525

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that reaper host deletion is reflected in kessel
    """
    hosts = host_inventory.kafka.create_random_hosts(2)
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[0])
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    hbi_kessel_relations_grpc.verify_created_or_updated(hosts[0], group)
    hbi_kessel_relations_grpc.verify_created_or_updated(hosts[1], ungrouped_group)

    deltas = (1, 2, 3)
    set_staleness(host_inventory, deltas)
    sleep(3)

    execute_reaper()

    host_inventory.apis.hosts.wait_for_deleted(hosts)

    for host in hosts:
        hbi_kessel_relations_grpc.verify_deleted(host, retries=60)
