import pytest

from tests.helpers.api_utils import do_request
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import USER_IDENTITY


@pytest.fixture(scope="function")
def flask_client(flask_app):
    return flask_app.test_client()


@pytest.fixture(scope="function")
def api_post(flask_client):
    def _api_post(url, host_data, query_parameters=None, extra_headers=None, auth_type=USER_IDENTITY['auth_type'], identity_type=USER_IDENTITY["type"]):
        return do_request(
            flask_client.post, url, host_data, query_parameters, extra_headers, auth_type=auth_type, identity_type=identity_type
        )

    return _api_post


@pytest.fixture(scope="function")
def api_patch(flask_client):
    def _api_patch(url, host_data, query_parameters=None, extra_headers=None, auth_type=USER_IDENTITY['auth_type'], identity_type=USER_IDENTITY["type"]):
        return do_request(
            flask_client.patch, url, host_data, query_parameters, extra_headers, auth_type=auth_type, identity_type=identity_type
        )

    return _api_patch


@pytest.fixture(scope="function")
def api_put(flask_client):
    def _api_put(url, host_data, query_parameters=None, extra_headers=None, auth_type=USER_IDENTITY['auth_type'], identity_type=USER_IDENTITY['type']):
        return do_request(
            flask_client.put, url, host_data, query_parameters, extra_headers, auth_type=auth_type, identity_type=identity_type
        )

    return _api_put


@pytest.fixture(scope="function")
def api_get(flask_client):
    def _api_get(url, query_parameters=None, extra_headers=None, auth_type=USER_IDENTITY['auth_type'], identity_type=USER_IDENTITY["type"]):
        return do_request(
            flask_client.get,
            url,
            query_parameters=query_parameters,
            extra_headers=extra_headers,
            auth_type=auth_type,
            identity_type=identity_type,
        )

    return _api_get


@pytest.fixture(scope="function")
def api_delete_host(flask_client):
    def _api_delete_host(host_id, query_parameters=None, extra_headers=None, auth_type=USER_IDENTITY['auth_type'], identity_type=USER_IDENTITY["type"]):
        url = f"{HOST_URL}/{host_id}"
        return do_request(
            flask_client.delete,
            url,
            query_parameters=query_parameters,
            extra_headers=extra_headers,
            auth_type=auth_type,
            identity_type=identity_type,
        )

    return _api_delete_host


@pytest.fixture(scope="function")
def disable_rest_api_post(inventory_config):
    inventory_config.rest_post_enabled = False


@pytest.fixture(scope="function")
def enable_rbac(inventory_config):
    inventory_config.rbac_enforced = True
