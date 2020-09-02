import pytest

from tests.helpers.api_utils import do_request
from tests.helpers.api_utils import HOST_URL


@pytest.fixture(scope="function")
def flask_client(flask_app):
    return flask_app.test_client()


@pytest.fixture(scope="function")
def api_create_or_update_host(flask_client):
    def _api_create_or_update_host(
        host_data, query_parameters=None, extra_headers=None, auth_type="account_number", identity_type="User"
    ):
        data = [item.data() for item in host_data]
        return do_request(flask_client.post, HOST_URL, data, query_parameters, extra_headers, auth_type, identity_type)

    return _api_create_or_update_host


@pytest.fixture(scope="function")
def api_patch(flask_client):
    def _api_patch(url, host_data, query_parameters=None, extra_headers=None, identity_type="User"):
        return do_request(
            flask_client.patch, url, host_data, query_parameters, extra_headers, identity_type=identity_type
        )

    return _api_patch


@pytest.fixture(scope="function")
def api_put(flask_client):
    def _api_put(url, host_data, query_parameters=None, extra_headers=None, identity_type="User"):
        return do_request(
            flask_client.put, url, host_data, query_parameters, extra_headers, identity_type=identity_type
        )

    return _api_put


@pytest.fixture(scope="function")
def api_get(flask_client):
    def _api_get(url, query_parameters=None, extra_headers=None, identity_type="User"):
        return do_request(
            flask_client.get,
            url,
            query_parameters=query_parameters,
            extra_headers=extra_headers,
            identity_type=identity_type,
        )

    return _api_get


@pytest.fixture(scope="function")
def api_delete_host(flask_client):
    def _api_delete_host(host_id, query_parameters=None, extra_headers=None, identity_type="User"):
        url = f"{HOST_URL}/{host_id}"
        return do_request(
            flask_client.delete,
            url,
            query_parameters=query_parameters,
            extra_headers=extra_headers,
            identity_type=identity_type,
        )

    return _api_delete_host


@pytest.fixture(scope="function")
def disable_rest_api_post(inventory_config):
    inventory_config.rest_post_enabled = False


@pytest.fixture(scope="function")
def enable_rbac(inventory_config):
    inventory_config.rbac_enforced = True
