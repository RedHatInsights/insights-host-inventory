import logging
from itertools import chain

import pytest

from app.exceptions import IdsNotFoundError
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import LEGACY_HOST_URL
from tests.helpers.api_utils import api_base_pagination_test
from tests.helpers.api_utils import api_pagination_invalid_parameters_test
from tests.helpers.api_utils import api_pagination_test
from tests.helpers.api_utils import assert_error_response
from tests.helpers.api_utils import assert_host_lists_equal
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_expected_host_list
from tests.helpers.api_utils import build_fields_query_parameters
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_order_query_parameters
from tests.helpers.api_utils import build_system_profile_sap_sids_url
from tests.helpers.api_utils import build_system_profile_sap_system_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.test_utils import IDENTITY_WITHOUT_HOSTS
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host

logger = logging.getLogger(__name__)


def test_query_single_non_existent_host(api_get):
    url = build_hosts_url(host_list_or_id=generate_uuid())
    response_status, _ = api_get(url)
    assert response_status == 404


def test_query_non_existent_host_response_includes_missing_ids(api_get):
    # Verify that 404 response includes the not_found_ids field
    host_id = generate_uuid()
    url = build_hosts_url(host_list_or_id=host_id)

    response_status, response_data = api_get(url)

    assert response_status == 404
    assert "not_found_ids" in response_data
    assert response_data["not_found_ids"] == [host_id]
    assert response_data["detail"] == "One or more hosts not found."


def test_ids_not_found_error_to_json_includes_ids():
    missing_ids = [generate_uuid(), generate_uuid()]

    error = IdsNotFoundError("host", missing_ids)
    error_json = error.to_json()

    assert error_json["status"] == 404
    assert error_json["detail"] == "One or more hosts not found."
    assert error_json["not_found_ids"] == missing_ids


def test_ids_not_found_error_to_json_omits_ids_when_none():
    error = IdsNotFoundError("host")
    error_json = error.to_json()

    assert error_json["status"] == 404
    assert error_json["detail"] == "One or more hosts not found."
    assert "not_found_ids" not in error_json


def test_query_mixed_valid_and_missing_hosts_response_includes_only_missing_ids(db_create_host, api_get):
    # Verify 404 response only includes the missing IDs, not the valid ones
    valid_host_id = str(db_create_host().id)
    missing_host_id = generate_uuid()
    url = build_hosts_url(host_list_or_id=f"{valid_host_id},{missing_host_id}")

    response_status, response_data = api_get(url)

    assert response_status == 404
    assert "not_found_ids" in response_data
    assert response_data["not_found_ids"] == [missing_host_id]
    assert valid_host_id not in response_data["not_found_ids"]
    assert response_data["detail"] == "One or more hosts not found."


def test_query_missing_hosts_with_pagination_omits_not_found_ids(db_create_host, api_get):
    """
    When requesting more IDs than can fit in a single page, the backend uses `total`
    to detect missing IDs but cannot reliably compute `not_found_ids`. In this
    paginated case, the 404 error body must NOT include `not_found_ids`.
    """
    # Create multiple valid hosts and a missing ID so that with per_page=1,
    # only some results are returned (total > len(found_objects))
    valid_host_1 = str(db_create_host().id)
    valid_host_2 = str(db_create_host().id)
    missing_host_id = str(generate_uuid())

    combined_ids = ",".join([valid_host_1, valid_host_2, missing_host_id])

    url = build_hosts_url(
        host_list_or_id=combined_ids,
        query="?per_page=1",
    )

    response_status, response_data = api_get(url)

    assert response_status == 404
    # In paginated scenarios where `have_all_results` is False, the API should *not*
    # include `not_found_ids` because it cannot be accurately computed.
    assert "not_found_ids" not in response_data


def test_query_invalid_host_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    bad_id_list = ["notauuid", "1234blahblahinvalid"]
    only_bad_id = bad_id_list.copy()

    # Can't have empty string as an only ID, that results in 404 Not Found.
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


def test_invalid_fields(mq_create_three_specific_hosts, api_get, subtests):
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
    get_host_list_mock = mocker.patch("api.host.get_host_list_by_id_list")

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_hosts_url(host_list_or_id=host.id)
            response_status, _ = api_get(url)

            assert_response_status(response_status, 403)

            get_host_list_mock.assert_not_called()


def test_get_hosts_with_RBAC_bypassed_as_system(db_create_host, api_get):
    host = db_create_host(
        SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}}
    )

    url = build_hosts_url(host_list_or_id=host.id)
    response_status, _ = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


