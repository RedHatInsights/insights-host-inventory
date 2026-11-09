import json
import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from itertools import combinations

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.groups.test_groups_hosts import group_to_hosts_api_dict
from iqe_host_inventory.utils import determine_positive_hosts_by_registered_with
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import _CORRECT_REGISTERED_WITH_VALUES
from iqe_host_inventory.utils.datagen_utils import _CORRECT_SYSTEM_TYPE_VALUES
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory.utils.tag_utils import assert_tags_not_found
from iqe_host_inventory.utils.upload_utils import get_archive_and_collect_method
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


@pytest.fixture
def setup_hosts_with_provider_fields(host_inventory: ApplicationHostInventory):
    hosts_data = host_inventory.datagen.create_n_hosts_data(3)
    hosts_data[0]["provider_type"] = "aws"
    hosts_data[0]["provider_id"] = generate_uuid()
    hosts_data[1]["provider_type"] = "azure"
    hosts_data[1]["provider_id"] = generate_uuid()
    hosts_data[2].pop("provider_type", None)
    hosts_data[2].pop("provider_id", None)
    yield host_inventory.kafka.create_hosts(hosts_data=hosts_data)


class TestGetHosts:
    @pytest.mark.parametrize("case", [str.lower, str.upper])
    def test_get_host_by_display_name_not_case_sensitive(
        self,
        host_inventory: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
        hbi_default_org_id: str,
        case: Callable,
    ):
        """
        Test GET host by display_name should not be case sensitive

        1. Create a host
        2. Issue a call to GET hosts using display_name parameter with different cases
        3. Confirm the response contains the right host details

        metadata:
            assignee: fstavela
            importance: high
            title: Inventory: Test GET host by display_name should not be case sensitive
        """
        display_name = hbi_upload_prepare_host_class.display_name
        searched_display_name = case(display_name)

        response = host_inventory.apis.hosts.get_hosts(display_name=searched_display_name)
        assert len(response) == 1
        host = response[0]

        assert host.id == hbi_upload_prepare_host_class.id
        assert host.display_name == display_name
        assert host.org_id == hbi_default_org_id

    @pytest.mark.usefixtures("hbi_upload_prepare_host_class")
    def test_get_host_by_not_exist_id(self, host_inventory: ApplicationHostInventory):
        """
        Test GET host using a non-existent ID.

        JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-598

        1. Create a host if none exist
        2. Issue a GET for id, specify a made-up UUID
        3. Confirm no matching host is returned

        metadata:
            assignee: fstavela
            importance: medium
            negative: true
            title: Inventory: test GET of host w/ non-existent id
        """
        fake_id = generate_uuid()

        with raises_apierror(404) as exc:
            host_inventory.apis.hosts.get_hosts_by_id_response(fake_id)

        # Verify that the response body includes the not_found_ids field
        response_body = json.loads(exc.value.body)
        assert "not_found_ids" in response_body, "Expected 'not_found_ids' in response body"
        assert response_body["not_found_ids"] == [fake_id], (
            f"Expected 'not_found_ids' to be '[{fake_id}]', got '{response_body['not_found_ids']}'"
        )


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
@pytest.mark.parametrize("operating_system", ["RHEL", "CentOS Linux"])
def test_get_host_by_id(host_inventory: ApplicationHostInventory, operating_system: str):
    """
    Test GET host by id.

    JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-598

    1. Issue a GET to determine the number of hosts
    2. Select the id of a random host from the first page of results
    3. Issue a GET using the selected ID
    4. Confirm the host was fetched successfully

    metadata:
        assignee: fstavela
        importance: critical
        title: Inventory: test GET of host by id
    """
    base_archive, core_collect = get_archive_and_collect_method(operating_system)
    host = host_inventory.upload.create_host(base_archive=base_archive, core_collect=core_collect)

    response = host_inventory.apis.hosts.get_hosts_by_id_response(host.id)

    assert response.count == 1
    assert response.results[0].id == host.id
    logger.info(f"Org ID: {response.results[0].org_id}")


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("case_insensitive", [False, True])
def test_get_hosts_by_hostname_or_id(
    host_inventory: ApplicationHostInventory, case_insensitive: bool
):
    """
    Test GET of host using hostname_or_id URL parameter.

    JIRA: https://issues.redhat.com/browse/ESSNTL-931

    metadata:
        assignee: fstavela
        importance: critical
        title: Inventory: Confirm hostname_or_id parameter retrieves right host
    """
    display_name = generate_display_name().lower()
    hostname = generate_display_name().lower()
    host_data = host_inventory.datagen.create_host_data(fqdn=hostname, display_name=display_name)
    host = host_inventory.kafka.create_host(host_data=host_data)
    host_inventory.kafka.create_host()

    host_id = host.id
    if case_insensitive:
        display_name = display_name.upper()
        hostname = hostname.upper()
        host_id = host_id.upper()

    response = host_inventory.apis.hosts.get_hosts_response(hostname_or_id=display_name)
    assert response.count == 1
    assert response.results[0].id == host.id

    response = host_inventory.apis.hosts.get_hosts_response(hostname_or_id=hostname)
    assert response.count == 1
    assert response.results[0].id == host.id

    response = host_inventory.apis.hosts.get_hosts_response(hostname_or_id=host_id)
    assert response.count == 1
    assert response.results[0].id == host.id


