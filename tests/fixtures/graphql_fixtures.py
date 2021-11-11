import json
from datetime import datetime
from datetime import timezone

import pytest

from api.tag import TAGS_QUERY
from app.config import BulkQuerySource
from tests.helpers.graphql_utils import CASEFOLDED_FIELDS
from tests.helpers.graphql_utils import EMPTY_HOSTS_RESPONSE
from tests.helpers.graphql_utils import SYSTEM_PROFILE_SAP_SIDS_EMPTY_RESPONSE
from tests.helpers.graphql_utils import SYSTEM_PROFILE_SAP_SYSTEM_EMPTY_RESPONSE
from tests.helpers.graphql_utils import TAGS_EMPTY_RESPONSE
from tests.helpers.graphql_utils import XJOIN_HOSTS_RESPONSE
from tests.helpers.graphql_utils import XJOIN_HOSTS_RESPONSE_FOR_FILTERING
from tests.helpers.graphql_utils import XJOIN_SPARSE_SYSTEM_PROFILE_EMPTY_RESPONSE
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SIDS
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SYSTEM
from tests.helpers.graphql_utils import XJOIN_TAGS_RESPONSE

# from tests.helpers.graphql_utils import XJOIN_HOST_IDS_RESPONSE


@pytest.fixture(scope="function")
def graphql_query(mocker):
    def _graphql_query(return_value, func="api.host_query_xjoin.graphql_query"):
        return mocker.patch(func, return_value=return_value)

    return _graphql_query


@pytest.fixture(scope="function")
def graphql_query_empty_response(graphql_query):
    return graphql_query(return_value=EMPTY_HOSTS_RESPONSE)


# TODO: check if this response works.
@pytest.fixture(scope="function")
def graphql_query_host_id_response(graphql_query):
    # return graphql_query(return_value=XJOIN_HOST_IDS_RESPONSE)
    return graphql_query(return_value=XJOIN_HOSTS_RESPONSE_FOR_FILTERING)


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
def patch_xjoin_post(mocker, query_source_xjoin):
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
def host_ids_xjoin_post(mocker, query_source_xjoin):
    def _host_ids_xjoin_post(response, status=200):
        return mocker.patch(
            "app.xjoin.post",
            **{
                "return_value.text": json.dumps(response),
                "return_value.json.return_value": response,
                "return_value.status_code": status,
            },
        )

    return _host_ids_xjoin_post


@pytest.fixture(scope="function")
def query_source_xjoin(inventory_config):
    inventory_config.bulk_query_source = BulkQuerySource.xjoin


@pytest.fixture(scope="function")
def query_source_xjoin_beta_db(inventory_config):
    inventory_config.bulk_query_source = BulkQuerySource.xjoin
    inventory_config.bulk_query_source_beta = BulkQuerySource.db


@pytest.fixture(scope="function")
def query_source_db_beta_xjoin(inventory_config):
    inventory_config.bulk_query_source = BulkQuerySource.db
    inventory_config.bulk_query_source_beta = BulkQuerySource.xjoin


@pytest.fixture(scope="function")
def culling_datetime_mock(mocker):
    date = datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)
    mock = mocker.patch("app.culling.datetime", **{"now.return_value": date})
    return mock.now.return_value


@pytest.fixture(scope="function")
def assert_tag_query_host_filter_single_call(mocker, api_get, graphql_tag_query_empty_response, query_source_xjoin):
    def _assert_tag_query_host_filter_single_call(url, host_filter={"OR": mocker.ANY}, filter=None, status=200):
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
            host_filter={
                "AND": ({field: {matcher: value.casefold() if field in CASEFOLDED_FIELDS else value}},),
                "OR": mocker.ANY,
            },
            status=status,
        )

    return _assert_tag_query_host_filter_for_field
