import pytest

from tests.helpers.api_utils import do_request
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import MockUserIdentity
from tests.helpers.test_utils import USER_IDENTITY


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
        kafka_patch("lib.host_delete.kafka_available")
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
def enable_rbac(inventory_config):
    inventory_config.bypass_rbac = False


@pytest.fixture(scope="function")
def user_identity_mock(flask_app):
    flask_app.user_identity = MockUserIdentity()
    yield flask_app.user_identity
    # flask_app.user_identity = None


def kafka_patch(mocker):
    def _kafka_patch(method):
        return mocker.patch(method, return_value=True)

    return _kafka_patch


@pytest.fixture(scope="function")
def patch_kafka_available():
    def _patch_kafka_available(method):
        kafka_patch(method)

    return _patch_kafka_available
