#!/usr/bin/env python
from tempfile import TemporaryDirectory
from unittest import main

from tests.test_api_utils import ApiBaseTestCase
from tests.test_utils import set_environment


HEALTH_URL = "/health"
METRICS_URL = "/metrics"
VERSION_URL = "/version"


class ManagementTestCase(ApiBaseTestCase):
    """
    Tests the health check endpoint.
    """

    def test_health(self):
        """
        The health check simply returns 200 to any GET request. The response body is
        irrelevant.
        """
        response = self.client().get(HEALTH_URL)  # No identity header.
        self.assertEqual(200, response.status_code)

    def test_metrics(self):
        """
        The metrics endpoint simply returns 200 to any GET request.
        """
        with TemporaryDirectory() as temp_dir:
            with set_environment({"prometheus_multiproc_dir": temp_dir}):
                response = self.client().get(METRICS_URL)  # No identity header.
                self.assertEqual(200, response.status_code)

    def test_version(self):
        response = self.get(VERSION_URL, 200)
        assert response["version"] is not None


if __name__ == "__main__":
    main()
