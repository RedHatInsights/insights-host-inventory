import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from itertools import combinations
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.groups.test_groups_hosts import group_to_hosts_api_dict
from iqe_host_inventory.tests.rest.validation.test_system_profile import INCORRECT_DATETIMES
from iqe_host_inventory.utils import determine_positive_hosts_by_registered_with
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import _CORRECT_REGISTERED_WITH_VALUES
from iqe_host_inventory.utils.datagen_utils import _CORRECT_SYSTEM_TYPE_VALUES
from iqe_host_inventory.utils.datagen_utils import gen_tag
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory.utils.tag_utils import assert_tags_not_found
from iqe_host_inventory.utils.tag_utils import convert_tag_to_string
from iqe_host_inventory.utils.upload_utils import get_archive_and_collect_method
from iqe_host_inventory_api import ApiException
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
    @pytest.mark.usefixtures("hbi_upload_prepare_host_class")
    def test_get_host_list_validate_structure(self, host_inventory: ApplicationHostInventory):
        """
        Test GET hosts by org_id.

        JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-597

        1. If no hosts exist, create a host.
        2. Issue a call to GET hosts
        3. Confirm the response contains some basic fields required in a response payload

        metadata:
            requirements: inv-hosts-get-list
            assignee: fstavela
            importance: high
            title: Inventory: Test GET hosts response structure
        """
        current_hosts = host_inventory.apis.hosts.get_hosts()

        attrs = (
            "insights_id",
            "subscription_manager_id",
            "satellite_id",
            "bios_uuid",
            "ip_addresses",
            "fqdn",
            "mac_addresses",
            "provider_id",
            "provider_type",
            "id",
            "account",
            "org_id",
            "display_name",
            "ansible_host",
            "facts",
            "reporter",
            "per_reporter_staleness",
            "stale_timestamp",
            "stale_warning_timestamp",
            "culled_timestamp",
            "created",
            "updated",
            "groups",
            "last_check_in",
        )
        for host in current_hosts:
            assert all(getattr(host, attr, False) is not False for attr in attrs)

    @pytest.mark.smoke
    @pytest.mark.core
    @pytest.mark.qa
    def test_get_host_by_display_name(
        self,
        host_inventory: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
        hbi_default_org_id: str,
    ):
        """
        Test GET host by display_name.

        1. Create a host
        2. Issue a call to GET hosts using display_name parameter
        3. Confirm the response contains the right host details

        metadata:
            requirements: inv-hosts-filter-by-display_name
            assignee: fstavela
            importance: critical
            title: Inventory: Test GET host by display_name
        """
        display_name = hbi_upload_prepare_host_class.display_name

        response = host_inventory.apis.hosts.get_hosts(display_name=display_name)
        assert len(response) == 1
        host = response[0]

        assert host.id == hbi_upload_prepare_host_class.id
        assert host.display_name == display_name
        assert host.org_id == hbi_default_org_id

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
            requirements: inv-hosts-filter-by-display_name
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
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: medium
            negative: true
            title: Inventory: test GET of host w/ non-existent id
        """
        fake_id = generate_uuid()

        with raises_apierror(404):
            host_inventory.apis.hosts.get_hosts_by_id_response(fake_id)

    def test_branch_id_parameter(
        self, host_inventory: ApplicationHostInventory, hbi_upload_prepare_host_class: HostOut
    ):
        """
        Test branch_id parameter.

        Confirm that the branch_id parameter is allowed but effectively ignored.

        1. Submit a request to create a host
        2. Issue a GET to retrieve the host by insights_id. also specify a branch_id parameter.
        3. Issue a GET to retrieve the host by insights_id. omit branch_id.
        4. Issue a GET to retrieve the host by id, include branch_id
        5. Issue a GET to retrieve the host by id, omit branch_id
        6. Issue a GET with multiple hosts without branch_id
        7. Issue a GET with multiple hosts with branch_id
        8. Issue a PATCH with multiple hosts without branch_id
        9. Issue a PATCH with multiple hosts with branch_id

        metadata:
            requirements: inv-hosts-filter-by-branch_id
            assignee: fstavela
            importance: low
            title: Inventory API: Confirm branch_id parameter is allowed but ignored.
        """
        host = hbi_upload_prepare_host_class

        # GET with host's id in the URL
        response = host_inventory.apis.hosts.get_hosts_by_id_response(
            host, branch_id="some_branch"
        )
        assert response.total == 1

        response = host_inventory.apis.hosts.get_hosts_by_id_response(host)
        assert response.total == 1

        # GET with multiple hosts in the URL
        host_2 = host_inventory.upload.create_host()
        assert host_2.id != host.id

        two_hosts = [host, host_2]
        response = host_inventory.apis.hosts.get_hosts_by_id_response(two_hosts, branch_id=12345)
        assert response.total == 2
        response = host_inventory.apis.hosts.get_hosts_by_id_response(two_hosts, branch_id=42.1)
        assert response.total == 2

        # PATCH with multiple hosts in the URL
        host_inventory.apis.hosts.patch_hosts(
            two_hosts, ansible_host="patched_data1", branch_id=42.1
        )

        host_inventory.apis.hosts.patch_hosts(two_hosts, ansible_host="patched_data2")


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
        requirements: inv-hosts-get-by-id
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
def test_get_hosts_by_fqdn(host_inventory: ApplicationHostInventory, case_insensitive: bool):
    """
    Test GET of host using fqdn URL parameter.

    JIRA: https://issues.redhat.com/browse/ESSNTL-931

    metadata:
        requirements: inv-hosts-filter-by-fqdn
        assignee: fstavela
        importance: critical
        title: Inventory: Confirm fqdn parameter retrieves right host
    """
    fqdn = generate_display_name().lower()
    host_data = host_inventory.datagen.create_host_data(fqdn=fqdn)
    host = host_inventory.kafka.create_host(host_data=host_data)
    host_inventory.kafka.create_host()

    if case_insensitive:
        fqdn = fqdn.upper()

    response = host_inventory.apis.hosts.get_hosts_response(fqdn=fqdn)
    assert response.count == 1
    assert response.results[0].id == host.id


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
        requirements: inv-hosts-filter-by-hostname_or_id
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
@pytest.mark.parametrize("case_insensitive", [False, True])
def test_get_hosts_by_insights_id(
    host_inventory: ApplicationHostInventory, case_insensitive: bool
):
    """
    Test GET of host using insights_id URL parameter.

    JIRA: https://issues.redhat.com/browse/ESSNTL-931

    metadata:
        requirements: inv-hosts-filter-by-insights_id
        assignee: fstavela
        importance: medium
        title: Inventory: Confirm insights_id parameter retrieves right host
    """
    insights_id = generate_uuid().lower()
    host_data = host_inventory.datagen.create_host_data(insights_id=insights_id)
    host = host_inventory.kafka.create_host(host_data=host_data)
    host_inventory.kafka.create_host()

    if case_insensitive:
        insights_id = insights_id.upper()

    response = host_inventory.apis.hosts.get_hosts_response(insights_id=insights_id)
    assert response.count == 1
    assert response.results[0].id == host.id


@pytest.mark.ephemeral
@pytest.mark.parametrize("case_insensitive", [False, True])
def test_get_hosts_by_subscription_manager_id(
    host_inventory: ApplicationHostInventory, case_insensitive: bool
):
    """
    Test GET of host using subscription_manager_id URL parameter.

    JIRA: https://issues.redhat.com/browse/RHINENG-17386

    metadata:
        requirements: inv-hosts-filter-by-subscription_manager_id
        assignee: addubey
        importance: medium
        title: Inventory: Confirm subscription_manager_id parameter retrieves right host
    """
    subscription_manager_id = generate_uuid().lower()
    host_data = host_inventory.datagen.create_host_data(
        subscription_manager_id=subscription_manager_id
    )
    host = host_inventory.kafka.create_host(host_data=host_data)
    host_inventory.kafka.create_host()

    if case_insensitive:
        subscription_manager_id = subscription_manager_id.upper()

    response = host_inventory.apis.hosts.get_hosts_response(
        subscription_manager_id=subscription_manager_id
    )
    assert response.count == 1
    assert response.results[0].id == host.id


@pytest.mark.ephemeral
@pytest.mark.parametrize("case_insensitive", [False, True])
def test_get_hosts_by_provider_id(
    setup_hosts_with_provider_fields, case_insensitive, host_inventory
):
    """
    https://issues.redhat.com/browse/RHCLOUD-12642

    metadata:
      requirements: inv-hosts-filter-by-provider_id
      assignee: fstavela
      importance: medium
      title: Inventory: get hosts by provider_id
    """
    hosts = setup_hosts_with_provider_fields
    provider_id = hosts[0].provider_id.upper() if case_insensitive else hosts[0].provider_id

    response = host_inventory.apis.hosts.get_hosts_response(provider_id=provider_id)
    assert response.count >= 1
    response_ids = {host.id for host in response.results}
    assert hosts[0].id in response_ids
    assert hosts[1].id not in response_ids and hosts[2].id not in response_ids

    response = host_inventory.apis.hosts.get_hosts_response(provider_id="invalid")
    assert response.count == 0


@pytest.mark.ephemeral
def test_get_hosts_by_provider_type(setup_hosts_with_provider_fields, host_inventory):
    """
    https://issues.redhat.com/browse/RHCLOUD-12642

    metadata:
      requirements: inv-hosts-filter-by-provider_type
      assignee: fstavela
      importance: medium
      title: Inventory: get hosts by provider_type
    """
    hosts = setup_hosts_with_provider_fields

    response = host_inventory.apis.hosts.get_hosts_response(provider_type=hosts[0].provider_type)
    assert response.count >= 1
    response_ids = {host.id for host in response.results}
    assert hosts[0].id in response_ids
    assert hosts[1].id not in response_ids and hosts[2].id not in response_ids

    with pytest.raises(ApiException) as err:
        response = host_inventory.apis.hosts.get_hosts_response(provider_type="invalid")
    assert err.value.status == 400


def test_get_host_by_non_existent_insights_id(host_inventory):
    """
    Test GET host by non-existent insights id.

    JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-841

    1. Generate a random UUID
    2. Issue a call to get hosts using the random UUID as insights_id
    3. Confirm that the response was empty (no hosts found)

    metadata:
        requirements: inv-hosts-filter-by-insights_id
        negative: true
        assignee: fstavela
        importance: medium
        title: Inventory: test GET host by non-existent insights id
    """
    insights_id = generate_uuid()
    response = host_inventory.apis.hosts.get_hosts_response(insights_id=insights_id)

    assert response.count == 0


@pytest.mark.ephemeral
def test_get_host_exists(host_inventory: ApplicationHostInventory):
    """
    metadata:
        requirements: inv-host_exists-get-by-insights-id
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
        requirements: inv-host_exists-get-by-insights-id
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
        requirements: inv-host_exists-get-by-insights-id
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
        requirements: inv-host_exists-get-by-insights-id
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
            requirements: inv-hosts-filter-by-registered_with
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
            requirements: inv-hosts-filter-by-registered_with
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
            requirements: inv-tags-get-list, inv-hosts-filter-by-registered_with
            assignee: fstavela
            importance: medium
            title: Inventory: GET on /tags with registered_with parameter
        """
        wanted_hosts, not_wanted_hosts = determine_positive_hosts_by_registered_with(
            registered_with, prepare_hosts_for_registered_with_filter_class
        )
        wanted_tags = flatten(host.tags for host in wanted_hosts)
        not_wanted_tags = flatten(host.tags for host in not_wanted_hosts)

        response = host_inventory.apis.tags.get_tags_response(registered_with=registered_with)
        assert response.count >= len(wanted_tags)
        assert len(response.results) == response.count
        assert_tags_found(wanted_tags, response.results)
        assert_tags_not_found(not_wanted_tags, response.results)


@pytest.mark.ephemeral
def test_get_hosts_by_registered_with_positive_and_negative_values(
    host_inventory: ApplicationHostInventory,
):
    """
    Test GET of host using negative and positive values on registered_with URL parameter.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2873

    metadata:
        requirements: inv-hosts-filter-by-registered_with
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
def test_get_hosts_by_registered_with_temp_old(host_inventory: ApplicationHostInventory):
    """
    Test registered_with with old 'insights' value.
    This value should be removed from valid options after UI starts using new options.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2613

    metadata:
        requirements: inv-hosts-filter-by-registered_with
        assignee: fstavela
        importance: high
        title: Confirm registered_with=insights returns correct hosts
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    hosts_data[1].pop("insights_id")
    hosts_ids = [
        host.id
        for host in host_inventory.kafka.create_hosts(
            hosts_data=hosts_data, field_to_match=HostWrapper.subscription_manager_id
        )
    ]

    response_ids = {host.id for host in host_inventory.apis.hosts.get_hosts_response().results}
    assert all(host_id in response_ids for host_id in hosts_ids)

    response_ids = {
        host.id
        for host in host_inventory.apis.hosts.get_hosts_response(
            registered_with=["insights"]
        ).results
    }
    assert hosts_ids[0] in response_ids
    assert hosts_ids[1] not in response_ids


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "params",
    [
        ("display_name", "fqdn"),
        ("display_name", "insights_id"),
        ("display_name", "hostname_or_id"),
        ("fqdn", "insights_id"),
        ("fqdn", "hostname_or_id"),
        ("insights_id", "hostname_or_id"),
        ("display_name", "fqdn", "insights_id"),
        ("display_name", "fqdn", "hostname_or_id"),
        ("display_name", "insights_id", "hostname_or_id"),
        ("fqdn", "insights_id", "hostname_or_id"),
        ("display_name", "fqdn", "insights_id", "hostname_or_id"),
    ],
)
def test_get_hosts_invalid_parameters_combinations(
    host_inventory: ApplicationHostInventory, params: tuple[str]
):
    """
    Test GET of host using invalid combination of parameters.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2193

    metadata:
        requirements: inv-hosts-get-list, inv-api-validation
        assignee: fstavela
        importance: low
        title: Inventory: Test GET of host using invalid combination of parameters.
    """
    host = host_inventory.kafka.create_host()
    parameters = {}
    for param in params:
        if param == "hostname_or_id":
            parameters["hostname_or_id"] = host.fqdn
        else:
            parameters[param] = getattr(host, param)

    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.get_hosts(**parameters)  # type: ignore[arg-type]
    assert err.value.status == 400
    assert (
        "Only one of [fqdn, display_name, hostname_or_id, insights_id] may be provided at a time."
        in err.value.body
    )


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
@pytest.mark.parametrize(
    "id_param_name",
    ["display_name", "fqdn", "insights_id", "hostname_or_id", "subscription_manager_id"],
)
def test_get_hosts_valid_parameters_combinations(
    host_inventory: ApplicationHostInventory,
    id_param_name: str,
):
    """
    Test GET of host using valid combination of parameters.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2193

    metadata:
        requirements: inv-hosts-get-list
        assignee: fstavela
        importance: medium
        title: Inventory: Test GET of host using valid combination of parameters.
    """
    # A total of 8 hosts will be created. Host 1 (using 0-based notation) will be
    # the target host we filter for at the end.  Host 7 will be completely different.
    # Hosts 0-6 will be mostly the same with these exceptions:
    #   hosts 1-6 will be in the same group (hosts 0 and 7 won't be in a group)
    #   host 2 will have a different value for the field that id_param_name represents
    #   host 3 will have a different provider_type
    #   host 4 will be stale (the rest will be fresh)
    #   host 5 will have different tags
    #   hosts 0-5 will be in the filtered time range
    #
    # All provider ids will be unique per host.

    tags = [gen_tag()]
    str_tags = [convert_tag_to_string(tag) for tag in tags]
    hosts_data = [host_inventory.datagen.create_host_data()]
    if id_param_name == "hostname_or_id":
        hosts_data[0]["display_name"] = generate_display_name()
    else:
        hosts_data[0][id_param_name] = generate_uuid()
    hosts_data[0]["provider_id"] = generate_uuid()
    hosts_data[0]["provider_type"] = "aws"
    hosts_data[0]["tags"] = tags

    for _ in range(6):
        hosts_data.append(dict(hosts_data[0]))
        hosts_data[-1]["provider_id"] = generate_uuid()
    if id_param_name == "hostname_or_id":
        hosts_data[2]["fqdn"] = generate_display_name()
    else:
        hosts_data[2][id_param_name] = generate_uuid()
    hosts_data[3]["provider_type"] = "ibm"
    hosts_data[5]["tags"] = [gen_tag()]

    hosts_data.append(host_inventory.datagen.create_host_data())
    hosts_data[-1]["provider_type"] = "gcp"
    hosts_data[-1]["provider_id"] = generate_uuid()

    hosts = host_inventory.kafka.create_hosts(hosts_data, field_to_match=HostWrapper.provider_id)

    # Assign hosts to group - all except hosts[0] and hosts[-1]
    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[1:-1])

    # Step through all events to remove conflicts during later update
    provider_ids = [host.provider_id for host in hosts[1:-1]]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.provider_id, provider_ids)

    # Group creation corrupted the hosts updated timestamps, so we have to reset
    # them now.  Update a random field (using rhc_client_id in this case) and
    # verify the update has completed.
    rhc_client_id = generate_uuid()
    for host_data in hosts_data:
        host_data["system_profile"]["rhc_client_id"] = rhc_client_id
    updated_hosts = host_inventory.kafka.create_hosts(
        hosts_data, field_to_match=HostWrapper.provider_id
    )
    for host in updated_hosts:
        host_inventory.apis.hosts.wait_for_system_profile_updated(
            host.id, rhc_client_id=rhc_client_id
        )

    # Make host 4 stale and preserve ordering.
    fresh_hosts_data = hosts_data[0:4] + hosts_data[5:]
    stale_hosts_data = hosts_data[4:5]
    hosts_in_state = create_hosts_fresh_stale(
        host_inventory,
        fresh_hosts_data,
        stale_hosts_data,
        deltas=(5, 3600, 7200),
        field_to_match=HostWrapper.provider_id,
    )
    updated_hosts = (
        hosts_in_state["fresh"][0:4] + hosts_in_state["stale"] + hosts_in_state["fresh"][4:]
    )

    # Guarantee that the updated_end host will have a later updated time than
    # the other hosts in the filtered range
    updated_end_host = host_inventory.kafka.create_hosts(
        [hosts_data[5]], field_to_match=HostWrapper.provider_id
    )[0]

    # Guarantee that the remaining hosts will be outside the filtered range
    host_inventory.kafka.create_hosts(hosts_data[6:], field_to_match=HostWrapper.provider_id)

    id_param = (
        {id_param_name: hosts_data[1][id_param_name]}
        if id_param_name != "hostname_or_id"
        else {id_param_name: hosts_data[1]["fqdn"]}
    )

    # Due to how we create a set of mixed-state hosts now, the stale host
    # (updated_hosts[4]) will have the earliest updated timestamp.  Thus, the
    # updated_start/updated_end params look a little strange, but they encompass
    # the first 6 hosts.
    response = host_inventory.apis.hosts.get_hosts_response(
        **id_param,
        provider_type=hosts_data[1]["provider_type"],
        staleness=["fresh"],
        tags=str_tags,
        updated_start=updated_hosts[4].updated,
        updated_end=updated_end_host.updated,
        group_name=[group_name],
    )
    assert response.count == 1
    assert response.results[0].id == updated_hosts[1].id


@pytest.mark.ephemeral
def test_get_hosts_empty_database(hbi_empty_database, host_inventory):
    """
    Test inventory with no hosts in database

    JIRA:

    metadata:
        requirements: inv-hosts-get-list
        assignee: fstavela
        importance: medium
        title: Test inventory with no hosts in database
    """
    response = host_inventory.apis.hosts.get_hosts_response()
    assert response.count == response.total == 0


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_hosts_by_updated_start(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Filter hosts by updated_start
    """
    host1 = host_inventory.kafka.create_host()
    time_filter = datetime.now()
    host2 = host_inventory.kafka.create_host()
    host3 = host_inventory.kafka.create_host()
    time_filter = host2.updated if timestamp == "exact" else time_filter
    time_filter_s = time_filter.strftime(time_format)

    response_hosts = host_inventory.apis.hosts.get_hosts(updated_start=time_filter_s)
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
def test_get_hosts_by_updated_end(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Filter hosts by updated_end
    """
    host1 = host_inventory.kafka.create_host()
    host2 = host_inventory.kafka.create_host()
    time_filter = datetime.now()
    host3 = host_inventory.kafka.create_host()
    time_filter = host2.updated if timestamp == "exact" else time_filter
    time_filter_s = time_filter.strftime(time_format)

    response_hosts = host_inventory.apis.hosts.get_hosts(updated_end=time_filter_s)
    response_ids = {host.id for host in response_hosts}
    assert len(response_hosts) >= 2
    assert response_ids.issuperset({host1.id, host2.id})
    assert host3.id not in response_ids


@pytest.mark.ephemeral
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_hosts_by_updated(host_inventory: ApplicationHostInventory, timestamp: str):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Filter hosts by combined updated_start and updated_end
    """
    host_before = host_inventory.kafka.create_host()
    time_start = datetime.now()
    hosts = host_inventory.kafka.create_random_hosts(3)
    time_end = datetime.now()
    host_after = host_inventory.kafka.create_host()

    time_start = hosts[0].updated if timestamp == "exact" else time_start
    time_end = hosts[-1].updated if timestamp == "exact" else time_end

    response_hosts = host_inventory.apis.hosts.get_hosts(
        updated_start=time_start, updated_end=time_end
    )
    response_ids = {host.id for host in response_hosts}
    assert len(response_hosts) >= 3
    assert response_ids.issuperset({host.id for host in hosts})
    assert len(response_ids.intersection({host_before.id, host_after.id})) == 0


@pytest.mark.ephemeral
def test_get_hosts_by_updated_both_same(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Filter hosts by combined updated_start and updated_end - both same
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    response_hosts = host_inventory.apis.hosts.get_hosts(
        updated_start=hosts[1].updated, updated_end=hosts[1].updated
    )
    response_ids = [host.id for host in response_hosts]
    assert response_ids == [hosts[1].id]


@pytest.mark.parametrize("timezone", ["+03:00", "-03:00"], ids=["plus", "minus"])
@pytest.mark.ephemeral
def test_get_hosts_by_updated_different_timezone(
    host_inventory: ApplicationHostInventory, timezone: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Filter hosts by updated with not-UTC timezone
    """
    host_before = host_inventory.kafka.create_host()
    hosts = host_inventory.kafka.create_random_hosts(3)
    host_after = host_inventory.kafka.create_host()

    hours_delta = 3 if timezone[0] == "+" else -3
    time_start = (hosts[0].updated + timedelta(hours=hours_delta)).strftime(
        f"%Y-%m-%dT%H:%M:%S.%f{timezone}"
    )
    time_end = (hosts[-1].updated + timedelta(hours=hours_delta)).strftime(
        f"%Y-%m-%dT%H:%M:%S.%f{timezone}"
    )

    response_hosts = host_inventory.apis.hosts.get_hosts(
        updated_start=time_start, updated_end=time_end
    )
    response_ids = {host.id for host in response_hosts}
    assert len(response_hosts) >= 3
    assert response_ids.issuperset({host.id for host in hosts})
    assert len(response_ids.intersection({host_before.id, host_after.id})) == 0


@pytest.mark.ephemeral
def test_get_hosts_by_updated_not_created(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Test that updated filters work by last updated, not created timestamp - hosts
    """
    host1 = host_inventory.kafka.create_host()
    host2 = host_inventory.kafka.create_host()
    time_start = datetime.now()
    host3 = host_inventory.kafka.create_host()
    host_inventory.apis.hosts.patch_hosts(host2, display_name=f"{host2.display_name}-updated")
    time_end = datetime.now()
    host_inventory.apis.hosts.patch_hosts(host3, display_name=f"{host3.display_name}-updated")

    response_hosts = host_inventory.apis.hosts.get_hosts(
        updated_start=time_start, updated_end=time_end
    )
    response_ids = {host.id for host in response_hosts}
    assert len(response_hosts) >= 1
    assert host2.id in response_ids
    assert len(response_ids.intersection({host1.id, host3.id})) == 0


@pytest.mark.ephemeral
@pytest.mark.parametrize("param", ["updated_start", "updated_end"])
@pytest.mark.parametrize("value", INCORRECT_DATETIMES)
def test_get_hosts_by_updated_incorrect_format(
    host_inventory: ApplicationHostInventory, param: str, value: Any
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Get hosts with wrong format of updated_start and updated_end parameters
    """
    host_inventory.kafka.create_host()
    if isinstance(value, str):
        value = value.replace("'", "").replace('"', "").replace("\\", "")
    api_param = {param: value}
    error_value = f'\\"{value}\\"' if (isinstance(value, list) and len(value)) else f"'{value}'"
    with raises_apierror(400, f"{error_value} is not a 'date-time'"):
        host_inventory.apis.hosts.get_hosts(**api_param)


@pytest.mark.ephemeral
def test_get_hosts_by_updated_start_after_end(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Get hosts with updated_start bigger than updated_end
    """
    host = host_inventory.kafka.create_host()
    time_start = host.updated + timedelta(hours=1)
    time_end = host.updated - timedelta(hours=1)
    with raises_apierror(400, "updated_start cannot be after updated_end."):
        host_inventory.apis.hosts.get_hosts(updated_start=time_start, updated_end=time_end)


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
      requirements: inv-hosts-filter-by-last_check_in
      assignee: aprice
      importance: high
      title: Filter hosts by last_check_in_start
    """
    host1 = host_inventory.kafka.create_host()
    time_filter = datetime.now()
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
      requirements: inv-hosts-filter-by-last_check_in
      assignee: aprice
      importance: high
      title: Filter hosts by last_check_in_end
    """
    host1 = host_inventory.kafka.create_host()
    host2 = host_inventory.kafka.create_host()
    time_filter = datetime.now()
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
      requirements: inv-hosts-filter-by-last_check_in
      assignee: aprice
      importance: high
      title: Filter hosts by combined last_check_in_start and last_check_in_end
    """
    host_before = host_inventory.kafka.create_host()
    time_start = datetime.now()
    hosts = host_inventory.kafka.create_random_hosts(3)
    time_end = datetime.now()
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
        requirements: inv-hosts-filter-by-group_name
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
    assert response[0].groups[0].to_dict() == group_to_hosts_api_dict(group)


@pytest.mark.ephemeral
def test_get_hosts_by_group_id(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21927

    metadata:
        requirements: inv-hosts-filter-by-group_id
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
    assert response[0].groups[0].to_dict() == group_to_hosts_api_dict(group)


@pytest.mark.ephemeral
def test_get_hosts_with_group_name_and_group_id(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21927

    metadata:
        requirements: inv-hosts-filter-by-group_name, inv-hosts-filter-by-group_id, inv-api-validation
        assignee: maarif
        importance: high
        negative: true
        title: Verify 400 error when both group_name and group_id filters are used together
    """
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)

    with raises_apierror(400, "Cannot use both 'group_name' and 'group_id' filters together"):
        host_inventory.apis.hosts.get_hosts(group_name=[group_name], group_id=[group.id])


@pytest.mark.ephemeral
def test_get_hosts_by_group_name_empty(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5138

    metadata:
        requirements: inv-hosts-filter-by-group_name
        assignee: fstavela
        importance: high
        title: Filter hosts by empty group_name - get ungrouped hosts
    """
    hosts = host_inventory.kafka.create_random_hosts(2)
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[0])

    response = host_inventory.apis.hosts.get_hosts(group_name=[""])
    assert len(response) >= 1
    response_ids = {host.id for host in response}
    assert hosts[1].id in response_ids
    assert hosts[0].id not in response_ids
    for host in response:
        assert len(host.groups) == 1
        assert host.groups[0].ungrouped is True


@pytest.mark.ephemeral
def test_get_hosts_by_group_name_multiple_groups(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5108

    metadata:
        requirements: inv-hosts-filter-by-group_name
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
        requirements: inv-hosts-filter-by-group_name
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
    assert response[0].groups[0].to_dict() == group_to_hosts_api_dict(group)


@pytest.mark.ephemeral
def test_get_hosts_by_group_name_multiple_hosts_in_group(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        requirements: inv-hosts-filter-by-group_name
        assignee: fstavela
        importance: high
        title: Filter hosts by group_name, if the group has multiple hosts
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])

    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response) == 2
    assert {host.id for host in response} == {host.id for host in hosts[:2]}
    for response_host in response:
        assert len(response_host.groups) == 1
        assert response_host.groups[0].to_dict() == group_to_hosts_api_dict(group)


@pytest.mark.ephemeral
def test_get_hosts_by_group_name_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        requirements: inv-hosts-filter-by-group_name, inv-account-integrity
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
    assert response[0].groups[0].to_dict() == group_to_hosts_api_dict(group_primary)

    response = host_inventory_secondary.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response) == 1
    assert response[0].id == host_secondary.id
    assert len(response[0].groups) == 1
    assert response[0].groups[0].to_dict() == group_to_hosts_api_dict(group_secondary)


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
        requirements: inv-hosts-filter-by-system_type
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
