import logging
from datetime import UTC
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.tests.rest.validation.test_system_profile import INCORRECT_CANONICAL_UUIDS
from iqe_host_inventory.utils.api_utils import api_disabled_validation
from iqe_host_inventory.utils.api_utils import is_ungrouped_host
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_digits
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_sp_field_value
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_timestamp
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_sp_field_by_name
from iqe_host_inventory_api.models import GroupOutWithHostCount

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def test_groups_add_hosts_response(
    host_inventory: ApplicationHostInventory,
    hbi_default_org_id: str,
    hbi_default_account_number: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: medium
      title: Test response for POST /groups/<group_id>/hosts request
    """
    hosts = host_inventory.upload.create_hosts(3)

    group_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    time2 = datetime.now(tz=UTC)

    data = [host.id for host in hosts[1:]]
    response = (
        host_inventory.apis.groups.raw_api.api_host_group_add_host_list_to_group_with_http_info(
            group.id, data
        )
    )
    time3 = datetime.now(tz=UTC)

    assert response[1] == 200
    updated_group: GroupOutWithHostCount = response[0]

    assert updated_group.id == group.id
    assert updated_group.name == group_name
    assert updated_group.host_count == len(hosts)
    assert updated_group.org_id == hbi_default_org_id
    # Skip for now since RBAC doesn't have the account number for some orgs.
    # See https://redhat-internal.slack.com/archives/C08T01AK7U6/p1753117255488139
    # assert updated_group.account == hbi_default_account_number
    assert updated_group.ungrouped is False
    assert time1 < updated_group.created < time2
    assert time2 < updated_group.updated < time3


@pytest.mark.ephemeral
def test_groups_add_hosts_check_timestamps(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: medium
      title: Test that `updated` timestamp gets updated after POST /groups/<group_id>/hosts request
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    time2 = datetime.now(tz=UTC)

    host_inventory.apis.groups.add_hosts_to_group(group, hosts[1:])
    time3 = datetime.now(tz=UTC)

    updated_group = host_inventory.apis.groups.get_group_by_id(group)

    assert updated_group.id == group.id
    assert time1 < updated_group.created < time2
    assert time2 < updated_group.updated < time3


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3], ids=["add single host", "add multiple hosts"])
@pytest.mark.parametrize("with_hosts", [False, True], ids=["empty", "with hosts"])
@pytest.mark.parametrize("host_type", ["conventional", "edge", "image-mode"])
def test_groups_add_hosts(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    with_hosts: bool,
    host_type: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: high
      title: Add hosts to group via POST request
    """
    sp_bootc = get_sp_field_by_name("bootc_status")
    hosts_data = host_inventory.datagen.create_n_hosts_data(4)

    if host_type == "edge":
        for i in range(1, 4):
            hosts_data[i]["system_profile"]["host_type"] = "edge"
    if host_type == "image-mode":
        for i in range(1, 4):
            hosts_data[i]["system_profile"]["bootc_status"] = generate_sp_field_value(sp_bootc)

    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    group_name = generate_display_name()
    pre_added_hosts = [hosts[0]] if with_hosts else []
    group = host_inventory.apis.groups.create_group(group_name, hosts=pre_added_hosts)

    hosts_to_add = hosts[1 : 1 + how_many]
    expected_hosts_ids = {host.id for host in pre_added_hosts + hosts_to_add}
    response = host_inventory.apis.groups.add_hosts_to_group(
        group, hosts_to_add, wait_for_added=False
    )
    assert response.id == group.id
    assert response.name == group_name
    assert response.host_count == len(expected_hosts_ids)

    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=expected_hosts_ids)


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [False, True], ids=["empty", "with hosts"])
def test_groups_add_hosts_empty_list(host_inventory: ApplicationHostInventory, with_hosts: bool):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: medium
      title: Send empty list of Host IDs to POST /groups/<group_id>/hosts endpoint
    """
    hosts = host_inventory.kafka.create_random_hosts(3) if with_hosts else []

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    with raises_apierror(
        400, "Body content must be an array with system UUIDs, not an empty array"
    ):
        host_inventory.apis.groups.add_hosts_to_group(group, [], wait_for_added=False)

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", ["one", "all"])
def test_groups_add_hosts_already_in_my_group(
    host_inventory: ApplicationHostInventory, how_many: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: medium
      title: Try to add host that is already in my group to my group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    hosts_to_add = [hosts[1]] if how_many == "one" else hosts

    response = host_inventory.apis.groups.add_hosts_to_group(
        group, hosts_to_add, wait_for_added=False
    )
    assert response.id == group.id
    assert response.name == group_name
    assert response.host_count == len(hosts)

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)


@pytest.mark.ephemeral
def test_groups_add_hosts_good_and_already_in_my_group(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: high
      title: Try to add new host to group together with the one that is already in my group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    hosts_ids = {host.id for host in hosts}

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    new_hosts = host_inventory.kafka.create_random_hosts(2)
    hosts_to_add = [new_hosts[0].id, hosts[1].id, new_hosts[1].id]
    expected_hosts = hosts_ids | set(hosts_to_add)

    response = host_inventory.apis.groups.add_hosts_to_group(
        group, hosts_to_add, wait_for_added=False
    )
    assert response.id == group.id
    assert response.name == group_name
    assert response.host_count == len(expected_hosts)

    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=expected_hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", ["one", "all"])
def test_groups_add_hosts_already_in_different_group(
    host_inventory: ApplicationHostInventory, how_many: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: high
      negative: true
      title: Try to add a host from a different group to my group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)
    group_name2 = generate_display_name()
    group2 = host_inventory.apis.groups.create_group(group_name2)

    hosts_to_add = [hosts[1]] if how_many == "one" else hosts
    with raises_apierror(
        400,
        (
            "The following subset of hosts are already associated with another group: ",
            *[host.id for host in hosts_to_add],
        ),
    ):
        host_inventory.apis.groups.add_hosts_to_group(
            group2, hosts=hosts_to_add, wait_for_added=False
        )

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)
    host_inventory.apis.groups.verify_not_updated(group2, name=group_name2, hosts=[])


@pytest.mark.ephemeral
def test_groups_add_hosts_good_and_already_in_different_group(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: high
      negative: true
      title: Try to add a new host together with a host from a different group to my group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)
    group_name2 = generate_display_name()
    group2 = host_inventory.apis.groups.create_group(group_name2)

    new_hosts = host_inventory.kafka.create_random_hosts(2)
    hosts_to_add = [new_hosts[0], hosts[1], new_hosts[1]]

    with raises_apierror(
        400,
        f"The following subset of hosts are already associated with another group: "
        f"['{hosts[1].id}'].",
    ):
        host_inventory.apis.groups.add_hosts_to_group(
            group2, hosts=hosts_to_add, wait_for_added=False
        )

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)
    host_inventory.apis.groups.verify_not_updated(group2, name=group_name2, hosts=[])


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [False, True], ids=["empty", "with hosts"])
def test_groups_add_hosts_not_existing(host_inventory: ApplicationHostInventory, with_hosts: bool):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: low
      negative: true
      title: Try to add a not existing host to group
    """
    hosts = host_inventory.kafka.create_random_hosts(3) if with_hosts else []

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    new_host = generate_uuid()
    with raises_apierror(400, f"Could not find existing host(s) with ID {{'{new_host}'}}."):
        host_inventory.apis.groups.add_hosts_to_group(group, hosts=new_host, wait_for_added=False)

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)


