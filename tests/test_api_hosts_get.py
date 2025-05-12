import random
from datetime import timedelta
from itertools import chain
from unittest.mock import patch

import pytest

from lib.host_repository import find_hosts_by_staleness
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import LEGACY_HOST_URL
from tests.helpers.api_utils import api_base_pagination_test
from tests.helpers.api_utils import api_pagination_invalid_parameters_test
from tests.helpers.api_utils import api_pagination_test
from tests.helpers.api_utils import api_query_test
from tests.helpers.api_utils import assert_error_response
from tests.helpers.api_utils import assert_host_lists_equal
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_expected_host_list
from tests.helpers.api_utils import build_fields_query_parameters
from tests.helpers.api_utils import build_host_exists_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_order_query_parameters
from tests.helpers.api_utils import build_system_profile_sap_sids_url
from tests.helpers.api_utils import build_system_profile_sap_system_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import quote
from tests.helpers.api_utils import quote_everything
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now


def test_query_single_non_existent_host(api_get, subtests):
    url = build_hosts_url(host_list_or_id=generate_uuid())
    api_query_test(api_get, subtests, url, [])


def test_query_invalid_host_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    bad_id_list = ["notauuid", "1234blahblahinvalid"]
    only_bad_id = bad_id_list.copy()

    # Can’t have empty string as an only ID, that results in 404 Not Found.
    more_bad_id_list = bad_id_list + [""]
    valid_id = created_hosts[0].id
    with_bad_id = [f"{valid_id},{bad_id}" for bad_id in more_bad_id_list]

    for host_id_list in chain(only_bad_id, with_bad_id):
        with subtests.test(host_id_list=host_id_list):
            url = build_hosts_url(host_list_or_id=host_id_list)
            response_status, _ = api_get(url)
            assert response_status == 400


def test_query_host_id_with_incorrect_formats(api_get, subtests):
    host_id = "6a2f41a3-c54c-fce8-32d2-0324e1c32e22"

    bad_host_ids = (f" {host_id}", f"{{{host_id}", f"{host_id}-")

    for bad_host_id in bad_host_ids:
        with subtests.test():
            url = build_hosts_url(host_list_or_id=bad_host_id)
            response_status, _ = api_get(url)
            assert response_status == 400


