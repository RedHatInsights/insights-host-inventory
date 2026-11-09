from __future__ import annotations

import logging
from collections import Counter

import attr
import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.test_system_profile_endpoints import os_dict_to_str
from iqe_host_inventory.tests.rest.test_system_profile_endpoints import os_filter_param
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.datagen_utils import SYSTEM_PROFILE
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory.utils.tag_utils import assert_tags_not_found
from iqe_host_inventory.utils.tag_utils import (
    log_response_tags_indices as _log_response_tags_indices,
)
from iqe_host_inventory_api import ApiException
from iqe_host_inventory_api import ApiTypeError
from iqe_host_inventory_api import HostOut
from iqe_host_inventory_api import StructuredTag

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


FILTER_OS_DISPLAY_NAME = "rhiqe-filter-os-display_name"


# TODO: use datetime post python 3.6, 3.7 adds iso parsing
iso_timestamp = str


@attr.s(auto_attribs=True)
class StaleReporterFilterGen:
    # todo: better structure
    VALID_OPERATORS = (
        "gt",
        "gte",
        "lt",
        "lte",
        "eq",
        "ne",
    )

    reporter: str

    exists: bool | None = None
    stale_timestamp_operator: str = "eq"
    stale_timestamp: iso_timestamp | None = None
    last_check_in_operator: str = "eq"
    last_check_in: iso_timestamp | None = None
    check_in_succeeded: bool | None = None

    def to_query(self):
        prefix = f"filter[per_reporter_staleness][{self.reporter}]"

        def maybe_filter(var, op=None):
            op = "" if op is None else f"[{op}]"
            val = getattr(self, var)
            if isinstance(val, bool):
                val = "true" if val else "false"
            if val is None:
                return {}
            return {f"{prefix}[{var}]{op}": val}

        query = {
            **maybe_filter(
                "exists",
            ),
            **maybe_filter("last_check_in", self.last_check_in_operator),
            **maybe_filter("stale_timestamp", self.last_check_in_operator),
            **maybe_filter(
                "check_in_succeeded",
            ),
        }
        assert query, query
        return query


def format_sap_sids_filters(use_contains, use_equals, values):
    for value in values:
        yield format_sap_sids_filter(use_contains, use_equals, value)


def format_sap_sids_filter(use_contains, use_equals, value):
    """Formats API url parameter for sap_sids filtering"""
    param = "[sap_sids]"
    if use_contains:
        param += "[contains]"
    if use_equals:
        param += f"[]={value}"
    else:
        param += f"[{value}]"
    return param


def log_response_hosts_indices(
    my_hosts: list[HostWrapper] | list[HostOut], response_ids: set[str]
):
    my_hosts_ids = [host.id for host in my_hosts]
    my_response_ids = response_ids & set(my_hosts_ids)
    response_hosts_indices = [my_hosts_ids.index(host_id) for host_id in my_response_ids]
    logger.info(f"Response hosts indices: {response_hosts_indices}")


