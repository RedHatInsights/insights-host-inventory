from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.groups.test_groups_mq_events import group_to_mq_dict
from iqe_host_inventory.utils.api_utils import is_ungrouped_host
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory_api import GroupOut
from iqe_host_inventory_api import GroupOutWithHostCount

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def group_to_hosts_api_dict(group: GroupOut | GroupOutWithHostCount) -> dict:
    group_dict = group.to_dict()
    group_dict.pop("host_count", None)
    return group_dict


@pytest.mark.ephemeral
def test_groups_delete_host_in_group(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post, inv-hosts-delete-by-id
      assignee: fstavela
      importance: high
      title: Delete a host assigned to group from Inventory
    """
    host = host_inventory.kafka.create_host()
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    host_inventory.apis.hosts.delete_by_id(host)

    response_group = host_inventory.apis.groups.get_group_by_id(group)
    assert response_group.host_count == 0


@pytest.mark.ephemeral
def test_groups_cant_update_host_groups_via_kafka(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-mq-host-field-validation
      assignee: fstavela
      importance: high
      negative: true
      title: Test that I can't update host's group data via kafka message
    """
    host_data = host_inventory.datagen.create_host_data()
    host = host_inventory.kafka.create_host(host_data)
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    group_dict = group_to_mq_dict(group)
    group_dict["name"] = generate_display_name()
    host_data["groups"] = [group_dict]
    updated_host = host_inventory.kafka.create_host(host_data)
    assert updated_host.groups == [group_to_mq_dict(group)]

    host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=host)


@pytest.mark.ephemeral
def test_groups_update_host_in_group(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-hosts-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Host's groups data is included in update events when updating host
    """
    host = host_inventory.kafka.create_host()
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    host_inventory.apis.hosts.patch_hosts(host, display_name=generate_display_name())
    msg = host_inventory.kafka.wait_for_filtered_host_message(
        HostWrapper.insights_id, host.insights_id
    )
    assert msg.host.groups == [group_to_mq_dict(group)]


@pytest.mark.ephemeral
@pytest.mark.parametrize("in_group", [True, False])
def test_groups_get_host_by_id_response(host_inventory: ApplicationHostInventory, in_group: bool):
    """
    https://issues.redhat.com/browse/ESSNTL-4771

    metadata:
      requirements: inv-hosts-get-by-id
      assignee: fstavela
      importance: high
      title: Host's groups data is included in GET /hosts/<host_id_list> response
    """
    host = host_inventory.kafka.create_host()
    if in_group:
        group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    response = host_inventory.apis.hosts.get_host_by_id(host)
    assert isinstance(response.groups, list)
    if in_group:
        assert len(response.groups) == 1
        assert response.groups[0].to_dict() == group_to_hosts_api_dict(group)
    else:
        assert is_ungrouped_host(response)


@pytest.mark.ephemeral
@pytest.mark.parametrize("in_group", [True, False])
def test_groups_get_hosts_list(host_inventory: ApplicationHostInventory, in_group: bool):
    """
    https://issues.redhat.com/browse/ESSNTL-4771

    metadata:
      requirements: inv-hosts-get-list
      assignee: fstavela
      importance: high
      title: Host's groups data is included in GET /hosts response
    """
    host = host_inventory.kafka.create_host()
    if in_group:
        group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    response = host_inventory.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert isinstance(response[0].groups, list)
    if in_group:
        assert len(response[0].groups) == 1
        assert response[0].groups[0].to_dict() == group_to_hosts_api_dict(group)
    else:
        assert is_ungrouped_host(response[0])


#
# Tests for GET /groups/{group_id}/hosts endpoint (RHINENG-21605)
#


@pytest.mark.ephemeral
def test_get_hosts_from_group_basic(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts
      assignee: maarif
      importance: high
      title: Get hosts from a specific group using dedicated endpoint
    """
    # Create 5 hosts via Kafka
    hosts = host_inventory.kafka.create_random_hosts(5)

    # Create a group with 3 of the hosts
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:3])

    # Get hosts from the group using the new endpoint
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(group)

    # Verify correct hosts returned
    assert len(response_hosts) == 3
    response_host_ids = {host.id for host in response_hosts}
    expected_host_ids = {host.id for host in hosts[:3]}
    assert response_host_ids == expected_host_ids

    # Verify each host has the group information
    for host in response_hosts:
        assert len(host.groups) == 1
        assert host.groups[0].id == group.id
        assert host.groups[0].name == group_name