@pytest.mark.ephemeral
def test_get_host_exists(host_inventory: ApplicationHostInventory):
    """
    metadata:
        assignee: msager
        importance: high
        title: Test the GET /host_exists endpoint
    """
    host = host_inventory.kafka.create_host()

    response = host_inventory.apis.hosts.get_host_exists(host.insights_id)
    assert response.id == host.id


@pytest.mark.ephemeral
def test_get_host_exists_non_existent_insights_id(host_inventory: ApplicationHostInventory):
    """
    metadata:
        assignee: msager
        importance: high
        title: Test GET /host_exists for a non-existent insights id
    """
    insights_id = generate_uuid()

    with raises_apierror(404, match_message=f"No host found for Insights ID '{insights_id}'"):
        host_inventory.apis.hosts.get_host_exists(insights_id)


@pytest.mark.ephemeral
def test_get_host_exists_two_hosts_same_insights_id(host_inventory: ApplicationHostInventory):
    """
    metadata:
        assignee: msager
        importance: high
        title: Test GET /host_exists when two hosts have the same insights id
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["provider_id"] = generate_uuid()
    host_data["provider_type"] = "aws"

    # First host
    host = host_inventory.kafka.create_host(host_data=host_data)

    # Second host
    host_data["provider_id"] = generate_uuid()
    host_inventory.kafka.create_host(host_data=host_data)

    with raises_apierror(
        409,
        match_message=f"More than one host was found with the Insights ID '{host.insights_id}'",
    ):
        host_inventory.apis.hosts.get_host_exists(host.insights_id)


@pytest.mark.ephemeral
def test_get_host_exists_proper_account(
    host_inventory: ApplicationHostInventory, host_inventory_secondary: ApplicationHostInventory
):
    """
    metadata:
        assignee: msager
        importance: high
        title: Test that GET /host_exists operates on the proper account
    """
    host = host_inventory_secondary.kafka.create_host()

    with raises_apierror(404, match_message=f"No host found for Insights ID '{host.insights_id}'"):
        host_inventory.apis.hosts.get_host_exists(host.insights_id)


class TestFilterByRegisteredWith:
    @pytest.mark.ephemeral
    @pytest.mark.parametrize(
        "registered_with",
        [
            pytest.param(values, id=", ".join(values))
            for n in range(len(_CORRECT_REGISTERED_WITH_VALUES))
            for values in combinations(_CORRECT_REGISTERED_WITH_VALUES, n + 1)
        ],
    )
    def test_get_hosts_by_registered_with(
        self,
        host_inventory: ApplicationHostInventory,
        prepare_hosts_for_registered_with_filter_class: dict[str, HostWrapper],
        registered_with: list[str],
    ):
        """
        Test GET of host using registered_with URL parameter.

        JIRA: https://issues.redhat.com/browse/ESSNTL-2613

        metadata:
            assignee: fstavela
            importance: high
            title: Confirm registered_with parameter retrieves right hosts
        """
        wanted_hosts, not_wanted_hosts = determine_positive_hosts_by_registered_with(
            registered_with, prepare_hosts_for_registered_with_filter_class
        )
        wanted_hosts_ids = {host.id for host in wanted_hosts}
        not_wanted_hosts_ids = {host.id for host in not_wanted_hosts}
        response = host_inventory.apis.hosts.get_hosts(registered_with=registered_with)
        response_ids = {host.id for host in response}
        assert response_ids & wanted_hosts_ids == wanted_hosts_ids
        assert len(response_ids & not_wanted_hosts_ids) == 0

    @pytest.mark.ephemeral
    @pytest.mark.parametrize("registered_with", _CORRECT_REGISTERED_WITH_VALUES)
    def test_get_hosts_by_registered_with_negative_values(
        self,
        host_inventory: ApplicationHostInventory,
        prepare_hosts_for_registered_with_filter_class: dict[str, HostWrapper],
        registered_with: str,
    ):
        """
        Test GET of host using negative values on registered_with URL parameter.

        JIRA: https://issues.redhat.com/browse/ESSNTL-2873

        metadata:
            assignee: fstavela
            importance: high
            title: Confirm negative values on registered_with parameter retrieves right hosts
        """
        positive_hosts, negative_hosts = determine_positive_hosts_by_registered_with(
            [registered_with], prepare_hosts_for_registered_with_filter_class
        )
        wanted_hosts_ids = {host.id for host in negative_hosts}
        not_wanted_hosts_ids = {host.id for host in positive_hosts}

        response = host_inventory.apis.hosts.get_hosts(registered_with=["!" + registered_with])
        response_ids = {host.id for host in response}
        assert response_ids & wanted_hosts_ids == wanted_hosts_ids
        assert len(response_ids & not_wanted_hosts_ids) == 0

    @pytest.mark.ephemeral
    @pytest.mark.parametrize(
        "registered_with",
        [
            pytest.param(values, id=", ".join(values))
            for n in range(len(_CORRECT_REGISTERED_WITH_VALUES))
            for values in combinations(_CORRECT_REGISTERED_WITH_VALUES, n + 1)
        ],
    )
    def test_get_tags_by_registered_with(
        self,
        host_inventory: ApplicationHostInventory,
        prepare_hosts_for_registered_with_filter_class: dict[str, HostWrapper],
        registered_with: list[str],
    ):
        """
        Test GET on /tags endpoint using registered_with URL parameter

        JIRA: https://issues.redhat.com/browse/ESSNTL-1383

        metadata:
            assignee: fstavela
            importance: medium
            title: Inventory: GET on /tags with registered_with parameter
        """
        wanted_hosts, not_wanted_hosts = determine_positive_hosts_by_registered_with(
            registered_with, prepare_hosts_for_registered_with_filter_class
        )
        wanted_tags = flatten(host.tags for host in wanted_hosts)
        not_wanted_tags = flatten(host.tags for host in not_wanted_hosts)

        response = host_inventory.apis.tags.get_tags_json(registered_with=registered_with)
        assert response["count"] >= len(wanted_tags)
        assert len(response["results"]) == response["count"]
        assert_tags_found(wanted_tags, response["results"])
        assert_tags_not_found(not_wanted_tags, response["results"])


@pytest.mark.ephemeral
def test_get_hosts_by_registered_with_positive_and_negative_values(
    host_inventory: ApplicationHostInventory,
):
    """
    Test GET of host using negative and positive values on registered_with URL parameter.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2873

    metadata:
        assignee: fstavela
        importance: high
        title: Test GET of host using negative and positive values on registered_with URL parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    hosts_data[0]["reporter"] = "puptoo"
    hosts_data[1]["reporter"] = "yupana"
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    response = host_inventory.apis.hosts.get_hosts_response(registered_with=["puptoo", "!puptoo"])
    response_ids = {host.id for host in response.results}
    assert response_ids & {hosts[0].id, hosts[1].id} == {hosts[0].id, hosts[1].id}