# All tests that use the setup_hosts_for_operating_system_filtering fixture are grouped here
# so that the expensive fixture (which creates 14 hosts across two accounts) runs only once.
@pytest.mark.usefixtures("setup_hosts_for_operating_system_filtering")
class TestOperatingSystemFiltering:
    @pytest.mark.smoke
    @pytest.mark.parametrize(
        "params, expected_hosts",
        [
            (["[RHEL][version][lt][]=7.10"], [0]),
            (["[RHEL][version][lte][]=7.10"], [0, 1]),
            (["[RHEL][version][gte][]=7.10"], [1, 2]),
            (["[RHEL][version][gt][]=7.10"], [2]),
            (["[RHEL][version][lt][]=7.6"], [0]),
            (["[RHEL][version][lte][]=7.6"], [0]),
            (["[RHEL][version][gte][]=7.6"], [1, 2]),
            (["[RHEL][version][gt][]=7.6"], [1, 2]),
            (["[RHEL][version][lt][]=7"], []),
            (["[RHEL][version][lte][]=7"], [0, 1]),
            (["[RHEL][version][gte][]=7"], [0, 1, 2]),
            (["[RHEL][version][gt][]=7"], [2]),
            (["[RHEL][version][gt][]=8"], []),
            (["[RHEL][version][gte][]=8"], [2]),
            (["[RHEL][version][gte][]=7.10", "[RHEL][version][lte][]=7.10"], [1]),
            (["[RHEL][version][gt][]=7", "[RHEL][version][lt][]=8"], []),
            # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-18750 is fixed
            # (["[RHEL][version][gte][]=7", "[RHEL][version][lte][]=8"], [0, 1, 2]),
            (["[RHEL][version][eq][]=7"], [0, 1]),
            (["[RHEL][version][eq][]=8"], [2]),
            (["[RHEL][version][eq][]=7.10"], [1]),
            (["[RHEL][version][eq][]=7.1"], []),
            (["[RHEL][version][eq][]=7.5", "[RHEL][version][eq][]=8.0"], [0, 2]),
            (["[RHEL][version][eq][]=7.6", "[RHEL][version][eq][]=8.0"], [2]),
            (["[RHEL][version][eq][]=7", "[RHEL][version][eq][]=8.0"], [0, 1, 2]),
            (["[RHEL][version][eq][]=7", "[RHEL][version][eq][]=8"], [0, 1, 2]),
            (["[RHEL][version][eq][]=7", "[RHEL][version][eq][]=7"], [0, 1]),
            (["[RHEL][version][eq][]=7.5", "[RHEL][version][gt][]=7.10"], [0, 2]),
            (["[RHEL][version][eq][]=7.5", "[RHEL][version][gt][]=7.5"], [0, 1, 2]),
            (
                [
                    "[RHEL][version][eq][]=7.5",
                    "[RHEL][version][eq][]=7.10",
                    "[RHEL][version][eq][]=8.0",
                ],
                [0, 1, 2],
            ),
            (
                [
                    "[RHEL][version][eq][]=7",
                    "[RHEL][version][eq][]=8",
                    "[RHEL][version][eq][]=7.5",
                ],
                [0, 1, 2],
            ),
            (
                [
                    "[RHEL][version][eq][]=7",
                    "[RHEL][version][eq][]=7.5",
                    "[RHEL][version][eq][]=8.0",
                ],
                [0, 1, 2],
            ),
            (
                [
                    "[RHEL][version][eq][]=7.5",
                    "[RHEL][version][gt][]=7.6",
                    "[RHEL][version][lt][]=8",
                ],
                [0, 1],
            ),
            (["[CentOS Linux][version][lt][]=7.10"], [3]),
            (["[CentOS Linux][version][lte][]=7.10"], [3, 4]),
            (["[CentOS Linux][version][gte][]=7.10"], [4, 5]),
            (["[CentOS Linux][version][gt][]=7.10"], [5]),
            (
                [
                    "[CentOS Linux][version][gte][]=7.10",
                    "[CentOS Linux][version][lte][]=7.10",
                ],
                [4],
            ),
            (["[CentOS Linux][version][eq][]=7"], [3, 4]),
            (["[CentOS Linux][version][eq][]=7.10"], [4]),
            (
                [
                    "[CentOS Linux][version][eq][]=7.5",
                    "[CentOS Linux][version][eq][]=8.0",
                ],
                [3, 5],
            ),
            (
                [
                    "[RHEL][version][eq][]=7.5",
                    "[CentOS Linux][version][eq][]=8.0",
                ],
                [0, 5],
            ),
            (["=nil"], [6]),
            (["=not_nil"], [0, 1, 2, 3, 4, 5]),
            (["[]=nil", "[]=not_nil"], [0, 1, 2, 3, 4, 5, 6]),
            (["[name][neq]=RHEL"], [3, 4, 5]),
            (["[name][eq]=RHEL"], [0, 1, 2]),
            (["[name][neq]=Centos linux"], [0, 1, 2]),
            (["[name][eq]=Centos Linux"], [3, 4, 5]),
            (["[name][neq][]=CentOS Linux", "[name][neq][]=RHEL"], [0, 1, 2, 3, 4, 5]),
            (["[name][eq][]=CentOS Linux", "[name][eq][]=RHEL"], [0, 1, 2, 3, 4, 5]),
            (
                ["[name][eq]=Centos Linux", "[CentOS Linux][version][eq][]=7.10"],
                [3, 4, 5],
            ),
            (
                ["[name][eq]=Centos Linux", "[RHEL][version][eq][]=7.10"],
                [1, 3, 4, 5],
            ),
            (["[name][neq]=RHEL", "[RHEL][version][eq][]=7.10"], [1, 3, 4, 5]),
            (["[name][eq]=RHEL", "[RHEL][version][eq][]=7.10"], [0, 1, 2]),
        ],
        ids=lambda param: "&".join(param) if param and isinstance(param[0], str) else None,
    )
    # TODO: Enable case_insensitive filtering  https://issues.redhat.com/browse/RHINENG-15761
    @pytest.mark.parametrize("case_insensitive", [False], ids=["case sensitive"])
    # @pytest.mark.parametrize(
    #     "case_insensitive", [False, True], ids=["case sensitive", "case insensitive"]
    # )
    def test_filter_hosts_by_system_profile_operating_system(
        self,
        host_inventory: ApplicationHostInventory,
        setup_hosts_for_operating_system_filtering: tuple[
            list[HostOut], list[list[StructuredTag]]
        ],
        hbi_default_org_id: str,
        params: list[str],
        expected_hosts: list[int],
        case_insensitive: bool,
    ):
        """
        https://issues.redhat.com/browse/RHCLOUD-13904

        metadata:
          assignee: fstavela
          importance: high
          title: Inventory: filter hosts by operating_system
        """
        hosts, _ = setup_hosts_for_operating_system_filtering
        expected_ids = {hosts[i].id for i in expected_hosts}
        not_expected_ids = {host.id for host in hosts} - expected_ids

        filter = [
            f"[operating_system]{param.lower() if case_insensitive else param}" for param in params
        ]
        response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
        response_ids = {host.id for host in response.results}
        log_response_hosts_indices(hosts, response_ids)

        assert response.count >= len(expected_hosts)
        assert response_ids & expected_ids == expected_ids
        assert len(response_ids & not_expected_ids) == 0
        for response_host in response.results:
            assert response_host.org_id == hbi_default_org_id

    @pytest.mark.parametrize(
        "params, expected_hosts",
        [
            (["[RHEL][version][lt][]=7.10"], [0]),
            (["[RHEL][version][lte][]=7.10"], [0, 1]),
            (["[RHEL][version][gte][]=7.10"], [1, 2]),
            (["[RHEL][version][gt][]=7.10"], [2]),
            (["[RHEL][version][lt][]=7.6"], [0]),
            (["[RHEL][version][lte][]=7.6"], [0]),
            (["[RHEL][version][gte][]=7.6"], [1, 2]),
            (["[RHEL][version][gt][]=7.6"], [1, 2]),
            (["[RHEL][version][lt][]=7"], []),
            (["[RHEL][version][lte][]=7"], [0, 1]),
            (["[RHEL][version][gte][]=7"], [0, 1, 2]),
            (["[RHEL][version][gt][]=7"], [2]),
            (["[RHEL][version][gt][]=8"], []),
            (["[RHEL][version][gte][]=8"], [2]),
            (["[RHEL][version][gte][]=7.10", "[RHEL][version][lte][]=7.10"], [1]),
            (["[RHEL][version][gt][]=7", "[RHEL][version][lt][]=8"], []),
            # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-18750 is fixed
            # (["[RHEL][version][gte][]=7", "[RHEL][version][lte][]=8"], [0, 1, 2]),
            (["[RHEL][version][eq][]=7"], [0, 1]),
            (["[RHEL][version][eq][]=8"], [2]),
            (["[RHEL][version][eq][]=7.10"], [1]),
            (["[RHEL][version][eq][]=7.1"], []),
            (["[RHEL][version][eq][]=7.5", "[RHEL][version][eq][]=8.0"], [0, 2]),
            (["[RHEL][version][eq][]=7.6", "[RHEL][version][eq][]=8.0"], [2]),
            (["[RHEL][version][eq][]=7", "[RHEL][version][eq][]=8.0"], [0, 1, 2]),
            (["[RHEL][version][eq][]=7", "[RHEL][version][eq][]=8"], [0, 1, 2]),
            (["[RHEL][version][eq][]=7", "[RHEL][version][eq][]=7"], [0, 1]),
            (["[RHEL][version][eq][]=7.5", "[RHEL][version][gt][]=7.10"], [0, 2]),
            (["[RHEL][version][eq][]=7.5", "[RHEL][version][gt][]=7.5"], [0, 1, 2]),
            (
                [
                    "[RHEL][version][eq][]=7.5",
                    "[RHEL][version][eq][]=7.10",
                    "[RHEL][version][eq][]=8.0",
                ],
                [0, 1, 2],
            ),
            (
                [
                    "[RHEL][version][eq][]=7",
                    "[RHEL][version][eq][]=8",
                    "[RHEL][version][eq][]=7.5",
                ],
                [0, 1, 2],
            ),
            (
                [
                    "[RHEL][version][eq][]=7",
                    "[RHEL][version][eq][]=7.5",
                    "[RHEL][version][eq][]=8.0",
                ],
                [0, 1, 2],
            ),
            (
                [
                    "[RHEL][version][eq][]=7.5",
                    "[RHEL][version][gt][]=7.6",
                    "[RHEL][version][lt][]=8",
                ],
                [0, 1],
            ),
            (["[CentOS Linux][version][lt][]=7.10"], [3]),
            (["[CentOS Linux][version][lte][]=7.10"], [3, 4]),
            (["[CentOS Linux][version][gte][]=7.10"], [4, 5]),
            (["[CentOS Linux][version][gt][]=7.10"], [5]),
            (
                [
                    "[CentOS Linux][version][gte][]=7.10",
                    "[CentOS Linux][version][lte][]=7.10",
                ],
                [4],
            ),
            (["[CentOS Linux][version][eq][]=7"], [3, 4]),
            (["[CentOS Linux][version][eq][]=7.10"], [4]),
            (
                [
                    "[CentOS Linux][version][eq][]=7.5",
                    "[CentOS Linux][version][eq][]=8.0",
                ],
                [3, 5],
            ),
            (
                [
                    "[RHEL][version][eq][]=7.5",
                    "[CentOS Linux][version][eq][]=8.0",
                ],
                [0, 5],
            ),
            (["=nil"], [6]),
            (["=not_nil"], [0, 1, 2, 3, 4, 5]),
            (["[]=nil", "[]=not_nil"], [0, 1, 2, 3, 4, 5, 6]),
            (["[name][neq]=RHEL"], [3, 4, 5]),
            (["[name][eq]=RHEL"], [0, 1, 2]),
            (["[name][neq]=Centos Linux"], [0, 1, 2]),
            (["[name][eq]=Centos Linux"], [3, 4, 5]),
            (["[name][neq][]=CentOS Linux", "[name][neq][]=RHEL"], [0, 1, 2, 3, 4, 5]),
            (["[name][eq][]=CentOS Linux", "[name][eq][]=RHEL"], [0, 1, 2, 3, 4, 5]),
            (
                ["[name][eq]=Centos Linux", "[CentOS Linux][version][eq][]=7.10"],
                [3, 4, 5],
            ),
            (
                ["[name][eq]=Centos Linux", "[RHEL][version][eq][]=7.10"],
                [1, 3, 4, 5],
            ),
            (["[name][neq]=RHEL", "[RHEL][version][eq][]=7.10"], [1, 3, 4, 5]),
            (["[name][eq]=RHEL", "[RHEL][version][eq][]=7.10"], [0, 1, 2]),
        ],
        ids=lambda param: "&".join(param) if param and isinstance(param[0], str) else None,
    )
    # TODO: Enable case_insensitive filtering  https://issues.redhat.com/browse/RHINENG-15761
    @pytest.mark.parametrize("case_insensitive", [False], ids=["case sensitive"])
    # @pytest.mark.parametrize(
    #     "case_insensitive", [False, True], ids=["case sensitive", "case insensitive"]
    # )
    def test_filter_tags_by_system_profile_operating_system(
        self,
        setup_hosts_for_operating_system_filtering: tuple[
            list[HostOut], list[list[StructuredTag]]
        ],
        host_inventory: ApplicationHostInventory,
        params: list[str],
        expected_hosts: list[int],
        case_insensitive: bool,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-10785

        metadata:
          assignee: fstavela
          importance: high
          title: Inventory: filter tags by operating_system
        """
        _, tags = setup_hosts_for_operating_system_filtering
        expected_tags = flatten(tags[i] for i in expected_hosts)
        not_expected_tags = flatten(tags[i] for i in range(len(tags)) if i not in expected_hosts)

        filter = [
            f"[operating_system]{param.lower() if case_insensitive else param}" for param in params
        ]
        # There are too many "module" scoped hosts with tags, 50 isn't enough
        response = host_inventory.apis.tags.get_tags_json(filter=filter, per_page=100)
        _log_response_tags_indices(tags, response)

        assert response["count"] >= len(expected_tags)
        assert_tags_found(expected_tags, response["results"])
        assert_tags_not_found(not_expected_tags, response["results"])

    @pytest.mark.ephemeral
    def test_system_profile_endpoint_operating_system(
        self,
        setup_hosts_for_operating_system_filtering: tuple[
            list[HostOut], list[list[StructuredTag]]
        ],
        host_inventory: ApplicationHostInventory,
    ):
        """
        Test enumerating all operating_system values in system_profile

        JIRA: https://issues.redhat.com/browse/ESSNTL-2751

        metadata:
            assignee: fstavela
            importance: high
            title: Inventory: operating_system values enumerating
        """
        hosts, _ = setup_hosts_for_operating_system_filtering
        hosts = hosts[:7]  # We don't want hosts from different account
        valid_values: Counter[str] = Counter()
        for host in hosts:
            response = host_inventory.apis.hosts.get_host_system_profile(host)
            operating_system = response.system_profile.operating_system
            if operating_system is not None:
                os_string = os_dict_to_str(operating_system.to_dict())
                valid_values.update([os_string])

        api_results = host_inventory.apis.system_profile.get_operating_systems()
        items = {}
        for result in api_results:
            items[os_dict_to_str(result.value)] = result.count
        assert all(value in items for value in valid_values.keys())
        assert all(items[os_string] >= count for os_string, count in valid_values.items())

        for value, count in items.items():
            parameters = os_filter_param(value)
            api_result = host_inventory.apis.hosts.get_hosts_response(filter=[parameters])
            assert api_result.total == count

    @pytest.mark.ephemeral
    def test_system_profile_operating_system_search(
        self, host_inventory: ApplicationHostInventory
    ):
        """
        Test that search parameter is not allowed on /system_profile/operating_system endpoint

        JIRA: https://issues.redhat.com/browse/ESSNTL-2923

        metadata:
            assignee: fstavela
            importance: medium
            title: test search parameter on /system_profile/operating_system endpoint
        """
        with pytest.raises(ApiTypeError):
            host_inventory.apis.system_profile.get_operating_systems(search="test")


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "params, expected_hosts",
    [
        (["[controller_version][]=1.2.3"], [0, 2]),
        (["[hub_version][]=4.5.6"], [0]),
        (["[catalog_worker_version][]=7.8.9"], [0]),
        (["[sso_version][]=10.11.12"], [0]),
        (["[controller_version][]=nil"], [3]),
        (["[hub_version][]=nil"], [3]),
        (["[catalog_worker_version][]=nil"], [2, 3]),
        (["[sso_version][]=nil"], [2, 3]),
        (["[controller_version][]=not_nil"], [0, 1, 2]),
        (["[hub_version][]=not_nil"], [0, 1, 2]),
        (["[catalog_worker_version][]=not_nil"], [0, 1]),
        (["[sso_version][]=not_nil"], [0, 1]),
        (["[controller_version][]=1.2.3", "[controller_version][]=4.5.6"], [0, 1, 2]),
        (["[controller_version][]=1.2.3", "[controller_version][]=nil"], [0, 2, 3]),
        (["[controller_version][]=not_nil", "[controller_version][]=nil"], [0, 1, 2, 3]),
        (
            [
                "[controller_version][]=1.2.3",
                "[controller_version][]=4.5.6",
                "[controller_version][]=nil",
            ],
            [0, 1, 2, 3],
        ),
        (["[controller_version][]=1.2.3", "[hub_version][]=4.5.6"], [0]),
        (["[controller_version][]=1.2.3", "[hub_version][]=7.8.9"], [2]),
        (
            [
                "[controller_version][]=1.2.3",
                "[hub_version][]=4.5.6",
                "[catalog_worker_version][]=7.8.9",
                "[sso_version][]=10.11.12",
            ],
            [0],
        ),
        (
            [
                "[controller_version][]=1.2.3",
                "[hub_version][]=4.5.6",
                "[catalog_worker_version][]=7.8.9",
                "[sso_version][]=nil",
            ],
            [],
        ),
        (
            [
                "[controller_version][]=1.2.3",
                "[hub_version][]=7.8.9",
                "[controller_version][]=4.5.6",
            ],
            [1, 2],
        ),
        (
            [
                "[controller_version][]=4.5.6",
                "[hub_version][]=7.8.9",
                "[controller_version][]=1.2.3",
            ],
            [1, 2],
        ),
    ],
)
def test_filter_hosts_by_system_profile_ansible(
    setup_hosts_for_ansible_filtering,
    host_inventory: ApplicationHostInventory,
    params,
    expected_hosts,
):
    """
    https://issues.redhat.com/browse/ESSNTL-1508

    metadata:
      assignee: fstavela
      importance: high
      title: Inventory: filter hosts by ansible
    """
    hosts = setup_hosts_for_ansible_filtering
    expected_ids = {hosts[i].id for i in expected_hosts}
    not_expected_ids = {host.id for host in hosts} - expected_ids

    filter = [f"[ansible]{param}" for param in params]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    response_ids = {host.id for host in response.results}
    log_response_hosts_indices(hosts, response_ids)

    assert response.count >= len(expected_hosts)
    assert response_ids & expected_ids == expected_ids
    assert len(response_ids & not_expected_ids) == 0


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "params, expected_hosts",
    [
        (["[sap_system][]=true"], [0, 1, 2]),
        (["[sap_system][]=false"], [3, 4, 5]),
        (["[sids][]=nil"], [5, 6]),
        (
            [
                "[sids][]=H20",
                "[sids][]=H30",
            ],
            [1, 3, 4],
        ),
        (["[sap_system][]=true", "[sids][]=H20"], [0, 1]),
        (["[instance_number][]=nil"], [1, 3, 4, 6]),
        (["[instance_number][]=nil", "[instance_number][]=not_nil"], [0, 1, 2, 3, 4, 5, 6]),
        (["[version][]=not_nil"], [0, 1, 2]),
        (["[version][]=nil"], [3, 4, 5, 6]),
        (["[sids][]=not_nil", "[instance_number][]=nil"], [1, 3, 4]),
        (["[version][]=not_nil", "[instance_number][]=not_nil"], [0, 2]),
        (["[version][]=1.00.122.04.1478575636", "[instance_number][]=02"], [2]),
        (["[version][]=2.00.122.04.1478575636", "[instance_number][]=03"], []),
        (
            [
                "[sap_system][]=true",
                "[sids][]=H20",
                "[instance_number][]=01",
                "[version][]=1.00.122.04.1478575636",
            ],
            [0],
        ),
        (
            [
                "[sap_system][]=true",
                "[sids][]=H20",
                "[sids][]=H30",
                "[instance_number][]=nil",
                "[version][]=2.00.122.04.1478575636",
            ],
            [1],
        ),
        (
            [
                "[sap_system][]=true",
                "[sids][]=H20",
                "[sids][]=H30",
                "[instance_number][]=not_nil",
                "[version][]=1.00.122.04.1478575636",
            ],
            [],
        ),
        (
            [
                "[sap_system][]=true",
                "[sids][]=H20",
                "[sids][]=H30",
                "[version][]=1.00.122.04.1478575636",
            ],
            [],
        ),
        (["[sap_system][]=false", "[sids][]=H20", "[sids][]=H30"], [3, 4]),
        (["[sap_system][]=false", "[sids][contains][]=H20", "[sids][contains][]=H30"], [3, 4]),
        (
            [
                "[sap_system][]=false",
                "[sids][contains][]=H20",
                "[sids][contains][]=H30",
                "[sids][contains][]=H40",
            ],
            [3],
        ),
        (
            [
                "[sap_system][]=true",
                "[sids][]=H2O",
                "[instance_number][]=08",
                "[version][]=1.00.122.04.1478575636",
            ],
            [],
        ),
    ],
)
def test_filter_hosts_by_system_profile_sap(
    setup_hosts_for_sap_filtering, host_inventory: ApplicationHostInventory, params, expected_hosts
):
    """
    https://issues.redhat.com/browse/ESSNTL-1616

    metadata:
      assignee: zabikeno
      importance: high
      title: Inventory: filter hosts by sap object
    """

    hosts = setup_hosts_for_sap_filtering
    expected_ids = {hosts[i].id for i in expected_hosts}
    not_expected_ids = {host.id for host in hosts} - expected_ids

    filter = [f"[sap]{param}" for param in params]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    response_ids = {host.id for host in response.results}
    log_response_hosts_indices(hosts, response_ids)

    assert response.count >= len(expected_hosts)
    assert response_ids & expected_ids == expected_ids
    assert len(response_ids & not_expected_ids) == 0


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "params, expected_hosts",
    [
        (["[version][]=15.2.0"], [0]),
        (["[version][]=nil"], [2]),
        (["[version][]=not_nil"], [0, 1]),
        (["[version][]=15.2.0", "[version][]=1.2.3"], [0, 1]),
        (["[version][]=15.2.0", "[version][]=nil"], [0, 2]),
        (["[version][]=not_nil", "[version][]=nil"], [0, 1, 2]),
        (
            [
                "[version][]=15.2.0",
                "[version][]=1.2.3",
                "[version][]=nil",
            ],
            [0, 1, 2],
        ),
    ],
    ids=lambda param: "&".join(param) if param and isinstance(param[0], str) else None,
)
def test_filter_hosts_by_system_profile_mssql(
    setup_hosts_for_mssql_filtering,
    host_inventory: ApplicationHostInventory,
    params,
    expected_hosts,
):
    """
    https://issues.redhat.com/browse/ESSNTL-1613

    metadata:
      assignee: fstavela
      importance: high
      title: Inventory: filter hosts by mssql
    """
    hosts = setup_hosts_for_mssql_filtering
    expected_ids = {hosts[i].id for i in expected_hosts}
    not_expected_ids = {host.id for host in hosts} - expected_ids

    filter = [f"[mssql]{param}" for param in params]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    response_ids = {host.id for host in response.results}
    log_response_hosts_indices(hosts, response_ids)

    assert response.count >= len(expected_hosts)
    assert response_ids & expected_ids == expected_ids
    assert len(response_ids & not_expected_ids) == 0


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "field",
    [
        pytest.param(field, id=field.name)
        for field in SYSTEM_PROFILE
        if field.type not in ("custom", "array")
    ],
)
def test_filter_hosts_by_system_profile_fields_nil(
    setup_hosts_for_filtering, filter_hosts, field: Field
):
    """Test generic filtering of hosts with nil and not_nil values
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      assignee: fstavela
      importance: high
      title: Generic filtering of hosts with nil and not_nil values
    """
    hosts = setup_hosts_for_filtering(field)
    hosts_ids = {host.id for host in hosts}
    non_nil_ids = {hosts[i].id for i in range(len(hosts) - 1)}

    # nil without eq comparator
    response = filter_hosts(field.name, "nil")
    assert response.count >= 1
    response_ids = {host.id for host in response.results}
    assert hosts[-1].id in response_ids
    assert len(response_ids & non_nil_ids) == 0

    # nil with eq comparator
    response = filter_hosts(field.name, "nil", "eq")
    assert response.count >= 1
    response_ids = {host.id for host in response.results}
    assert hosts[-1].id in response_ids
    assert len(response_ids & non_nil_ids) == 0

    # not nil without eq comparator
    response = filter_hosts(field.name, "not_nil")
    assert response.count >= 1
    response_ids = {host.id for host in response.results}
    assert hosts[-1].id not in response_ids
    assert response_ids & non_nil_ids == non_nil_ids

    # not nil with eq comparator
    response = filter_hosts(field.name, "not_nil", "eq")
    assert response.count >= 1
    response_ids = {host.id for host in response.results}
    assert hosts[-1].id not in response_ids
    assert response_ids & non_nil_ids == non_nil_ids

    # empty value
    if field.type in ("bool", "int", "int64"):
        # empty value without eq comparator
        with pytest.raises(ApiException) as err:
            filter_hosts(field.name, "")
        assert err.value.status == 400
        assert f" is an invalid value for field {field.name}" in err.value.body

        # empty value with eq comparator
        with pytest.raises(ApiException) as err:
            filter_hosts(field.name, "", "eq")
        assert err.value.status == 400
        assert f" is an invalid value for field {field.name}" in err.value.body
    elif field.type == "str" and field.min_len == 0:
        # empty value without eq comparator
        response = filter_hosts(field.name, "")
        assert response.count >= 1
        response_ids = {host.id for host in response.results}
        assert hosts[-2].id in response_ids
        assert response_ids & hosts_ids == {hosts[-2].id}

        # empty value with eq comparator
        response = filter_hosts(field.name, "", "eq")
        assert response.count >= 1
        response_ids = {host.id for host in response.results}
        assert hosts[-2].id in response_ids
        assert response_ids & hosts_ids == {hosts[-2].id}
    else:
        # empty value without eq comparator
        response = filter_hosts(field.name, "")
        assert response.count == 0

        # empty value with eq comparator
        response = filter_hosts(field.name, "", "eq")
        assert response.count == 0


@pytest.mark.ephemeral
def test_filter_hosts_by_system_profile_object_nil(
    setup_hosts_for_ansible_filtering,
    host_inventory: ApplicationHostInventory,
):
    """
    Test filtering hosts by object fields by nil/not_nil

    Jira: https://issues.redhat.com/browse/ESSNTL-2362

    metadata:
      assignee: fstavela
      importance: high
      title: Filtering hosts by object fields by nil/not_nil
    """
    hosts = setup_hosts_for_ansible_filtering
    not_nil_ids = {hosts[i].id for i in range(len(hosts) - 1)}

    filter = ["[ansible]=nil"]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    response_ids = {host.id for host in response.results}
    log_response_hosts_indices(hosts, response_ids)

    assert response.count >= 1
    assert hosts[-1].id in response_ids
    assert len(response_ids & not_nil_ids) == 0

    filter = ["[ansible]=not_nil"]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    response_ids = {host.id for host in response.results}
    log_response_hosts_indices(hosts, response_ids)

    assert response.count >= len(not_nil_ids)
    assert hosts[-1].id not in response_ids
    assert response_ids & not_nil_ids == not_nil_ids


# All tests that use the setup_hosts_for_os_rhc_filtering fixture are grouped here
# so that the expensive fixture (which creates 12 hosts across two accounts) runs only once.
# All tests that use the setup_hosts_for_os_display_name_filtering fixture are grouped here
# so that the expensive fixture (which creates 6 hosts across two accounts) runs only once.
@pytest.mark.usefixtures("setup_hosts_for_os_display_name_filtering")
class TestOsDisplayNameFiltering:
    @pytest.mark.parametrize(
        "params, expected_hosts",
        [
            (
                [
                    "[operating_system][RHEL][version][eq][]=7.5",
                    "[operating_system][RHEL][version][eq][]=7.10",
                ],
                [1],
            ),
            (
                [
                    "[operating_system][RHEL][version][eq][]=7.5",
                    "[operating_system][RHEL][version][eq][]=8.0",
                ],
                [],
            ),
            (
                [
                    "[operating_system][RHEL][version][eq][]=7.5",
                    "[operating_system][RHEL][version][eq][]=7.10",
                    "[operating_system][RHEL][version][eq][]=8.0",
                ],
                [1],
            ),
        ],
        ids=lambda param: "&".join(param) if param and isinstance(param[0], str) else None,
    )
    def test_filter_hosts_by_system_profile_os_display_name(
        self,
        setup_hosts_for_os_display_name_filtering: tuple[list[HostOut], list[list[StructuredTag]]],
        host_inventory: ApplicationHostInventory,
        hbi_default_org_id: str,
        params: list[str],
        expected_hosts: list[int],
    ):
        """
        https://issues.redhat.com/browse/RHINENG-10785

        metadata:
                        inv-hosts-filter-by-display_name
          assignee: fstavela
          importance: high
          title: Inventory: filter hosts by operating_system & display_name
        """
        hosts, _ = setup_hosts_for_os_display_name_filtering
        expected_ids = {hosts[i].id for i in expected_hosts}
        not_expected_ids = {host.id for host in hosts} - expected_ids

        filter = [f"{param}" for param in params]
        response = host_inventory.apis.hosts.get_hosts_response(
            display_name=f"{FILTER_OS_DISPLAY_NAME}-1", filter=filter
        )
        response_ids = {host.id for host in response.results}
        log_response_hosts_indices(hosts, response_ids)

        assert response.count >= len(expected_hosts)
        assert response_ids & expected_ids == expected_ids
        assert len(response_ids & not_expected_ids) == 0
        for response_host in response.results:
            assert response_host.org_id == hbi_default_org_id

    @pytest.mark.parametrize(
        "params, expected_hosts",
        [
            (
                [
                    "[operating_system][RHEL][version][eq][]=7.5",
                    "[operating_system][RHEL][version][eq][]=7.10",
                ],
                [1],
            ),
            (
                [
                    "[operating_system][RHEL][version][eq][]=7.5",
                    "[operating_system][RHEL][version][eq][]=8.0",
                ],
                [],
            ),
            (
                [
                    "[operating_system][RHEL][version][eq][]=7.5",
                    "[operating_system][RHEL][version][eq][]=7.10",
                    "[operating_system][RHEL][version][eq][]=8.0",
                ],
                [1],
            ),
        ],
        ids=lambda param: "&".join(param) if param and isinstance(param[0], str) else None,
    )
    def test_filter_tags_by_system_profile_os_display_name(
        self,
        setup_hosts_for_os_display_name_filtering: tuple[list[HostOut], list[list[StructuredTag]]],
        host_inventory: ApplicationHostInventory,
        params: list[str],
        expected_hosts: list[int],
    ):
        """
        https://issues.redhat.com/browse/RHINENG-10785

        metadata:
                        inv-hosts-filter-by-display_name
          assignee: fstavela
          importance: high
          title: Inventory: filter tags by operating_system & display_name
        """
        _, tags = setup_hosts_for_os_display_name_filtering
        expected_tags = flatten(tags[i] for i in expected_hosts)
        not_expected_tags = flatten(tags[i] for i in range(len(tags)) if i not in expected_hosts)

        filter = [f"{param}" for param in params]
        response = host_inventory.apis.tags.get_tags_json(
            filter=filter, display_name=f"{FILTER_OS_DISPLAY_NAME}-1"
        )
        _log_response_tags_indices(tags, response)

        assert response["count"] >= len(expected_tags)
        assert_tags_found(expected_tags, response["results"])
        assert_tags_not_found(not_expected_tags, response["results"])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "params, expected_hosts",
    [
        (["[variant][]=Centos"], []),
        (["[variant][]=RHEL AI"], [1, 2, 3, 4, 5]),
        (["[rhel_ai_version_id][]=v1.1.3"], [1, 3]),
        (["[rhel_ai_version_id][]=v1.1.2"], [2]),
        (["[rhel_ai_version_id][]=v1.1.4"], [4, 5, 6]),
        (["[rhel_ai_version_id][]=v1.1.2", "[variant][]=Centos"], []),
        (["[gpu_models][name][]=NVIDIA T1000"], [1, 3, 5, 6]),
        (["[gpu_models][name][]=NVIDIA T1000", "[gpu_models][name][]=Tesla 2"], [3]),
        (
            ["[gpu_models][name][]=NVIDIA T1000", "[gpu_models][name][]=Tesla V100-PCIE-16GB"],
            [1, 3],
        ),
        (["[gpu_models][name][]=Habana Labs Ltd. Device 10202"], [2, 3]),
        (["[gpu_models][name][]=Habana Labs Ltd. Device 1021"], [6]),
        (
            [
                "[gpu_models][name][]=Habana Labs Ltd. Device 10202",
                "[gpu_models][name][]=Habana Labs Ltd. HL-2001 AI Training Accelerator",
            ],
            [3],
        ),
        (["[gpu_models][name][]=Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34"], [1, 2, 3]),
        (
            [
                "[gpu_models][name][]=Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34",
                "[gpu_models][name][]=Advanced Micro Devices, Inc. [AMD/ATI] Device 0c31",
            ],
            [2],
        ),
        (
            [
                "[rhel_ai_version_id][]=v1.1.3",
                "[gpu_models][name][]=Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34",
            ],
            [1, 3],
        ),
        (
            [
                "[rhel_ai_version_id][]=v1.1.3",
                "[gpu_models][name][]=Advanced Micro Devices, Inc. [AMD/ATI] Device 0c350000",
            ],
            [3],
        ),
        (["[gpu_models][vendor][]=Nvidia"], [1, 3, 4, 5, 6]),
        (["[gpu_models][vendor][]=Intel"], [1, 2, 3, 4, 6]),
        (["[gpu_models][vendor][]=AMD"], [1, 2, 3, 4, 5]),
        (["[gpu_models][vendor][]=Nvidia", "[gpu_models][vendor][]=Intel"], [1, 3, 4, 6]),
    ],
)
def test_filter_hosts_by_system_profile_rhel_ai(
    setup_hosts_for_rhel_ai_filtering: list[HostWrapper],
    host_inventory: ApplicationHostInventory,
    params: list[str],
    expected_hosts: list[int],
):
    """
    https://issues.redhat.com/browse/RHINENG-14894

    metadata:
      assignee: zabikeno
      importance: high
      title: Inventory: filter hosts by rhel_ai
    """
    hosts = setup_hosts_for_rhel_ai_filtering
    expected_ids = {hosts[i].id for i in expected_hosts}
    not_expected_ids = {host.id for host in hosts} - expected_ids

    filter = [f"[workloads][rhel_ai]{param}" for param in params]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    response_ids = {host.id for host in response.results}
    log_response_hosts_indices(hosts, response_ids)

    assert response.count >= len(expected_hosts)
    assert response_ids & expected_ids == expected_ids
    assert len(response_ids & not_expected_ids) == 0
