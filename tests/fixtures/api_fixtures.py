import pytest
from flask import abort

from tests.helpers.api_utils import GROUP_URL
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import STALENESS_URL
from tests.helpers.api_utils import do_request
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid


@pytest.fixture(scope="function")
def flask_client(flask_app):
    return flask_app.test_client()


@pytest.fixture(scope="function")
def api_post(flask_client):
    def _api_post(url, host_data, identity=USER_IDENTITY, query_parameters=None, extra_headers=None):
        return do_request(flask_client.post, url, identity, host_data, query_parameters, extra_headers)

    return _api_post


@pytest.fixture(scope="function")
def api_patch(flask_client):
    def _api_patch(url, host_data, identity=USER_IDENTITY, query_parameters=None, extra_headers=None):
        return do_request(flask_client.patch, url, identity, host_data, query_parameters, extra_headers)

    return _api_patch


@pytest.fixture(scope="function")
def api_put(flask_client):
    def _api_put(url, host_data, identity=USER_IDENTITY, query_parameters=None, extra_headers=None):
        return do_request(flask_client.put, url, identity, host_data, query_parameters, extra_headers)

    return _api_put


@pytest.fixture(scope="function")
def api_get(flask_client):
    def _api_get(url, identity=USER_IDENTITY, query_parameters=None, extra_headers=None):
        return do_request(
            flask_client.get, url, identity, query_parameters=query_parameters, extra_headers=extra_headers
        )

    return _api_get


@pytest.fixture(scope="function")
def api_delete_host(flask_client):
    def _api_delete_host(host_id, identity=USER_IDENTITY, query_parameters=None, extra_headers=None):
        url = f"{HOST_URL}/{host_id}"
        return do_request(
            flask_client.delete, url, identity, query_parameters=query_parameters, extra_headers=extra_headers
        )

    return _api_delete_host


@pytest.fixture(scope="function")
def api_delete_filtered_hosts(flask_client):
    def _api_delete_filtered_hosts(query_parameters, identity=USER_IDENTITY, extra_headers=None):
        return do_request(
            flask_client.delete, HOST_URL, identity, query_parameters=query_parameters, extra_headers=extra_headers
        )

    return _api_delete_filtered_hosts


@pytest.fixture(scope="function")
def api_delete_all_hosts(flask_client):
    def _api_delete_all_hosts(query_parameters, identity=USER_IDENTITY, extra_headers=None):
        url = f"{HOST_URL}/all"
        return do_request(
            flask_client.delete, url, identity, query_parameters=query_parameters, extra_headers=extra_headers
        )

    return _api_delete_all_hosts


@pytest.fixture(scope="function")
def api_create_group(flask_client, mocker):
    def _api_create_group(
        group_data,
        identity=USER_IDENTITY,
        query_parameters=None,
        extra_headers=None,
        abort_status=None,
        abort_detail=None,
    ):
        create_rbac_group_mock = mocker.patch("api.group.post_rbac_workspace")
        if abort_status:
            create_rbac_group_mock.side_effect = lambda *args, **kwargs: abort(
                abort_status, description=abort_detail or "Unexpected error"
            )
        else:
            create_rbac_group_mock.return_value = generate_uuid()

        get_rbac_ungrouped_group_mock = mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace")
        get_rbac_ungrouped_group_mock.return_value = generate_uuid()

        return do_request(flask_client.post, GROUP_URL, identity, group_data, query_parameters, extra_headers)

    return _api_create_group


@pytest.fixture(scope="function")
def api_create_group_kessel(flask_client, mocker):
    def _api_create_group_kessel(group_data, identity=USER_IDENTITY, query_parameters=None, extra_headers=None):
        get_rbac_ungrouped_group_mock = mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace")
        get_rbac_ungrouped_group_mock.return_value = generate_uuid()
        return do_request(flask_client.post, GROUP_URL, identity, group_data, query_parameters, extra_headers)

    return _api_create_group_kessel


@pytest.fixture(scope="function")
def api_delete_groups(flask_client, mocker):
    def _api_delete_group(group_id_list, identity=USER_IDENTITY, query_parameters=None, extra_headers=None):
        delete_rbac_group_mock = mocker.patch("api.group.delete_rbac_workspace")
        delete_rbac_group_mock.return_value = None
        url = f"{GROUP_URL}/{','.join([str(group_id) for group_id in group_id_list])}"
        return do_request(
            flask_client.delete, url, identity, query_parameters=query_parameters, extra_headers=extra_headers
        )

    return _api_delete_group


@pytest.fixture(scope="function")
def api_remove_hosts_from_group(flask_client):
    def _api_remove_hosts_from_group(
        group_id, host_id_list, identity=USER_IDENTITY, query_parameters=None, extra_headers=None
    ):
        url = f"{GROUP_URL}/{group_id}/hosts/{','.join([str(host_id) for host_id in host_id_list])}"
        return do_request(
            flask_client.delete, url, identity, query_parameters=query_parameters, extra_headers=extra_headers
        )

    return _api_remove_hosts_from_group


@pytest.fixture(scope="function")
def api_add_hosts_to_group(flask_client):
    def _api_add_hosts_to_group(
        group_id, host_id_list, identity=USER_IDENTITY, query_parameters=None, extra_headers=None
    ):
        url = f"{GROUP_URL}/{group_id}/hosts"
        return do_request(
            flask_client.post,
            url,
            identity,
            host_id_list,
            query_parameters=query_parameters,
            extra_headers=extra_headers,
        )

    return _api_add_hosts_to_group


@pytest.fixture(scope="function")
def api_patch_group(flask_client):
    def _api_patch_group(group_id, group_data, identity=USER_IDENTITY, query_parameters=None, extra_headers=None):
        url = f"{GROUP_URL}/{group_id}"
        return do_request(flask_client.patch, url, identity, group_data, query_parameters, extra_headers)

    return _api_patch_group


@pytest.fixture(scope="function")
def api_remove_hosts_from_diff_groups(flask_client):
    def _api_remove_hosts_from_diff_groups(
        host_id_list, identity=USER_IDENTITY, query_parameters=None, extra_headers=None
    ):
        url = f"{GROUP_URL}/hosts/{','.join([str(host_id) for host_id in host_id_list])}"
        return do_request(
            flask_client.delete, url, identity, query_parameters=query_parameters, extra_headers=extra_headers
        )

    return _api_remove_hosts_from_diff_groups


@pytest.fixture(scope="function")
def enable_rbac(inventory_config):
    inventory_config.bypass_rbac = False


@pytest.fixture(scope="function")
def enable_org_id_translation(inventory_config):
    inventory_config.bypass_tenant_translation = False


@pytest.fixture(scope="function")
def _enable_unleash(inventory_config):
    inventory_config.unleash_token = "mockUnleashTokenValue"


@pytest.fixture(scope="function")
def api_create_staleness(flask_client):
    def _api_create_staleness(staleness_data, identity=USER_IDENTITY, query_parameters=None, extra_headers=None):
        return do_request(flask_client.post, STALENESS_URL, identity, staleness_data, query_parameters, extra_headers)

    return _api_create_staleness


@pytest.fixture(scope="function")
def api_delete_staleness(flask_client):
    def _api_delete_staleness(identity=USER_IDENTITY):
        return do_request(flask_client.delete, STALENESS_URL, identity)

    return _api_delete_staleness