@pytest.mark.ephemeral
def test_groups_add_hosts_good_and_not_existing(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: low
      negative: true
      title: Try to add a new host together with a not existing host to group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    new_hosts = host_inventory.kafka.create_random_hosts(2)
    hosts_to_add = [new_hosts[0].id, generate_uuid(), new_hosts[1].id]

    with raises_apierror(400, f"Could not find existing host(s) with ID {{'{hosts_to_add[1]}'}}."):
        host_inventory.apis.groups.add_hosts_to_group(
            group, hosts=hosts_to_add, wait_for_added=False
        )

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "host_ids, error_type",
    [
        (generate_uuid(), "list"),
        ([[generate_uuid()]], "string"),
        ([generate_uuid()[:35]], "match"),
        ([generate_uuid() + "a"], "match"),
        ([generate_uuid().replace("-", "_")], "match"),
        ([generate_uuid().replace("-", "")], "uuid"),
        ([generate_string_of_length(36)], "match"),
        ([None], "string"),
        (123, "list"),
        ([123], "string"),
        (False, "list"),
        ([False], "string"),
    ],
    ids=[
        "not a list",
        "list of list",
        "too short",
        "too long",
        "underscores",
        "without dashes",
        "random string",
        "list None",
        "int",
        "list int",
        "bool",
        "list bool",
    ],
)
def test_groups_add_hosts_validate_host_ids_wrong(
    host_inventory: ApplicationHostInventory,
    host_ids,
    error_type: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Try to add host IDs of a wrong format to group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)
    err_msgs: tuple[str, ...]
    if error_type == "list":
        err_msgs = (str(host_ids), " is not of type 'array'")
    elif error_type == "string":
        err_msgs = (str(host_ids[0]), " is not of type 'string'")
    elif error_type == "uuid":
        err_msgs = (f"'{host_ids[0]}' is not a 'uuid'",)
    else:
        host_ids[0] = host_ids[0].replace("'", "").replace('"', "").replace("\\", "")
        err_msgs = (f"'{host_ids[0]}' does not match",)

    with raises_apierror(400, err_msgs):
        host_inventory.apis.groups.raw_api.api_host_group_add_host_list_to_group(
            group.id, host_ids
        )

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


