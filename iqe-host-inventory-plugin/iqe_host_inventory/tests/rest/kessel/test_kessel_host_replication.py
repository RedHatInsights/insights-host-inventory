# mypy: disallow-untyped-defs

import json
import logging
import uuid
from os import getenv
from time import sleep

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.kessel_relations import EPHEMERAL_ENVS
from iqe_host_inventory.modeling.kessel_relations import HBIKesselRelationsGRPC
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.modeling.wrappers import KesselOutboxWrapper
from iqe_host_inventory.tests.db.test_host_reaper import execute_reaper
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.staleness_utils import set_staleness
from iqe_host_inventory_api import HostOut

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

pytestmark = [
    pytest.mark.backend,
    pytest.mark.skipif(
        getenv("ENV_FOR_DYNACONF", "stage_proxy").lower() == "prod",
        reason="The HBI -> Kessel data migration is not yet complete in Prod",
    ),
]

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def prepare_hosts(host_inventory: ApplicationHostInventory) -> list[HostOut]:
    return host_inventory.upload.create_hosts(8, cleanup_scope="module")


def verify_kessel_event(
    message: KesselOutboxWrapper,
    host: HostOut | HostWrapper,
    *,
    group_id: str,
    insights_id: str | None = None,
    ansible_host: str | None = None,
    satellite_id: str | None = None,
    subscription_manager_id: str | None = None,
) -> None:
    assert message.host_id == host.id
    assert message.workspace_id == group_id
    assert message.insights_id == (insights_id or host.insights_id)
    assert message.ansible_host == (ansible_host or host.ansible_host)
    assert message.satellite_id == (satellite_id or host.satellite_id)
    assert message.subscription_manager_id == (
        subscription_manager_id or host.subscription_manager_id
    )


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
    hosts = host_inventory.upload.create_hosts(3)

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)

    if host_inventory.application.config.current_env.lower() in EPHEMERAL_ENVS:
        messages = host_inventory.kafka.wait_for_filtered_kessel_messages(
            host_ids=[host.id for host in hosts]
        )
        assert len(messages) == len(hosts)
        for i, message in enumerate(messages):
            verify_kessel_event(message, hosts[i], group_id=ungrouped_group.id)


