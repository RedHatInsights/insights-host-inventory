from api.group_query import QUERY as GROUP_QUERY
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_groups_url
from tests.helpers.api_utils import GROUP_URL
from tests.helpers.api_utils import quote
from tests.helpers.test_utils import generate_uuid


def test_basic_group_deserialization(patch_xjoin_post, api_get):
    group_id = generate_uuid()
    query = "?name=testGroup"
    xjoin_response = [
        {
            "id": group_id,
            "name": "testGroup",
            "account": "1234567",
            "org_id": "1234567",
            "created_on": "2023-02-10T08:07:03.354307+00:00",
            "modified_on": "2023-02-10T08:07:03.354307+00:00",
        },
    ]

    patch_xjoin_post(response={"data": {"hostGroups": {"meta": {"total": 1, "count": 1}, "data": xjoin_response}}})
    response_status, response_data = api_get(build_groups_url(query=query))

    assert_response_status(response_status, 200)
    assert response_data["total"] == 1
    assert response_data["count"] == 1


def test_query_variables_group_name(mocker, graphql_query_empty_group_response, api_get):
    group_name = "neato group"

    url = build_groups_url(query=f"?name={quote(group_name)}")
    response_status, _ = api_get(url)

    assert response_status == 200

    graphql_query_empty_group_response.assert_called_once_with(
        GROUP_QUERY,
        {
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "hostFilter": ({"group": {"name": {"eq": f"{group_name}"}}},),
        },
        mocker.ANY,
    )


def test_single_group_id_filter(mocker, graphql_query_empty_group_response, api_get):
    group_id = generate_uuid()

    url = build_groups_url(group_id)
    response_status, _ = api_get(url)

    assert response_status == 200

    graphql_query_empty_group_response.assert_called_once_with(
        GROUP_QUERY,
        {
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "hostFilter": ({"OR": [{"group": {"id": {"eq": f"{group_id}"}}}]},),
        },
        mocker.ANY,
    )


def test_multiple_group_id_filter(mocker, graphql_query_empty_group_response, api_get):
    group_ids = [str(generate_uuid()) for _ in range(3)]
    response_status, _ = api_get(GROUP_URL + "/" + ",".join(group_ids))

    assert response_status == 200

    graphql_query_empty_group_response.assert_called_once_with(
        GROUP_QUERY,
        {
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "hostFilter": ({"OR": [{"group": {"id": {"eq": f"{group_id}"}}} for group_id in group_ids]},),
        },
        mocker.ANY,
    )