@pytest.mark.ephemeral
def test_groups_add_hosts_good_and_bad(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Try to add one good and one wrong host ID to a group at the same time
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    new_hosts = host_inventory.kafka.create_random_hosts(2)
    bad_id = generate_string_of_length(10).replace("'", "").replace('"', "").replace("\\", "")
    assigned_hosts = [new_hosts[0].id, bad_id, new_hosts[1].id]

    with raises_apierror(400, f"'{bad_id}' does not match "):
        host_inventory.apis.groups.add_hosts_to_group(
            group, hosts=assigned_hosts, wait_for_added=False
        )

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)


@pytest.mark.ephemeral
def test_groups_add_hosts_from_different_account(
    host_inventory: ApplicationHostInventory, host_inventory_secondary: ApplicationHostInventory
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-account-integrity
      assignee: fstavela
      importance: critical
      negative: true
      title: Try to add hosts from different account to group via POST request
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)
    hosts_ids_secondary = {host.id for host in hosts_secondary}

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    with raises_apierror(400, ("Could not find existing host(s) with ID ", *hosts_ids_secondary)):
        host_inventory.apis.groups.add_hosts_to_group(
            group, hosts=hosts_secondary, wait_for_added=False
        )

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)
    response = host_inventory_secondary.apis.hosts.get_hosts_by_id_response(hosts_secondary)
    assert {host.id for host in response.results} == hosts_ids_secondary
    for host in response.results:
        assert is_ungrouped_host(host)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "added_hosts",
    ["same", "my_account", "their_account"],
    ids=["same hosts", "my account hosts", "their account hosts"],
)
def test_groups_add_hosts_to_different_account_group(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    added_hosts: str,
    is_kessel_phase_1_enabled: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-account-integrity
      assignee: fstavela
      importance: critical
      negative: true
      title: Try to add hosts to a group from a different account
    """
    original_hosts = host_inventory_secondary.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group_secondary = host_inventory_secondary.apis.groups.create_group(
        group_name, hosts=original_hosts
    )

    if added_hosts == "my_account":
        updated_hosts = host_inventory.kafka.create_random_hosts(3)
    elif added_hosts == "their_account":
        updated_hosts = host_inventory_secondary.kafka.create_random_hosts(3)
    else:
        updated_hosts = original_hosts

    with host_inventory.apis.groups.verify_group_count_not_changed():
        with host_inventory_secondary.apis.groups.verify_group_count_not_changed():
            error_code = 403 if is_kessel_phase_1_enabled else 404
            with raises_apierror(error_code):
                host_inventory.apis.groups.add_hosts_to_group(
                    group_secondary, hosts=updated_hosts, wait_for_added=False
                )

    host_inventory_secondary.apis.groups.verify_not_updated(
        group_secondary, name=group_name, hosts=original_hosts
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "group_id",
    [generate_uuid(), generate_uuid().upper()],
    ids=["random uuid", "random uuid upper"],
)
def test_groups_add_hosts_not_existing_group(
    host_inventory: ApplicationHostInventory,
    group_id: str,
    is_kessel_phase_1_enabled: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: low
      negative: true
      title: Try to add hosts to a not existing group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    data = [host.id for host in hosts]
    with host_inventory.apis.groups.verify_group_count_not_changed():
        with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
            error_code = 403 if is_kessel_phase_1_enabled else 404
            with raises_apierror(error_code):
                api.api_host_group_add_host_list_to_group(group_id, data)


@pytest.mark.ephemeral
@pytest.mark.parametrize("group_id", INCORRECT_CANONICAL_UUIDS)
def test_groups_add_hosts_validate_group_id_wrong(
    host_inventory: ApplicationHostInventory, group_id: Any
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Try to add hosts to a group with a wrong group ID
    """
    if group_id == "":
        pytest.skip("This is tested in test_groups_add_hosts_not_existing_group")
    hosts = host_inventory.kafka.create_random_hosts(3)
    data = [host.id for host in hosts]
    err_msgs: tuple[str, ...]
    try:
        UUID(group_id)
    except (ValueError, AttributeError):
        if "á" in group_id:
            err_msgs = (group_id.replace("á", "\\u00e1"), " does not match ")
        else:
            err_msgs = (str(group_id), " does not match ")
    else:
        if group_id.isupper():
            pytest.skip("This is tested in test_groups_add_hosts_not_existing_group")
        err_msgs = (f"'{group_id}' is not a 'uuid'",)

    with host_inventory.apis.groups.verify_group_count_not_changed():
        with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
            with raises_apierror(400, err_msgs):
                api.api_host_group_add_host_list_to_group(group_id, data)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "field, value",
    [
        ("id", generate_uuid()),
        ("account", generate_digits(5)),
        ("created_on", generate_timestamp()),
        ("modified_on", generate_timestamp()),
        ("name", generate_display_name()),
        ("field123", "value123"),
    ],
    ids=["id", "account", "created_on", "updated_on", "name", "random field"],
)
def test_groups_add_hosts_validate_protected_fields(
    host_inventory: ApplicationHostInventory, field: str, value: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-api-validation
      assignee: fstavela
      importance: medium
      negative: true
      title: Try to send wrong fields in the POST /groups/<group_id>/hosts endpoint
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)

    data = {field: value}
    with raises_apierror(400, f"{data} is not of type 'array'"):
        host_inventory.apis.groups.raw_api.api_host_group_add_host_list_to_group(group.id, data)

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("org_id", ["same", "different"])
def test_groups_add_hosts_with_changed_org_id(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_default_org_id: str,
    hbi_secondary_org_id: str,
    org_id: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-api-validation
      assignee: fstavela
      importance: high
      negative: true
      title: Try to add hosts to a group with changing the org_id
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)

    value = hbi_default_org_id if org_id == "same" else hbi_secondary_org_id
    data = {"org_id": value}
    with host_inventory_secondary.apis.groups.verify_group_count_not_changed():
        with raises_apierror(400, f"{data} is not of type 'array'"):
            host_inventory.apis.groups.raw_api.api_host_group_add_host_list_to_group(
                group.id, data
            )

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


