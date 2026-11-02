from datetime import datetime
from datetime import timedelta

import pytest

from app.exceptions import IdsNotFoundError
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import api_pagination_invalid_parameters_test
from tests.helpers.api_utils import api_pagination_test
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_fields_query_parameters
from tests.helpers.api_utils import build_host_exists_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_order_query_parameters
from tests.helpers.api_utils import build_system_profile_sap_sids_url
from tests.helpers.api_utils import build_system_profile_sap_system_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.test_utils import INVALID_UUIDS
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host


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


@pytest.mark.parametrize("invalid_uuid", INVALID_UUIDS)
@pytest.mark.parametrize("prepend_existing_uuid", (False, True))
def test_query_invalid_host_id(invalid_uuid, prepend_existing_uuid, mq_create_three_specific_hosts, api_get):
    """
    INVALID_UUID only have random invalid UUIDs along with non existing valid uuid
    Below makes sure tests are performed with existing uuids as well with help of
    mq_create_three_specific_hosts To test all invalid patterns, we used stacked
    parameterization
    """
    if prepend_existing_uuid:
        invalid_uuid = f"{mq_create_three_specific_hosts[0].id},{invalid_uuid}"
    url = build_hosts_url(host_list_or_id=invalid_uuid)
    response_status, response_data = api_get(url)
    # If Empty UUID (in INVALID_UUIDS), api results in 200 OK.
    if not invalid_uuid:
        assert_response_status(response_status, expected_status=200)
    else:
        assert_response_status(response_status, expected_status=400)


def test_query_invalid_paging_parameters(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(host_list_or_id=created_hosts)

    api_pagination_invalid_parameters_test(api_get, subtests, url)


@pytest.mark.parametrize("invalid_uuid", INVALID_UUIDS)
def test_query_with_invalid_insights_id(api_get, invalid_uuid):
    url = build_hosts_url(query=f"?insights_id={invalid_uuid}")
    response_status, response_data = api_get(url)
    assert response_status == 400
    assert "is not a 'uuid'" in response_data["detail"]


def test_get_host_with_invalid_tag_no_key(api_get):
    """
    Attempt to find host with an incomplete tag (no key).
    Expects 400 response.
    """
    url = build_hosts_url(query="?tags=namespace/=Value")
    response_status, _ = api_get(url)

    assert response_status == 400


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
        "?fields[foo]=bar",
    ):
        with subtests.test(query=query):
            host_one_id, host_two_id = generate_uuid(), generate_uuid()
            hosts = [minimal_host(id=host_one_id), minimal_host(id=host_two_id)]

            response_status, _ = api_get(build_system_profile_url(hosts, query=query))
            assert response_status == 400


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


def test_query_using_non_existent_fqdn(api_get):
    url = build_hosts_url(query="?fqdn=NONEXISTENT.com")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0


@pytest.mark.parametrize("value", ["NotGonnaFindMe", lambda: generate_uuid()])
def test_query_using_non_existent_host(api_get, subtests, value):
    query_value = value() if callable(value) else value
    url = build_hosts_url(query=f"?hostname_or_id={query_value}")
    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=0)
    assert response_status == 200
    assert len(response_data["results"]) == 0


@pytest.mark.parametrize("group_param_to_use", ("workspace", "group"))
def test_query_group_id_rejects_invalid_uuid(api_get, group_param_to_use):
    """Test that group_id parameter rejects non-UUID values."""
    # Try with an invalid UUID
    url = build_hosts_url(query=f"?{group_param_to_use}_id=invalid-uuid")
    response_status, response_data = api_get(url)

    # Should return 400 Bad Request for invalid UUID
    assert response_status == 400

    # Verify error message mentions the invalid value and UUID requirement
    assert "invalid-uuid" in response_data["detail"]
    assert "pattern" in response_data["detail"].lower() or "uuid" in response_data["detail"].lower()


def test_query_hosts_filter_last_check_in_and_updated_invalid_format(api_get, subtests):
    invalid_formats = ("foobar", "{}", "[]", generate_uuid(), [datetime.now(), datetime.now() - timedelta(days=7)])
    for invalid_format in invalid_formats:
        for param in ("last_check_in_start", "last_check_in_end", "updated_start", "updated_end"):
            with subtests.test(invalid_format=invalid_format, param=param):
                url = build_hosts_url(query=f"?{param}={invalid_format}")
                response_status, response_data = api_get(url)
                assert response_status == 400
                assert "is not a 'date-time'" in response_data["detail"]


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        # Non-object JSON values: must not be treated as deep object filters
        "=true",
        "=1",
        '=["ABC", "DEF"]',
    ),
)
def test_query_all_sp_filters_json_invalid_object_notation(api_get, sp_filter_param):
    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")
    response_status, _ = api_get(url)
    assert response_status == 400


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


def test_get_host_exists_error_multiple_found(db_create_host, api_get):
    insights_id = generate_uuid()

    # Create 2 hosts with the same Insights ID
    for _ in range(2):
        db_create_host(extra_data={"insights_id": insights_id, "subscription_manager_id": generate_uuid()})

    url = build_host_exists_url(insights_id)
    response_status, _ = api_get(url)

    assert response_status == 409


@pytest.mark.parametrize("invalid_system_type", ("invalid_type", ""))
def test_system_type_filter_invalid_types(api_get, invalid_system_type):
    url = build_hosts_url(query=f"?system_type={invalid_system_type}")
    response_status, _ = api_get(url)

    assert response_status == 400
