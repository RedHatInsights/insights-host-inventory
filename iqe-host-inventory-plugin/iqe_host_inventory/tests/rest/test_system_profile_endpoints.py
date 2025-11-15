import logging
from collections import Counter

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory_api import ApiTypeError
from iqe_host_inventory_api import HostOut
from iqe_host_inventory_api import StructuredTag

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


def paginate_test_impl(api):
    from pprint import pprint

    result = api()
    assert result.total > 1
    pprint(result)

    def _fetch_result(page, per_page):
        page = api(page=page, per_page=per_page)
        assert page.count <= per_page
        assert page.total == result.total
        pprint(page)
        return page.results

    (result1,) = _fetch_result(page=1, per_page=1)
    (result2,) = _fetch_result(page=2, per_page=1)

    atonce = _fetch_result(page=1, per_page=2)

    assert result.results[:2] == [result1, result2]
    assert atonce == [result1, result2]


def os_dict_to_str(operating_system):
    if not isinstance(operating_system, dict):
        operating_system = operating_system.to_dict()
    return f"{operating_system['name']} {operating_system['major']}.{operating_system['minor']}"


def os_filter_param(operating_system: str):
    name, version = operating_system.rsplit(" ", 1)
    return f"[operating_system][{name}][version][eq][]={version}"


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_kafka_setup_hosts_for_sap_sids_endpoint")
def test_sap_sids_pagination(host_inventory: ApplicationHostInventory):
    """
    metadata:
        requirements: inv-pagination, inv-system_profile-get-sap_sids
        assignee: fstavela
        importance: medium
        title: Inventory: sap_sid pagination
    """
    paginate_test_impl(host_inventory.apis.system_profile.get_sap_sids_response)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("mq_setup_hosts_for_sap_system_filtering")
def test_sap_systems_pagination(host_inventory: ApplicationHostInventory):
    """
    metadata:
        requirements: inv-pagination, inv-system_profile-get-sap_system
        assignee: fstavela
        importance: medium
        title: Inventory: sap_system pagination
    """
    paginate_test_impl(host_inventory.apis.system_profile.get_sap_systems_response)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("setup_hosts_for_operating_system_filtering")
def test_operating_systems_pagination(host_inventory: ApplicationHostInventory):
    """
    metadata:
        requirements: inv-pagination, inv-system_profile-operating_system
        assignee: fstavela
        importance: medium
        title: Inventory: operating_system pagination
    """
    paginate_test_impl(host_inventory.apis.system_profile.get_operating_systems_response)


@pytest.mark.ephemeral
def test_system_profile_endpoint_sap_system(
    host_inventory: ApplicationHostInventory,
    mq_setup_hosts_for_sap_system_filtering,
):
    """
    Test enumerating all sap_system values in system_profile

    JIRA: https://issues.redhat.com/browse/RHCLOUD-9059

    1. Issue a call to GET all available sap_system values and number of systems with this value
    2. Issue calls to GET filtered hosts based on sap_system values from previous call
    3. Make sure that all values from sap_system endpoint are valid and that number of
       systems with this value is correct

    metadata:
        requirements: inv-system_profile-get-sap_system
        assignee: fstavela
        importance: high
        title: Inventory: sap_system values enumerating
    """
    api_result = host_inventory.apis.system_profile.get_sap_systems_response()
    valid_values = ["true", "false"]
    items = {}
    for result in api_result.results:
        items[result.value] = result.count

    assert api_result.total == len(valid_values)
    assert len(items) == len(valid_values)
    assert all(str(value).lower() in valid_values for value in items)
    assert all(count >= 1 for count in items.values())

    for value, count in items.items():
        filter = [f"[sap_system]={value}"]
        api_result = host_inventory.apis.hosts.get_hosts_response(filter=filter)
        assert api_result.total == count


@pytest.mark.ephemeral
def test_system_profile_endpoint_sap_sids(
    host_inventory: ApplicationHostInventory,
    hbi_kafka_setup_hosts_for_sap_sids_endpoint,
):
    """
    Test enumerating all sap_sids values in system_profile

    JIRA: https://issues.redhat.com/browse/RHCLOUD-9059

    1. Issue a call to GET all available sap_sids values and number of systems with this value
    2. Issue calls to GET filtered hosts based on sap_sids values from previous call
    3. Make sure that all values from sap_sids endpoint are valid and that number of
       systems with this value is correct

    metadata:
        requirements: inv-system_profile-get-sap_sids
        assignee: fstavela
        importance: high
        title: Inventory: sap_sids values enumerating
    """
    api_result = host_inventory.apis.system_profile.get_sap_sids_response()
    valid_values: Counter[str] = Counter()
    for host in hbi_kafka_setup_hosts_for_sap_sids_endpoint:
        valid_values.update(host.system_profile["workloads"]["sap"]["sids"])

    items: dict[str, int] = {}
    for result in api_result.results:
        items[result.value] = result.count
    assert all(value in items for value in valid_values.keys())
    assert all(items[sid] >= count for sid, count in valid_values.items())

    for value, count in items.items():
        filter = [f"[sap_sids][]={value}"]
        api_result = host_inventory.apis.hosts.get_hosts_response(filter=filter)
        assert api_result.total == count


@pytest.mark.ephemeral
def test_system_profile_sap_sids_search(
    host_inventory: ApplicationHostInventory, hbi_kafka_setup_hosts_for_sap_sids_endpoint
):
    """
    Test enumerating sap_sids values with search parameter

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10069

    1. Issue a call to GET all available sap_sids values that contain the searched string
    2. Make sure that all values from sap_sids endpoint are valid and they contain the
       string from the search parameter

    metadata:
        requirements: inv-system_profile-get-sap_sids
        assignee: fstavela
        importance: medium
        title: Inventory: sap_sids values enumerating with search parameter
    """
    api_results = host_inventory.apis.system_profile.get_sap_sids(search="BC")
    assert any(result.value == "ABC" for result in api_results)
    assert all("BC" in result.value for result in api_results)


@pytest.mark.ephemeral
def test_system_profile_endpoint_operating_system(
    setup_hosts_for_operating_system_filtering: tuple[list[HostOut], list[list[StructuredTag]]],
    host_inventory: ApplicationHostInventory,
):
    """
    Test enumerating all operating_system values in system_profile

    JIRA: https://issues.redhat.com/browse/ESSNTL-2751

    metadata:
        requirements: inv-system_profile-operating_system
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
@pytest.mark.usefixtures("setup_hosts_for_operating_system_filtering")
def test_system_profile_operating_system_search(host_inventory: ApplicationHostInventory):
    """
    Test that search parameter is not allowed on /system_profile/operating_system endpoint

    JIRA: https://issues.redhat.com/browse/ESSNTL-2923

    metadata:
        requirements: inv-system_profile-operating_system
        assignee: fstavela
        importance: medium
        title: test search parameter on /system_profile/operating_system endpoint
    """
    with pytest.raises(ApiTypeError):
        host_inventory.apis.system_profile.get_operating_systems(search="test")
