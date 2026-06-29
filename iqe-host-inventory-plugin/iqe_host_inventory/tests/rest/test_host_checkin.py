# mypy: disallow-untyped-defs

from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_host_checkin_via_base_api_wrapper(host_inventory: ApplicationHostInventory) -> None:
    """POST /api/inventory/v1/hosts/checkin via BaseAPIWrapper (no apigen).

    Creates a host via Kafka, then checks it in using the new
    ``host_checkin_response`` method which calls the endpoint directly
    through ``app.http_client`` instead of the apigen layer.

    This is the POC test for RHINENG-26236: it proves that BaseAPIWrapper
    can make authenticated V1 write calls without any generated code.

    metadata:
        requirements: inv-host-checkin
        assignee: aarif
        importance: medium
        title: Check in a host via BaseAPIWrapper (POST /hosts/checkin)
    """
    host = host_inventory.kafka.create_host()

    response = host_inventory.apis.hosts.host_checkin_response(
        insights_id=host.insights_id,
    )

    assert response["id"] == host.id
    assert response["insights_id"] == host.insights_id
    logger.info("host_checkin_response returned host id=%s", response["id"])


@pytest.mark.ephemeral
def test_host_checkin_with_frequency(host_inventory: ApplicationHostInventory) -> None:
    """POST /hosts/checkin with explicit checkin_frequency via BaseAPIWrapper.

    metadata:
        requirements: inv-host-checkin
        assignee: aarif
        importance: medium
        title: Check in a host with a custom checkin_frequency via BaseAPIWrapper
    """
    host = host_inventory.kafka.create_host()

    response = host_inventory.apis.hosts.host_checkin_response(
        insights_id=host.insights_id,
        checkin_frequency=60,
    )

    assert response["id"] == host.id
    assert response["insights_id"] == host.insights_id


@pytest.mark.ephemeral
def test_host_checkin_missing_canonical_facts(host_inventory: ApplicationHostInventory) -> None:
    """Verify that host_checkin_response raises ValueError when no canonical facts given.

    metadata:
        requirements: inv-host-checkin
        assignee: aarif
        importance: low
        title: host_checkin_response rejects calls with no canonical facts
    """
    with pytest.raises(ValueError, match="At least one canonical fact must be provided"):
        host_inventory.apis.hosts.host_checkin_response()
