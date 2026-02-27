"""Smoke test to verify the integration test setup works."""

import logging

from integration_tests.utils.app import TestApp

logger = logging.getLogger(__name__)


def test_hosts_status_code(test_app: TestApp) -> None:
    response = test_app.hbi_api.get_host_list_response()
    assert response.status_code == 200


def test_create_host(test_app: TestApp) -> None:
    host_data = test_app.uploader.create_host()
    response_hosts = test_app.hbi_api.get_host_list(fqdn=host_data.fqdn)
    assert len(response_hosts) == 1
