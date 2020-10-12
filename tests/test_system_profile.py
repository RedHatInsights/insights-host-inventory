from tests.helpers.api_utils import build_system_profile_sap_sids_url
from tests.helpers.api_utils import build_system_profile_sap_system_url
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SIDS
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SYSTEM


def test_system_profile_sap_system_endpoint_response(
    mocker, query_source_xjoin, graphql_system_profile_sap_system_query_with_response, api_get
):
    url = build_system_profile_sap_system_url()

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == XJOIN_SYSTEM_PROFILE_SAP_SYSTEM["hostSystemProfile"]["sap_system"]["data"]
    assert (
        response_data["total"] == XJOIN_SYSTEM_PROFILE_SAP_SYSTEM["hostSystemProfile"]["sap_system"]["meta"]["total"]
    )
    assert (
        response_data["count"] == XJOIN_SYSTEM_PROFILE_SAP_SYSTEM["hostSystemProfile"]["sap_system"]["meta"]["count"]
    )


def test_system_profile_sap_sids_endpoint_response(
    mocker, query_source_xjoin, graphql_system_profile_sap_sids_query_with_response, api_get
):
    url = build_system_profile_sap_sids_url()

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == XJOIN_SYSTEM_PROFILE_SAP_SIDS["hostSystemProfile"]["sap_sids"]["data"]
    assert response_data["total"] == XJOIN_SYSTEM_PROFILE_SAP_SIDS["hostSystemProfile"]["sap_sids"]["meta"]["total"]
    assert response_data["count"] == XJOIN_SYSTEM_PROFILE_SAP_SIDS["hostSystemProfile"]["sap_sids"]["meta"]["count"]
