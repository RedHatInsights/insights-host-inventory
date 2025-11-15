import logging
from urllib.parse import urljoin

import pytest
from iqe.utils.blockers import iqe_blocker

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


@pytest.fixture(scope="session")
def metrics_url(application):
    inventory_conf = (
        application.host_inventory.config.get("service_objects").get("api").get("config")
    )
    base = f"{inventory_conf.get('scheme')}://{inventory_conf.get('hostname')}:9000"
    url = urljoin(base, "metrics")
    return url


@iqe_blocker(iqe_blocker.jira("RHINENG-11724", category=iqe_blocker.AUTOMATION_ISSUE))
@pytest.mark.ephemeral
def test_prometheus_access(application, metrics_url):
    """
    Check that we can access prometheus metrics on /metrics endpoint

    https://issues.redhat.com/browse/ESSNTL-4100
    https://issues.redhat.com/browse/RHINENG-11169

    metadata:
        requirements: inv-metrics
        assignee: fstavela
        importance: high
        title: Test prometheus metrics access - GET /metrics
    """
    logger.info(f"Trying to access metrics on {metrics_url}")
    response = application.http_client.get(metrics_url)
    assert response.status_code == 200
    assert "inventory_request_processing_seconds_count" in response.text
    assert 'inventory_outbound_http_response_time_seconds_sum{dependency="xjoin"}' in response.text
    assert 'inventory_outbound_http_response_time_seconds_sum{dependency="rbac"}' in response.text
