from __future__ import annotations

import logging
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.datagen_utils import SYSTEM_PROFILE
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory.utils.tag_utils import assert_tags_not_found

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def host_tags(input_hosts: list[Any]) -> list[TagDict]:
    return [tag for host in input_hosts for tag in host.tags]


def check_tags_response(
    response: dict, expected_tags: list[TagDict], not_expected_tags: list[TagDict]
) -> None:
    assert response["count"] >= len(expected_tags)
    assert_tags_found(expected_tags, response["results"])
    assert_tags_not_found(not_expected_tags, response["results"])


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
def test_filter_tags_by_system_profile_ansible(
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
      title: Inventory: filter tags by ansible
    """
    hosts = setup_hosts_for_ansible_filtering
    expected_tags = flatten(hosts[i].tags for i in expected_hosts)
    not_expected_tags = flatten(
        hosts[i].tags for i in range(len(hosts)) if i not in expected_hosts
    )

    filter = [f"[ansible]{param}" for param in params]
    response = host_inventory.apis.tags.get_tags_response(filter=filter).json()
    check_tags_response(response, expected_tags, not_expected_tags)


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
def test_filter_tags_by_system_profile_sap(
    setup_hosts_for_sap_filtering, host_inventory: ApplicationHostInventory, params, expected_hosts
):
    """
    https://issues.redhat.com/browse/ESSNTL-1616

    metadata:
      assignee: zabikeno
      importance: high
      title: Inventory: filter tags by sap
    """
    hosts = setup_hosts_for_sap_filtering
    expected_tags = flatten(hosts[i].tags for i in expected_hosts)
    not_expected_tags = flatten(
        host.tags for i, host in enumerate(hosts) if i not in expected_hosts
    )

    filter = [f"[sap]{param}" for param in params]
    response = host_inventory.apis.tags.get_tags_response(filter=filter).json()
    check_tags_response(response, expected_tags, not_expected_tags)


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
def test_filter_tags_by_system_profile_mssql(
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
      title: Inventory: filter tags by mssql
    """
    hosts = setup_hosts_for_mssql_filtering
    expected_tags = flatten(hosts[i].tags for i in expected_hosts)
    not_expected_tags = flatten(
        host.tags for i, host in enumerate(hosts) if i not in expected_hosts
    )

    filter = [f"[mssql]{param}" for param in params]
    response = host_inventory.apis.tags.get_tags_response(filter=filter).json()
    check_tags_response(response, expected_tags, not_expected_tags)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "field",
    [
        pytest.param(field, id=field.name)
        for field in SYSTEM_PROFILE
        if field.type not in ("custom", "array")
    ],
)
def test_filter_tags_by_system_profile_fields_nil(
    setup_hosts_for_filtering, filter_tags, field: Field
):
    """Test generic filtering of tags with nil and not_nil values
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      assignee: fstavela
      importance: high
      title: Generic filtering of tags with nil and not_nil values
    """
    hosts = setup_hosts_for_filtering(field)
    all_tags: list[TagDict] = flatten(host.tags for host in hosts)
    non_nil_tags: list[TagDict] = flatten(host.tags for host in hosts[:-1])

    # nil without eq comparator
    response = filter_tags(field.name, "nil").json()
    assert response["count"] >= 1
    assert_tags_found(hosts[-1].tags, response["results"])
    assert_tags_not_found(non_nil_tags, response["results"])

    # nil with eq comparator
    response = filter_tags(field.name, "nil", "eq").json()
    assert response["count"] >= 1
    assert_tags_found(hosts[-1].tags, response["results"])
    assert_tags_not_found(non_nil_tags, response["results"])

    # not nil without eq comparator
    response = filter_tags(field.name, "not_nil").json()
    assert response["count"] >= 1
    assert_tags_found(non_nil_tags, response["results"])
    assert_tags_not_found(hosts[-1].tags, response["results"])

    # not nil with eq comparator
    response = filter_tags(field.name, "not_nil", "eq").json()
    assert response["count"] >= 1
    assert_tags_found(non_nil_tags, response["results"])
    assert_tags_not_found(hosts[-1].tags, response["results"])

    # empty value
    if field.type in ("bool", "int", "int64"):
        # empty value without eq comparator
        resp = filter_tags(field.name, "")
        assert resp.status_code == 400
        assert f" is an invalid value for field {field.name}" in resp.text

        # empty value with eq comparator
        resp = filter_tags(field.name, "", "eq")
        assert resp.status_code == 400
        assert f" is an invalid value for field {field.name}" in resp.text
    elif field.type == "str" and field.min_len == 0:
        not_empty_tags = flatten(hosts[i].tags for i in range(len(hosts)) if i != len(hosts) - 2)
        # empty value without eq comparator
        response = filter_tags(field.name, "").json()
        assert response["count"] >= 1
        assert_tags_found(hosts[-2].tags, response["results"])
        assert_tags_not_found(not_empty_tags, response["results"])

        # empty value with eq comparator
        response = filter_tags(field.name, "", "eq").json()
        assert response["count"] >= 1
        assert_tags_found(hosts[-2].tags, response["results"])
        assert_tags_not_found(not_empty_tags, response["results"])
    else:
        # empty value without eq comparator
        response = filter_tags(field.name, "").json()
        assert response["count"] == 0
        assert_tags_not_found(all_tags, response["results"])

        # empty value with eq comparator
        response = filter_tags(field.name, "", "eq").json()
        assert response["count"] == 0
        assert_tags_not_found(all_tags, response["results"])


@pytest.mark.ephemeral
def test_filter_tags_by_system_profile_object_nil(
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
    not_nil_tags = flatten(host.tags for host in hosts[:-1])

    filter = ["[ansible]=nil"]
    response = host_inventory.apis.tags.get_tags_response(filter=filter).json()
    check_tags_response(response, hosts[-1].tags, not_nil_tags)

    filter = ["[ansible]=not_nil"]
    response = host_inventory.apis.tags.get_tags_response(filter=filter).json()
    check_tags_response(response, not_nil_tags, hosts[-1].tags)


# NOTE: test_filter_tags_by_system_profile_operating_system,
# test_filter_tags_by_system_profile_os_rhc, and
# test_filter_tags_by_system_profile_os_display_name have been moved to
# test_filter_hosts.py to share the expensive setup fixtures with other OS filtering tests.