@pytest.mark.parametrize(
    "query",
    (
        "?filter[system_profile][workloads][sap][sap_system]=Garfield",
        "?filter[system_profile][workloads][sap][sap_system][eq]=Garfield",
    ),
)
def test_get_hosts_sap_system_bad_parameter_values(api_get, query):
    implicit_url = build_hosts_url(query=query)
    status, _ = api_get(implicit_url)

    assert_response_status(status, 400)


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


def test_query_all_with_edge(mq_create_three_specific_hosts, mq_create_edge_host, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts + [mq_create_edge_host]
    expected_host_list = build_expected_host_list(created_hosts)

    response_status, response_data = api_get(HOST_URL)
    api_base_pagination_test(api_get, subtests, HOST_URL, expected_total=len(expected_host_list))

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
        (f"display_name={generate_uuid()}&fqdn={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&fqdn={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&insights_id={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"fqdn={generate_uuid()}&insights_id={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (
            f"display_name={generate_uuid()}&fqdn={generate_uuid()}&insights_id={generate_uuid()}&hostname_or_id={generate_uuid()}"
        ),
    ),
)
def test_query_by_conflitcting_ids(api_get, query):
    # Not allowed to query on more than one of these fields at once
    url = build_hosts_url(query=f"?{query}")
    response_status, response_body = api_get(url)

    assert response_status == 400
    assert (
        "Only one of [fqdn, display_name, hostname_or_id, insights_id] may be provided at a time."
        in response_body["detail"]
    )


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


@pytest.mark.parametrize(
    "param_name,value_getter",
    [
        ("hostname_or_id", lambda h: h[0].id),
        ("insights_id", lambda h: h[0].insights_id.upper()),
        ("subscription_manager_id", lambda h: h[0].subscription_manager_id),
    ],
)
def test_query_using_single_field(mq_create_three_specific_hosts, api_get, subtests, param_name, value_getter):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?{param_name}={value_getter(created_hosts)}")
    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=1)
    assert response_status == 200
    assert len(response_data["results"]) == 1


@pytest.mark.parametrize("value", ["NotGonnaFindMe", lambda: generate_uuid()])
def test_query_using_non_existent_host(api_get, subtests, value):
    query_value = value() if callable(value) else value
    url = build_hosts_url(query=f"?hostname_or_id={query_value}")
    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=0)
    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_get_host_by_tag(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=SPECIAL/tag=ToFind")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
        assert host.id == result["id"]


def test_get_multiple_hosts_by_tag(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0], created_hosts[1]]
    url = build_hosts_url(query="?tags=NS1/key1=val1&order_by=updated&order_how=ASC")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
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
    Don't get a host with two tags in the same namespace, from which only one match. This is a
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

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
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

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
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

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
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

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
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

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
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

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
        assert host.id == result["id"]


def test_no_hosts_in_org(api_get):
    """Test no hosts are returned if for empty organization."""

    url = build_hosts_url()
    response_status, response_data = api_get(url, identity=IDENTITY_WITHOUT_HOSTS)
    assert response_status == 200
    assert response_data["results"] == []
    assert response_data["count"] == response_data["total"] == 0


def test_system_profile_wildcard_url_encoding_documentation(db_create_host, api_get):
    """Document the current URL encoding behavior and limitations for RHINENG-4809.

    This test documents that URL-encoded asterisks (%2A) are decoded to regular asterisks
    before wildcard processing, so they behave as wildcards rather than literals.
    The fix implements backslash-escaped asterisks (\\*) as the workaround for literal matching.
    """
    # Create a host with literal asterisk
    db_create_host(
        extra_data={"system_profile_facts": {"insights_client_version": "prod*env"}, "display_name": "test_host"}
    )

    # Document current behavior:
    # 1. %2A (URL-encoded *) is decoded to * before wildcard processing, so it acts as wildcard
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=prod%2Aenv")
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(response_data["results"]) == 1  # Matches because %2A becomes wildcard *

    # 2. \\* (backslash-escaped *) is treated as literal * in wildcard processing
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=prod\\*env")
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(response_data["results"]) == 1  # Matches because \\* becomes literal *

    # 3. Regular * acts as wildcard
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=prod*env")
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(response_data["results"]) == 1  # Matches because * is wildcard

    # 4. The original issue: users cannot distinguish URL-encoded * from regular *
    #    Both %2A and * behave as wildcards, so there's no way to match literal * via URL encoding
    #    The fix provides \\* as a workaround for literal asterisk matching
