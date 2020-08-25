from requests import exceptions

from tests.helpers.api_utils import build_hosts_url


def test_rbac_retry_error_handling(mocker, db_create_host, api_get, enable_rbac):
    request_session_get_mock = mocker.patch("lib.middleware.Session.get")
    request_session_get_mock.side_effect = exceptions.RetryError

    host = db_create_host()

    url = build_hosts_url(host_list_or_id=host.id)

    mock_rbac_failure = mocker.patch("lib.middleware.rbac_failure")
    abort_mock = mocker.patch("lib.middleware.abort")

    api_get(url, identity_type="User")

    mock_rbac_failure.assert_called_once()
    abort_mock.assert_called_once()


def test_rbac_exception_handling(mocker, db_create_host, api_get, enable_rbac):
    request_session_get_mock = mocker.patch("lib.middleware.Session.get")
    request_session_get_mock.side_effect = Exception()

    host = db_create_host()

    url = build_hosts_url(host_list_or_id=host.id)

    mock_rbac_failure = mocker.patch("lib.middleware.rbac_failure")
    abort_mock = mocker.patch("lib.middleware.abort")

    api_get(url, identity_type="User")

    abort_mock.assert_called_once()
    mock_rbac_failure.assert_called_once()
