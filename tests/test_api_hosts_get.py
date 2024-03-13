import random
from datetime import timedelta
from itertools import chain
from unittest.mock import patch

import pytest

from lib.host_repository import find_hosts_by_staleness
from tests.helpers.api_utils import api_base_pagination_test
from tests.helpers.api_utils import api_pagination_invalid_parameters_test
from tests.helpers.api_utils import api_pagination_test
from tests.helpers.api_utils import api_query_test
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
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import quote
from tests.helpers.api_utils import quote_everything
from tests.helpers.graphql_utils import XJOIN_HOSTS_RESPONSE
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SIDS
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SYSTEM
from tests.helpers.graphql_utils import XJOIN_TAGS_RESPONSE
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now
from tests.helpers.test_utils import SYSTEM_IDENTITY


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
            response_status, response_data = api_get(url)
            assert response_status == 400


def test_query_host_id_with_incorrect_formats(api_get, subtests):
    host_id = "6a2f41a3-c54c-fce8-32d2-0324e1c32e22"

    bad_host_ids = (f" {host_id}", f"{{{host_id}", f"{host_id}-")

    for bad_host_id in bad_host_ids:
        with subtests.test():
            url = build_hosts_url(host_list_or_id=bad_host_id)
            response_status, response_data = api_get(url)
            assert response_status == 400


