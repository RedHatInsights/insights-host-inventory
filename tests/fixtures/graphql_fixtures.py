import json
from datetime import datetime
from datetime import timezone

import pytest

from app.config import BulkQuerySource
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
