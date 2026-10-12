"""Smoke test to verify the integration test setup works."""

import logging

from integration_tests.utils.app import TestApp
from integration_tests.utils.app import create_test_app

logger = logging.getLogger(__name__)


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


def test_create_host(test_app: TestApp) -> None:
    host_data = test_app.uploader.create_host()
    assert host_data.insights_id == host_data.subscription_manager_id
    response_hosts = test_app.hbi_api.get_host_list(fqdn=host_data.fqdn)
    assert len(response_hosts) == 1
    assert response_hosts[0]["insights_id"] == host_data.insights_id
    assert response_hosts[0]["subscription_manager_id"] == host_data.subscription_manager_id