def test_query_invalid_paging_parameters(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(host_list_or_id=created_hosts)

    api_pagination_invalid_parameters_test(api_get, subtests, url)


def test_query_with_invalid_insights_id(mq_create_three_specific_hosts, api_get, subtests):
    url = build_hosts_url(query="?insights_id=notauuid")
    response_status, response_data = api_get(url)

    assert response_status == 400


def test_get_host_with_invalid_tag_no_key(mq_create_three_specific_hosts, api_get):
    """
    Attempt to find host with an incomplete tag (no key).
    Expects 400 response.
    """
    url = build_hosts_url(query="?tags=namespace/=Value")
    response_status, response_data = api_get(url)

    assert response_status == 400


@pytest.mark.parametrize(
    "tag_query,part_name",
    (
        (f"{'a' * 256}/key=val", "namespace"),
        (f"namespace/{'a' * 256}=val", "key"),
        (f"namespace/key={'a' * 256}", "value"),
    ),
)
def test_get_host_tag_part_too_long(tag_query, part_name, mq_create_three_specific_hosts, api_get):
    """
    send a request to find hosts with a string tag where the length
    of the namespace excedes the 255 character limit
    """

    url = build_hosts_url(query=f"?tags={tag_query}")
    response_status, response_data = api_get(url)

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
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
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
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
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
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
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
            response_status, response_data = api_get(url, query_parameters=fields_query_parameters)
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


def test_get_hosts_with_RBAC_allowed(subtests, mocker, db_create_host, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_hosts_url(host_list_or_id=host.id)
            response_status, response_data = api_get(url)

            assert_response_status(response_status, 200)


def test_get_hosts_with_RBAC_denied(subtests, mocker, db_create_host, api_get, enable_rbac):
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
            response_status, response_data = api_get(url)

            assert_response_status(response_status, 403)

            find_hosts_by_staleness_mock.assert_not_called()


def test_get_hosts_with_RBAC_bypassed_as_system(db_create_host, api_get, enable_rbac):
    host = db_create_host(SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": generate_uuid()}})

    url = build_hosts_url(host_list_or_id=host.id)
    response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


def test_get_hosts_sap_system(patch_xjoin_post, api_get, subtests):
    patch_xjoin_post(response={"data": {"hosts": {"meta": {"total": 1}, "data": []}}})

    values = ("true", "false", "nil", "not_nil")

    for value in values:
        with subtests.test(value=value):
            implicit_url = build_hosts_url(query=f"?filter[system_profile][sap_system]={value}")
            eq_url = build_hosts_url(query=f"?filter[system_profile][sap_system][eq]={value}")

            implicit_response_status, implicit_response_data = api_get(implicit_url)
            eq_response_status, eq_response_data = api_get(eq_url)

            assert_response_status(implicit_response_status, 200)
            assert_response_status(eq_response_status, 200)
            assert implicit_response_data["total"] == 1
            assert eq_response_data["total"] == 1


def test_get_hosts_sap_sids(patch_xjoin_post, api_get, subtests):
    patch_xjoin_post(response={"data": {"hosts": {"meta": {"total": 1}, "data": []}}})

    filter_paths = ("[system_profile][sap_sids][]", "[system_profile][sap_sids][contains][]")
    value_sets = (("ABC",), ("BEN", "A72"), ("CDA", "MK2", "C2C"))

    for path in filter_paths:
        for values in value_sets:
            with subtests.test(values=values, path=path):
                url = build_hosts_url(query="?" + "".join([f"filter{path}={value}&" for value in values]))

                response_status, response_data = api_get(url)

                assert_response_status(response_status, 200)
                assert response_data["total"] == 1


def test_get_hosts_sap_system_bad_parameter_values(patch_xjoin_post, api_get, subtests):
    patch_xjoin_post(response={})

    values = "Garfield"

    for value in values:
        with subtests.test(value=value):
            implicit_url = build_hosts_url(query=f"?filter[system_profile][sap_system]={value}")
            eq_url = build_hosts_url(query=f"?filter[system_profile][sap_system][eq]={value}")

            implicit_response_status, implicit_response_data = api_get(implicit_url)
            eq_response_status, eq_response_data = api_get(eq_url)

            assert_response_status(implicit_response_status, 400)
            assert_response_status(eq_response_status, 400)


@pytest.mark.parametrize(
    "hide_edge_hosts",
    (True, False),
)
def test_get_hosts_unsupported_filter(mocker, patch_xjoin_post, api_get, hide_edge_hosts):
    patch_xjoin_post(response={})
    # Should work whether hide-edge-hosts feature flag is on or off
    mocker.patch("api.filtering.filtering.get_flag_value", return_value=hide_edge_hosts)

    implicit_url = build_hosts_url(query="?filter[system_profile][bad_thing]=Banana")
    eq_url = build_hosts_url(query="?filter[Bad_thing][Extra_bad_one][eq]=Pinapple")

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


def test_sp_sparse_fields_xjoin_response_translation(patch_xjoin_post, api_get):
    host_one_id, host_two_id = generate_uuid(), generate_uuid()

    hosts = [minimal_host(id=host_one_id), minimal_host(id=host_two_id)]

    for query, xjoin_post in (
        (
            "?fields[system_profile]=os_kernel_version,arch,sap_sids",
            [
                {
                    "id": host_one_id,
                    "system_profile_facts": {
                        "os_kernel_version": "3.10.0",
                        "arch": "string",
                        "sap_sids": ["H2O", "PH3", "CO2"],
                    },
                },
                {"id": host_two_id, "system_profile_facts": {"os_kernel_version": "1.11.1", "arch": "host_arch"}},
            ],
        ),
        (
            "?fields[system_profile]=arch",
            [{"id": host_one_id, "system_profile_facts": {}}, {"id": host_two_id, "system_profile_facts": {}}],
        ),
        (
            "?fields[system_profile]=os_kernel_version,arch&fields[system_profile]=sap_sids",
            [
                {
                    "id": host_one_id,
                    "system_profile_facts": {
                        "os_kernel_version": "3.10.0",
                        "arch": "string",
                        "sap_sids": ["H2O", "PH3", "CO2"],
                    },
                },
                {"id": host_two_id, "system_profile_facts": {"os_kernel_version": "1.11.1", "arch": "host_arch"}},
            ],
        ),
    ):
        patch_xjoin_post(response={"data": {"hosts": {"meta": {"total": 2, "count": 2}, "data": xjoin_post}}})
        response_status, response_data = api_get(build_system_profile_url(hosts, query=query))

        assert_response_status(response_status, 200)
        assert response_data["total"] == 2
        assert response_data["count"] == 2
        assert response_data["results"][0]["system_profile"] == xjoin_post[0]["system_profile_facts"]


def test_sp_sparse_fields_xjoin_response_with_invalid_field(patch_xjoin_post, db_create_host, api_get):
    host = minimal_host(id=generate_uuid())

    xjoin_post = [
        {
            "id": str(host.id),
            "invalid_key": {"os_kernel_version": "3.10.0", "arch": "string", "sap_sids": ["H2O", "PH3", "CO2"]},
        }
    ]
    patch_xjoin_post(response={"data": {"hosts": {"meta": {"total": 1, "count": 1}, "data": xjoin_post}}})
    response_status, response_data = api_get(
        build_system_profile_url([host], query="?fields[system_profile]=os_kernel_version,arch,sap_sids")
    )

    assert_response_status(response_status, 200)
    assert response_data["total"] == 1
    assert response_data["count"] == 1
    assert response_data["results"][0]["system_profile"] == {}


def test_validate_sp_sparse_fields_invalid_requests(api_get):
    for query in (
        "?fields[system_profile]=os_kernel_version&order_how=ASC",
        "?fields[system_profile]=os_kernel_version&order_by=modified",
        "?fields[system_profile]=os_kernel_version&order_how=display_name&order_by=NOO",
        "?fields[foo]=bar",
    ):
        host_one_id, host_two_id = generate_uuid(), generate_uuid()
        hosts = [minimal_host(id=host_one_id), minimal_host(id=host_two_id)]

        response_status, response_data = api_get(build_system_profile_url(hosts, query=query))
        assert response_status == 400


def test_host_list_sp_fields_requested(patch_xjoin_post, api_get):
    patch_xjoin_post(response={"data": XJOIN_HOSTS_RESPONSE})
    fields = ["arch", "kernel_modules", "owner_id"]
    response_status, response_data = api_get(HOST_URL + f"?fields[system_profile]={','.join(fields)}")

    assert response_status == 200

    for host_data in response_data["results"]:
        assert "system_profile" in host_data
        for key in host_data["system_profile"].keys():
            assert key in fields


def test_host_list_sp_fields_not_requested(patch_xjoin_post, api_get):
    patch_xjoin_post(response={"data": XJOIN_HOSTS_RESPONSE})
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200

    for host_data in response_data["results"]:
        assert "system_profile" not in host_data


def test_unindexed_fields_fail_gracefully(api_get):
    url_builders = (
        build_hosts_url,
        build_system_profile_sap_sids_url,
        build_tags_url,
        build_system_profile_sap_system_url,
    )

    for url_builder in url_builders:
        for query in ("?filter[system_profile][installed_packages_delta]=foo",):
            response_status, _ = api_get(url_builder(query=query))
            assert response_status == 400


# This test verifies that the [contains] operation is accepted for a string array field such as cpu_flags
def test_get_hosts_contains_works_on_string_array(patch_xjoin_post, api_get, subtests):
    url_builders = (
        build_hosts_url,
        build_system_profile_sap_sids_url,
        build_tags_url,
        build_system_profile_sap_system_url,
    )
    responses = (
        XJOIN_HOSTS_RESPONSE,
        XJOIN_SYSTEM_PROFILE_SAP_SIDS,
        XJOIN_TAGS_RESPONSE,
        XJOIN_SYSTEM_PROFILE_SAP_SYSTEM,
    )
    query = "?filter[system_profile][cpu_flags][contains]=ex1"
    for url_builder, response in zip(url_builders, responses):
        with subtests.test(url_builder=url_builder, response=response, query=query):
            patch_xjoin_post(response={"data": response})
            response_status, _ = api_get(url_builder(query=query))
            assert response_status == 200


# This test verifies that the [contains] operation is denied for a non-array string field such as cpu_model
def test_get_hosts_contains_invalid_on_string_not_array(patch_xjoin_post, api_get, subtests):
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


def test_get_hosts_timestamp_invalid_value_graceful_rejection(patch_xjoin_post, api_get):
    assert 400 == api_get(build_hosts_url(query="?filter[system_profile][last_boot_time][eq]=foo"))[0]


def test_query_all(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list(created_hosts)

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(HOST_URL)
        api_base_pagination_test(api_get, subtests, HOST_URL, expected_total=len(expected_host_list))

    assert response_status == 200
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_display_name(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[0]])
    url = build_hosts_url(query=f"?display_name={created_hosts[0].display_name}")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_fqdn_two_results(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[0], created_hosts[1]])

    url = build_hosts_url(query=f"?fqdn={created_hosts[0].fqdn}")
    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_fqdn_one_result(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[2]])
    url = build_hosts_url(query=f"?fqdn={created_hosts[2].fqdn}")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_non_existent_fqdn(api_get):
    url = build_hosts_url(query="?fqdn=NONEXISTENT.com")
    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_query_using_display_name_substring(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list(created_hosts)
    host_name_substr = created_hosts[0].display_name[:4]
    url = build_hosts_url(query=f"?display_name={host_name_substr}")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)
        api_pagination_test(api_get, subtests, url, expected_total=len(created_hosts))

    assert response_status == 200
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_display_name_as_hostname(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[0].display_name}")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)
        api_pagination_test(api_get, subtests, url, expected_total=2)

    assert response_status == 200
    assert len(response_data["results"]) == 2


def test_query_using_fqdn_as_hostname(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[2].display_name}")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)
        api_pagination_test(api_get, subtests, url, expected_total=1)

    assert response_status == 200
    assert len(response_data["results"]) == 1


def test_query_using_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[0].id}")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)
        api_pagination_test(api_get, subtests, url, expected_total=1)

    assert response_status == 200
    assert len(response_data["results"]) == 1


