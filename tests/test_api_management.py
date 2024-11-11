from tempfile import TemporaryDirectory

from tests.helpers.test_utils import set_environment

HEALTH_URL = "/health"
METRICS_URL = "/metrics"
VERSION_URL = "/version"


def test_health(flask_client):
    """
    The health check simply returns 200 to any GET request. The response body is
    irrelevant.
    """
    response = flask_client.get(HEALTH_URL)  # No identity header.
    assert response.status_code == 200


def test_metrics(flask_client):
    """
    The metrics endpoint simply returns 200 to any GET request.
    """
    with TemporaryDirectory() as temp_dir:
        with set_environment({"prometheus_multiproc_dir": temp_dir}):
            response = flask_client.get(METRICS_URL)  # No identity header.
            assert response.status_code == 200


def test_version(api_get):
    response_status, response_data = api_get(VERSION_URL)
    assert response_status == 200
    assert response_data["version"] is not None