def test_query_invalid_paging_parameters(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(host_list_or_id=created_hosts)

    api_pagination_invalid_parameters_test(api_get, subtests, url)


def test_query_with_invalid_insights_id(api_get):
    url = build_hosts_url(query="?insights_id=notauuid")
    response_status, _ = api_get(url)

    assert response_status == 400


def test_get_host_with_invalid_tag_no_key(api_get):
    """
    Attempt to find host with an incomplete tag (no key).
    Expects 400 response.
    """
    url = build_hosts_url(query="?tags=namespace/=Value")
    response_status, _ = api_get(url)

    assert response_status == 400


def test_get_host_with_slash_in_key_name(api_get):
    """
    Attempt to find host with a "/" in the key.
    Expects 200 response.
    """
    url = build_hosts_url(query="?tags=namespace/key/key_value=Value")
    response_status, _ = api_get(url)

    assert response_status == 200


def test_get_host_with_slash_in_key_name_empty_namespace(api_get):
    """
    Attempt to find host with a "/" in the key with an empty namespace.
    Expects 200 response.
    """
    url = build_hosts_url(query="?tags=/key/key_value=Value")
    response_status, _ = api_get(url)

    assert response_status == 200


@pytest.mark.parametrize(
    "tag_query,part_name",
    (
        (f"{'a' * 256}/key=val", "namespace"),
        (f"namespace/{'a' * 256}=val", "key"),
        (f"namespace/key={'a' * 256}", "value"),
    ),
)
def test_get_host_tag_part_too_long(tag_query, part_name, api_get):
    """
    send a request to find hosts with a string tag where the length
    of the namespace excedes the 255 character limit
    """

    url = build_hosts_url(query=f"?tags={tag_query}")
    _, response_data = api_get(url)

    assert_error_response(
        response_data, expected_status=400, expected_detail=f"{part_name} is longer than 255 characters"
    )


def test_invalid_order_by(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    for url in urls:
        with subtests.test(url=url):
            order_query_parameters = build_order_query_parameters(order_by="fqdn", order_how="ASC")
            response_status, _ = api_get(url, query_parameters=order_query_parameters)
            assert response_status == 400


def test_invalid_order_how(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    for url in urls:
        with subtests.test(url=url):
            order_query_parameters = build_order_query_parameters(order_by="display_name", order_how="asc")
            response_status, _ = api_get(url, query_parameters=order_query_parameters)
            assert response_status == 400


def test_only_order_how(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    for url in urls:
        with subtests.test(url=url):
            order_query_parameters = build_order_query_parameters(order_by=None, order_how="ASC")
            response_status, _ = api_get(url, query_parameters=order_query_parameters)
            assert response_status == 400


@pytest.mark.parametrize("feature_flag", (True, False))
def test_invalid_fields(mq_create_three_specific_hosts, api_get, subtests, feature_flag):
    with patch("api.host_query_db.get_flag_value", return_value=feature_flag):
        created_hosts = mq_create_three_specific_hosts

        urls = (
            HOST_URL,
            build_hosts_url(host_list_or_id=created_hosts),
            build_system_profile_url(host_list_or_id=created_hosts),
        )
        for url in urls:
            with subtests.test(url=url):
                fields_query_parameters = build_fields_query_parameters(fields="i_love_ketchup")
                response_status, _ = api_get(url, query_parameters=fields_query_parameters)
                assert response_status == 400


@pytest.mark.parametrize(
    "value",
    ("insights", "cloud-connector", "puptoo", "rhsm-conduit", "yupana", "puptoo&registered_with=yupana"),
)
def test_get_hosts_registered_with(api_get, value):
    url = build_hosts_url(query=f"?registered_with={value}")
    response_status, _ = api_get(url)

    assert response_status == 200


def test_query_variables_registered_with_using_unknown_reporter(api_get):
    MSG = "'unknown' is not one of ["
    url = build_hosts_url(query="?registered_with=unknown")

    response_status, response_data = api_get(url)

    assert response_status == 400
    assert MSG in str(response_data)


@pytest.mark.usefixtures("enable_rbac")
def test_get_hosts_with_RBAC_allowed(subtests, mocker, db_create_host, api_get):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_hosts_url(host_list_or_id=host.id)
            response_status, _ = api_get(url)

            assert_response_status(response_status, 200)


@pytest.mark.usefixtures("enable_rbac")
def test_get_hosts_with_RBAC_denied(subtests, mocker, db_create_host, api_get):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    find_hosts_by_staleness_mock = mocker.patch(
        "lib.host_repository.find_hosts_by_staleness", wraps=find_hosts_by_staleness
    )

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_hosts_url(host_list_or_id=host.id)
            response_status, _ = api_get(url)

            assert_response_status(response_status, 403)

            find_hosts_by_staleness_mock.assert_not_called()


@pytest.mark.usefixtures("enable_rbac")
def test_get_hosts_with_RBAC_bypassed_as_system(db_create_host, api_get):
    host = db_create_host(SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": generate_uuid()}})

    url = build_hosts_url(host_list_or_id=host.id)
    response_status, _ = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


def test_get_hosts_sap_system_bad_parameter_values(api_get):
    implicit_url = build_hosts_url(query="?filter[system_profile][sap_system]=Garfield")
    eq_url = build_hosts_url(query="?filter[system_profile][sap_system][eq]=Garfield")

    implicit_response_status, _ = api_get(implicit_url)
    eq_response_status, _ = api_get(eq_url)

    assert_response_status(implicit_response_status, 400)
    assert_response_status(eq_response_status, 400)


@pytest.mark.parametrize(
    "query_params",
    (
        "?filter[foo]=bar&filter[foo]=baz&filter[foo]=asdf",
        "?filter[system_profile][number_of_cpus]=1&filter[system_profile][number_of_cpus]=2",
        "?asdf[foo]=bar&asdf[foo]=baz",
    ),
)
def test_get_hosts_invalid_deep_object_params(query_params, api_get):
    invalid_url = build_hosts_url(query=query_params)

    response_code, _ = api_get(invalid_url)
    assert_response_status(response_code, 400)


def test_validate_sp_sparse_fields_invalid_requests(api_get, subtests):
    for query in (
        "?fields[system_profile]=os_kernel_version&order_how=ASC",
        "?fields[system_profile]=os_kernel_version&order_by=modified",
        "?fields[system_profile]=os_kernel_version&order_how=display_name&order_by=NOO",
        # Bypass until https://github.com/spec-first/connexion/issues/1920 is resolved,
        # or until we make a workaround and re-enable strict_validation.
        # "?fields[foo]=bar",
    ):
        with subtests.test(query=query):
            host_one_id, host_two_id = generate_uuid(), generate_uuid()
            hosts = [minimal_host(id=host_one_id), minimal_host(id=host_two_id)]

            response_status, _ = api_get(build_system_profile_url(hosts, query=query))
            assert response_status == 400


# This test verifies that the [contains] operation is denied for a non-array string field such as cpu_model
def test_get_hosts_contains_invalid_on_string_not_array(api_get, subtests):
    url_builders = (
        build_hosts_url,
        build_system_profile_sap_sids_url,
        build_tags_url,
        build_system_profile_sap_system_url,
    )
    query = "?filter[system_profile][cpu_model][contains]=Intel(R) I7(R) CPU I7-10900k 0 @ 4.90GHz"
    for url_builder in url_builders:
        with subtests.test(url_builder=url_builder, query=query):
            response_status, _ = api_get(url_builder(query=query))
            assert response_status == 400


@pytest.mark.parametrize(
    "host_url",
    (HOST_URL, LEGACY_HOST_URL),
)
def test_query_all(mq_create_three_specific_hosts, api_get, subtests, host_url):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list(created_hosts)

    response_status, response_data = api_get(host_url)
    api_base_pagination_test(api_get, subtests, host_url, expected_total=len(expected_host_list))

    assert response_status == 200
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_display_name(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[0]])
    url = build_hosts_url(query=f"?display_name={created_hosts[0].display_name.upper()}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_fqdn_two_results(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[0], created_hosts[1]])

    url = build_hosts_url(query=f"?fqdn={created_hosts[0].fqdn.upper()}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_fqdn_one_result(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[2]])
    url = build_hosts_url(query=f"?fqdn={created_hosts[2].fqdn}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_non_existent_fqdn(api_get):
    url = build_hosts_url(query="?fqdn=NONEXISTENT.com")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0


@pytest.mark.parametrize(
    "query",
    (
        (f"fqdn={generate_uuid()}&display_name={generate_uuid()}"),
        (f"fqdn={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"fqdn={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"hostname_or_id={generate_uuid()}&insights_id={generate_uuid()}"),
    ),
)
def test_query_by_conflitcting_ids(api_get, query):
    # Not allowed to query on more than one of these fields at once
    url = build_hosts_url(query=f"?{query}")
    response_status, _ = api_get(url)

    assert response_status == 400


def test_query_using_display_name_substring(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list(created_hosts)
    host_name_substr = created_hosts[0].display_name[:4]
    url = build_hosts_url(query=f"?display_name={host_name_substr}")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=len(created_hosts))

    assert response_status == 200
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_display_name_as_hostname(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[0].display_name}")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=2)

    assert response_status == 200
    assert len(response_data["results"]) == 2


def test_query_using_fqdn_as_hostname(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[2].display_name}")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=1)

    assert response_status == 200
    assert len(response_data["results"]) == 1


def test_query_using_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[0].id}")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=1)

    assert response_status == 200
    assert len(response_data["results"]) == 1


def test_query_using_non_existent_hostname(api_get, subtests):
    url = build_hosts_url(query="?hostname_or_id=NotGonnaFindMe")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=0)

    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_query_using_non_existent_id(api_get, subtests):
    url = build_hosts_url(query=f"?hostname_or_id={generate_uuid()}")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=0)

    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_query_using_insights_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?insights_id={created_hosts[0].insights_id.upper()}")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=1)

    assert response_status == 200
    assert len(response_data["results"]) == 1


def test_query_using_subscription_manager_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?subscription_manager_id={created_hosts[0].subscription_manager_id}")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=1)

    assert response_status == 200
    assert len(response_data["results"]) == 1


def test_get_host_by_tag(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=SPECIAL/tag=ToFind")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_multiple_hosts_by_tag(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0], created_hosts[1]]
    url = build_hosts_url(query="?tags=NS1/key1=val1&order_by=updated&order_how=ASC")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_by_multiple_tags(db_create_host, api_get, subtests):
    """
    Get only the host with all three tags on it, and not the other hosts,
    which both have some (but not all) of the tags we query for.
    """
    tags_data_list = [
        {"tags": {"ns1": {"key1": ["val1"]}}},
        {"tags": {"ns1": {"key1": ["val1"], "key2": ["val2"]}}},
        {"tags": {"ns1": {"key1": ["val1"], "key3": ["val3"]}}},
        {"tags": {"ns1": {"key3": ["val3"], "key4": ["val4"]}}},
    ]

    host_ids = [str(db_create_host(extra_data=tags_data).id) for tags_data in tags_data_list]
    url = build_hosts_url(query="?tags=ns1/key1=val1&tags=ns1/key2=val2")

    api_pagination_test(api_get, subtests, url, expected_total=3)
    _, response_data = api_get(url)

    for result in response_data["results"]:
        assert result["id"] in host_ids[:3]


def test_get_host_by_subset_of_tags(mq_create_three_specific_hosts, api_get, subtests):
    """
    Get a host using a subset of its tags
    """
    created_host_ids = [str(host.id) for host in mq_create_three_specific_hosts]
    url = build_hosts_url(query="?tags=NS1/key1=val1&tags=NS3/key3=val3")

    api_pagination_test(api_get, subtests, url, expected_total=len(created_host_ids))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(created_host_ids) == len(response_data["results"])

    for result in response_data["results"]:
        assert result["id"] in created_host_ids


def test_get_no_host_with_different_tags_same_namespace(api_get):
    """
    Don’t get a host with two tags in the same namespace, from which only one match. This is a
    regression test.
    """
    url = build_hosts_url(query="?tags=NS4/key1=val2&tags=NS1/key8=val1")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_get_host_with_tag_no_value_at_all(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with no stored value
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=no/key")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_with_tag_no_value_in_query(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with a stored value by a value-less query
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=NS1/key2")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_with_tag_no_namespace(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with no namespace.
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[2]]
    url = build_hosts_url(query="?tags=key4=val4")

    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])
    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_with_tag_only_key(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with no namespace.
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[2]]
    url = build_hosts_url(query="?tags=key5")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_by_display_name_and_tag(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to get only the host with the specified key and
    the specified display name
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=NS1/key1=val1&display_name=host1")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_by_display_name_and_tag_backwards(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to get only the host with the specified key and
    the specified display name, but the parameters are backwards
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?display_name=host1&tags=NS1/key1=val1")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


@pytest.mark.parametrize("tag_query", (";?:@&+$/-_.!~*'()'=#", " \t\n\r\f\v/ \t\n\r\f\v= \t\n\r\f\v"))
def test_get_host_with_unescaped_special_characters(tag_query, mq_create_or_update_host, api_get):
    tags = [
        {"namespace": ";?:@&+$", "key": "-_.!~*'()'", "value": "#"},
        {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]

    host = minimal_host(tags=tags)
    created_host = mq_create_or_update_host(host)
    url = build_hosts_url(query=f"?tags={quote(tag_query)}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"]
    assert response_data["results"][0]["id"] == created_host.id


@pytest.mark.parametrize(
    "namespace,key,value", ((";,/?:@&=+$", "-_.!~*'()", "#"), (" \t\n\r\f\v", " \t\n\r\f\v", " \t\n\r\f\v"))
)
def test_get_host_with_escaped_special_characters(namespace, key, value, mq_create_or_update_host, api_get):
    tags = [
        {"namespace": ";,/?:@&=+$", "key": "-_.!~*'()", "value": "#"},
        {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]

    host = minimal_host(tags=tags)
    created_host = mq_create_or_update_host(host)
    tags_query = quote(f"{quote_everything(namespace)}/{quote_everything(key)}={quote_everything(value)}")
    url = build_hosts_url(query=f"?tags={tags_query}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"]
    assert response_data["results"][0]["id"] == created_host.id


@pytest.mark.parametrize("num_groups", (1, 3, 5))
def test_query_using_group_name(db_create_group_with_hosts, api_get, num_groups):
    hosts_per_group = 3
    for i in range(num_groups):
        db_create_group_with_hosts(f"existing_group_{i}", hosts_per_group)

    # Some other group that we don't want to see in the response
    db_create_group_with_hosts("some_other_group", 5)

    group_name_params = "&".join([f"group_name=EXISTING_GROUP_{i}" for i in range(num_groups)])
    url = build_hosts_url(query=f"?{group_name_params}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == num_groups * hosts_per_group
    for result in response_data["results"]:
        assert "existing_group_" in result["groups"][0]["name"]
        assert result["groups"][0]["ungrouped"] is False


def test_query_ungrouped_hosts(db_create_group_with_hosts, mq_create_three_specific_hosts, api_get):
    # Create 3 hosts that are not in a group
    ungrouped_hosts = mq_create_three_specific_hosts

    # Also create 5 hosts that are in a group
    db_create_group_with_hosts("group_with_hosts", 5)
    url = build_hosts_url(query="?group_name=")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert_host_lists_equal(build_expected_host_list(ungrouped_hosts), response_data["results"])


@pytest.mark.parametrize("ungrouped", (True, False))
def test_query_hosts_with_group_data_kessel(ungrouped, db_create_group_with_hosts, api_get):
    # Create a host in the "ungrouped" group
    ungrouped_group_id = db_create_group_with_hosts("test_group", 1, ungrouped).id
    url = build_hosts_url(query="?group_name=test_group")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert (group_result := response_data["results"][0]["groups"][0])["name"] == "test_group"
    assert group_result["id"] == str(ungrouped_group_id)
    assert group_result["ungrouped"] is ungrouped


def test_query_hosts_filter_updated_start_end(mq_create_or_update_host, api_get):
    host_list = [mq_create_or_update_host(minimal_host(insights_id=generate_uuid())) for _ in range(3)]

    url = build_hosts_url(query=f"?updated_start={host_list[0].updated.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200

    # This query should return all 3 hosts
    assert len(response_data["results"]) == 3

    url = build_hosts_url(query=f"?updated_end={host_list[0].updated.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200

    # This query should return only the first host
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["insights_id"] == host_list[0].insights_id

    url = build_hosts_url(
        query=(
            f"?updated_start={host_list[0].updated.replace('+00:00', 'Z')}"
            f"&updated_end={host_list[1].updated.replace('+00:00', 'Z')}"
        )
    )
    response_status, response_data = api_get(url)
    assert response_status == 200
    # This query should return 2 hosts
    assert len(response_data["results"]) == 2

    url = build_hosts_url(query=f"?updated_start={host_list[2].updated.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200
    # This query should return only the last host
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["insights_id"] == host_list[2].insights_id

    url = build_hosts_url(query=f"?updated_end={host_list[2].updated.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200
    # This query should return all 3 hosts
    assert len(response_data["results"]) == 3


@pytest.mark.parametrize("order_how", ("ASC", "DESC"))
def test_get_hosts_order_by_group_name(db_create_group_with_hosts, db_create_multiple_hosts, api_get, order_how):
    hosts_per_group = 3
    num_ungrouped_hosts = 5
    names = ["ABC Group", "BCD Group", "CDE Group", "DEF Group"]

    # Shuffle the list so the groups aren't created in alphabetical order
    # Just to make sure it's actually ordering by name and not date
    shuffled_group_names = names.copy()
    random.shuffle(shuffled_group_names)
    [db_create_group_with_hosts(group_name, hosts_per_group) for group_name in shuffled_group_names]

    # Create some ungrouped hosts
    db_create_multiple_hosts(how_many=num_ungrouped_hosts)

    url = build_hosts_url(query=f"?order_by=group_name&order_how={order_how}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(names) * hosts_per_group + num_ungrouped_hosts == len(response_data["results"])

    if order_how == "DESC":
        # If DESC, reverse the expected order of group names
        names.reverse()
        ungrouped_buffer = 0
    else:
        # If ASC, set a buffer for the ungrouped hosts (which should show first)
        ungrouped_buffer = num_ungrouped_hosts

    for group_index in range(len(names)):
        # Ungrouped hosts should show at the top for order_how=ASC
        for host_index in range(ungrouped_buffer, ungrouped_buffer + hosts_per_group):
            assert (
                response_data["results"][group_index * hosts_per_group + host_index]["groups"][0]["name"]
                == names[group_index]
            )


@pytest.mark.usefixtures("enable_rbac")
@pytest.mark.parametrize("order_how", ("ASC", "DESC"))
def test_get_hosts_order_by_group_name_post_kessel(mocker, db_create_group_with_hosts, api_get, order_how):
    hosts_per_group = 3
    num_ungrouped_hosts = 5
    names = ["ABC Group", "BCD Group", "CDE Group", "DEF Group"]
    num_grouped_hosts = hosts_per_group * len(names)

    # Shuffle the list so the groups aren't created in alphabetical order
    # Just to make sure it's actually ordering by name and not date
    shuffled_group_names = names.copy()
    random.shuffle(shuffled_group_names)
    [db_create_group_with_hosts(group_name, hosts_per_group) for group_name in shuffled_group_names]

    mocker.patch("api.host_query_db.get_flag_value", return_value=True)

    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-hosts-read-resource-defs-template.json"
    )
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Create some ungrouped hosts
    db_create_group_with_hosts("ungrouped", num_ungrouped_hosts, True)

    url = build_hosts_url(query=f"?order_by=group_name&order_how={order_how}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert num_grouped_hosts + num_ungrouped_hosts == len(response_data["results"])

    if order_how == "DESC":
        num_grouped_hosts = hosts_per_group * len(names)
        for group_index in range(num_grouped_hosts, num_grouped_hosts + num_ungrouped_hosts):
            assert response_data["results"][group_index]["groups"][0]["name"] == "ungrouped"
    else:
        # Ungrouped hosts whould be at the top of the list
        for group_index in range(0, num_ungrouped_hosts):
            assert response_data["results"][group_index]["groups"][0]["name"] == "ungrouped"


@pytest.mark.parametrize("order_how", ("ASC", "DESC"))
def test_get_hosts_order_by_last_check_in(mocker, db_create_host, api_get, order_how):
    host0 = str(db_create_host().id)
    host1 = str(db_create_host().id)

    with (
        mocker.patch("app.serialization.get_flag_value", return_value=True),
        mocker.patch("api.host_query_db.get_flag_value", return_value=True),
    ):
        url = build_hosts_url(query=f"?order_by=last_check_in&order_how={order_how}")

        response_status, response_data = api_get(url)

        assert response_status == 200
        assert len(response_data["results"]) == 2
        hosts = response_data["results"]
        if order_how == "DESC":
            assert host1 == hosts[0]["id"]
            assert host0 == hosts[1]["id"]
        else:
            assert host0 == hosts[0]["id"]
            assert host1 == hosts[1]["id"]


@pytest.mark.parametrize("order_how", ("", "ASC", "DESC"))
def test_get_hosts_order_by_operating_system(mq_create_or_update_host, api_get, order_how):
    # Create some operating systems in ASC sort order
    ordered_operating_system_data = [
        {"name": "CentOS", "major": 4, "minor": 0},
        {"name": "CentOS", "major": 4, "minor": 1},
        {"name": "CentOS", "major": 5, "minor": 0},
        {"name": "CentOS", "major": 5, "minor": 1},
        {"name": "RHEL", "major": 3, "minor": 0},
        {"name": "RHEL", "major": 3, "minor": 11},
        {"name": "RHEL", "major": 8, "minor": 0},
        {"name": "RHEL", "major": 8, "minor": 1},
    ]
    ordered_insights_ids = [generate_uuid() for _ in range(len(ordered_operating_system_data))]

    # Create an association between the insights IDs
    ordered_host_data = dict(zip(ordered_insights_ids, ordered_operating_system_data))

    # Create a shuffled list of insights_ids so we can create the hosts in a random order
    shuffled_insights_ids = ordered_insights_ids.copy()
    random.shuffle(shuffled_insights_ids)

    # Create hosts for the above host data (in shuffled order)
    created_hosts = [
        mq_create_or_update_host(
            minimal_host(insights_id=insights_id, system_profile={"operating_system": ordered_host_data[insights_id]})
        )
        for insights_id in shuffled_insights_ids
    ]
    # Create host without operating system
    minimal_host(insights_id=generate_uuid(), system_profile={})

    query = "?order_by=operating_system"
    if order_how:
        query += f"&order_how={order_how}"

    url = build_hosts_url(query=query)

    # Validate the basics, i.e. response code and results size
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(created_hosts) == len(response_data["results"])

    # If descending order is requested, reverse the expected order of hosts
    if order_how != "ASC":
        ordered_insights_ids.reverse()

    for index in range(len(ordered_insights_ids)):
        assert ordered_insights_ids[index] == response_data["results"][index]["insights_id"]


@pytest.mark.parametrize("num_hosts_to_query", (1, 2, 3))
def test_query_using_id_list(mq_create_three_specific_hosts, api_get, subtests, num_hosts_to_query):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(host_list_or_id=[host.id for host in created_hosts[:num_hosts_to_query]])

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=num_hosts_to_query)

    assert response_status == 200
    assert len(response_data["results"]) == num_hosts_to_query


def test_query_using_id_list_nonexistent_host(api_get):
    response_status, response_data = api_get(build_hosts_url(generate_uuid()))

    assert response_status == 200
    assert len(response_data["results"]) == 0


@pytest.mark.parametrize("num_hosts_to_query", (1, 2, 3))
@pytest.mark.parametrize("sparse_request", (True, False))
def test_query_sp_by_id_list_sparse(db_create_multiple_hosts, api_get, num_hosts_to_query, sparse_request):
    sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "os_kernel_version": "4.18.2",
            "host_type": "edge",
            "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        }
    }
    created_hosts = db_create_multiple_hosts(how_many=3, extra_data=sp_data)
    created_hosts_ids = [str(host.id) for host in created_hosts]
    host_list_url = build_hosts_url(host_list_or_id=created_hosts[:num_hosts_to_query])
    url = f"{host_list_url}/system_profile"
    if sparse_request:
        url += "?fields[system_profile]=arch,os_kernel_version,installed_packages,host_type"

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == num_hosts_to_query
    for response_host in response_data["results"]:
        assert response_host["id"] in created_hosts_ids

        # "!=" works as an XOR
        assert sparse_request != ("owner_id" in response_host["system_profile"])
        for fact in ["arch", "os_kernel_version", "host_type"]:
            assert fact in response_host["system_profile"]


def test_query_all_sparse_fields(db_create_multiple_hosts, api_get):
    # Create hosts that have a system profile
    sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "os_kernel_version": "4.18.2",
            "host_type": "edge",
            "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        }
    }
    db_create_multiple_hosts(how_many=3, extra_data=sp_data)
    url = build_hosts_url(query="?fields[system_profile]=arch,host_type")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that the system_profile is not in the response by default
    for result in response_data["results"]:
        assert "system_profile" in result
        assert "arch" in result["system_profile"]
        assert "host_type" in result["system_profile"]
        assert "os_kernel_version" not in result["system_profile"]
        assert "owner_id" not in result["system_profile"]


def test_query_sys_profile_with_sql_characters(db_create_multiple_hosts, api_get):
    # Create hosts that have a system profile
    sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "os_kernel_version": "4.18.2",
            "host_type": "edge",
            "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        }
    }
    db_create_multiple_hosts(how_many=3, extra_data=sp_data)
    url = build_hosts_url(query="?filter[system_profile][bios_vendor]=%3E/%3AX%26x5wVZCj%25mC")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that the system_profile is not in the response by default
    for result in response_data["results"]:
        assert "system_profile" in result
        assert "arch" in result["system_profile"]
        assert "host_type" in result["system_profile"]
        assert "os_kernel_version" not in result["system_profile"]
        assert "owner_id" not in result["system_profile"]


def test_query_by_id_sparse_fields(db_create_multiple_hosts, api_get):
    # Create hosts that have a system profile
    sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "os_kernel_version": "4.18.2",
            "host_type": "edge",
            "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        }
    }
    created_hosts = db_create_multiple_hosts(how_many=3, extra_data=sp_data)
    url = build_hosts_url(
        host_list_or_id=created_hosts[0].id, query="?fields[system_profile]=os_kernel_version,owner_id"
    )

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that the system_profile is not in the response by default
    for result in response_data["results"]:
        assert "system_profile" in result
        assert "arch" not in result["system_profile"]
        assert "host_type" not in result["system_profile"]
        assert "os_kernel_version" in result["system_profile"]
        assert "owner_id" in result["system_profile"]


def test_query_by_id_culled_hosts(db_create_host, api_get):
    # Create a culled host
    with patch("app.models.datetime", **{"now.return_value": now() - timedelta(days=365)}):
        created_host_id = str(db_create_host().id)

    url = build_hosts_url(host_list_or_id=created_host_id)
    # The host should not be returned as it is in the "culled" state
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_query_by_registered_with(db_create_multiple_hosts, api_get, subtests):
    _now = now()
    registered_with_data = [
        {
            "puptoo": {
                "last_check_in": _now.isoformat(),
                "stale_timestamp": (_now + timedelta(days=7)).isoformat(),
                "check_in_succeeded": True,
            },
            "yupana": {
                "last_check_in": (_now - timedelta(days=3)).isoformat(),
                "stale_timestamp": (_now + timedelta(days=4)).isoformat(),
                "check_in_succeeded": True,
            },
        },
        {
            "puptoo": {
                "last_check_in": (_now - timedelta(days=1)).isoformat(),
                "stale_timestamp": (_now + timedelta(days=6)).isoformat(),
                "check_in_succeeded": True,
            },
            "satellite": {
                "last_check_in": (_now - timedelta(days=3)).isoformat(),
                "stale_timestamp": (_now + timedelta(days=4)).isoformat(),
                "check_in_succeeded": True,
            },
        },
        {
            "puptoo": {
                "last_check_in": (_now - timedelta(days=30)).isoformat(),
                "stale_timestamp": (_now - timedelta(days=23)).isoformat(),
                "check_in_succeeded": True,
            },
            "discovery": {
                "last_check_in": (_now - timedelta(days=3)).isoformat(),
                "stale_timestamp": (_now + timedelta(days=4)).isoformat(),
                "check_in_succeeded": True,
            },
        },
        {
            "rhsm-conduit": {
                "last_check_in": (_now - timedelta(days=1)).isoformat(),
                "stale_timestamp": (_now + timedelta(days=6)).isoformat(),
                "check_in_succeeded": True,
            },
        },
    ]
    insights_ids = [generate_uuid() for _ in range(len(registered_with_data))]

    # Create an association between the insights IDs
    registered_with_host_data = dict(zip(insights_ids, registered_with_data))

    # Create hosts for the above host data
    _ = [
        db_create_multiple_hosts(
            how_many=1,
            extra_data={
                "canonical_facts": {"insights_id": insights_id},
                "per_reporter_staleness": registered_with_host_data[insights_id],
            },
        )
        for insights_id in insights_ids
    ]

    expected_reporter_results_map = {
        "puptoo": 2,
        "yupana": 3,
        "!yupana": 1,
        "rhsm-conduit": 1,
        "rhsm-conduit&registered_with=yupana": 4,
    }
    for reporter, count in expected_reporter_results_map.items():
        with subtests.test():
            url = build_hosts_url(query=f"?registered_with={reporter}")
            # Validate the basics, i.e. response code and results size
            response_status, response_data = api_get(url)
            assert response_status == 200
            assert count == len(response_data["results"])


def test_query_by_staleness(db_create_multiple_hosts, api_get, subtests):
    expected_staleness_results_map = {
        "fresh": 3,
        "stale": 4,
        "stale_warning": 2,
    }
    staleness_timestamp_map = {
        "fresh": now(),
        "stale": now() - timedelta(days=3),
        "stale_warning": now() - timedelta(days=10),
    }
    staleness_to_host_ids_map = dict()

    # Create the hosts in each state
    for staleness, num_hosts in expected_staleness_results_map.items():
        # Patch the "now" function so the hosts are created in the desired state
        with patch("app.models.datetime", **{"now.return_value": staleness_timestamp_map[staleness]}):
            staleness_to_host_ids_map[staleness] = [str(h.id) for h in db_create_multiple_hosts(how_many=num_hosts)]

    for staleness, count in expected_staleness_results_map.items():
        with subtests.test():
            url = build_hosts_url(query=f"?staleness={staleness}")
            # Validate the basics, i.e. response code and results size
            response_status, response_data = api_get(url)
            assert response_status == 200
            assert count == len(response_data["results"])


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[arch]=x86_64",
        "[arch][eq]=x86_64",
        "[arch][neq]=ARM",
        "[insights_client_version]=3.0.1-2.el4_2",
        "[insights_client_version]=3.0.*",
        "[host_type]=edge",
        "[sap][sap_system]=true",
        "[sap][sap_system]=True",
        "[sap][sap_system]=TRUE",
        "[is_marketplace]=false",
        "[is_marketplace]=False",
        "[is_marketplace]=FALSE",
        "[arch]=x86_64&filter[system_profile][host_type]=edge",
        "[insights_client_version][]=3.0.*&filter[system_profile][insights_client_version][]=*el4_2",
        "[greenboot_status][is]=nil",
        "[host_type]=not_nil",
        "[greenboot_status][is][]=nil",
        "[host_type][]=not_nil",
        "[bootc_status][booted][image]=quay.io*",
        "[sap_sids][contains][]=ABC",
        "[sap_sids][contains][]=ABC&filter[system_profile][sap_sids][contains][]=DEF",
        "[sap_sids][contains]=ABC",
        "[sap_sids][]=ABC",
        "[sap][sids][contains][]=ABC&filter[system_profile][sap][sids][contains][]=DEF",
        "[sap][sids][contains][]=ABC",
        "[sap][sids][contains]=ABC",
        "[sap][sids][]=ABC",
        "[systemd][failed_services][contains][]=foo",
        "[system_memory_bytes][lte]=9000000000000000",
        "[system_memory_bytes][eq]=8292048963606259",
        "[number_of_cpus][is]=nil",
        "[number_of_cpus]=nil",
        "[bios_version]=2.0/3.5A",
        "[cpu_flags][]=nil",
        "[sap_sids][]=not_nil",
        "[sap][sids][]=not_nil",
    ),
)
def test_query_all_sp_filters_basic(db_create_host, api_get, sp_filter_param):
    # Create host with this system profile
    match_sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "insights_client_version": "3.0.1-2.el4_2",
            "host_type": "edge",
            "sap": {"sap_system": True, "sids": ["ABC", "DEF"]},
            "bootc_status": {"booted": {"image": "quay.io/centos-bootc/fedora-bootc-cloud:eln"}},
            "sap_sids": ["ABC", "DEF"],
            "is_marketplace": False,
            "systemd": {"failed_services": ["foo", "bar"]},
            "system_memory_bytes": 8292048963606259,
            "bios_version": "2.0/3.5A",
        }
    }
    match_host_id = str(db_create_host(extra_data=match_sp_data).id)

    # Create host with differing SP
    nomatch_sp_data = {
        "system_profile_facts": {
            "arch": "ARM",
            "cpu_flags": ["ex1", "ex2"],
            "insights_client_version": "1.2.3",
            "greenboot_status": "green",
            "sap": {"sap_system": False},
            "bootc_status": {"booted": {"image": "192.168.0.1:5000/foo/foo:latest"}},
            "is_marketplace": True,
            "number_of_cpus": 8,
            "bios_version": "2.0-3.5A",
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "query_filter_param,match_host_facts",
    (
        ("?display_name=1*m", [{"display_name": "HkqL12lmIW"}]),
        (
            "?hostname_or_id=1*m",
            [
                {"display_name": "HkqL12lmIW"},
                {"canonical_facts": {"fqdn": "HkqL1m2lIW"}},
            ],
        ),
    ),
)
def test_query_host_fuzzy_match(db_create_host, api_get, query_filter_param, match_host_facts):
    # Create host with matching data
    match_host_id_list = [str(db_create_host(extra_data=host_fact).id) for host_fact in match_host_facts]

    # Create host with differing SP
    nomatch_host_facts = [
        {"display_name": "masdf1"},
        {"canonical_facts": {"fqdn": "masdf1"}},
    ]
    nomatch_host_id_list = [str(db_create_host(extra_data=host_fact).id) for host_fact in nomatch_host_facts]

    url = build_hosts_url(query=query_filter_param)

    response_status, response_data = api_get(url)

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert response_status == 200
    assert len(response_ids) == len(match_host_facts)

    for response_id in response_ids:
        assert response_id in match_host_id_list
        assert response_id not in nomatch_host_id_list


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[system_memory_bytes][eq]=8292048963606259",
        "[system_memory_bytes][]=8292048963606259",
        "[system_memory_bytes]=8292048963606259",
        "[arch]=x86",  # EQ field, no wildcard
        "[host_type]=",  # Valid bc it's a string field, but no match
        "[host_type][eq]=",  # Same for this one
        "[sap][sids][contains][]=ABC&filter[system_profile][sap][sids][contains][]=GHI",
    ),
)
def test_query_all_sp_filters_not_found(db_create_host, api_get, sp_filter_param):
    # Create host with this system profile
    nomatch_sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "host_type": "edge",
            "sap_sids": ["ABC", "DEF"],
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=nomatch_sp_data)

    # This host has none of the fields, so it shouldn't be returned either
    nomatch_sp_data = {
        "system_profile_facts": {
            "bios_vendor": "ex1",
        }
    }
    db_create_host(extra_data=nomatch_sp_data)

    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, response_data = api_get(url)

    # Assert that the request succeeds but no hosts are returned
    assert response_status == 200
    assert len(response_data["results"]) == 0


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[RHEL][version]=8.11",
        "[RHEL][version][eq]=8.11",
        "[RHEL][version][eq][]=8.11",
        "[RHEL][version][eq][]=8.11&filter[system_profile][operating_system][RHEL][version][gt][]=8",
        "[RHEL][version][eq][]=8.11&filter[system_profile][operating_system][RHEL][version][eq][]=9.1",
        "[RHEL][version][gte]=8",
        "[RHEL][version][gte][]=8",
        "[RHEL][version][gt]=7",  # Minor version should be ignored
        "[RHEL][version][gt][]=7",
        "[RHEL][version][eq]=8",  # Minor version should be ignored
        "[RHEL][version][eq][]=8",
        "[RHEL][version]=8",  # Minor version should be ignored
        "[RHEL][version][gte]=8&filter[system_profile][operating_system][RHEL][version][lte]=8",
    ),
)
def test_query_all_sp_filters_operating_system(db_create_host, api_get, sp_filter_param):
    # Create host with this system profile
    match_sp_data = {
        "system_profile_facts": {
            "operating_system": {
                "name": "RHEL",
                "major": "8",
                "minor": "11",
            }
        }
    }
    match_host_id = str(db_create_host(extra_data=match_sp_data).id)

    # Create host with differing SP
    nomatch_sp_data = {
        "system_profile_facts": {
            "operating_system": {
                "name": "RHEL",
                "major": "7",
                "minor": "12",
            }
        }
    }
    nomatch_host_id_1 = str(db_create_host(extra_data=nomatch_sp_data).id)

    # Create host with differing SP
    nomatch_sp_data = {
        "system_profile_facts": {
            "operating_system": {
                "name": "RHEL",
                "major": "7",
                "minor": "5",
            }
        }
    }
    nomatch_host_id_2 = str(db_create_host(extra_data=nomatch_sp_data).id)

    # Create host with differing SP
    nomatch_sp_data = {
        "system_profile_facts": {
            "operating_system": {
                "name": "CentOS",
                "major": "7",
                "minor": "0",
            }
        }
    }
    nomatch_host_id_3 = str(db_create_host(extra_data=nomatch_sp_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][operating_system]{sp_filter_param}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id_1 not in response_ids
    assert nomatch_host_id_2 not in response_ids
    assert nomatch_host_id_3 not in response_ids


@pytest.mark.parametrize(
    "sp_filter_param,match",
    (
        ("[name][eq]=CentOS", True),
        ("[name][eq]=centos", True),
        ("[name][eq]=CENTOS", True),
        ("[name][eq]=centos&filter[system_profile][operating_system][RHEL][version][eq][]=8", True),
        ("[name][neq]=CENTOS", False),
        ("[name][neq]=CentOS", False),
    ),
)
def test_query_sp_filters_operating_system_name(db_create_host, api_get, sp_filter_param, match):
    # Create host with this OS
    match_sp_data = {
        "system_profile_facts": {
            "operating_system": {
                "name": "CentOS",
                "major": "8",
                "minor": "11",
            }
        }
    }
    match_host_id = str(db_create_host(extra_data=match_sp_data).id)

    # Create host with differing OS
    nomatch_sp_data = {
        "system_profile_facts": {
            "operating_system": {
                "name": "RHEL",
                "major": "7",
                "minor": "12",
            }
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][operating_system]{sp_filter_param}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]

    if match:
        assert match_host_id in response_ids
        assert nomatch_host_id not in response_ids
    else:
        assert nomatch_host_id in response_ids
        assert match_host_id not in response_ids


@pytest.mark.parametrize(
    "os_match_data_list,os_nomatch_data_list,sp_filter_param_list",
    (
        (
            [None],
            [
                {
                    "operating_system": {
                        "name": "RHEL",
                        "major": "8",
                        "minor": "1",
                    },
                }
            ],
            [
                "[operating_system][]=nil",
                "[operating_system]=nil",
            ],
        ),
        (
            [
                {
                    "operating_system": {
                        "name": "RHEL",
                        "major": "8",
                        "minor": "1",
                    },
                }
            ],
            [None],
            [
                "[operating_system][]=not_nil",
                "[operating_system]=not_nil",
            ],
        ),
        (
            [
                None,
                {
                    "operating_system": {
                        "name": "RHEL",
                        "major": "8",
                        "minor": "1",
                    },
                },
            ],
            None,
            [
                "[operating_system][]=nil&filter[system_profile][operating_system][]=not_nil",
            ],
        ),
    ),
)
def test_query_all_operating_system_nil(
    db_create_host, api_get, os_match_data_list, os_nomatch_data_list, sp_filter_param_list, subtests
):
    # Create host with this system profile
    match_host_id_list = [
        str(db_create_host(extra_data={"system_profile_facts": {"operating_system": os_data}}).id)
        for os_data in os_match_data_list
    ]
    if os_nomatch_data_list:
        nomatch_host_id_list = [
            str(db_create_host(extra_data={"system_profile_facts": {"operating_system": os_data}}).id)
            for os_data in os_nomatch_data_list
        ]

    for sp_filter_param in sp_filter_param_list:
        with subtests.test(query_param=sp_filter_param):
            url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

            response_status, response_data = api_get(url)

            assert response_status == 200

            # Assert that only the matching hosts are returned
            response_ids = [result["id"] for result in response_data["results"]]
            for match_host_id in match_host_id_list:
                assert match_host_id in response_ids

            if os_nomatch_data_list:
                for nomatch_host_id in nomatch_host_id_list:
                    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "sp_filter_param_list",
    (
        ["[arch][eq][]=x86_64", "[arch][eq][]=ARM"],  # Uses OR (same comparator)
        [
            "[operating_system][name][eq][]=CentOS Linux",
            "[operating_system][name][eq][]=RHEL",
        ],  # Uses OR
        [
            "[operating_system][CentOS Linux][version][eq][]=8.0",
            "[operating_system][RHEL][version][eq][]=7.5",
        ],
        ["[insights_client_version][]=3.0.1*", "[insights_client_version][]=1.2.3"],  # Uses OR
        ["[systemd][jobs_queued][lt][]=10", "[systemd][jobs_queued][gte][]=1"],  # Uses AND (different comparators)
    ),
)
def test_query_all_sp_filters_multiple_of_same_field(db_create_host, api_get, sp_filter_param_list):
    # Create two hosts that we want to show up in the results
    match_1_sp_data = {
        "system_profile_facts": {
            "operating_system": {"name": "RHEL", "major": "7", "minor": "5"},
            "arch": "x86_64",
            "insights_client_version": "3.0.1-2.el4_2",
            "systemd": {"jobs_queued": "1"},
        }
    }
    match_1_host_id = str(db_create_host(extra_data=match_1_sp_data).id)

    match_2_sp_data = {
        "system_profile_facts": {
            "operating_system": {"name": "CentOS Linux", "major": "8", "minor": "0"},
            "arch": "ARM",
            "insights_client_version": "1.2.3",
            "systemd": {"jobs_queued": "5"},
        }
    }
    match_2_host_id = str(db_create_host(extra_data=match_2_sp_data).id)

    # Create a host that we don't want to appear in the results
    nomatch_sp_data = {
        "system_profile_facts": {
            "operating_system": {"name": "CentOS"},
            "arch": "RISC-V",
            "insights_client_version": "4.5.6",
            "systemd": {"jobs_queued": "10"},
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    sp_query_filter = "&".join([f"filter[system_profile]{param}" for param in sp_filter_param_list])
    url = build_hosts_url(query=f"?{sp_query_filter}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_1_host_id in response_ids
    assert match_2_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "sp_filter_param,parent,child",
    (
        ("[foo]=val", "system_profile", "foo"),  # Invalid top-level field
        ("[bootc_status][foo]=val", "bootc_status", "foo"),  # Invalid non-top-level field
        ("[bootc_status][booted][foo]=val", "booted", "foo"),  # Invalid non-top-level field
        ("[arch][gteq]=val", "arch", "gteq"),  # Invalid comparator/field
    ),
)
def test_query_all_sp_filters_invalid_field(api_get, sp_filter_param, parent, child):
    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")
    response_status, response_data = api_get(url)

    assert response_status == 400
    assert f"Invalid operation or child node for {parent}: {child}" == response_data.get("detail")


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[number_of_cpus]=",  # Blank not allowed for non-string field
        "[number_of_cpus][eq]=",  # Blank not allowed for non-string field
        "[is_marketplace]=",  # Blank not allowed for non-string field
        "[is_marketplace][eq]=",  # Blank not allowed for non-string field
        "[number_of_cpus]=asdf",  # String not allowed for non-string field
    ),
)
def test_query_all_sp_filters_invalid_value(api_get, sp_filter_param):
    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, response_data = api_get(url)

    assert response_status == 400
    assert "is an invalid value for field" in response_data.get("detail")


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[operating_system][foo][version]=8.1",  # Invalid OS name
        "[operating_system][name][eq]=rhelz",  # Invalid OS name
        "[operating_system][][version][eq][]=7",  # Invalid OS name
        "[operating_system][RHEL][version]=bar",  # Invalid OS version
    ),
)
def test_query_all_sp_filters_invalid_operating_system(api_get, sp_filter_param):
    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, _ = api_get(url)

    assert response_status == 400


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[arch]=RkFz%60Z%2Ag%5D9_tW%3A%2CR%27v%22sjJsEo%23R%5D%27%27n.N2%3D%60G%22R%7C%7C.ER/1/wd6%603w-71%3CxC2",
        "[arch]=%5B%3Cb_Tu%7Dd%21%5D%7C/%22%29IS-%3Ct%28EwU%3F%3C4s7%7Cv%5DRE5hSU%3AQRJ%7D%29%230%27Vcf7%60eU%25k%2B/Cp%3CSxgKopb%3E%60",  # noqa E501
        "[arch]=%26.%40%7DE%21_A%2AE%26dgjV%7D%60yPc%22wO%7B%21b0%28kAGL%24-3mh%5EV%3E86%27RmG%7D.%2C5xQI~W/d%23/n%5DAr%22T",  # noqa E501
        "[arch]=EElM%298Z%28%29HjNL%21oRSc/gxC2%24%5Dpc%27tv%2A~mW%22kiF%7Ddos%60TE%7D%7DpAZ9C%3CNCRsEb%5BxH0",
    ),
)
def test_query_all_sp_filters_sql_character_issues(api_get, sp_filter_param):
    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, _ = api_get(url)

    assert response_status == 200


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[arch]=qbe%5Dd%3Fsdx%60.%7B0%60sTfX%3AGP%26dp%24kf%3By0%60F3%3B%60%5EZ1aa-b-%5B%3A9%24%26s48%5E08W%3EC%7C%2565D488De%23",  # noqa: E501
        "[arch]=%25T%5E%3EGYlS%22Q%2A2K%3A6v57YGLU5.7H%2Ap%23kEHqhTH1u6yEX%3AyaJyFkCRN%3Ew%22xX%5B3_",
        "[arch]=0~j%40TiIP%5ExYk%26yoFc0f%28%22El%6073g2%3B%22pqm%250z",
        "[arch]=%5Bw%7B%22%28caY4%28m%605A%7D%5B%2Cn8Eif%25%25%25E8%3FFg%3FC%3By%7BA%23Viv3SZVgAUhQ",
        "[arch]=Zk0%2A%2CgJjkL%3E%7CM%25b2W%60KZgY%5BjIaH%7DB-c%2CtfWv%2AdkpHR%29%7Cje",
        "[arch]=7%25%23a%40%7CyEptSf7_%3F%28SQ%60G%7CMc_Q8P1%3F",
    ),
)
def test_query_all_sp_filters_sql_char_contents(db_create_host, api_get, sp_filter_param):
    # Create host with this system profile
    sp_data = {
        "system_profile_facts": {
            "arch": "qbe]d?sdx`.{0`sTfX:GP&dp$kf;y0`F3;`^Z1aa-b-[:9$&s48^08W>C|%65D488De#",
            "host_type": "edge",
            "sap_sids": ["ABC", "DEF"],
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)
    sp_data = {
        "system_profile_facts": {
            "arch": '%T^>GYlS"Q*2K:6v57YGLU5.7H*p#kEHqhTH1u6yEX:yaJyFkCRN>w"xX[3_',
            "host_type": "edge",
            "sap_sids": ["ABC", "DEF"],
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)
    sp_data = {
        "system_profile_facts": {
            "arch": '0~j@TiIP^xYk&yoFc0f("El`73g2;"pqm%0z',
            "host_type": "edge",
            "sap_sids": ["ABC", "DEF"],
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)
    sp_data = {
        "system_profile_facts": {
            "arch": '[w{"(caY4(m`5A}[,n8Eif%%%E8?Fg?C;y{A#Viv3SZVgAUhQ',
            "host_type": "edge",
            "sap_sids": ["ABC", "DEF"],
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)
    sp_data = {
        "system_profile_facts": {
            "arch": "Zk0*,gJjkL>|M%b2W`KZgY[jIaH}B-c,tfWv*dkpHR)|je",
            "host_type": "edge",
            "sap_sids": ["ABC", "DEF"],
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)
    sp_data = {
        "system_profile_facts": {
            "arch": "7%#a@|yEptSf7_?(SQ`G|Mc_Q8P1?",
            "host_type": "edge",
            "sap_sids": ["ABC", "DEF"],
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)

    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, response_data = api_get(url)

    # Assert that the request succeeds but no hosts are returned
    assert response_status == 200
    assert len(response_data["results"]) == 1


def test_query_sp_filters_os_and_rhc_client_id(db_create_host, api_get):
    # Create host with this system profile
    match_sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "insights_client_version": "3.0.1-2.el4_2",
            "host_type": "edge",
            "sap": {"sap_system": True, "sids": ["ABC", "DEF"]},
            "bootc_status": {"booted": {"image": "quay.io/centos-bootc/fedora-bootc-cloud:eln"}},
            "sap_sids": ["ABC", "DEF"],
            "systemd": {"failed_services": ["foo", "bar"]},
            "system_memory_bytes": 8292048963606259,
            "rhc_client_id": "6b655c07-0daf-4564-9e1b-f6fb95510370",
            "operating_system": {"name": "RHEL", "major": 8, "minor": 6},
        }
    }
    match_host_id = str(db_create_host(extra_data=match_sp_data).id)

    # Create host with differing SP
    nomatch_sp_data = {
        "system_profile_facts": {
            "arch": "ARM",
            "insights_client_version": "1.2.3",
            "greenboot_status": "green",
            "bootc_status": {"booted": {"image": "192.168.0.1:5000/foo/foo:latest"}},
            "sap_sids": ["DEF"],
            "number_of_cpus": 8,
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    url = build_hosts_url(
        query="?filter[system_profile][operating_system][RHEL][version][eq][]=8.6&filter[system_profile][rhc_client_id][]=not_nil"  # noqa: E501
    )

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[bootc_status][is]=nil",
        "[bootc_status][is]=not_nil",
        "[bootc_status][booted][is]=nil",
        "[bootc_status][booted][is]=not_nil",
    ),
)
def test_query_sp_filters_query_on_object_with_is_successful_request(db_create_host, api_get, sp_filter_param):
    # Create host with this system profile
    match_sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "insights_client_version": "3.0.1-2.el4_2",
            "host_type": "edge",
            "sap": {"sap_system": True, "sids": ["ABC", "DEF"]},
            "bootc_status": {"booted": {"image": "quay.io/centos-bootc/fedora-bootc-cloud:eln"}},
            "sap_sids": ["ABC", "DEF"],
            "systemd": {"failed_services": ["foo", "bar"]},
            "system_memory_bytes": 8292048963606259,
            "rhc_client_id": "6b655c07-0daf-4564-9e1b-f6fb95510370",
            "operating_system": {"name": "RHEL", "major": 8, "minor": 6},
        }
    }
    db_create_host(extra_data=match_sp_data)

    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, _ = api_get(url)

    assert response_status == 200


def test_query_hosts_multiple_os(api_get, db_create_host, subtests):
    sp_facts_list = [
        {
            "operating_system": {"name": "RHEL", "major": 7, "minor": 7},
            "host_type": "edge",
        },
        {
            "operating_system": {"name": "RHEL", "major": 7, "minor": 8},
            "host_type": "edge",
        },
        {
            "operating_system": {"name": "RHEL", "major": 7, "minor": 7},
        },
        {
            "operating_system": {"name": "RHEL", "major": 7, "minor": 8},
        },
        {
            "operating_system": {"name": "RHEL", "major": 7, "minor": 8},
        },
        {
            "operating_system": {"name": "RHEL", "major": 7, "minor": 10},
        },
        {
            "operating_system": {"name": "RHEL", "major": 8, "minor": 0},
        },
        {
            "operating_system": {"name": "RHEL", "major": 8, "minor": 5},
        },
        {
            "operating_system": {"name": "RHEL", "major": 9, "minor": 1},
        },
    ]

    for sp_facts in sp_facts_list:
        # Create the hosts we expect to be returned
        db_create_host(extra_data={"system_profile_facts": sp_facts})

        # Create hosts with the same data, but on a different account
        db_create_host(
            identity=SERVICE_ACCOUNT_IDENTITY,
            extra_data={
                "system_profile_facts": sp_facts,
            },
        )

    sp_filter_param_list = [
        ("[operating_system][RHEL][version]=7.7", 2),
        ("[operating_system][RHEL][version][]=7.7&filter[system_profile][operating_system][RHEL][version][]=7.9", 2),
        ("[operating_system][RHEL][version][]=7.7&filter[system_profile][operating_system][RHEL][version][]=7.8", 5),
        ("[operating_system][RHEL][version][gt]=7.7", 7),
        ("[operating_system][RHEL][version][gte]=7.8", 7),
        ("[operating_system][RHEL][version][gte]=7.10", 4),
        ("[operating_system][RHEL][version][lte]=7.6", 0),
        ("[operating_system][RHEL][version][lte]=7.8", 5),
        (
            (
                "[operating_system][RHEL][version][]=7.7&filter[system_profile][operating_system][RHEL][version][]=7.8"
                "&filter[system_profile][operating_system][RHEL][version]=7.9&filter[system_profile][host_type][]=edge"
            ),
            2,
        ),
        (
            (
                "[operating_system][RHEL][version][eq][]=7"
                "&filter[system_profile][operating_system][RHEL][version][eq][]=8"
            ),
            8,
        ),
        (
            (
                "[operating_system][RHEL][version][eq][]=8"
                "&filter[system_profile][operating_system][RHEL][version][eq][]=7.8"
                "&filter[system_profile][operating_system][RHEL][version][eq][]=7.7"
            ),
            7,
        ),
        (
            (
                "[operating_system][RHEL][version][eq][]=8.0"
                "&filter[system_profile][operating_system][RHEL][version][eq][]=7.8"
                "&filter[system_profile][operating_system][RHEL][version][eq][]=7.7"
            ),
            6,
        ),
        (
            (
                "[operating_system][RHEL][version][eq][]=7.8"
                "&filter[system_profile][operating_system][RHEL][version][gt][]=8.1"
                "&filter[system_profile][operating_system][RHEL][version][lt][]=9.1"
            ),
            4,
        ),
        (
            (
                "[operating_system][RHEL][version][gte][]=7.10"
                "&filter[system_profile][operating_system][RHEL][version][lte][]=7.10"
            ),
            1,
        ),
    ]

    for sp_filter_param, expected_host_count in sp_filter_param_list:
        with subtests.test(query_param=sp_filter_param):
            url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

            response_status, response_data = api_get(url)

            assert response_status == 200
            assert response_data["count"] == expected_host_count


def test_get_host_exists_found(db_create_host, api_get):
    insights_id = generate_uuid()
    created_host = db_create_host(extra_data={"canonical_facts": {"insights_id": insights_id}})

    url = build_host_exists_url(insights_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["id"] == str(created_host.id)


def test_get_host_exists_not_found(api_get):
    url = build_host_exists_url(generate_uuid())
    response_status, _ = api_get(url)

    assert response_status == 404


def test_get_host_exists_error_multiple_found(db_create_host, api_get):
    insights_id = generate_uuid()

    # Create 2 hosts with the same Insights ID
    for _ in range(2):
        db_create_host(
            extra_data={"canonical_facts": {"insights_id": insights_id, "subscription_manager_id": generate_uuid()}}
        )

    url = build_host_exists_url(insights_id)
    response_status, _ = api_get(url)

    assert response_status == 409


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_exists_granular_rbac(db_create_host, db_create_group, db_create_host_group_assoc, api_get, mocker):
    # Create 3 hosts with unique insights IDs that the user has access to
    accessible_group_id = db_create_group("accessible_group").id
    accessible_insights_id_list = [generate_uuid() for _ in range(3)]
    accessible_host_id_list = [
        db_create_host(extra_data={"canonical_facts": {"insights_id": insights_id}}).id
        for insights_id in accessible_insights_id_list
    ]
    for host_id in accessible_host_id_list:
        db_create_host_group_assoc(host_id, accessible_group_id)

    # Create 2 hosts with unique insights IDs that the user does not have access to
    inaccessible_group_id = db_create_group("inaccessible_group").id
    inaccessible_insights_id_list = [generate_uuid() for _ in range(2)]
    inaccessible_host_id_list = [
        db_create_host(extra_data={"canonical_facts": {"insights_id": insights_id}}).id
        for insights_id in inaccessible_insights_id_list
    ]
    for host_id in inaccessible_host_id_list:
        db_create_host_group_assoc(host_id, inaccessible_group_id)

    # Grant access to first group
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-hosts-read-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = [str(accessible_group_id)]
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Verify that the user can see each of the hosts in the "accessible" group
    for insights_id in accessible_insights_id_list:
        url = build_host_exists_url(insights_id)
        response_status, _ = api_get(url)
        assert_response_status(response_status, 200)

    # Verify that the user can NOT see the hosts in the "inaccessible" group
    for insights_id in inaccessible_insights_id_list:
        url = build_host_exists_url(insights_id)
        response_status, _ = api_get(url)
        assert_response_status(response_status, 404)


@pytest.mark.usefixtures("enable_rbac")
def test_get_ungrouped_hosts_granular_rbac(
    db_create_host, db_create_group, db_create_host_group_assoc, api_get, mocker
):
    # Create the groups
    ungrouped_group_id = db_create_group("ungrouped", ungrouped=True).id
    grouped_group_id = db_create_group("grouped", ungrouped=False).id

    # Create hosts
    ungrouped_host_ids = [str(db_create_host().id) for _ in range(3)]
    ungrouped_group_host_ids = [str(db_create_host().id) for _ in range(4)]
    grouped_host_ids = [str(db_create_host().id) for _ in range(5)]

    # Assign assign hosts to the "ungrouped" group
    for host_id in ungrouped_group_host_ids:
        db_create_host_group_assoc(host_id, ungrouped_group_id)

    # Assign hosts to the regular group
    for host_id in grouped_host_ids:
        db_create_host_group_assoc(host_id, grouped_group_id)

    # Mock RBAC perms; only grant access to ungrouped hosts
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-hosts-read-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = [None]
    get_rbac_permissions_mock.return_value = mock_rbac_response

    response_status, response_data = api_get(build_hosts_url())
    assert_response_status(response_status, 200)

    actual_host_ids = [host["id"] for host in response_data["results"]]

    # Make sure it returned only ungrouped hosts and hosts in the "ungrouped" group
    for host_id in ungrouped_host_ids + ungrouped_group_host_ids:
        assert host_id in actual_host_ids

    for host_id in grouped_host_ids:
        assert host_id not in actual_host_ids


def test_get_host_from_different_org(mocker, api_get):
    get_host_list_mock = mocker.patch("api.host.build_paginated_host_list_response")
    get_host_list_mock.return_value = {
        "total": 1,
        "count": 1,
        "page": 1,
        "per_page": 50,
        "results": [
            {
                "insights_id": "2d052fcb-04fd-4529-8052-bb924410eb8b",
                "subscription_manager_id": None,
                "satellite_id": None,
                "bios_uuid": None,
                "ip_addresses": None,
                "fqdn": None,
                "mac_addresses": None,
                "provider_id": None,
                "provider_type": None,
                "id": "12172925-832f-4341-b55f-557746ae2748",
                "account": "test",
                "org_id": "diff_test",
                "display_name": "12172925-832f-4341-b55f-557746ae2748",
                "ansible_host": None,
                "facts": [],
                "reporter": "test-reporter",
                "per_reporter_staleness": {
                    "test-reporter": {
                        "last_check_in": "2025-02-04T00:11:45.902105+00:00",
                        "stale_timestamp": "2025-02-05T05:11:45.902105+00:00",
                        "check_in_succeeded": True,
                        "stale_warning_timestamp": "2025-02-11T00:11:45.902105+00:00",
                        "culled_timestamp": "2025-02-18T00:11:45.902105+00:00",
                    }
                },
                "stale_timestamp": "2025-02-05T05:11:45.902627+00:00",
                "stale_warning_timestamp": "2025-02-11T00:11:45.902627+00:00",
                "culled_timestamp": "2025-02-18T00:11:45.902627+00:00",
                "created": "2025-02-04T00:11:45.902625+00:00",
                "updated": "2025-02-04T00:11:45.902627+00:00",
                "groups": [],
            }
        ],
    }

    url = build_hosts_url()
    response_status, _ = api_get(url)
    assert_response_status(response_status, 403)


def test_query_by_staleness_using_columns(db_create_multiple_hosts, api_get, subtests):
    patch("app.staleness_serialization.get_flag_value", return_value=True)
    patch("app.models.get_flag_value", return_value=True)
    patch("app.serialization.get_flag_value", return_value=True)
    patch("api.host_query_db.get_flag_value", return_value=True)

    expected_staleness_results_map = {
        "fresh": 3,
        "stale": 4,
        "stale_warning": 2,
    }
    staleness_timestamp_map = {
        "fresh": now(),
        "stale": now() - timedelta(days=3),
        "stale_warning": now() - timedelta(days=10),
    }
    staleness_to_host_ids_map = dict()

    # Create the hosts in each state
    for staleness, num_hosts in expected_staleness_results_map.items():
        # Patch the "now" function so the hosts are created in the desired state
        with patch("app.models.datetime", **{"now.return_value": staleness_timestamp_map[staleness]}):
            staleness_to_host_ids_map[staleness] = [str(h.id) for h in db_create_multiple_hosts(how_many=num_hosts)]

    for staleness, count in expected_staleness_results_map.items():
        with subtests.test():
            url = build_hosts_url(query=f"?staleness={staleness}")
            # Validate the basics, i.e. response code and results size
            response_status, response_data = api_get(url)
            assert response_status == 200
            assert count == len(response_data["results"])