@pytest.mark.ephemeral
def test_kessel_repl_create_full_host(
    host_inventory: ApplicationHostInventory, hbi_kessel_relations_grpc: HBIKesselRelationsGRPC
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that full host data is replicated to Kessel
    """
    host_data = host_inventory.datagen.create_complete_host_data()
    host = host_inventory.kafka.create_host(host_data=host_data)

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)

    if host_inventory.application.config.current_env.lower() in EPHEMERAL_ENVS:
        messages = host_inventory.kafka.wait_for_filtered_kessel_messages(host_ids=[host.id])
        assert len(messages) == 1
        verify_kessel_event(messages[0], host, group_id=ungrouped_group.id)


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

    if host_inventory.application.config.current_env.lower() in EPHEMERAL_ENVS:
        messages = host_inventory.kafka.wait_for_filtered_kessel_messages(host_ids=[host.id])
        assert len(messages) == 1
        verify_kessel_event(messages[0], host, group_id=ungrouped_group.id)


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
    if host_inventory.application.config.current_env.lower() in EPHEMERAL_ENVS:
        messages = host_inventory.kafka.wait_for_filtered_kessel_messages(host_ids=[host.id])
        assert len(messages) == 1
        verify_kessel_event(messages[0], host, group_id=ungrouped_group.id)

    host_update_data = host_data.copy()
    host_update_data[update_field] = update_value
    host = host_inventory.kafka.create_host(host_update_data)

    host_inventory.apis.hosts.wait_for_updated(host, **{update_field: update_value})  # type: ignore[arg-type]

    hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
    if host_inventory.application.config.current_env.lower() in EPHEMERAL_ENVS:
        messages = host_inventory.kafka.wait_for_filtered_kessel_messages(host_ids=[host.id])
        assert len(messages) == 1
        verify_kessel_event(
            messages[0], host, group_id=ungrouped_group.id, **{update_field: update_value}
        )


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
    if host_inventory.application.config.current_env.lower() in EPHEMERAL_ENVS:
        messages = host_inventory.kafka.wait_for_filtered_kessel_messages(host_ids=[host.id])
        assert len(messages) == 1
        verify_kessel_event(messages[0], host, group_id=ungrouped_group.id)

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
    if host_inventory.application.config.current_env.lower() in EPHEMERAL_ENVS:
        messages = host_inventory.kafka.wait_for_filtered_kessel_messages(host_ids=[host.id])
        assert len(messages) == 1
        verify_kessel_event(messages[0], host, group_id=ungrouped_group.id, **updates)


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
    if host_inventory.application.config.current_env.lower() in EPHEMERAL_ENVS:
        messages = host_inventory.kafka.wait_for_filtered_kessel_messages(host_ids=[host.id])
        assert len(messages) == 1
        verify_kessel_event(messages[0], host, group_id=ungrouped_group.id)

    updated_ansible_host = generate_display_name()
    host_inventory.apis.hosts.patch_hosts(host, ansible_host=updated_ansible_host)

    hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)
    if host_inventory.application.config.current_env.lower() in EPHEMERAL_ENVS:
        messages = host_inventory.kafka.wait_for_filtered_kessel_messages(host_ids=[host.id])
        assert len(messages) == 1
        verify_kessel_event(
            messages[0], host, group_id=ungrouped_group.id, ansible_host=updated_ansible_host
        )


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
    hosts = host_inventory.upload.create_hosts(3)

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)

    host_inventory.apis.hosts.delete_by_id(hosts[:host_count])

    for host in hosts[:host_count]:
        hbi_kessel_relations_grpc.verify_deleted(host)

    for host in hosts[host_count:]:
        assert (
            hbi_kessel_relations_grpc.get_host_workspace_tuple(host, ungrouped_group) is not None
        )


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
            host_data["display_name"] = hosts_data[0]["display_name"]
    hosts = host_inventory.kafka.create_hosts(
        hosts_data=hosts_data, field_to_match=HostWrapper.subscription_manager_id
    )

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)

    host_inventory.apis.hosts.delete_filtered(display_name=hosts_data[0]["display_name"])

    for host in hosts[:host_count]:
        hbi_kessel_relations_grpc.verify_deleted(host)

    for host in hosts[host_count:]:
        assert (
            hbi_kessel_relations_grpc.get_host_workspace_tuple(host, ungrouped_group) is not None
        )


def test_kessel_repl_create_group_with_hosts(
    host_inventory: ApplicationHostInventory,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
    prepare_hosts: list[HostOut],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that grouped hosts' info is replicated to kessel
    """
    hosts = prepare_hosts[:3]

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)


def test_kessel_repl_add_hosts_to_group(
    host_inventory: ApplicationHostInventory,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
    prepare_hosts: list[HostOut],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that addings hosts to groups are reflected correctly in kessel
    """
    hosts = prepare_hosts[:3]
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)

    group = host_inventory.apis.groups.add_hosts_to_group(group, hosts[:2])
    assert group.host_count == 2

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts[:2]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)

    for host in hosts[2:]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)


def test_kessel_repl_remove_hosts_from_group(
    host_inventory: ApplicationHostInventory,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
    prepare_hosts: list[HostOut],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that deleting hosts from group is reflected correctly in kessel
    """
    hosts = prepare_hosts[:3]
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    host_inventory.apis.groups.remove_hosts_from_group(group, hosts[:2])
    group = host_inventory.apis.groups.get_groups(name=group_name)[0]
    assert group.host_count == 1

    for host in hosts[:2]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)

    for host in hosts[2:]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)