def test_query_using_non_existent_hostname(mq_create_three_specific_hosts, api_get, subtests):
    url = build_hosts_url(query="?hostname_or_id=NotGonnaFindMe")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)
        api_pagination_test(api_get, subtests, url, expected_total=0)

    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_query_using_non_existent_id(mq_create_three_specific_hosts, api_get, subtests):
    url = build_hosts_url(query=f"?hostname_or_id={generate_uuid()}")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)
        api_pagination_test(api_get, subtests, url, expected_total=0)

    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_query_using_insights_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?insights_id={created_hosts[0].insights_id}")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)
        api_pagination_test(api_get, subtests, url, expected_total=1)

    assert response_status == 200
    assert len(response_data["results"]) == 1


def test_get_host_by_tag(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=SPECIAL/tag=ToFind")

    with patch("api.host.get_flag_value", return_value=True):
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

    with patch("api.host.get_flag_value", return_value=True):
        api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_by_multiple_tags(mq_create_three_specific_hosts, api_get, subtests):
    """
    Get only the host with all three tags on it, and not the other hosts,
    which both have some (but not all) of the tags we query for.
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[1]]
    url = build_hosts_url(query="?tags=NS1/key1=val1&tags=NS2/key2=val2&tags=NS3/key3=val3")

    with patch("api.host.get_flag_value", return_value=True):
        api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_by_subset_of_tags(mq_create_three_specific_hosts, api_get, subtests):
    """
    Get a host using a subset of its tags
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[1]]
    url = build_hosts_url(query="?tags=NS1/key1=val1&tags=NS3/key3=val3")

    with patch("api.host.get_flag_value", return_value=True):
        api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_with_different_tags_same_namespace(mq_create_three_specific_hosts, api_get, subtests):
    """
    get a host with two tags in the same namespace with diffent key and same value
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=NS1/key1=val1&tags=NS1/key2=val1")

    with patch("api.host.get_flag_value", return_value=True):
        api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_no_host_with_different_tags_same_namespace(mq_create_three_specific_hosts, api_get, subtests):
    """
    Don’t get a host with two tags in the same namespace, from which only one match. This is a
    regression test.
    """
    url = build_hosts_url(query="?tags=NS1/key1=val2&tags=NS1/key2=val1")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_get_host_with_same_tags_different_namespaces(mq_create_three_specific_hosts, api_get, subtests):
    """
    get a host with two tags in the same namespace with different key and same value
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[2]]
    url = build_hosts_url(query="?tags=NS3/key3=val3&tags=NS1/key3=val3")

    with patch("api.host.get_flag_value", return_value=True):
        api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_with_tag_no_value_at_all(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with no stored value
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=no/key")

    with patch("api.host.get_flag_value", return_value=True):
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

    with patch("api.host.get_flag_value", return_value=True):
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

    with patch("api.host.get_flag_value", return_value=True):
        api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


def test_get_host_with_tag_only_key(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with no namespace.
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[2]]
    url = build_hosts_url(query="?tags=key5")

    with patch("api.host.get_flag_value", return_value=True):
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

    with patch("api.host.get_flag_value", return_value=True):
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

    with patch("api.host.get_flag_value", return_value=True):
        api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]


