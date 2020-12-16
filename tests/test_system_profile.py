import pytest

from lib.host_repository import find_hosts_by_staleness
from tests.helpers.api_utils import assert_error_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_system_profile_sap_sids_url
from tests.helpers.api_utils import build_system_profile_sap_system_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SIDS
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SYSTEM
from tests.helpers.test_utils import generate_uuid


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


def test_get_system_profile_sap_system_with_RBAC_allowed(
    subtests, mocker, query_source_xjoin, graphql_system_profile_sap_system_query_with_response, api_get, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    url = build_system_profile_sap_system_url()

    for response_file in READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, response_data = api_get(url, identity_type="User")

            assert_response_status(response_status, 200)


def test_get_system_profile_sap_sids_with_RBAC_allowed(
    subtests, mocker, query_source_xjoin, graphql_system_profile_sap_sids_query_with_response, api_get, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    url = build_system_profile_sap_sids_url()

    for response_file in READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, response_data = api_get(url, identity_type="User")

            assert_response_status(response_status, 200)


def test_get_system_profile_with_RBAC_denied(subtests, mocker, query_source_xjoin, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    urls = (build_system_profile_sap_system_url(), build_system_profile_sap_sids_url())

    for url in urls:
        for response_file in READ_PROHIBITED_RBAC_RESPONSE_FILES:
            mock_rbac_response = create_mock_rbac_response(response_file)
            with subtests.test():
                get_rbac_permissions_mock.return_value = mock_rbac_response

                response_status, response_data = api_get(url, identity_type="User")

                assert_response_status(response_status, 403)


# TODO: This test is valid until a system with "owner_id" is used.
def test_get_system_profile_sap_system_with_RBAC_bypassed_as_system(
    query_source_xjoin, graphql_system_profile_sap_system_query_with_response, api_get, enable_rbac
):
    url = build_system_profile_sap_system_url()

    response_status, response_data = api_get(url, identity_type="System")

    assert_response_status(response_status, 200)


# TODO: This test is valid until a system with "owner_id" is used.
def test_get_system_profile_sap_sids_with_RBAC_bypassed_as_system(
    query_source_xjoin, graphql_system_profile_sap_sids_query_with_response, api_get, enable_rbac
):
    url = build_system_profile_sap_sids_url()

    response_status, response_data = api_get(url, identity_type="System")

    assert_response_status(response_status, 200)


def test_get_system_profile_RBAC_allowed(mocker, subtests, api_get, db_create_host, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    host = db_create_host()

    for response_file in READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response
            response_status, response_data = api_get(f"{HOST_URL}/{host.id}/system_profile")

            assert_response_status(response_status, 200)


def test_get_system_profile_RBAC_denied(mocker, subtests, api_get, db_create_host, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    find_hosts_by_staleness_mock = mocker.patch(
        "lib.host_repository.find_hosts_by_staleness", wraps=find_hosts_by_staleness
    )

    host = db_create_host()

    for response_file in READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response
            response_status, response_data = api_get(f"{HOST_URL}/{host.id}/system_profile")

            assert_response_status(response_status, 403)
            find_hosts_by_staleness_mock.assert_not_called()


def test_get_system_profile_of_host_that_does_not_exist(api_get):
    expected_count = 0
    expected_total = 0
    host_id = generate_uuid()

    response_status, response_data = api_get(f"{HOST_URL}/{host_id}/system_profile")

    assert_response_status(response_status, 200)

    assert response_data["count"] == expected_count
    assert response_data["total"] == expected_total


@pytest.mark.parametrize("invalid_host_id", ["notauuid", "922680d3-4aa2-4f0e-9f39-38ab8ea318bb,notuuid"])
def test_get_system_profile_with_invalid_host_id(api_get, invalid_host_id):
    response_status, response_data = api_get(f"{HOST_URL}/{invalid_host_id}/system_profile")

    assert_error_response(response_data, expected_title="Bad Request", expected_status=400)