@pytest.mark.ephemeral
def test_groups_add_hosts_validate_wrong_data_format(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Try to send wrong data format to POST /groups/<group_id>/hosts endpoint
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts[0])

    data = {"host_ids": [host.id for host in hosts[1:]]}
    with raises_apierror(400, f"{data} is not of type 'array'"):
        host_inventory.apis.groups.raw_api.api_host_group_add_host_list_to_group(group.id, data)

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts[0])


@pytest.mark.ephemeral
@pytest.mark.parametrize("data", [None, {}], ids=["None", "empty dict"])
def test_groups_add_hosts_without_data(
    host_inventory: ApplicationHostInventory, data: dict | None
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Try to add hosts to a group without sending any data
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)

    err_msg = "RequestBody is required" if data is None else "{} is not of type 'array'"

    with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
        with raises_apierror(400, err_msg):
            api.api_host_group_add_host_list_to_group(group.id, data)

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


@pytest.mark.ephemeral
def test_groups_add_hosts_the_same_host_multiple_times(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-10846
    https://issues.redhat.com/browse/RHINENG-10845

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: low
      negative: true
      title: Try to add the same host to a group multiple times in the same request
    """
    host = host_inventory.kafka.create_host()
    group = host_inventory.apis.groups.create_group(generate_display_name())
    with raises_apierror(400, "Host IDs must be unique."):
        host_inventory.apis.groups.add_hosts_to_group(
            group, hosts=[host.id, host.id], wait_for_added=False
        )

    host_inventory.apis.groups.verify_not_updated(group, name=group.name)
