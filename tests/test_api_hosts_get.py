from itertools import chain

import pytest

from lib.host_repository import find_hosts_by_staleness
from tests.helpers.api_utils import api_pagination_invalid_parameters_test
from tests.helpers.api_utils import api_query_test
from tests.helpers.api_utils import assert_error_response
from tests.helpers.api_utils import assert_response_status
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
from tests.helpers.graphql_utils import XJOIN_HOSTS_RESPONSE
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SIDS
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SYSTEM
from tests.helpers.graphql_utils import XJOIN_TAGS_RESPONSE
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
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


def test_get_hosts_unsupported_filter(patch_xjoin_post, api_get):
    patch_xjoin_post(response={})

    implicit_url = build_hosts_url(query="?filter[system_profile][bad_thing]=Banana")
    eq_url = build_hosts_url(query="?filter[Bad_thing][Extra_bad_one][eq]=Pinapple")

    implicit_response_status, implicit_response_data = api_get(implicit_url)
    eq_response_status, eq_response_data = api_get(eq_url)

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
