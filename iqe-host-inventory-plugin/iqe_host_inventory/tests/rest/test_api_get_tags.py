import logging
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from itertools import combinations

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.datagen_utils import _CORRECT_SYSTEM_TYPE_VALUES
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_tags
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory.utils.tag_utils import assert_tags_not_found

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


@pytest.fixture
def setup_hosts_with_tags(host_inventory: ApplicationHostInventory):
    hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    for data in hosts_data:
        data["display_name"] = generate_display_name()
        data["fqdn"] = generate_display_name()
        data["insights_id"] = generate_uuid()
        data["provider_id"] = generate_uuid()
        data["tags"] = generate_tags()
    hosts_data[0]["provider_type"] = "alibaba"
    hosts_data[1]["provider_type"] = "aws"
    yield host_inventory.kafka.create_hosts(hosts_data=hosts_data)


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_get_all_tags(setup_hosts_with_tags, host_inventory):
    """
    Test GET on /tags endpoint without parameters

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        assignee: fstavela
        importance: high
        title: Inventory: GET on /tags without parameters
    """
    response = host_inventory.apis.tags.get_tags_response()
    body = response.json()
    assert body["count"] >= 2
    assert len(body["results"]) == body["count"]
    assert_tags_found(
        setup_hosts_with_tags[0].tags + setup_hosts_with_tags[1].tags, body["results"]
    )


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("case", ["exact", "lower", "upper"])
def test_get_tags_by_display_name(setup_hosts_with_tags, host_inventory, case):
    """
    Test GET on /tags endpoint using display_name URL parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        assignee: fstavela
        importance: high
        title: Inventory: GET on /tags with display_name parameter
    """
    display_name = setup_hosts_with_tags[0].display_name
    if case != "exact":
        display_name = getattr(display_name, case)()
    body = host_inventory.apis.tags.get_tags_response(display_name=display_name).json()
    assert body["total"] == len(setup_hosts_with_tags[0].tags)
    assert len(body["results"]) == body["total"]
    assert_tags_found(setup_hosts_with_tags[0].tags, body["results"])
    assert_tags_not_found(setup_hosts_with_tags[1].tags, body["results"])


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("case", ["exact", "lower", "upper"])
def test_get_tags_by_hostname_or_id(setup_hosts_with_tags, host_inventory, case):
    """
    Test GET on /tags endpoint using hostname_or_id URL parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        assignee: fstavela
        importance: high
        title: Inventory: GET on /tags with hostname_or_id parameter
    """

    def _test_hostname_or_id(hostname_or_id):
        value = hostname_or_id if case == "exact" else getattr(hostname_or_id, case)()
        body = host_inventory.apis.tags.get_tags_response(hostname_or_id=value).json()
        assert body["total"] == len(setup_hosts_with_tags[0].tags)
        assert len(body["results"]) == body["total"]
        assert_tags_found(setup_hosts_with_tags[0].tags, body["results"])
        assert_tags_not_found(setup_hosts_with_tags[1].tags, body["results"])

    _test_hostname_or_id(setup_hosts_with_tags[0].id)
    _test_hostname_or_id(setup_hosts_with_tags[0].fqdn)
    _test_hostname_or_id(setup_hosts_with_tags[0].display_name)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_tags_by_last_check_in_start(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      assignee: aprice
      importance: high
      title: Filter tags by last_check_in_start
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host1 = host_inventory.kafka.create_host(host_data=host_data)
    time_filter = datetime.now(tz=UTC)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host2 = host_inventory.kafka.create_host(host_data=host_data)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host3 = host_inventory.kafka.create_host(host_data=host_data)

    time_filter = host2.last_check_in if timestamp == "exact" else time_filter
    time_filter_str = time_filter.strftime(time_format)

    response = host_inventory.apis.tags.get_tags_response(last_check_in_start=time_filter_str)
    body = response.json()
    assert body["count"] >= len(host2.tags + host3.tags)
    assert_tags_found(host2.tags + host3.tags, body["results"])
    assert_tags_not_found(host1.tags, body["results"])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_tags_by_last_check_in_end(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      assignee: aprice
      importance: high
      title: Filter tags by last_check_in_end
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host1 = host_inventory.kafka.create_host(host_data=host_data)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host2 = host_inventory.kafka.create_host(host_data=host_data)
    time_filter = datetime.now(tz=UTC)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host3 = host_inventory.kafka.create_host(host_data=host_data)

    time_filter = host2.last_check_in if timestamp == "exact" else time_filter
    time_filter_s = time_filter.strftime(time_format)

    response = host_inventory.apis.tags.get_tags_response(last_check_in_end=time_filter_s)
    body = response.json()
    assert body["count"] >= len(host1.tags + host2.tags)
    assert_tags_found(host1.tags + host2.tags, body["results"])
    assert_tags_not_found(host3.tags, body["results"])


@pytest.mark.ephemeral
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_tags_by_last_check_in(
    host_inventory: ApplicationHostInventory,
    timestamp: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      assignee: aprice
      importance: high
      title: Filter tags by combined last_check_in_start and last_check_in_end
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host_before = host_inventory.kafka.create_host(host_data=host_data)
    time_start = datetime.now(tz=UTC)
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    time_end = datetime.now(tz=UTC)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host_after = host_inventory.kafka.create_host(host_data=host_data)

    time_start = hosts[0].last_check_in if timestamp == "exact" else time_start
    time_end = hosts[-1].last_check_in if timestamp == "exact" else time_end

    response = host_inventory.apis.tags.get_tags_response(
        last_check_in_start=time_start, last_check_in_end=time_end
    )
    body = response.json()
    wanted_tags = flatten(host.tags for host in hosts)
    assert body["count"] >= len(wanted_tags)
    assert_tags_found(wanted_tags, body["results"])
    assert_tags_not_found(host_before.tags + host_after.tags, body["results"])


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "case_insensitive", [False, True], ids=["case sensitive", "case insensitive"]
)
def test_get_tags_by_group_name(host_inventory: ApplicationHostInventory, case_insensitive: bool):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        assignee: fstavela
        importance: high
        title: Filter tags by group_name
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[1])

    filtered_name = group_name.upper() if case_insensitive else group_name

    response = host_inventory.apis.tags.get_tags_response(group_name=[filtered_name])
    body = response.json()
    assert body["count"] == len(hosts[0].tags)
    assert_tags_found(hosts[0].tags, body["results"])
    assert_tags_not_found(hosts[1].tags + hosts[2].tags, body["results"])


@pytest.mark.ephemeral
def test_get_tags_by_group_id(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21927

    metadata:
        assignee: maarif
        importance: high
        title: Filter tags by group_id
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[1])

    response = host_inventory.apis.tags.get_tags_response(group_id=[group.id])
    body = response.json()
    assert body["count"] == len(hosts[0].tags)
    assert_tags_found(hosts[0].tags, body["results"])
    assert_tags_not_found(hosts[1].tags + hosts[2].tags, body["results"])


@pytest.mark.ephemeral
def test_get_tags_by_group_name_multiple_groups(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5108

    metadata:
        assignee: fstavela
        importance: high
        title: Filter tags by multiple group_name values
    """
    hosts = host_inventory.kafka.create_random_hosts(5)
    group_name1 = generate_display_name()
    group_name2 = generate_display_name()
    host_inventory.apis.groups.create_group(group_name1, hosts=hosts[0])
    host_inventory.apis.groups.create_group(group_name2, hosts=hosts[1:3])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[3])

    correct_tags = hosts[0].tags + hosts[1].tags + hosts[2].tags
    response = host_inventory.apis.tags.get_tags_response(group_name=[group_name1, group_name2])
    body = response.json()
    assert body["count"] == len(correct_tags)
    assert_tags_found(correct_tags, body["results"])
    assert_tags_not_found(hosts[3].tags + hosts[4].tags, body["results"])


@pytest.mark.ephemeral
def test_get_tags_by_group_name_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        assignee: fstavela
        importance: high
        title: Test that I can't get tags by group_name from different account
    """
    host_data_primary = host_inventory.datagen.create_host_data_with_tags()
    host_data_secondary = host_inventory_secondary.datagen.create_host_data_with_tags()

    host_primary = host_inventory.kafka.create_host(host_data_primary)
    host_secondary = host_inventory_secondary.kafka.create_host(host_data_secondary)

    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=host_primary)
    host_inventory_secondary.apis.groups.create_group(group_name, hosts=host_secondary)

    response = host_inventory.apis.tags.get_tags_response(group_name=[group_name])
    body = response.json()
    assert body["count"] == len(host_primary.tags)
    assert_tags_found(host_primary.tags, body["results"])
    assert_tags_not_found(host_secondary.tags, body["results"])

    response = host_inventory_secondary.apis.tags.get_tags_response(group_name=[group_name])
    body = response.json()
    assert body["count"] == len(host_secondary.tags)
    assert_tags_found(host_secondary.tags, body["results"])
    assert_tags_not_found(host_primary.tags, body["results"])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "system_type",
    [
        pytest.param(values, id=", ".join(values))
        for n in range(len(_CORRECT_SYSTEM_TYPE_VALUES))
        for values in combinations(_CORRECT_SYSTEM_TYPE_VALUES, n + 1)
    ],
)
def test_get_tags_by_system_type(
    host_inventory: ApplicationHostInventory,
    setup_hosts_for_system_type_filtering: dict[str, list[HostWrapper]],
    system_type: list[str],
):
    """
    JIRA: https://issues.redhat.com/browse/RHINENG-19125

    metadata:
        assignee: zabikeno
        importance: high
        title: Inventory: filter tags by system_type
    """
    prepared_hosts = deepcopy(setup_hosts_for_system_type_filtering)
    expected_hosts = flatten(prepared_hosts.pop(item) for item in system_type)
    expected_tags = flatten(host.tags for host in expected_hosts)

    response = host_inventory.apis.tags.get_tags_response(system_type=system_type)
    body = response.json()
    assert len(body["results"]) >= len(expected_tags)
    assert_tags_found(expected_tags, body["results"])

    not_expected_hosts = flatten(hosts for hosts in prepared_hosts.values())
    not_expected_tags = flatten(host.tags for host in not_expected_hosts)
    assert_tags_not_found(not_expected_tags, body["results"])
