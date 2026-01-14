from __future__ import annotations

import logging
from datetime import UTC
from datetime import datetime

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.utils.api_utils import is_ungrouped_host
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


def test_groups_remove_hosts_from_multiple_groups_response(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups
      assignee: fstavela
      importance: high
      title: Test response for DELETE /groups/hosts/<host_ids> endpoint
    """
    host = host_inventory.upload.create_host()
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    response = host_inventory.apis.groups.raw_api.api_group_delete_hosts_from_different_groups_with_http_info(  # noqa
        [host.id]
    )
    assert response[1] == 204


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_check_timestamps(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups
      assignee: fstavela
      importance: medium
      title: Test that `updated` timestamp gets updated after
             DELETE /groups/hosts/<host_ids> request
    """
    host = host_inventory.kafka.create_host()

    time1 = datetime.now(tz=UTC)
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)
    time2 = datetime.now(tz=UTC)

    host_inventory.apis.groups.remove_hosts_from_multiple_groups(host)
    time3 = datetime.now(tz=UTC)

    updated_group = host_inventory.apis.groups.get_group_by_id(group)

    assert updated_group.id == group.id
    logger.info(f"time1: {time1}")
    logger.info(f"time2: {time2}")
    logger.info(f"time3: {time3}")
    logger.info(f"created: {updated_group.created}")
    logger.info(f"updated: {updated_group.updated}")
    assert time1 < updated_group.created < time2
    assert time2 < updated_group.updated < time3


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_single_host(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups
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
      requirements: inv-groups-remove-hosts-multiple-groups
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
      requirements: inv-groups-remove-hosts-multiple-groups
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
      requirements: inv-groups-remove-hosts-multiple-groups
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


def test_groups_remove_hosts_from_multiple_groups_non_existing_host(host_inventory):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups
      assignee: fstavela
      importance: low
      negative: true
      title: Test removing non-existing host from group by using
             DELETE /groups/hosts/<host_ids> endpoint
    """
    with raises_apierror(404, "One or more hosts not found."):
        host_inventory.apis.groups.remove_hosts_from_multiple_groups(
            generate_uuid(), wait_for_removed=False
        )


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_good_and_non_existing_hosts(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups
      assignee: fstavela
      importance: medium
      title: Test removing grouped and non-existing hosts from groups by using
             DELETE /groups/hosts/<host_ids> endpoint
    """
    hosts = host_inventory.kafka.create_random_hosts(2)
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts)

    with raises_apierror(404):
        host_inventory.apis.groups.remove_hosts_from_multiple_groups(
            [hosts[0].id, generate_uuid()], wait_for_removed=False
        )


@pytest.mark.parametrize(
    "host_id",
    (
        pytest.param([], id="empty list"),
        pytest.param({}, id="empty dict"),
        pytest.param(1, id="int"),
        pytest.param(1.5, id="float"),
        pytest.param(generate_uuid() + "a", id="bad uuid"),
        pytest.param(generate_string_of_length(36, use_punctuation=False), id="random string"),
        pytest.param(True, id="True"),
        pytest.param(False, id="False"),
        pytest.param("None", id="None"),
    ),
)
def test_groups_remove_hosts_from_multiple_groups_bad_host_id(
    host_inventory: ApplicationHostInventory, host_id
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups
      assignee: fstavela
      importance: low
      negative: true
      title: Test bad host IDs on DELETE /groups/hosts/<host_ids> endpoint
    """
    with raises_apierror(400, (f"{host_id}", " does not match ")):
        host_inventory.apis.groups.raw_api.api_group_delete_hosts_from_different_groups([host_id])


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_good_and_bad_host_id(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups
      assignee: fstavela
      importance: medium
      negative: true
      title: Test good and bad host IDs on DELETE /groups/hosts/<host_ids> endpoint
    """
    host = host_inventory.kafka.create_host()
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)
    bad_id = generate_uuid() + "a"

    with raises_apierror(400, (f"{bad_id}", " does not match ")):
        host_inventory.apis.groups.raw_api.api_group_delete_hosts_from_different_groups([
            host.id,
            bad_id,
        ])

    host_inventory.apis.groups.verify_not_updated(group, hosts=host)


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_multiple_groups_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-1655

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups
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
      requirements: inv-groups-remove-hosts-multiple-groups
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

    host_inventory.apis.groups.verify_not_updated(group_primary, hosts=[])
    host_inventory_secondary.apis.groups.verify_not_updated(group_secondary, hosts=host_secondary)