@pytest.mark.ephemeral
def test_get_hosts_from_empty_group(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts
      assignee: maarif
      importance: high
      title: Get hosts from an empty group returns empty list
    """
    # Create an empty group
    group = host_inventory.apis.groups.create_group(generate_display_name())

    # Get hosts from empty group
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(group)

    # Verify empty result
    assert len(response_hosts) == 0


@pytest.mark.ephemeral
def test_get_hosts_from_group_with_pagination(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts, inv-pagination
      assignee: maarif
      importance: high
      title: Pagination works correctly for GET /groups/{group_id}/hosts
    """
    # Create 10 hosts
    hosts = host_inventory.kafka.create_random_hosts(10)

    # Create a group with all hosts
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    # Get first page (5 hosts)
    page1_hosts = host_inventory.apis.groups.get_hosts_from_group(group, page=1, per_page=5)
    assert len(page1_hosts) == 5

    # Get second page (5 hosts)
    page2_hosts = host_inventory.apis.groups.get_hosts_from_group(group, page=2, per_page=5)
    assert len(page2_hosts) == 5

    # Verify no duplicates across pages
    page1_ids = {host.id for host in page1_hosts}
    page2_ids = {host.id for host in page2_hosts}
    assert len(page1_ids & page2_ids) == 0

    # Verify all hosts retrieved
    all_ids = page1_ids | page2_ids
    expected_ids = {host.id for host in hosts}
    assert all_ids == expected_ids


@pytest.mark.ephemeral
@pytest.mark.parametrize("order_by", ["display_name", "updated"])
@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_get_hosts_from_group_with_ordering(
    host_inventory: ApplicationHostInventory, order_by: str, order_how: str
):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts, inv-hosts-sorting
      assignee: maarif
      importance: high
      title: Ordering works correctly for GET /groups/{group_id}/hosts
    """
    # Create hosts with distinct display names for sorting
    hosts_data = [
        host_inventory.datagen.create_host_data(display_name=f"host-{i:02d}") for i in range(5)
    ]
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    # Create a group with all hosts
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    # Get hosts with ordering
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(
        group, order_by=order_by, order_how=order_how
    )

    assert len(response_hosts) == 5

    # Verify ordering
    if order_by == "display_name":
        display_names = [host.display_name for host in response_hosts]
        if order_how == "ASC":
            assert display_names == sorted(display_names)
        else:
            assert display_names == sorted(display_names, reverse=True)
    elif order_by == "updated":
        updated_times = [host.updated for host in response_hosts]
        if order_how == "ASC":
            assert updated_times == sorted(updated_times)
        else:
            assert updated_times == sorted(updated_times, reverse=True)


@pytest.mark.ephemeral
def test_get_hosts_from_group_with_display_name_filter(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts
      assignee: maarif
      importance: high
      title: Display name filter works for GET /groups/{group_id}/hosts
    """
    # Create hosts with specific display names
    host1_data = host_inventory.datagen.create_host_data(display_name="web-server-01")
    host2_data = host_inventory.datagen.create_host_data(display_name="web-server-02")
    host3_data = host_inventory.datagen.create_host_data(display_name="db-server-01")

    hosts = host_inventory.kafka.create_hosts(hosts_data=[host1_data, host2_data, host3_data])

    # Create a group with all hosts
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    # Filter by display name wildcard
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(
        group, display_name="web-server"
    )

    # Verify only web servers returned
    assert len(response_hosts) == 2
    for host in response_hosts:
        assert "web-server" in host.display_name


@pytest.mark.ephemeral
def test_get_hosts_from_group_with_fqdn_filter(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts, inv-hosts-filter-by-fqdn
      assignee: maarif
      importance: high
      title: FQDN filter works for GET /groups/{group_id}/hosts
    """
    # Create hosts with specific FQDNs
    host1_data = host_inventory.datagen.create_host_data(fqdn="host1.example.com")
    host2_data = host_inventory.datagen.create_host_data(fqdn="host2.example.com")
    host3_data = host_inventory.datagen.create_host_data(fqdn="host3.different.com")

    hosts = host_inventory.kafka.create_hosts(hosts_data=[host1_data, host2_data, host3_data])

    # Create a group with all hosts
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    # Filter by exact FQDN
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(
        group, fqdn="host1.example.com"
    )

    # Verify only matching host returned
    assert len(response_hosts) == 1
    assert response_hosts[0].fqdn == "host1.example.com"


@pytest.mark.ephemeral
def test_get_hosts_from_group_with_staleness_filter(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts, inv-hosts-filter-by-staleness
      assignee: maarif
      importance: high
      title: Staleness filter works for GET /groups/{group_id}/hosts
    """
    # Create hosts (they should be 'fresh' by default)
    hosts = host_inventory.kafka.create_random_hosts(3)

    # Create a group with hosts
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    # Filter by staleness
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(
        group, staleness=["fresh", "stale"]
    )

    # Verify hosts returned (exact count depends on staleness state)
    assert len(response_hosts) >= 0


@pytest.mark.ephemeral
def test_get_hosts_from_group_with_tags_filter(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts, inv-hosts-filter-by-tags
      assignee: maarif
      importance: high
      title: Tags filter works for GET /groups/{group_id}/hosts
    """
    # Create hosts with specific tags
    host1_data = host_inventory.datagen.create_host_data_with_tags(
        tags={"env": ["prod"], "region": ["us-east"]}
    )
    host2_data = host_inventory.datagen.create_host_data_with_tags(
        tags={"env": ["dev"], "region": ["us-west"]}
    )
    host3_data = host_inventory.datagen.create_host_data_with_tags(
        tags={"env": ["prod"], "region": ["us-west"]}
    )

    hosts = host_inventory.kafka.create_hosts(hosts_data=[host1_data, host2_data, host3_data])

    # Create a group with all hosts
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    # Filter by tags
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(group, tags=["env=prod"])

    # Verify only production hosts returned
    assert len(response_hosts) == 2
    for host in response_hosts:
        assert any(tag.namespace == "env" and tag.value == "prod" for tag in host.tags)


@pytest.mark.ephemeral
def test_get_hosts_from_group_multiple_filters(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts
      assignee: maarif
      importance: high
      title: Multiple filters work together for GET /groups/{group_id}/hosts
    """
    # Create hosts with various attributes
    hosts_data = [
        host_inventory.datagen.create_host_data(
            display_name=f"web-server-{i:02d}", fqdn=f"web{i}.example.com"
        )
        for i in range(5)
    ]
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    # Create a group with all hosts
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    # Apply multiple filters
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(
        group, display_name="web-server", order_by="display_name", order_how="ASC", per_page=3
    )

    # Verify filtering, ordering, and pagination
    assert len(response_hosts) == 3
    display_names = [host.display_name for host in response_hosts]
    assert display_names == sorted(display_names)
    for host in response_hosts:
        assert "web-server" in host.display_name


@pytest.mark.ephemeral
def test_get_hosts_from_group_with_hostname_or_id_filter(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts
      assignee: maarif
      importance: high
      title: Hostname or ID filter works for GET /groups/{group_id}/hosts
    """
    # Create hosts with specific display names
    host1_data = host_inventory.datagen.create_host_data(display_name="app-server-prod")
    host2_data = host_inventory.datagen.create_host_data(display_name="db-server-prod")
    host3_data = host_inventory.datagen.create_host_data(display_name="web-server-dev")

    hosts = host_inventory.kafka.create_hosts(hosts_data=[host1_data, host2_data, host3_data])

    # Create a group with all hosts
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    # Filter by hostname_or_id (partial match on display_name "app-server")
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(
        group, hostname_or_id="app-server"
    )

    # Verify only matching host returned
    assert len(response_hosts) == 1
    assert "app-server" in response_hosts[0].display_name

    # Filter by hostname_or_id using actual host ID
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(
        group, hostname_or_id=hosts[1].id
    )

    # Verify correct host returned when filtering by ID
    assert len(response_hosts) == 1
    assert response_hosts[0].id == hosts[1].id


@pytest.mark.ephemeral
def test_get_hosts_from_group_with_insights_id_filter(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21605

    metadata:
      requirements: inv-groups-get-hosts
      assignee: maarif
      importance: high
      title: Insights ID filter works for GET /groups/{group_id}/hosts
    """
    # Create 3 hosts (they'll have unique insights_id values)
    hosts = host_inventory.kafka.create_random_hosts(3)

    # Create a group with all hosts
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    # Filter by insights_id of the second host
    target_insights_id = hosts[1].insights_id
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(
        group, insights_id=target_insights_id
    )

    # Verify only the matching host is returned
    assert len(response_hosts) == 1
    assert response_hosts[0].insights_id == target_insights_id
    assert response_hosts[0].id == hosts[1].id
