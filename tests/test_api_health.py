import tempfile

from tests.helpers.api_utils import HEALTH_URL
from tests.helpers.api_utils import METRICS_URL
from tests.helpers.api_utils import VERSION_URL
from tests.helpers.test_utils import set_environment


def test_health(flask_client):
    """
    The health check simply returns 200 to any GET request. The response body is
    irrelevant.
    """
    response = flask_client.get(HEALTH_URL)
    assert 200 == response.status_code


def test_metrics(flask_client):
    """
    The metrics endpoint simply returns 200 to any GET request.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        with set_environment({"prometheus_multiproc_dir": temp_dir}):
            response = flask_client.get(METRICS_URL)  # No identity header.
            assert 200 == response.status_code


def test_version(api_get):
    response_status, response_data = api_get(VERSION_URL)
    assert response_data["version"] is not None