# todo: Remove this test when https://issues.redhat.com/browse/ESSNTL-2743 is done
@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_hosts_by_last_check_in_start(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      assignee: aprice
      importance: high
      title: Filter hosts by last_check_in_start
    """
    host1 = host_inventory.kafka.create_host()
    time_filter = datetime.now(tz=UTC)
    host2 = host_inventory.kafka.create_host()
    host3 = host_inventory.kafka.create_host()
    time_filter = host2.last_check_in if timestamp == "exact" else time_filter
    time_filter_str = time_filter.strftime(time_format)

    response_hosts = host_inventory.apis.hosts.get_hosts(last_check_in_start=time_filter_str)
    response_ids = {host.id for host in response_hosts}
    assert len(response_hosts) >= 2
    assert response_ids.issuperset({host2.id, host3.id})
    assert host1.id not in response_ids


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_hosts_by_last_check_in_end(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      assignee: aprice
      importance: high
      title: Filter hosts by last_check_in_end
    """
    host1 = host_inventory.kafka.create_host()
    host2 = host_inventory.kafka.create_host()
    time_filter = datetime.now(tz=UTC)
    host3 = host_inventory.kafka.create_host()
    time_filter = host2.last_check_in if timestamp == "exact" else time_filter
    time_filter_str = time_filter.strftime(time_format)

    response_hosts = host_inventory.apis.hosts.get_hosts(last_check_in_end=time_filter_str)
    response_ids = {host.id for host in response_hosts}
    assert len(response_hosts) >= 2
    assert response_ids.issuperset({host1.id, host2.id})
    assert host3.id not in response_ids


@pytest.mark.ephemeral
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_hosts_by_last_check_in(host_inventory: ApplicationHostInventory, timestamp: str):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      assignee: aprice
      importance: high
      title: Filter hosts by combined last_check_in_start and last_check_in_end
    """
    host_before = host_inventory.kafka.create_host()
    time_start = datetime.now(tz=UTC)
    hosts = host_inventory.kafka.create_random_hosts(3)
    time_end = datetime.now(tz=UTC)
    host_after = host_inventory.kafka.create_host()

    time_start = hosts[0].last_check_in if timestamp == "exact" else time_start
    time_end = hosts[-1].last_check_in if timestamp == "exact" else time_end

    response_hosts = host_inventory.apis.hosts.get_hosts(
        last_check_in_start=time_start, last_check_in_end=time_end
    )
    response_ids = {host.id for host in response_hosts}
    assert len(response_hosts) >= 3
    assert response_ids.issuperset({host.id for host in hosts})
    assert len(response_ids.intersection({host_before.id, host_after.id})) == 0


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "case_insensitive", [False, True], ids=["case sensitive", "case insensitive"]
)
def test_get_hosts_by_group_name(host_inventory: ApplicationHostInventory, case_insensitive: bool):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        assignee: fstavela
        importance: high
        title: Filter hosts by group_name
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[1])

    filtered_name = group_name.upper() if case_insensitive else group_name

    response = host_inventory.apis.hosts.get_hosts(group_name=[filtered_name])
    assert len(response) == 1
    assert response[0].id == hosts[0].id
    assert len(response[0].groups) == 1
    assert group_to_hosts_api_dict(response[0].groups[0]) == group_to_hosts_api_dict(group)


@pytest.mark.ephemeral
def test_get_hosts_by_group_id(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21927

    metadata:
        assignee: maarif
        importance: high
        title: Filter hosts by group_id
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[1])

    response = host_inventory.apis.hosts.get_hosts(group_id=[group.id])
    assert len(response) == 1
    assert response[0].id == hosts[0].id
    assert len(response[0].groups) == 1
    assert group_to_hosts_api_dict(response[0].groups[0]) == group_to_hosts_api_dict(group)


@pytest.mark.ephemeral
def test_get_hosts_by_group_name_multiple_groups(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5108

    metadata:
        assignee: fstavela
        importance: high
        title: Filter hosts by multiple group_name values
    """
    hosts = host_inventory.kafka.create_random_hosts(5)
    group_name1 = generate_display_name()
    group_name2 = generate_display_name()
    group1 = host_inventory.apis.groups.create_group(group_name1, hosts=hosts[0])
    group2 = host_inventory.apis.groups.create_group(group_name2, hosts=hosts[1:3])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[3])

    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name1, group_name2])
    assert len(response) == 3
    for host in response:
        assert len(host.groups) == 1

    correct_hosts_ids = {host.id for host in hosts[:3]}
    response_hosts_groups = {host.id for host in response}
    assert response_hosts_groups == correct_hosts_ids

    correct_groups_ids = {group1.id, group2.id}
    response_groups_ids = {host.groups[0].id for host in response}
    assert response_groups_ids == correct_groups_ids