@pytest.mark.parametrize("tag_query", (";?:@&+$/-_.!~*'()'=#", " \t\n\r\f\v/ \t\n\r\f\v= \t\n\r\f\v"))
def test_get_host_with_unescaped_special_characters(tag_query, mq_create_or_update_host, api_get, subtests):
    tags = [
        {"namespace": ";?:@&+$", "key": "-_.!~*'()'", "value": "#"},
        {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]

    host = minimal_host(tags=tags)
    created_host = mq_create_or_update_host(host)
    url = build_hosts_url(query=f"?tags={quote(tag_query)}")

    with patch("api.host.get_flag_value", return_value=True):
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

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"]
    assert response_data["results"][0]["id"] == created_host.id


@pytest.mark.parametrize("num_groups", (1, 3, 5))
def test_query_using_group_name(db_create_group_with_hosts, api_get, num_groups):
    hosts_per_group = 3
    for i in range(num_groups):
        db_create_group_with_hosts(f"existing_group_{i}", hosts_per_group).id

    # Some other group that we don't want to see in the response
    db_create_group_with_hosts("some_other_group", 5)

    group_name_params = "&".join([f"group_name=existing_group_{i}" for i in range(num_groups)])
    url = build_hosts_url(query=f"?{group_name_params}")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == num_groups * hosts_per_group


def test_query_ungrouped_hosts(db_create_group_with_hosts, mq_create_three_specific_hosts, api_get):
    # Create 3 hosts that are not in a group
    ungrouped_hosts = mq_create_three_specific_hosts

    # Also create 5 hosts that are in a group
    db_create_group_with_hosts("group_with_hosts", 5)
    url = build_hosts_url(query="?group_name=")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert_host_lists_equal(build_expected_host_list(ungrouped_hosts), response_data["results"])


def test_query_hosts_filter_updated_start_end(mq_create_or_update_host, api_get):
    host_list = [mq_create_or_update_host(minimal_host(insights_id=generate_uuid())) for _ in range(3)]

    with patch("api.host.get_flag_value", return_value=True):
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
def test_get_hosts_order_by_group_name(db_create_group_with_hosts, api_get, subtests, order_how):
    hosts_per_group = 2
    names = ["A Group", "B Group", "C Group"]
    [db_create_group_with_hosts(group_name, hosts_per_group) for group_name in names]

    url = build_hosts_url(query=f"?order_by=group_name&order_how={order_how}")

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(names) * hosts_per_group == len(response_data["results"])

    # If descending order is requested, reverse the expected order of group names
    if order_how == "DESC":
        names.reverse()

    for group_index in range(len(names)):
        for host_index in range(hosts_per_group):
            assert (
                response_data["results"][group_index * hosts_per_group + host_index]["groups"][0]["name"]
                == names[group_index]
            )


@pytest.mark.parametrize("order_how", ("ASC", "DESC"))
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
    url = build_hosts_url(query=f"?order_by=operating_system&order_how={order_how}")

    with patch("api.host.get_flag_value", return_value=True):
        # Validate the basics, i.e. response code and results size
        response_status, response_data = api_get(url)
        assert response_status == 200
        assert len(created_hosts) == len(response_data["results"])

    # If descending order is requested, reverse the expected order of hosts
    if order_how == "DESC":
        ordered_insights_ids.reverse()

    for index in range(len(ordered_insights_ids)):
        assert ordered_insights_ids[index] == response_data["results"][index]["insights_id"]


@pytest.mark.parametrize("num_hosts_to_query", (1, 2, 3))
def test_query_using_id_list(mq_create_three_specific_hosts, api_get, subtests, num_hosts_to_query):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(host_list_or_id=[host.id for host in created_hosts[:num_hosts_to_query]])

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)
        api_pagination_test(api_get, subtests, url, expected_total=num_hosts_to_query)

    assert response_status == 200
    assert len(response_data["results"]) == num_hosts_to_query


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

    with patch("api.host.get_flag_value", return_value=True):
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

    with patch("api.host.get_flag_value", return_value=True):
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

    with patch("api.host.get_flag_value", return_value=True):
        response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that the system_profile is not in the response by default
    for result in response_data["results"]:
        assert "system_profile" in result
        assert "arch" not in result["system_profile"]
        assert "host_type" not in result["system_profile"]
        assert "os_kernel_version" in result["system_profile"]
        assert "owner_id" in result["system_profile"]


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
            }
        },
        {
            "puptoo": {
                "last_check_in": (_now - timedelta(days=30)).isoformat(),
                "stale_timestamp": (_now - timedelta(days=23)).isoformat(),
                "check_in_succeeded": True,
            }
        },
        {
            "rhsm-conduit": {
                "last_check_in": (_now - timedelta(days=1)).isoformat(),
                "stale_timestamp": (_now + timedelta(days=6)).isoformat(),
                "check_in_succeeded": True,
            }
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
        "yupana": 1,
        "rhsm-conduit": 1,
        "rhsm-conduit&registered_with=yupana": 2,
    }
    for reporter, count in expected_reporter_results_map.items():
        with subtests.test():
            url = build_hosts_url(query=f"?registered_with={reporter}")
            with patch("api.host.get_flag_value", return_value=True):
                # Validate the basics, i.e. response code and results size
                response_status, response_data = api_get(url)
                assert response_status == 200
                assert count == len(response_data["results"])
