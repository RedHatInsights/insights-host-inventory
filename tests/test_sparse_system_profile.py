import pytest

from api.fields_parser import custom_fields_parser
from api.system_profile_host_list import SYSTEM_PROFILE_QUERY
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.api_utils import HOST_LIST_SYSTEM_PROFILE_URL


@pytest.mark.parametrize(
    "parser_input,output",
    (
        (("fields", ["foo"], ["bar"]), [{"foo": {"bar": True}}]),
        (("fields", ["foo"], ["bar,hello"]), [{"foo": {"bar": True, "hello": True}}]),
        (("fields", ["foo"], ["bar", "hello"]), [{"foo": {"bar": True, "hello": True}}]),
        (("anything", ["profile"], ["bar,hello", "baz"]), [{"profile": {"bar": True, "hello": True, "baz": True}}]),
        (
            ("fields", ["system_profile"], ["os_version,arch,yum_repos"]),
            [{"system_profile": {"os_version": True, "arch": True, "yum_repos": True}}],
        ),
    ),
)
def test_custom_fields_parser(parser_input, output):
    root_key, response, is_deep_object = custom_fields_parser(*parser_input)
    assert root_key == parser_input[0]
    assert response == output
    assert is_deep_object is True


def test_sp_sparse_fields_xjoin_response_translation(patch_xjoin_post, query_source_xjoin, db_create_host, api_get):
    host_one, host_two = db_create_host(), db_create_host()
    host_one_id, host_two_id = str(host_one.id), str(host_two.id)

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
            "?fields[system_profile]=unknown_field",
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
        response_status, response_data = api_get(build_system_profile_url([host_one, host_two], query=query))

        assert_response_status(response_status, 200)
        assert response_data["total"] == 2
        assert response_data["count"] == 2
        assert response_data["results"][0]["system_profile"] == xjoin_post[0]["system_profile_facts"]


def test_sp_sparse_fields_xjoin_response_with_invalid_field(
    patch_xjoin_post, query_source_xjoin, db_create_host, api_get
):
    host = db_create_host()

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


def test_validate_sp_sparse_fields_invalid_requests(query_source_xjoin, api_get):
    for query in (
        "?fields[system_profile]=os_kernel_version&order_how=ASC",
        "?fields[system_profile]=os_kernel_version&order_by=modified",
        "?fields[system_profile]=os_kernel_version&order_how=display_name&order_by=NOO",
    ):
        response_status, response_data = api_get(f"{HOST_LIST_SYSTEM_PROFILE_URL}{query}")
        assert response_status == 400


@pytest.mark.parametrize(
    "variables,query",
    (
        (
            {
                "fields": ["field_1", "field_2", "field_3"],
                "limit": 50,
                "offset": 0,
                "order_by": "modified_on",
                "order_how": "DESC",
            },
            "?fields[system_profile]=field_1,field_2,field_3",
        ),
        (
            {
                "fields": ["field_1", "field_2"],
                "limit": 2,
                "offset": 0,
                "order_by": "modified_on",
                "order_how": "DESC",
            },
            "?fields[system_profile]=field_1,field_2&per_page=2",
        ),
        (
            {
                "fields": ["field_1", "field_2"],
                "limit": 1,
                "offset": 1,
                "order_by": "modified_on",
                "order_how": "DESC",
            },
            "?fields[system_profile]=field_1,field_2&per_page=1&page=2",
        ),
        (
            {
                "fields": ["field_1", "field_2"],
                "limit": 50,
                "offset": 0,
                "order_by": "display_name",
                "order_how": "ASC",
            },
            "?fields[system_profile]=field_1,field_2&order_by=display_name&order_how=ASC",
        ),
        (
            {
                "fields": ["field_1", "field_2"],
                "limit": 1,
                "offset": 1,
                "order_by": "display_name",
                "order_how": "ASC",
            },
            "?fields[system_profile]=field_1,field_2&order_by=display_name&order_how=ASC&per_page=1&page=2",
        ),
        (
            {
                "fields": ["field_1", "field_2"],
                "limit": 1,
                "offset": 1,
                "order_by": "modified_on",
                "order_how": "DESC",
            },
            "?fields[system_profile]=field_1,field_2&order_by=updated&order_how=DESC&per_page=1&page=2",
        ),
        (
            {
                "fields": ["field_1", "field_2", "field_3", "field_4"],
                "limit": 1,
                "offset": 1,
                "order_by": "display_name",
                "order_how": "ASC",
            },
            "?fields[system_profile]=field_1,field_2&order_by=display_name&order_how=ASC&per_page=1\
                &fields[system_profile]=field_3,field_4&page=2",
        ),
    ),
)
def test_sp_sparse_xjoin_query_translation(
    variables, query, mocker, query_source_xjoin, graphql_sparse_system_profile_empty_response, api_get
):
    variables["host_ids"] = [
        {"id": {"eq": "6e7b6317-0a2d-4552-a2f2-b7da0aece49d"}},
        {"id": {"eq": "22cd8e39-13bb-4d02-8316-84b850dc5136"}},
    ]

    response_status, response_data = response_status, response_data = api_get(f"{HOST_LIST_SYSTEM_PROFILE_URL}{query}")

    assert response_status == 200
    graphql_sparse_system_profile_empty_response.assert_called_once_with(SYSTEM_PROFILE_QUERY, variables, mocker.ANY)
