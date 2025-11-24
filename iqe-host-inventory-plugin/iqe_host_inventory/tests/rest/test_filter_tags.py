from __future__ import annotations

import logging
from random import randint
from typing import Any
from urllib.parse import quote

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.test_filter_hosts import FILTER_OS_DISPLAY_NAME
from iqe_host_inventory.tests.rest.test_filter_hosts import format_sap_sids_filters
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import SYSTEM_PROFILE
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_sp_field_by_name
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory.utils.tag_utils import assert_tags_not_found
from iqe_host_inventory_api import ActiveTags
from iqe_host_inventory_api import ApiException
from iqe_host_inventory_api import HostOut
from iqe_host_inventory_api import StructuredTag

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def host_tags(input_hosts: list[Any]) -> list[TagDict]:
    return [tag for host in input_hosts for tag in host.tags]


def log_response_tags_indices(my_tags: list[list[StructuredTag]], response: ActiveTags):
    response_tags = [res_item.tag for res_item in response.results]
    response_tags_indices = set()
    for res_tag in response_tags:
        found_index = -1
        for i, tag_list in enumerate(my_tags):
            search_list = [tag.to_dict() for tag in tag_list]
            if res_tag in search_list:
                found_index = i
                break
        if found_index != -1:
            response_tags_indices.add(found_index)
    logger.info(f"Response tags indices: {response_tags_indices}")


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "filters,expected_hosts", [(("ABC",), (0, 1)), (("C1E",), (1,)), (("ABC", "C1E"), (1,))]
)
@pytest.mark.parametrize("use_contains,use_equals", [(True, True), (False, True)])
def test_filter_tags_by_system_profile_sap_sids(
    filters: tuple[str, ...],
    expected_hosts: tuple[int, ...],
    use_contains: bool,
    use_equals: bool,
    host_inventory: ApplicationHostInventory,
    mq_setup_hosts_for_sap_sids_filtering,
):
    """
    Test filtering tags based on sap_sids value in system_profile

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10412

    1. Issue a call to GET the tags with filter[system_profile][sap_sids] parameter
    2. Make sure that the correct tags are in the result

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-sp-sap_sids
        assignee: fstavela
        importance: medium
        title: Inventory: Tags filtering by sap_sids
    """
    setup_hosts = mq_setup_hosts_for_sap_sids_filtering
    not_expected_hosts = set(range(len(setup_hosts))) - set(expected_hosts)
    expected_tags = host_tags([setup_hosts[i] for i in expected_hosts])
    not_expected_tags = host_tags([setup_hosts[i] for i in not_expected_hosts])

    param_list = [*format_sap_sids_filters(use_contains, use_equals, filters)]
    logger.info(f"Retrieving tags by filtering sap_sids: {filters}")
    response = host_inventory.apis.tags.get_tags_response(filter=param_list)
    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


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
      requirements: inv-tags-get-list, inv-hosts-filter-by-system_profile-ansible
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
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


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
      requirements: inv-tags-get-list, inv-hosts-filter-by-system_profile-sap
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
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


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
      requirements: inv-tags-get-list, inv-hosts-filter-by-system_profile-mssql
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
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


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
      requirements: inv-tags-get-list, inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Generic filtering of tags with nil and not_nil values
    """
    hosts = setup_hosts_for_filtering(field)
    all_tags: list[TagDict] = flatten(host.tags for host in hosts)
    non_nil_tags: list[TagDict] = flatten(host.tags for host in hosts[:-1])

    # nil without eq comparator
    response = filter_tags(field.name, "nil")
    assert response.count >= 1
    assert_tags_found(hosts[-1].tags, response.results)
    assert_tags_not_found(non_nil_tags, response.results)

    # nil with eq comparator
    response = filter_tags(field.name, "nil", "eq")
    assert response.count >= 1
    assert_tags_found(hosts[-1].tags, response.results)
    assert_tags_not_found(non_nil_tags, response.results)

    # not nil without eq comparator
    response = filter_tags(field.name, "not_nil")
    assert response.count >= 1
    assert_tags_found(non_nil_tags, response.results)
    assert_tags_not_found(hosts[-1].tags, response.results)

    # not nil with eq comparator
    response = filter_tags(field.name, "not_nil", "eq")
    assert response.count >= 1
    assert_tags_found(non_nil_tags, response.results)
    assert_tags_not_found(hosts[-1].tags, response.results)

    # empty value
    if field.type in ("bool", "int", "int64"):
        # empty value without eq comparator
        with pytest.raises(ApiException) as err:
            filter_tags(field.name, "")
        assert err.value.status == 400
        assert f" is an invalid value for field {field.name}" in err.value.body

        # empty value with eq comparator
        with pytest.raises(ApiException) as err:
            filter_tags(field.name, "", "eq")
        assert err.value.status == 400
        assert f" is an invalid value for field {field.name}" in err.value.body
    elif field.type == "str" and field.min_len == 0:
        not_empty_tags = flatten(hosts[i].tags for i in range(len(hosts)) if i != len(hosts) - 2)
        # empty value without eq comparator
        response = filter_tags(field.name, "")
        assert response.count >= 1
        assert_tags_found(hosts[-2].tags, response.results)
        assert_tags_not_found(not_empty_tags, response.results)

        # empty value with eq comparator
        response = filter_tags(field.name, "", "eq")
        assert response.count >= 1
        assert_tags_found(hosts[-2].tags, response.results)
        assert_tags_not_found(not_empty_tags, response.results)
    else:
        # empty value without eq comparator
        response = filter_tags(field.name, "")
        assert response.count == 0
        assert_tags_not_found(all_tags, response.results)

        # empty value with eq comparator
        response = filter_tags(field.name, "", "eq")
        assert response.count == 0
        assert_tags_not_found(all_tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "field",
    [
        pytest.param(field, id=field.name)
        for field in SYSTEM_PROFILE
        if field.type in ("str", "canonical_uuid", "date-time", "enum")
    ],
)
def test_filter_tags_by_system_profile_string_fields(
    setup_hosts_for_filtering,
    filter_tags,
    host_inventory: ApplicationHostInventory,
    field: Field,
):
    """Test generic filtering of tags by string fields
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-tags-get-list, inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Generic filtering of tags by string fields
    """
    is_enum_1 = (
        field.type == "enum"
        and field.correct_values is not None
        and len(field.correct_values) == 1
    )

    hosts = setup_hosts_for_filtering(field)
    if is_enum_1:
        expected_tags = host_tags(hosts[:2])
        not_expected_tags = host_tags(hosts[2:])
    else:
        expected_tags = host_tags(hosts[:1])
        not_expected_tags = host_tags(hosts[1:])

    value = quote(hosts[0].system_profile[field.name])
    another_value = quote(hosts[1].system_profile[field.name])

    def _test_filter(comparator: str | None = None):
        response = filter_tags(field.name, value, comparator)
        assert response.count >= len(expected_tags)
        assert_tags_found(expected_tags, response.results)
        assert_tags_not_found(not_expected_tags, response.results)

    _test_filter()
    _test_filter("eq")

    filter = [f"[{field.name}][]={value}", f"[{field.name}][]={another_value}"]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    expected_tags = host_tags(hosts[:2])
    not_expected_tags = host_tags(hosts[2:])
    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "field",
    [pytest.param(field, id=field.name) for field in SYSTEM_PROFILE if "int" in field.type],
)
def test_filter_tags_by_system_profile_integer_fields(
    setup_hosts_for_filtering,
    filter_tags,
    host_inventory: ApplicationHostInventory,
    field: Field,
):
    """Test generic filtering of tags by integer fields
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-tags-get-list, inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Generic filtering of tags by integer fields
    """
    hosts = setup_hosts_for_filtering(field)
    value = hosts[1].system_profile[field.name]
    lower_value = hosts[0].system_profile[field.name]
    higher_value = hosts[2].system_profile[field.name]

    def _check_response(
        response: ActiveTags, expected_tags: list[TagDict], not_expected_tags: list[TagDict]
    ):
        assert response.count >= len(expected_tags)
        assert_tags_found(expected_tags, response.results)
        assert_tags_not_found(not_expected_tags, response.results)

    def _test_filter(
        comparator: str | None, expected_tags: list[TagDict], not_expected_tags: list[TagDict]
    ):
        response = filter_tags(field.name, value, comparator)
        _check_response(response, expected_tags, not_expected_tags)

    _test_filter(None, hosts[1].tags, host_tags(hosts[:1] + hosts[2:]))
    _test_filter("eq", hosts[1].tags, host_tags(hosts[:1] + hosts[2:]))
    _test_filter("gt", hosts[2].tags, host_tags(hosts[:2] + hosts[3:]))
    _test_filter("gte", host_tags(hosts[1:3]), host_tags(hosts[:1] + hosts[3:]))
    _test_filter("lt", hosts[0].tags, host_tags(hosts[1:]))
    _test_filter("lte", host_tags(hosts[:2]), host_tags(hosts[2:]))

    # Combination on 'eq' filtering uses OR logic
    filter = [f"[{field.name}][]={lower_value}", f"[{field.name}][]={value}"]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    _check_response(response, host_tags(hosts[:2]), host_tags(hosts[2:]))

    # Combination on range filtering uses AND logic
    filter = [f"[{field.name}][gt][]={lower_value}", f"[{field.name}][lt][]={higher_value}"]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    _check_response(response, hosts[1].tags, host_tags(hosts[:1] + hosts[2:]))


@pytest.mark.ephemeral
@pytest.mark.parametrize("filtered_type", ["lower", "capitalize", "upper"])
@pytest.mark.parametrize("filtered_value", ["true", "false"])
@pytest.mark.parametrize(
    "field",
    [pytest.param(field, id=field.name) for field in SYSTEM_PROFILE if field.type == "bool"],
)
def test_filter_tags_by_system_profile_boolean_fields(
    setup_hosts_for_filtering,
    filter_tags,
    host_inventory: ApplicationHostInventory,
    field: Field,
    filtered_type,
    filtered_value,
):
    """Test generic filtering of tags by boolean fields
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-tags-get-list, inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Generic filtering of tags by boolean fields
    """
    hosts = setup_hosts_for_filtering(field)
    correct_host = 0 if filtered_value == "true" else 1
    expected_tags = hosts[correct_host].tags
    not_expected_tags = host_tags(hosts[:correct_host] + hosts[correct_host + 1 :])
    filtered_value = getattr(filtered_value, filtered_type)()

    def _test_filter(comparator: str | None = None):
        response = filter_tags(field.name, filtered_value, comparator)
        assert response.count >= len(expected_tags)
        assert_tags_found(expected_tags, response.results)
        assert_tags_not_found(not_expected_tags, response.results)

    _test_filter()
    _test_filter("eq")

    # Combination on 'eq' filtering uses OR logic
    logger.info("Filtering by multiple filters combined")
    filter = [f"[{field.name}][]=true", f"[{field.name}][]=false"]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    expected_tags = host_tags(hosts[:2])
    not_expected_tags = host_tags(hosts[2:])
    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "field",
    [pytest.param(field, id=field.name) for field in SYSTEM_PROFILE if field.type == "date-time"],
)
def test_filter_tags_by_system_profile_datetime_fields_range_operations(
    setup_hosts_for_filtering,
    filter_tags,
    host_inventory: ApplicationHostInventory,
    field: Field,
):
    """Test range operations generic filtering of tags by date-time fields
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-tags-get-list, inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Range operations generic filtering of tags by date-time fields
    """
    hosts = setup_hosts_for_filtering(field)
    value = quote(hosts[1].system_profile[field.name])
    lower_value = quote(hosts[0].system_profile[field.name])
    higher_value = quote(hosts[2].system_profile[field.name])

    def _check_response(
        response: ActiveTags, expected_tags: list[TagDict], not_expected_tags: list[TagDict]
    ):
        assert response.count >= len(expected_tags)
        assert_tags_found(expected_tags, response.results)
        assert_tags_not_found(not_expected_tags, response.results)

    def _test_filter(
        comparator: str, expected_tags: list[TagDict], not_expected_tags: list[TagDict]
    ):
        response = filter_tags(field.name, value, comparator)
        _check_response(response, expected_tags, not_expected_tags)

    _test_filter("gt", hosts[2].tags, host_tags(hosts[:2] + hosts[3:]))
    _test_filter("gte", host_tags(hosts[1:3]), host_tags(hosts[:1] + hosts[3:]))
    _test_filter("lt", hosts[0].tags, host_tags(hosts[1:]))
    _test_filter("lte", host_tags(hosts[:2]), host_tags(hosts[2:]))

    # Combination on range filtering uses AND logic
    filter = [f"[{field.name}][gt][]={lower_value}", f"[{field.name}][lt][]={higher_value}"]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    _check_response(response, hosts[1].tags, host_tags(hosts[:1] + hosts[2:]))


@pytest.mark.ephemeral
def test_filter_tags_by_system_profile_multiple_types(host_inventory: ApplicationHostInventory):
    """Test generic filtering of tags by fields of various types at the same time
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-tags-get-list, inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Generic filtering of tags by fields of various types at the same time
    """
    hosts_data = [host_inventory.datagen.create_host_data_with_tags()]
    cpus = get_sp_field_by_name("number_of_cpus")
    assert cpus.min is not None and cpus.max is not None
    hosts_data[0]["system_profile"]["owner_id"] = generate_uuid()
    hosts_data[0]["system_profile"]["number_of_cpus"] = randint(cpus.min, cpus.max)
    hosts_data[0]["system_profile"]["is_marketplace"] = True
    for _ in range(3):
        host_data = host_inventory.datagen.create_host_data_with_tags()
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
    not_matching_tags = flatten(host.tags for host in hosts[1:])

    filter = [
        f"[owner_id][]={hosts[0].system_profile['owner_id']}",
        f"[number_of_cpus]={hosts[0].system_profile['number_of_cpus']}",
        f"[is_marketplace][]={hosts[0].system_profile['is_marketplace']}",
    ]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    assert response.count == 2
    assert_tags_found(hosts[0].tags, response.results)
    assert_tags_not_found(not_matching_tags, response.results)


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
            id="$random_str",
        ),
    ],
)
@pytest.mark.usefixtures("prepare_hosts_for_incorrect_filter_comparator")
def test_filter_tags_by_system_profile_fields_incorrect_comparator(
    filter_tags, field: Field, comparator
):
    """Test generic filtering of hosts with incorrect comparators
    https://issues.redhat.com/browse/RHCLOUD-13901

    metadata:
      requirements: inv-tags-get-list, inv-hosts-get-by-sp-scalar-fields, inv-api-validation
      assignee: fstavela
      importance: medium
      title: Generic filtering of hosts with incorrect comparators
    """
    value = "True" if field.type == "bool" else "123"

    with raises_apierror(400) as err:
        filter_tags(field.name, value, comparator)

    assert err.value.body is not None
    assert "invalid operation" in err.value.body.lower()


@pytest.mark.ephemeral
def test_filter_tags_by_system_profile_object_nil(
    setup_hosts_for_ansible_filtering,
    host_inventory: ApplicationHostInventory,
):
    """
    Test filtering hosts by object fields by nil/not_nil

    Jira: https://issues.redhat.com/browse/ESSNTL-2362

    metadata:
      requirements: inv-tags-get-list, inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Filtering hosts by object fields by nil/not_nil
    """
    hosts = setup_hosts_for_ansible_filtering
    not_nil_tags = flatten(host.tags for host in hosts[:-1])

    filter = ["[ansible]=nil"]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    assert response.count >= len(hosts[-1].tags)
    assert_tags_found(hosts[-1].tags, response.results)
    assert_tags_not_found(not_nil_tags, response.results)

    filter = ["[ansible]=not_nil"]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    assert response.count >= len(not_nil_tags)
    assert_tags_found(not_nil_tags, response.results)
    assert_tags_not_found(hosts[-1].tags, response.results)


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
def test_filter_tags_by_system_profile_bootc_status(
    setup_hosts_for_bootc_status_filtering,
    host_inventory: ApplicationHostInventory,
    params,
    expected_hosts,
):
    """
    https://issues.redhat.com/browse/RHINENG-8987

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-system_profile-bootc_status
      assignee: fstavela
      importance: high
      title: Inventory: filter tags by bootc_status
    """
    hosts = setup_hosts_for_bootc_status_filtering
    expected_tags = flatten(hosts[i].tags for i in expected_hosts)
    not_expected_tags = flatten(
        hosts[i].tags for i in range(len(hosts)) if i not in expected_hosts
    )

    filter = [f"[bootc_status]{param}" for param in params]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


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
def test_filter_tags_by_system_profile_bootc_status_host_type(
    setup_hosts_for_bootc_status_filtering,
    host_inventory: ApplicationHostInventory,
    params,
    expected_hosts,
):
    """
    https://issues.redhat.com/browse/RHINENG-8987

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-system_profile-bootc_status,
                    inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Inventory: filter tags by bootc_status & host_type
    """
    hosts = setup_hosts_for_bootc_status_filtering
    expected_tags = flatten(hosts[i].tags for i in expected_hosts)
    not_expected_tags = flatten(
        hosts[i].tags for i in range(len(hosts)) if i not in expected_hosts
    )

    filter = [f"{param}" for param in params]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


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
        (["[name][neq]=Centos Linux"], [0, 1, 2]),
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
def test_filter_tags_by_system_profile_operating_system(
    setup_hosts_for_operating_system_filtering: tuple[list[HostOut], list[list[StructuredTag]]],
    host_inventory: ApplicationHostInventory,
    params: list[str],
    expected_hosts: list[int],
    case_insensitive: bool,
):
    """
    https://issues.redhat.com/browse/RHINENG-10785

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-sp-operating_system,
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
    response = host_inventory.apis.tags.get_tags_response(filter=filter, per_page=100)
    log_response_tags_indices(tags, response)

    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


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
def test_filter_tags_by_system_profile_os_rhc(
    setup_hosts_for_os_rhc_filtering: list[HostWrapper],
    host_inventory: ApplicationHostInventory,
    params: list[str],
    expected_hosts: list[int],
):
    """
    https://issues.redhat.com/browse/RHINENG-9784

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-sp-operating_system,
                    inv-hosts-get-by-sp-scalar-fields
      assignee: fstavela
      importance: high
      title: Inventory: filter tags by operating_system & rhc_client_id
    """
    hosts = setup_hosts_for_os_rhc_filtering
    expected_tags = flatten(hosts[i].tags for i in expected_hosts)
    not_expected_tags = flatten(
        hosts[i].tags for i in range(len(hosts)) if i not in expected_hosts
    )

    filter = [f"{param}" for param in params]
    response = host_inventory.apis.tags.get_tags_response(filter=filter)
    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


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
    setup_hosts_for_os_display_name_filtering: tuple[list[HostOut], list[list[StructuredTag]]],
    host_inventory: ApplicationHostInventory,
    params: list[str],
    expected_hosts: list[int],
):
    """
    https://issues.redhat.com/browse/RHINENG-10785

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-sp-operating_system,
                    inv-hosts-filter-by-display_name
      assignee: fstavela
      importance: high
      title: Inventory: filter tags by operating_system & display_name
    """
    _, tags = setup_hosts_for_os_display_name_filtering
    expected_tags = flatten(tags[i] for i in expected_hosts)
    not_expected_tags = flatten(tags[i] for i in range(len(tags)) if i not in expected_hosts)

    filter = [f"{param}" for param in params]
    response = host_inventory.apis.tags.get_tags_response(
        filter=filter, display_name=f"{FILTER_OS_DISPLAY_NAME}-1"
    )
    log_response_tags_indices(tags, response)

    assert response.count >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)
    assert_tags_not_found(not_expected_tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "param",
    [
        "[Cent][version][lt][]=7.10",
        "[Linux][version][gte][]=7.5",
        "[][version][eq][]=7",
    ],
)
def test_filter_tags_with_invalid_system_profile_operating_system(
    host_inventory: ApplicationHostInventory,
    param: str,
):
    """
    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-sp-operating_system,
      assignee: msager
      importance: medium
      negative: true
      title: Inventory: attempt to filter tags using an invalid operating_system
    """
    filter = [f"[operating_system]{param}"]

    with raises_apierror(
        400,
        match_message="operating_system filter only supports these OS names: ['RHEL', 'CentOS', 'CentOS Linux'].",  # noqa
    ):
        host_inventory.apis.tags.get_tags(filter=filter, per_page=100)
