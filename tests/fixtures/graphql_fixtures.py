import json
from datetime import datetime
from datetime import timezone

import pytest

from api.tag import TAGS_QUERY
from tests.helpers.graphql_utils import CASEFOLDED_FIELDS
from tests.helpers.graphql_utils import EMPTY_HOSTS_RESPONSE
from tests.helpers.graphql_utils import SYSTEM_PROFILE_SAP_SIDS_EMPTY_RESPONSE
from tests.helpers.graphql_utils import SYSTEM_PROFILE_SAP_SYSTEM_EMPTY_RESPONSE
from tests.helpers.graphql_utils import TAGS_EMPTY_RESPONSE
from tests.helpers.graphql_utils import XJOIN_HOSTS_RESPONSE
from tests.helpers.graphql_utils import XJOIN_SPARSE_SYSTEM_PROFILE_EMPTY_RESPONSE
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SIDS
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SYSTEM
from tests.helpers.graphql_utils import XJOIN_TAGS_RESPONSE


@pytest.fixture(scope="function")
def graphql_query(mocker):
    def _graphql_query(return_value, func="api.host_query_xjoin.graphql_query"):
        return mocker.patch(func, return_value=return_value)

    return _graphql_query


@pytest.fixture(scope="function")
def graphql_query_empty_response(graphql_query):
    return graphql_query(return_value=EMPTY_HOSTS_RESPONSE)


@pytest.fixture(scope="function")
def graphql_query_with_response(graphql_query):
    return graphql_query(return_value=XJOIN_HOSTS_RESPONSE)


@pytest.fixture(scope="function")
def graphql_tag_query_empty_response(graphql_query):
    return graphql_query(func="api.tag.graphql_query", return_value=TAGS_EMPTY_RESPONSE)


@pytest.fixture(scope="function")
def graphql_tag_query_with_response(graphql_query):
    return graphql_query(func="api.tag.graphql_query", return_value=XJOIN_TAGS_RESPONSE)


@pytest.fixture(scope="function")
def graphql_system_profile_sap_system_query_empty_response(graphql_query):
    return graphql_query(
        func="api.system_profile.graphql_query", return_value=SYSTEM_PROFILE_SAP_SYSTEM_EMPTY_RESPONSE
    )


@pytest.fixture(scope="function")
def graphql_system_profile_sap_system_query_with_response(graphql_query):
    return graphql_query(func="api.system_profile.graphql_query", return_value=XJOIN_SYSTEM_PROFILE_SAP_SYSTEM)


@pytest.fixture(scope="function")
def graphql_system_profile_sap_sids_query_empty_response(graphql_query):
    return graphql_query(func="api.system_profile.graphql_query", return_value=SYSTEM_PROFILE_SAP_SIDS_EMPTY_RESPONSE)


@pytest.fixture(scope="function")
def graphql_system_profile_sap_sids_query_with_response(graphql_query):
    return graphql_query(func="api.system_profile.graphql_query", return_value=XJOIN_SYSTEM_PROFILE_SAP_SIDS)


@pytest.fixture(scope="function")
def graphql_sparse_system_profile_empty_response(graphql_query):
    return graphql_query(
        func="api.sparse_host_list_system_profile.graphql_query",
        return_value=XJOIN_SPARSE_SYSTEM_PROFILE_EMPTY_RESPONSE,
    )


@pytest.fixture(scope="function")
def patch_xjoin_post(mocker):
    def _patch_xjoin_post(response, status=200):
        return mocker.patch(
            "app.xjoin.post",
            **{
                "return_value.text": json.dumps(response),
                "return_value.json.return_value": response,
                "return_value.status_code": status,
            },
        )

    return _patch_xjoin_post


@pytest.fixture(scope="function")
def culling_datetime_mock(mocker):
    date = datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)
    mock = mocker.patch("app.culling.datetime", **{"now.return_value": date})
    return mock.now.return_value


@pytest.fixture(scope="function")
def filtering_datetime_mock(mocker):
    date = datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)
    mock = mocker.patch("api.filtering.filtering.datetime", **{"now.return_value": date})
    return mock.now.return_value


@pytest.fixture(scope="function")
def assert_tag_query_host_filter_single_call(mocker, api_get, graphql_tag_query_empty_response):
    def _assert_tag_query_host_filter_single_call(url, host_filter=({"OR": mocker.ANY},), filter=None, status=200):
        response_status, _ = api_get(url)

        assert response_status == status

        graphql_vars = {"order_by": "tag", "order_how": "ASC", "limit": 50, "offset": 0, "hostFilter": host_filter}

        if filter:
            graphql_vars["filter"] = filter

        graphql_tag_query_empty_response.assert_called_once_with(TAGS_QUERY, graphql_vars, mocker.ANY)

    return _assert_tag_query_host_filter_single_call


@pytest.fixture(scope="function")
def assert_tag_query_host_filter_for_field(mocker, assert_tag_query_host_filter_single_call):
    def _assert_tag_query_host_filter_for_field(url, field, matcher, value, status=200):
        return assert_tag_query_host_filter_single_call(
            url=url,
            host_filter=(
                {field: {matcher: value.casefold() if field in CASEFOLDED_FIELDS else value}},
                {"OR": mocker.ANY},
            ),
            status=status,
        )

    return _assert_tag_query_host_filter_for_field
