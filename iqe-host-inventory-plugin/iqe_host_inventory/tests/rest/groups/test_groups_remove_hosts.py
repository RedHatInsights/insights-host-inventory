import logging
from datetime import UTC
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.tests.rest.validation.test_system_profile import INCORRECT_CANONICAL_UUIDS
from iqe_host_inventory.utils.api_utils import api_disabled_validation
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def test_groups_remove_host(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      requirements: inv-groups-remove-hosts
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
def test_groups_remove_hosts_check_timestamps(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      requirements: inv-groups-remove-hosts
      assignee: fstavela
      importance: medium
      title: Test that `updated` timestamp gets updated after
             DELETE /groups/{group_id}/hosts/{host_id_list} request
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)
    time2 = datetime.now(tz=UTC)

    host_inventory.apis.groups.remove_hosts_from_group(group, hosts[1])
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
def test_groups_remove_multiple_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      requirements: inv-groups-remove-hosts
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
      requirements: inv-groups-remove-hosts
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
def test_groups_remove_hosts_not_belong_to_group(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      requirements: inv-groups-remove-hosts
      assignee: zabikeno
      importance: high
      negative: true
      title: Try to remove host that not belong to target group
    """
    hosts = host_inventory.kafka.create_random_hosts(2)

    group_name1 = generate_display_name()
    group1 = host_inventory.apis.groups.create_group(group_name1, hosts=hosts[0])
    group_name2 = generate_display_name()
    group2 = host_inventory.apis.groups.create_group(group_name2, hosts=hosts[1])

    # TODO: Switch the next 2 lines when https://issues.redhat.com/browse/RHINENG-17234 is done
    # with raises_apierror(404, match_message="Hosts not found."):
    with raises_apierror(404):
        host_inventory.apis.groups.remove_hosts_from_group(
            group1, hosts[1], wait_for_removed=False
        )

    # ensure host wasn't removed from groups
    host_inventory.apis.groups.verify_not_updated(group1, hosts=hosts[0])
    host_inventory.apis.groups.verify_not_updated(group2, hosts=hosts[1])


@pytest.mark.ephemeral
@pytest.mark.parametrize("wrong_value", [[], {}], ids=["empty list", "empty dict"])
@pytest.mark.parametrize("field", ["group_id", "host_id_list"])
def test_groups_remove_host_with_wrong_type_id(
    host_inventory: ApplicationHostInventory,
    wrong_value: list | dict,
    field: str,
):
    """
    metadata:
        requirements: inv-groups-remove-hosts
        assignee: zabikeno
        importance: low
        negative: true
        title: Inventory: Confirm removing host from group with wrong type host_ids/group_id does
            not remove anything.
    """
    host = host_inventory.kafka.create_host()

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=host)
    err_msgs: tuple[str, ...]
    params = {
        "group_id": wrong_value if field == "group_id" else group.id,
        "host_id_list": wrong_value if field == "host_id_list" else [host.id],
    }

    if field == "group_id":
        status = 400
        err_msgs = (str(wrong_value), "does not match")
    else:
        status = 405
        err_msgs = ("Method Not Allowed",)

    with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
        with raises_apierror(status, match_message=err_msgs):
            api.api_host_group_delete_hosts_from_group(**params)

    host_inventory.apis.groups.verify_not_updated(group, hosts=host)


@pytest.mark.ephemeral
@pytest.mark.parametrize("invalid_host_id", INCORRECT_CANONICAL_UUIDS)
def test_groups_remove_hosts_with_invalid_id(
    host_inventory: ApplicationHostInventory, invalid_host_id: Any
):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      requirements: inv-groups-remove-hosts
      assignee: zabikeno
      importance: high
      negative: true
      title: Remove host with invalid id from group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    # Put one invalid host_id in the mix
    bad_host_id_list = [host.id for host in hosts]
    bad_host_id_list[1] = invalid_host_id
    err_msgs: tuple[str, ...]
    try:
        UUID(invalid_host_id)
    except (ValueError, AttributeError):
        if "á" in invalid_host_id:
            err_msgs = (invalid_host_id.replace("á", "\\u00e1"), " does not match ")
        else:
            err_msgs = (str(invalid_host_id), " does not match ")
    else:
        if invalid_host_id.isupper():
            pytest.skip("This is tested in test_groups_remove_not_existing_host")
        err_msgs = (f"'{invalid_host_id}' is not a 'uuid'",)

    with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
        with raises_apierror(400, match_message=err_msgs):
            api.api_host_group_delete_hosts_from_group(group.id, bad_host_id_list)

    host_inventory.apis.groups.verify_not_updated(group, hosts=hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("invalid_group_id", INCORRECT_CANONICAL_UUIDS)
def test_groups_remove_host_from_group_with_invalid_id(
    host_inventory: ApplicationHostInventory, invalid_group_id: Any
):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      requirements: inv-groups-remove-hosts
      assignee: zabikeno
      importance: high
      negative: true
      title: Remove host from group with invalid id
    """
    host = host_inventory.kafka.create_host()
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=host)
    err_msgs: tuple[str, ...]
    try:
        UUID(invalid_group_id)
    except (ValueError, AttributeError):
        if "á" in invalid_group_id:
            err_msgs = (invalid_group_id.replace("á", "\\u00e1"), " does not match ")
        else:
            if invalid_group_id == "":
                pytest.skip("This is tested in test_groups_remove_host_with_wrong_type_id")
            err_msgs = (str(invalid_group_id), " does not match ")
    else:
        if invalid_group_id.isupper():
            pytest.skip("This is tested in test_groups_remove_host_from_non_existing_group")
        err_msgs = (f"'{invalid_group_id}' is not a 'uuid'",)

    with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
        with raises_apierror(400, match_message=err_msgs):
            api.api_host_group_delete_hosts_from_group(invalid_group_id, [host.id])

    host_inventory.apis.groups.verify_not_updated(group, hosts=host)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "group_id",
    [generate_uuid(), generate_uuid().upper()],
    ids=["random uuid", "random uuid upper"],
)
def test_groups_remove_host_from_non_existing_group(
    host_inventory: ApplicationHostInventory,
    group_id: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      requirements: inv-groups-remove-hosts
      assignee: zabikeno
      importance: high
      negative: true
      title: Remove host from non existing group (invalid id)
    """
    host = host_inventory.kafka.create_host()
    response_hosts_before = host_inventory.apis.hosts.get_hosts_response().total

    with raises_apierror(404):
        host_inventory.apis.groups.remove_hosts_from_group(group_id, host, wait_for_removed=False)

    # ensure same amount of host left after failed request
    response_hosts_after = host_inventory.apis.hosts.get_hosts_response()
    assert response_hosts_before == response_hosts_after.total


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "host_id",
    [generate_uuid(), generate_uuid().upper()],
    ids=["random uuid", "random uuid upper"],
)
def test_groups_remove_not_existing_host(host_inventory: ApplicationHostInventory, host_id: str):
    """
    https://issues.redhat.com/browse/ESSNTL-3853

    metadata:
      requirements: inv-groups-remove-hosts
      assignee: zabikeno
      importance: high
      negative: true
      title: Remove non existing host from group
    """
    host = host_inventory.kafka.create_host()

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=host)

    # TODO: Switch the next 2 lines when https://issues.redhat.com/browse/RHINENG-17234 is done
    # with raises_apierror(404, match_message="Hosts not found."):
    with raises_apierror(404):
        host_inventory.apis.groups.remove_hosts_from_group(group, host_id, wait_for_removed=False)

    # ensure host wasn't removed from group
    host_inventory.apis.groups.verify_not_updated(group, hosts=host)


@pytest.mark.ephemeral
def test_groups_remove_hosts_from_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    metadata:
        requirements: inv-groups-remove-hosts
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
        requirements: inv-groups-remove-hosts
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
