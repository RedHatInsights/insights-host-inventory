import pytest

from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import RBACFilterOperation
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_exists_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import create_custom_rbac_response
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid


@pytest.mark.usefixtures("enable_rbac")
def test_get_hosts_with_RBAC_allowed(subtests, mocker, db_create_host, api_get):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_hosts_url(host_list_or_id=host.id)
            response_status, _ = api_get(url)

            assert_response_status(response_status, 200)


@pytest.mark.usefixtures("enable_rbac")
def test_get_hosts_with_RBAC_denied(subtests, mocker, db_create_host, api_get):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    get_host_list_mock = mocker.patch("api.host.get_host_list_by_id_list")

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_hosts_url(host_list_or_id=host.id)
            response_status, _ = api_get(url)

            assert_response_status(response_status, 403)

            get_host_list_mock.assert_not_called()


def test_get_hosts_with_RBAC_bypassed_as_system(db_create_host, api_get):
    host = db_create_host(
        SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}}
    )

    url = build_hosts_url(host_list_or_id=host.id)
    response_status, _ = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


@pytest.mark.usefixtures("enable_rbac")
@pytest.mark.parametrize("rbac_operation", [RBACFilterOperation.EQUAL, RBACFilterOperation.IN])
def test_get_host_exists_granular_rbac(
    db_create_host, db_create_group, db_create_host_group_assoc, api_get, mocker, rbac_operation
):
    # Create 3 hosts with unique insights IDs that the user has access to
    accessible_group_id = db_create_group("accessible_group").id
    accessible_insights_id_list = [generate_uuid() for _ in range(3)]
    accessible_host_id_list = [
        db_create_host(extra_data={"insights_id": insights_id}).id for insights_id in accessible_insights_id_list
    ]
    for host_id in accessible_host_id_list:
        db_create_host_group_assoc(host_id, accessible_group_id)

    # Create 2 hosts with unique insights IDs that the user does not have access to
    inaccessible_group_id = db_create_group("inaccessible_group").id
    inaccessible_insights_id_list = [generate_uuid() for _ in range(2)]
    inaccessible_host_id_list = [
        db_create_host(extra_data={"insights_id": insights_id}).id for insights_id in inaccessible_insights_id_list
    ]
    for host_id in inaccessible_host_id_list:
        db_create_host_group_assoc(host_id, inaccessible_group_id)

    # Grant access to first group
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    get_rbac_permissions_mock.return_value = create_custom_rbac_response([str(accessible_group_id)], rbac_operation)

    # Verify that the user can see each of the hosts in the "accessible" group
    for insights_id in accessible_insights_id_list:
        url = build_host_exists_url(insights_id)
        response_status, _ = api_get(url)
        assert_response_status(response_status, 200)

    # Verify that the user can NOT see the hosts in the "inaccessible" group
    for insights_id in inaccessible_insights_id_list:
        url = build_host_exists_url(insights_id)
        response_status, _ = api_get(url)
        assert_response_status(response_status, 404)