@pytest.mark.ephemeral
def test_get_hosts_by_group_name_not_contains(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        assignee: fstavela
        importance: high
        title: Filter hosts by group_name - filter uses 'eq', not 'contains'
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    # Second group with the same name + additional chars
    host_inventory.apis.groups.create_group(group_name + "2", hosts=hosts[1])

    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response) == 1
    assert response[0].id == hosts[0].id
    assert len(response[0].groups) == 1
    assert group_to_hosts_api_dict(response[0].groups[0]) == group_to_hosts_api_dict(group)


@pytest.mark.ephemeral
def test_get_hosts_by_group_name_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        assignee: fstavela
        importance: high
        title: Test that I can't get hosts by group_name from different account
    """
    host_primary = host_inventory.kafka.create_host()
    host_secondary = host_inventory_secondary.kafka.create_host()

    group_name = generate_display_name()
    group_primary = host_inventory.apis.groups.create_group(group_name, hosts=host_primary)
    group_secondary = host_inventory_secondary.apis.groups.create_group(
        group_name, hosts=host_secondary
    )

    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response) == 1
    assert response[0].id == host_primary.id
    assert len(response[0].groups) == 1
    assert group_to_hosts_api_dict(response[0].groups[0]) == group_to_hosts_api_dict(group_primary)

    response = host_inventory_secondary.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response) == 1
    assert response[0].id == host_secondary.id
    assert len(response[0].groups) == 1
    assert group_to_hosts_api_dict(response[0].groups[0]) == group_to_hosts_api_dict(
        group_secondary
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "system_type",
    [
        pytest.param(values, id=", ".join(values))
        for n in range(len(_CORRECT_SYSTEM_TYPE_VALUES))
        for values in combinations(_CORRECT_SYSTEM_TYPE_VALUES, n + 1)
    ],
)
def test_get_hosts_by_system_type(
    host_inventory: ApplicationHostInventory,
    setup_hosts_for_system_type_filtering: dict[str, list[HostWrapper]],
    system_type: list[str],
):
    """
    Test GET of host using system_type URL parameter.
    JIRA: https://issues.redhat.com/browse/RHINENG-19125
    metadata:
        assignee: zabikeno
        importance: high
        title: Confirm system_type parameter retrieves right hosts
    """
    prepared_hosts = deepcopy(setup_hosts_for_system_type_filtering)
    expected_hosts = flatten(prepared_hosts.pop(item) for item in system_type)
    response = host_inventory.apis.hosts.get_hosts(system_type=system_type)
    assert len(response) >= len(expected_hosts)

    response_ids = {host.id for host in response}
    wanted_hosts_ids = {host.id for host in expected_hosts}
    assert response_ids & wanted_hosts_ids == wanted_hosts_ids

    not_expected_hosts = flatten(hosts for hosts in prepared_hosts.values())
    not_expected_hosts_ids = {host.id for host in not_expected_hosts}
    assert len(response_ids & not_expected_hosts_ids) == 0
