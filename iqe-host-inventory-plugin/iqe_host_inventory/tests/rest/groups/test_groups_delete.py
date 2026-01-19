import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.tests.rest.validation.test_system_profile import EMPTY_BASICS
from iqe_host_inventory.utils.api_utils import api_disabled_validation
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def test_groups_delete_empty_group(host_inventory: ApplicationHostInventory):
    """
    metadata:
        requirements: inv-groups-delete
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
        requirements: inv-groups-delete
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
        requirements: inv-groups-delete
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


@pytest.mark.parametrize("single_group", [True, False], ids=["Single group", "Multiple groups"])
@pytest.mark.parametrize(
    "invalid_group_id",
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
def test_groups_delete_group_with_invalid_id(
    host_inventory: ApplicationHostInventory, single_group, invalid_group_id
):
    """
    metadata:
        requirements: inv-groups-delete
        assignee: zabikeno
        importance: low
        negative: true
        title: Inventory: Confirm deletion of group with an invalid id does not
            delete anything.
    """
    group_name1 = generate_display_name()
    group1 = host_inventory.apis.groups.create_group(group_name1)
    groups_to_delete = [group1]
    if not single_group:
        group_name2 = generate_display_name()
        group_name3 = generate_display_name()
        group2 = host_inventory.apis.groups.create_group(group_name2)
        group3 = host_inventory.apis.groups.create_group(group_name3)
        groups_to_delete = [group1, group2, group3]

    err_msgs = (str(invalid_group_id), "does not match")

    # Put one invalid groups_id in the mix
    if single_group:
        bad_group_id_list = [invalid_group_id]
    else:
        bad_group_id_list = [group.id for group in groups_to_delete]
        bad_group_id_list[1] = invalid_group_id

    with host_inventory.apis.groups.verify_group_count_not_changed():
        with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
            with raises_apierror(400, match_message=err_msgs):
                api.api_group_delete_groups(bad_group_id_list)

    # ensure groups are not deleted
    host_inventory.apis.groups.verify_not_deleted(groups_to_delete)


@pytest.mark.ephemeral
@pytest.mark.parametrize("wrong_value", EMPTY_BASICS)
def test_groups_delete_group_with_wrong_type_id(
    host_inventory: ApplicationHostInventory, wrong_value
):
    """
    Note: The Stage/Prod gateway doesn't like HTTP error 405 and can't forward
    a request/response.

    metadata:
        requirements: inv-groups-delete
        assignee: zabikeno
        importance: low
        negative: true
        title: Inventory: Confirm deletion of group with wrong type group_id_list does not
            delete anything.
    """
    with host_inventory.apis.groups.verify_group_count_not_changed():
        with raises_apierror(405, match_message="Method Not Allowed"):
            host_inventory.apis.groups.raw_api.api_group_delete_groups(group_id_list=wrong_value)


@pytest.mark.parametrize(
    "group_id",
    [generate_uuid(), generate_uuid().upper()],
    ids=["random uuid", "random uuid upper"],
)
def test_groups_delete_non_existing_group(host_inventory: ApplicationHostInventory, group_id):
    """
    metadata:
        requirements: inv-groups-delete
        assignee: zabikeno
        importance: low
        negative: true
        title: Inventory: Confirm deletion of no existing group does not
            delete anything.
    """
    with host_inventory.apis.groups.verify_group_count_not_changed():
        with raises_apierror(404, match_message="One or more groups not found."):
            host_inventory.apis.groups.raw_api.api_group_delete_groups([group_id])


@pytest.mark.parametrize("invalid_group_id", ["group", "78", "1.223434"])
def test_groups_delete_not_valid_and_existing_group(
    host_inventory: ApplicationHostInventory, invalid_group_id
):
    """
    metadata:
        requirements: inv-groups-delete
        assignee: zabikeno
        importance: low
        negative: true
        title: Inventory: Confirm deletion of not valid group and existing group
            in the same request does not delete anything.
    """
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)

    bad_group_list = [invalid_group_id, group.id]

    with host_inventory.apis.groups.verify_group_count_not_changed():
        with raises_apierror(400, match_message=(invalid_group_id, "does not match")):
            host_inventory.apis.groups.raw_api.api_group_delete_groups(bad_group_list)

    # ensure group wasn't deleted from db
    host_inventory.apis.groups.verify_not_deleted(group)


@pytest.mark.ephemeral
def test_groups_delete_group_from_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    metadata:
        requirements: inv-groups-delete
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

    with raises_apierror(404, match_message="One or more groups not found."):
        host_inventory.apis.groups.raw_api.api_group_delete_groups([group_secondary.id])

    # ensure groups weren't deleted from db
    host_inventory.apis.groups.verify_not_deleted(group_primary)
    host_inventory_secondary.apis.groups.verify_not_deleted(group_secondary)
