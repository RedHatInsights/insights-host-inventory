"""Smoke test to verify the integration test setup works."""

from integration_tests.utils.app import TestApp
from integration_tests.utils.app import create_test_app


def test_hosts_status_code(test_app: TestApp) -> None:
    # Certificate credentials are configured only on Stage; other environments
    # retain the original single-app smoke behavior and their selected auth.
    if test_app.config.current_env.lower() != "stage":
        response = test_app.hbi_api.get_host_list_response()
        assert response.status_code == 200
        return

    with create_test_app(test_app.config, auth_type="cert") as cert_app:
        response = test_app.hbi_api.get_host_list_response()
        assert response.status_code == 200
        response = cert_app.hbi_api.get_host_list_response()
        assert response.status_code == 200
        response = test_app.hbi_api.get_host_list_response()
        assert response.status_code == 200
