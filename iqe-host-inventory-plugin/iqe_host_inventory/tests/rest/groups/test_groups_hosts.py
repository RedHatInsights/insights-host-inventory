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