def test_kessel_repl_remove_hosts_from_multiple_groups(
    host_inventory: ApplicationHostInventory,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
    prepare_hosts: list[HostOut],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: msager
      importance: high
      title: Verify that deleting hosts from multiple groups is reflected correctly in kessel
    """
    hosts = prepare_hosts[:5]
    group1 = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[:2])
    group2 = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[2:4])
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts[:2]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group1)
    for host in hosts[2:4]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group2)

    host_inventory.apis.groups.remove_hosts_from_multiple_groups(hosts[:4])

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)


def test_kessel_repl_patch_group_add_hosts(
    host_inventory: ApplicationHostInventory,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
    prepare_hosts: list[HostOut],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that adding hosts to group via PATCH is reflected correctly in kessel
    """
    hosts = prepare_hosts[:3]
    group = host_inventory.apis.groups.create_group(generate_display_name())

    host_inventory.apis.groups.patch_group(group, hosts=hosts)

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)


def test_kessel_repl_patch_group_remove_hosts(
    host_inventory: ApplicationHostInventory,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
    prepare_hosts: list[HostOut],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that removing hosts from group via PATCH is reflected correctly in kessel
    """
    hosts = prepare_hosts[:3]
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)

    host_inventory.apis.groups.patch_group(group, hosts=[])

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)


def test_kessel_repl_patch_group_change_hosts(
    host_inventory: ApplicationHostInventory,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
    prepare_hosts: list[HostOut],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that changing hosts in group via PATCH is reflected correctly in kessel
    """
    hosts = prepare_hosts

    # Add first 4 hosts to group
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[:4])
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    for host in hosts[:4]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)

    for host in hosts[4:]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)

    # Remove 2 hosts from the group and add 2 new hosts to the group at the same time
    host_inventory.apis.groups.patch_group(group, hosts=hosts[2:6])

    for host in hosts[2:6]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, group)

    for host in hosts[:2] + hosts[6:]:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)


def test_kessel_repl_delete_group(
    host_inventory: ApplicationHostInventory,
    hbi_kessel_relations_grpc: HBIKesselRelationsGRPC,
    prepare_hosts: list[HostOut],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19245

    metadata:
      requirements: inv-kessel-hosts
      assignee: fstavela
      importance: high
      title: Verify that deleting group is reflected correctly in kessel
    """
    hosts = prepare_hosts[:3]
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    host_inventory.apis.groups.delete_groups(group)

    for host in hosts:
        hbi_kessel_relations_grpc.verify_created_or_updated(host, ungrouped_group)


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


def test_kessel_get_single_non_existent_host(host_inventory: ApplicationHostInventory) -> None:
    """
    metadata:
      requirements: inv-kessel-hosts
      assignee: aprice
      importance: medium
      negative: true
      title: Verify that getting a single non-existent host returns 404 with not_found_ids
    """
    non_existent_host_id = generate_uuid()

    with raises_apierror(404, match_message="One or more hosts not found.") as exc:
        host_inventory.apis.hosts.get_hosts_by_id_response(non_existent_host_id)

    # Verify that the response body includes the not_found_ids field
    response_body = json.loads(exc.value.body)
    assert "not_found_ids" in response_body, "Expected 'not_found_ids' in response body"
    assert non_existent_host_id in response_body["not_found_ids"], (
        f"Expected '{non_existent_host_id}' in not_found_ids, got {response_body['not_found_ids']}"
    )


def test_kessel_get_mixed_existent_and_non_existent_hosts(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    metadata:
      requirements: inv-kessel-hosts
      assignee: aprice
      importance: medium
      negative: true
      title: Verify that getting a mix of existent and non-existent hosts returns 404
             with only the non-existent ID in not_found_ids
    """
    # Create a real host
    existing_host = host_inventory.upload.create_hosts(1)[0]
    non_existent_host_id = generate_uuid()

    with raises_apierror(404, match_message="One or more hosts not found.") as exc:
        host_inventory.apis.hosts.get_hosts_by_id_response([
            existing_host.id,
            non_existent_host_id,
        ])

    # Verify that the response body includes only the non-existent ID in not_found_ids
    response_body = json.loads(exc.value.body)
    assert "not_found_ids" in response_body, "Expected 'not_found_ids' in response body"
    assert non_existent_host_id in response_body["not_found_ids"], (
        f"Expected '{non_existent_host_id}' in not_found_ids, got {response_body['not_found_ids']}"
    )
    assert existing_host.id not in response_body["not_found_ids"], (
        f"Existing host ID '{existing_host.id}' should not be in not_found_ids"
    )
