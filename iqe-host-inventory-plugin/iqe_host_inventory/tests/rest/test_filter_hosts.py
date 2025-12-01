from __future__ import annotations

import logging
from random import randint
from urllib.parse import quote

import attr
import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.kafka_interaction import SAP_FILTER_DISPLAY_NAME
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import SYSTEM_PROFILE
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_sp_field_by_name
from iqe_host_inventory_api import ApiException
from iqe_host_inventory_api import HostOut
from iqe_host_inventory_api import HostQueryOutput
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


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "filters,expected_hosts", [(("ABC",), (0, 1)), (("C1E",), (1,)), (("ABC", "C1E"), (1,))]
)
@pytest.mark.parametrize("use_contains,use_equals", [(True, True), (False, True)])
def test_filter_hosts_by_system_profile_sap_sids(
    filters,
    expected_hosts,
    use_contains,
    use_equals,
    host_inventory: ApplicationHostInventory,
    mq_setup_hosts_for_sap_sids_filtering,
):
    """
    Test filtering hosts based on sap_sids value in system_profile

    JIRA: https://issues.redhat.com/browse/RHCLOUD-9747

    1. Issue a call to GET the hosts with filter[system_profile][sap_sids] parameter
    2. Make sure that all hosts from the result have the correct sap_sids value

    metadata:
        requirements: inv-hosts-filter-by-sp-sap_sids
        assignee: fstavela
        importance: high
        title: Inventory: Hosts filtering by sap_sids
    """
    setup_hosts = mq_setup_hosts_for_sap_sids_filtering
    all_hosts_ids = {host.id for host in setup_hosts}
    expected_ids = {setup_hosts[i].id for i in expected_hosts}

    logger.info(f"Retrieving hosts by filtering sap_sids: {filters}")
    response = host_inventory.apis.hosts.get_hosts_response(
        display_name=SAP_FILTER_DISPLAY_NAME,
        filter=[*format_sap_sids_filters(use_contains, use_equals, filters)],
    )
    response_ids = {host.id for host in response.results}
    log_response_hosts_indices(setup_hosts, response_ids)
    assert response.count >= len(expected_ids)
    assert response_ids & all_hosts_ids == expected_ids


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
            ["[RHEL][version][eq][]=7", "[RHEL][version][eq][]=8", "[RHEL][version][eq][]=7.5"],
            [0, 1, 2],
        ),
        (
            ["[RHEL][version][eq][]=7", "[RHEL][version][eq][]=7.5", "[RHEL][version][eq][]=8.0"],
            [0, 1, 2],
        ),
        (
            ["[RHEL][version][eq][]=7.5", "[RHEL][version][gt][]=7.6", "[RHEL][version][lt][]=8"],
            [0, 1],
        ),
        (["[CentOS Linux][version][lt][]=7.10"], [3]),
        (["[CentOS Linux][version][lte][]=7.10"], [3, 4]),
        (["[CentOS Linux][version][gte][]=7.10"], [4, 5]),
        (["[CentOS Linux][version][gt][]=7.10"], [5]),
        (["[CentOS Linux][version][gte][]=7.10", "[CentOS Linux][version][lte][]=7.10"], [4]),
        (["[CentOS Linux][version][eq][]=7"], [3, 4]),
        (["[CentOS Linux][version][eq][]=7.10"], [4]),
        (["[CentOS Linux][version][eq][]=7.5", "[CentOS Linux][version][eq][]=8.0"], [3, 5]),
        (["[RHEL][version][eq][]=7.5", "[CentOS Linux][version][eq][]=8.0"], [0, 5]),
        (["=nil"], [6]),
        (["=not_nil"], [0, 1, 2, 3, 4, 5]),
        (["[]=nil", "[]=not_nil"], [0, 1, 2, 3, 4, 5, 6]),
        (["[name][neq]=RHEL"], [3, 4, 5]),
        (["[name][eq]=RHEL"], [0, 1, 2]),
        (["[name][neq]=Centos linux"], [0, 1, 2]),
        (["[name][eq]=Centos Linux"], [3, 4, 5]),
        (["[name][neq][]=CentOS Linux", "[name][neq][]=RHEL"], [0, 1, 2, 3, 4, 5]),
        (["[name][eq][]=CentOS Linux", "[name][eq][]=RHEL"], [0, 1, 2, 3, 4, 5]),
        (["[name][eq]=Centos Linux", "[CentOS Linux][version][eq][]=7.10"], [3, 4, 5]),
        (["[name][eq]=Centos Linux", "[RHEL][version][eq][]=7.10"], [1, 3, 4, 5]),
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
    host_inventory: ApplicationHostInventory,
    setup_hosts_for_operating_system_filtering: tuple[list[HostOut], list[list[StructuredTag]]],
    hbi_default_org_id: str,
    params: list[str],
    expected_hosts: list[int],
    case_insensitive: bool,
):
    """
    https://issues.redhat.com/browse/RHCLOUD-13904

    metadata:
      requirements: inv-hosts-filter-by-sp-operating_system
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
      requirements: inv-hosts-filter-by-system_profile-ansible
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
      requirements: inv-hosts-filter-by-system_profile-sap
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
      requirements: inv-hosts-filter-by-system_profile-mssql
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
      requirements: inv-hosts-get-by-sp-scalar-fields
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
@pytest.mark.parametrize(
    "field",
    [
        pytest.param(field, id=field.name)
        for field in SYSTEM_PROFILE
        if field.type in ("str", "canonical_uuid", "date-time", "enum")
    ],
)
def test_filter_hosts_by_system_profile_string_fields(
    setup_hosts_for_filtering,
    filter_hosts,
    host_inventory: ApplicationHostInventory,
    field: Field,
):
    """Test generic filtering of hosts by string fields
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Generic filtering of hosts by string fields
    """
    is_enum_1 = (
        field.type == "enum"
        and field.correct_values is not None
        and len(field.correct_values) == 1
    )

    hosts = setup_hosts_for_filtering(field)
    all_hosts_ids = {host.id for host in hosts}
    expected_ids = {hosts[0].id, hosts[1].id} if is_enum_1 else {hosts[0].id}

    value = quote(hosts[0].system_profile[field.name])
    another_value = quote(hosts[1].system_profile[field.name])

    def _test_filter(comparator: str | None = None):
        response = filter_hosts(field.name, value, comparator)
        response_ids = {host.id for host in response.results}
        log_response_hosts_indices(hosts, response_ids)
        assert response.count >= len(expected_ids)
        assert response_ids & all_hosts_ids == expected_ids

    _test_filter()
    _test_filter("eq")

    # Combination on 'eq' filtering uses OR logic
    filter = [
        f"[{field.name}][]={value}",
        f"[{field.name}][]={another_value}",
    ]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    response_ids = {host.id for host in response.results}
    log_response_hosts_indices(hosts, response_ids)
    assert response.count >= 2
    assert response_ids & all_hosts_ids == {hosts[0].id, hosts[1].id}


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "field",
    [pytest.param(field, id=field.name) for field in SYSTEM_PROFILE if "int" in field.type],
)
def test_filter_hosts_by_system_profile_integer_fields(
    setup_hosts_for_filtering,
    filter_hosts,
    host_inventory: ApplicationHostInventory,
    field: Field,
):
    """Test generic filtering of hosts by integer fields
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Generic filtering of hosts by integer fields
    """
    hosts = setup_hosts_for_filtering(field)
    all_hosts_ids = {host.id for host in hosts}
    value = hosts[1].system_profile[field.name]
    lower_value = hosts[0].system_profile[field.name]
    higher_value = hosts[2].system_profile[field.name]

    def _check_response(response: HostQueryOutput, expected_ids: set[str]):
        response_ids = {host.id for host in response.results}
        log_response_hosts_indices(hosts, response_ids)
        assert response.count >= len(expected_ids)
        assert response_ids & all_hosts_ids == expected_ids

    def _test_filter(comparator: str | None, expected_ids: set[str]):
        response = filter_hosts(field.name, value, comparator)
        _check_response(response, expected_ids)

    _test_filter(None, {hosts[1].id})
    _test_filter("eq", {hosts[1].id})
    _test_filter("gt", {hosts[2].id})
    _test_filter("gte", {hosts[1].id, hosts[2].id})
    _test_filter("lt", {hosts[0].id})
    _test_filter("lte", {hosts[0].id, hosts[1].id})

    # Combination on 'eq' filtering uses OR logic
    filter = [
        f"[{field.name}][]={lower_value}",
        f"[{field.name}][]={higher_value}",
    ]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    _check_response(response, {hosts[0].id, hosts[2].id})

    filter = [
        f"[{field.name}][gt][]={lower_value}",
        f"[{field.name}][lt][]={higher_value}",
    ]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    _check_response(response, {hosts[1].id})


@pytest.mark.ephemeral
@pytest.mark.parametrize("filtered_type", ["lower", "capitalize", "upper"])
@pytest.mark.parametrize("filtered_value", ["true", "false"])
@pytest.mark.parametrize(
    "field",
    [pytest.param(field, id=field.name) for field in SYSTEM_PROFILE if field.type == "bool"],
)
def test_filter_hosts_by_system_profile_boolean_fields(
    setup_hosts_for_filtering,
    filter_hosts,
    host_inventory: ApplicationHostInventory,
    field: Field,
    filtered_type,
    filtered_value,
):
    """Test generic filtering of hosts by boolean fields
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Generic filtering of hosts by boolean fields
    """
    hosts = setup_hosts_for_filtering(field)
    all_hosts_ids = {host.id for host in hosts}
    correct_host = 0 if filtered_value == "true" else 1
    expected_ids = {hosts[correct_host].id}
    filtered_value = getattr(filtered_value, filtered_type)()

    def _test_filter(comparator: str | None = None):
        response = filter_hosts(field.name, filtered_value, comparator)
        response_ids = {host.id for host in response.results}
        log_response_hosts_indices(hosts, response_ids)
        assert response.count >= len(expected_ids)
        assert response_ids & all_hosts_ids == expected_ids

    _test_filter()
    _test_filter("eq")

    # Combination on 'eq' filtering uses OR logic
    filter = [f"[{field.name}][]=true", f"[{field.name}][]=false"]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    response_ids = {host.id for host in response.results}
    log_response_hosts_indices(hosts, response_ids)
    assert response.count >= 2
    assert response_ids & all_hosts_ids == {hosts[0].id, hosts[1].id}


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "field",
    [pytest.param(field, id=field.name) for field in SYSTEM_PROFILE if field.type == "date-time"],
)
def test_filter_hosts_by_system_profile_datetime_fields_range_operations(
    setup_hosts_for_filtering,
    filter_hosts,
    host_inventory: ApplicationHostInventory,
    field: Field,
):
    """Test range operations generic filtering of hosts by date-time fields
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Range operations generic filtering of hosts by date-time fields
    """
    hosts = setup_hosts_for_filtering(field)
    all_hosts_ids = {host.id for host in hosts}
    value = quote(hosts[1].system_profile[field.name])
    lower_value = quote(hosts[0].system_profile[field.name])
    higher_value = quote(hosts[2].system_profile[field.name])

    def _check_response(response: HostQueryOutput, expected_ids: set[str]):
        response_ids = {host.id for host in response.results}
        log_response_hosts_indices(hosts, response_ids)
        assert response.count >= len(expected_ids)
        assert response_ids & all_hosts_ids == expected_ids

    def _test_filter(comparator: str, expected_ids: set[str]):
        response = filter_hosts(field.name, value, comparator)
        _check_response(response, expected_ids)

    _test_filter("gt", {hosts[2].id})
    _test_filter("gte", {hosts[1].id, hosts[2].id})
    _test_filter("lt", {hosts[0].id})
    _test_filter("lte", {hosts[0].id, hosts[1].id})

    # Combination on range filtering uses AND logic
    filter = [
        f"[{field.name}][gt][]={lower_value}",
        f"[{field.name}][lt][]={higher_value}",
    ]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    _check_response(response, {hosts[1].id})


@pytest.mark.ephemeral
def test_filter_hosts_by_system_profile_multiple_types(host_inventory: ApplicationHostInventory):
    """Test generic filtering of hosts by fields of various types at the same time
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Generic filtering of hosts by fields of various types at the same time
    """
    hosts_data = [host_inventory.datagen.create_host_data()]
    cpus = get_sp_field_by_name("number_of_cpus")
    assert cpus.min is not None
    assert cpus.max is not None
    hosts_data[0]["system_profile"]["owner_id"] = generate_uuid()
    hosts_data[0]["system_profile"]["number_of_cpus"] = randint(cpus.min, cpus.max)
    hosts_data[0]["system_profile"]["is_marketplace"] = True
    for _ in range(3):
        host_data = host_inventory.datagen.create_host_data()
        host_data["system_profile"]["owner_id"] = hosts_data[0]["system_profile"]["owner_id"]
        host_data["system_profile"]["number_of_cpus"] = hosts_data[0]["system_profile"][
            "number_of_cpus"
        ]
        host_data["system_profile"]["is_marketplace"] = hosts_data[0]["system_profile"][
            "is_marketplace"
        ]
        hosts_data.append(host_data)
    hosts_data[1]["system_profile"]["owner_id"] = generate_uuid()
    while (
        hosts_data[2]["system_profile"]["number_of_cpus"]
        == hosts_data[0]["system_profile"]["number_of_cpus"]
    ):
        hosts_data[2]["system_profile"]["number_of_cpus"] = randint(cpus.min, cpus.max)
    hosts_data[3]["system_profile"]["is_marketplace"] = not hosts_data[0]["system_profile"][
        "is_marketplace"
    ]
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    filter = [
        f"[owner_id][]={hosts[0].system_profile['owner_id']}",
        f"[number_of_cpus]={hosts[0].system_profile['number_of_cpus']}",
        f"[is_marketplace][]={hosts[0].system_profile['is_marketplace']}",
    ]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    assert response.count == 1
    assert response.results[0].id == hosts[0].id


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "field",
    [
        pytest.param(field, id=field.name)
        for field in SYSTEM_PROFILE
        if field.type not in ("custom", "array")
    ],
)
@pytest.mark.parametrize(
    "comparator",
    [
        "not_eq",
        "not_eq_i",
        "contains",
        "contains_i",
        "starts_with",
        "starts_with_i",
        "ends_with",
        "ends_with_i",
        pytest.param(
            generate_string_of_length(10, use_punctuation=False, use_digits=False),
            id="$random string",
        ),
    ],
)
@pytest.mark.usefixtures("prepare_hosts_for_incorrect_filter_comparator")
def test_filter_hosts_by_system_profile_fields_incorrect_comparator(
    filter_hosts, field: Field, comparator
):
    """Test generic filtering of hosts with incorrect comparators
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-hosts-get-by-sp-scalar-fields, inv-api-validation
      assignee: fstavela
      importance: low
      title: Generic filtering of hosts with incorrect comparators
    """
    value = "True" if field.type == "bool" else "123"

    with raises_apierror(400) as err:
        filter_hosts(field.name, value, comparator)

    assert err.value.body is not None
    assert "invalid operation" in err.value.body.lower()


@pytest.mark.ephemeral
def test_filter_hosts_by_system_profile_multiple_values_without_brackets(
    setup_hosts_for_mssql_filtering,
    host_inventory: ApplicationHostInventory,
):
    """
    Test that filtering hosts by multiple values of the same field without [] returns error 400

    Jira: https://issues.redhat.com/browse/ESSNTL-1960

    metadata:
      requirements: inv-hosts-get-by-sp-scalar-fields, inv-api-validation
      assignee: fstavela
      importance: low
      title: Filtering hosts by multiple values of the same field without [] returns error 400
    """
    hosts = setup_hosts_for_mssql_filtering
    versions = [
        host.system_profile["workloads"]["mssql"]["version"]
        for host in hosts
        if host.system_profile.get("workloads").get("mssql", None)
    ]
    filter = [f"[mssql][version]={version}" for version in versions]
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.get_hosts_response(filter=filter)
    assert err.value.status == 400
    assert "Param filter must be appended with [] to accept multiple values." in err.value.body


@pytest.mark.ephemeral
def test_filter_hosts_by_system_profile_object_nil(
    setup_hosts_for_ansible_filtering,
    host_inventory: ApplicationHostInventory,
):
    """
    Test filtering hosts by object fields by nil/not_nil

    Jira: https://issues.redhat.com/browse/ESSNTL-2362

    metadata:
      requirements: inv-hosts-get-by-sp-scalar-fields
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


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "params, expected_hosts",
    [
        (["[]=nil"], [0, 9]),
        (["[]=not_nil"], list(range(1, 9))),
        (["[booted][]=nil"], [0, 2, 3, 9]),
        (["[booted][]=not_nil"], [1, 4, 5, 6, 7, 8]),
        (["[rollback][]=nil"], [0, 1, 3, 4, 5, 6, 9]),
        (["[rollback][]=not_nil"], [2, 7, 8]),
        (["[staged][]=nil"], [0, 1, 2, 5, 6, 9]),
        (["[staged][]=not_nil"], [3, 4, 7, 8]),
        (["[booted][image][]=nil"], [0, 2, 3, 6, 9]),
        (["[booted][image][]=not_nil"], [1, 4, 5, 7, 8]),
        (["[booted][image_digest][]=nil"], [0, 2, 3, 6, 9]),
        (["[booted][image_digest][]=not_nil"], [1, 4, 5, 7, 8]),
        (["[booted][cached_image][]=nil"], [0, 2, 3, 5, 9]),
        (["[booted][cached_image][]=not_nil"], [1, 4, 6, 7, 8]),
        (["[booted][cached_image_digest][]=nil"], [0, 2, 3, 5, 9]),
        (["[booted][cached_image_digest][]=not_nil"], [1, 4, 6, 7, 8]),
        (["[rollback][image][]=nil"], [0, 1, 3, 4, 5, 6, 9]),
        (["[rollback][image][]=not_nil"], [2, 7, 8]),
        (["[staged][image][]=nil"], [0, 1, 2, 5, 6, 9]),
        (["[staged][image][]=not_nil"], [3, 4, 7, 8]),
        (["[is]=nil"], [0, 9]),
        (["[is]=not_nil"], list(range(1, 9))),
        (["[booted][is]=nil"], [0, 2, 3, 9]),
        (["[booted][is]=not_nil"], [1, 4, 5, 6, 7, 8]),
        (["[rollback][is]=nil"], [0, 1, 3, 4, 5, 6, 9]),
        (["[rollback][is]=not_nil"], [2, 7, 8]),
        (["[staged][is]=nil"], [0, 1, 2, 5, 6, 9]),
        (["[staged][is]=not_nil"], [3, 4, 7, 8]),
        (["[booted][image][is]=nil"], [0, 2, 3, 6, 9]),
        (["[booted][image][is]=not_nil"], [1, 4, 5, 7, 8]),
        (["[booted][image_digest][is]=nil"], [0, 2, 3, 6, 9]),
        (["[booted][image_digest][is]=not_nil"], [1, 4, 5, 7, 8]),
        (["[booted][cached_image][is]=nil"], [0, 2, 3, 5, 9]),
        (["[booted][cached_image][is]=not_nil"], [1, 4, 6, 7, 8]),
        (["[booted][cached_image_digest][is]=nil"], [0, 2, 3, 5, 9]),
        (["[booted][cached_image_digest][is]=not_nil"], [1, 4, 6, 7, 8]),
        (["[rollback][image][is]=nil"], [0, 1, 3, 4, 5, 6, 9]),
        (["[rollback][image][is]=not_nil"], [2, 7, 8]),
        (["[staged][image][is]=nil"], [0, 1, 2, 5, 6, 9]),
        (["[staged][image][is]=not_nil"], [3, 4, 7, 8]),
        (["[booted][image][]=quay.io/b-7:latest"], [7]),
        (["[rollback][image][]=quay.io/r-7:latest"], [7]),
        (["[staged][image][]=quay.io/s-7:latest"], [7]),
        (
            [
                "[booted][image_digest][]=sha256:"
                "abcdefABCDEF01234567890000000000000000000000000000000000000000a7"
            ],
            [7],
        ),
        (["[booted][cached_image][]=quay.io/bc-7:latest"], [7]),
        (
            [
                "[booted][cached_image_digest][]=sha256:"
                "abcdefABCDEF0123456789000000000000000000000000000000000000000ac7"
            ],
            [7],
        ),
        (["[booted][]=nil", "[rollback][]=nil", "[staged][]=nil"], [0, 9]),
        (["[booted][]=not_nil", "[rollback][]=not_nil", "[staged][]=not_nil"], [7, 8]),
        (["[booted][]=not_nil", "[rollback][]=nil", "[staged][]=not_nil"], [4]),
        (["[booted][is]=nil", "[rollback][is]=nil", "[staged][is]=nil"], [0, 9]),
        (["[booted][is]=not_nil", "[rollback][is]=not_nil", "[staged][is]=not_nil"], [7, 8]),
        (["[booted][is]=not_nil", "[rollback][is]=nil", "[staged][is]=not_nil"], [4]),
        (["[booted][image][]=quay.io/b-1:latest", "[booted][image][]=quay.io/b-7:latest"], [1, 7]),
        (["[booted][image][]=not_nil", "[booted][cached_image][]=not_nil"], [1, 4, 7, 8]),
        (["[booted][image][]=not_nil", "[staged][image][]=not_nil"], [4, 7, 8]),
        (["[booted][image][is]=not_nil", "[booted][cached_image][is]=not_nil"], [1, 4, 7, 8]),
        (["[booted][image][is]=not_nil", "[staged][image][is]=not_nil"], [4, 7, 8]),
        (["[booted][image][]=quay.io/b-4:latest", "[staged][image][]=quay.io/s-4:latest"], [4]),
        (["[booted][image][]=quay.io/b-4:latest", "[staged][image][]=quay.io/s-7:latest"], []),
        (
            [
                "[booted][image][]=quay.io/b-7:latest",
                "[booted][image_digest][]=sha256:"
                "abcdefABCDEF01234567890000000000000000000000000000000000000000a7",
                "[booted][cached_image][]=quay.io/bc-7:latest",
                "[booted][cached_image_digest][]=sha256:"
                "abcdefABCDEF0123456789000000000000000000000000000000000000000ac7",
            ],
            [7],
        ),
        (
            [
                "[booted][image][]=quay.io/b-5:latest",
                "[booted][image_digest][]=sha256:"
                "abcdefABCDEF01234567890000000000000000000000000000000000000000a5",
                "[booted][cached_image][]=quay.io/bc-6:latest",
                "[booted][cached_image_digest][]=sha256:"
                "abcdefABCDEF0123456789000000000000000000000000000000000000000ac6",
            ],
            [],
        ),
        (
            [
                "[staged][image][]=quay.io/s-7:latest",
                "[rollback][image_digest][]=sha256:"
                "abcdefABCDEF01234567890000000000000000000000000000000000000000b7",
                "[booted][cached_image][]=quay.io/bc-7:latest",
            ],
            [7],
        ),
        (
            [
                "[booted][image][]=quay.io/b-7:latest",
                "[booted][image_digest][]=not_nil",
            ],
            [7],
        ),
        (
            [
                "[booted][image][]=quay.io/b-7:latest",
                "[booted][image_digest][is]=not_nil",
            ],
            [7],
        ),
    ],
)
def test_filter_hosts_by_system_profile_bootc_status(
    setup_hosts_for_bootc_status_filtering,
    host_inventory: ApplicationHostInventory,
    params,
    expected_hosts,
):
    """
    https://issues.redhat.com/browse/RHINENG-8987

    metadata:
      requirements: inv-hosts-filter-by-system_profile-bootc_status
      assignee: fstavela
      importance: high
      title: Inventory: filter hosts by bootc_status
    """
    hosts = setup_hosts_for_bootc_status_filtering
    expected_ids = {hosts[i].id for i in expected_hosts}
    not_expected_ids = {host.id for host in hosts} - expected_ids

    filter = [f"[bootc_status]{param}" for param in params]
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
        (["[bootc_status][booted][image_digest][is]=nil", "[host_type]=nil"], [0, 2, 3, 6]),
        (["[bootc_status][booted][image_digest][is]=not_nil", "[host_type]=nil"], [1, 4, 5, 7, 8]),
        (["[bootc_status][booted][image_digest][is]=nil", "[host_type]=not_nil"], [9]),
        (["[bootc_status][booted][image_digest][is]=nil", "[host_type]=edge"], [9]),
    ],
)
def test_filter_hosts_by_system_profile_bootc_status_host_type(
    setup_hosts_for_bootc_status_filtering,
    host_inventory: ApplicationHostInventory,
    params,
    expected_hosts,
):
    """
    https://issues.redhat.com/browse/RHINENG-8987

    metadata:
      requirements: inv-hosts-filter-by-system_profile-bootc_status,
                    inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Inventory: filter hosts by bootc_status & host_type
    """
    hosts = setup_hosts_for_bootc_status_filtering
    expected_ids = {hosts[i].id for i in expected_hosts}
    not_expected_ids = {host.id for host in hosts} - expected_ids

    filter = [f"{param}" for param in params]
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
        (["[operating_system][RHEL][version][eq][]=8.6", "[rhc_client_id][]=not_nil"], [3]),
        (["[operating_system][RHEL][version][eq][]=8.6", "[rhc_client_id][]=nil"], [0]),
        (
            [
                "[operating_system][RHEL][version][eq][]=8.6",
                "[operating_system][RHEL][version][eq][]=7.10",
                "[rhc_client_id][]=not_nil",
            ],
            [3, 4],
        ),
        (
            [
                "[operating_system][RHEL][version][eq][]=8.6",
                "[operating_system][RHEL][version][eq][]=7.10",
                "[rhc_client_id][]=nil",
            ],
            [0, 1],
        ),
    ],
    ids=lambda param: "&".join(param) if param and isinstance(param[0], str) else None,
)
def test_filter_hosts_by_system_profile_os_rhc(
    setup_hosts_for_os_rhc_filtering: list[HostWrapper],
    host_inventory: ApplicationHostInventory,
    hbi_default_org_id: str,
    params: list[str],
    expected_hosts: list[int],
):
    """
    https://issues.redhat.com/browse/RHINENG-9784

    metadata:
      requirements: inv-hosts-filter-by-sp-operating_system,
                    inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Inventory: filter hosts by operating_system & rhc_client_id
    """
    hosts = setup_hosts_for_os_rhc_filtering
    expected_ids = {hosts[i].id for i in expected_hosts}
    not_expected_ids = {host.id for host in hosts} - expected_ids

    filter = [f"{param}" for param in params]
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
    setup_hosts_for_os_display_name_filtering: tuple[list[HostOut], list[list[StructuredTag]]],
    host_inventory: ApplicationHostInventory,
    hbi_default_org_id: str,
    params: list[str],
    expected_hosts: list[int],
):
    """
    https://issues.redhat.com/browse/RHINENG-10785

    metadata:
      requirements: inv-hosts-filter-by-sp-operating_system,
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


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "param",
    [
        "[Cent][version][lt][]=7.10",
        "[Linux][version][gte][]=7.5",
        "[][version][eq][]=7",
    ],
)
def test_filter_hosts_with_invalid_system_profile_operating_system(
    param: str,
    host_inventory: ApplicationHostInventory,
):
    """
    metadata:
      requirements: inv-hosts-filter-by-sp-operating_system
      assignee: msager
      importance: medium
      negative: true
      title: Inventory: attempt to filter hosts using an invalid operating_system

    """
    filter = [f"[operating_system]{param}"]

    with raises_apierror(
        400,
        match_message="operating_system filter only supports these OS names: ['RHEL', 'CentOS', 'CentOS Linux'].",  # noqa
    ):
        host_inventory.apis.hosts.get_hosts(filter=filter)


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
        (["[nvidia_gpu_models][]=NVIDIA T1000"], [1, 3, 5, 6]),
        (["[nvidia_gpu_models][]=NVIDIA T1000", "[nvidia_gpu_models][]=Tesla 2"], [3]),
        (["[nvidia_gpu_models][]=NVIDIA T1000", "[nvidia_gpu_models][]=Tesla"], [1, 3]),
        (
            ["[nvidia_gpu_models][]=NVIDIA T1000", "[nvidia_gpu_models][]=Tesla V100-PCIE-16GB"],
            [1, 3],
        ),
        (["[intel_gaudi_hpu_models][]=Habana Labs Ltd. Device 10202"], [2, 3]),
        (["[intel_gaudi_hpu_models][]=Habana Labs Ltd. Device 1021"], [6]),
        (
            [
                "[intel_gaudi_hpu_models][]=Habana Labs Ltd. Device 10202",
                "[intel_gaudi_hpu_models][]=Habana Labs Ltd. HL-2001 AI Training Accelerator",
            ],
            [3],
        ),
        (["[amd_gpu_models][]=Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34"], [1, 2, 3]),
        (
            [
                "[amd_gpu_models][]=Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34",
                "[amd_gpu_models][]=Advanced Micro Devices, Inc. [AMD/ATI] Device 0c31",
            ],
            [2],
        ),
        (
            [
                "[rhel_ai_version_id][]=v1.1.3",
                "[amd_gpu_models][]=Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34",
            ],
            [1, 3],
        ),
        (
            [
                "[rhel_ai_version_id][]=v1.1.3",
                "[amd_gpu_models][]=Advanced Micro Devices, Inc. [AMD/ATI] Device 0c350000",
            ],
            [3],
        ),
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
      requirements: inv-hosts-filter-by-system_profile-rhel_ai
      assignee: zabikeno
      importance: high
      title: Inventory: filter hosts by rhel_ai
    """
    hosts = setup_hosts_for_rhel_ai_filtering
    expected_ids = {hosts[i].id for i in expected_hosts}
    not_expected_ids = {host.id for host in hosts} - expected_ids

    filter = [f"[rhel_ai]{param}" for param in params]
    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    response_ids = {host.id for host in response.results}
    log_response_hosts_indices(hosts, response_ids)

    assert response.count >= len(expected_hosts)
    assert response_ids & expected_ids == expected_ids
    assert len(response_ids & not_expected_ids) == 0
