# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from datetime import datetime

import pytest

from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


def assert_checkin_response(response: dict, host: object) -> None:
    """Assert that a POST /hosts/checkin response identifies the correct host and that
    all staleness-related timestamps are strictly newer than they were before the call."""
    assert response["id"] == host.id
    assert response["insights_id"] == host.insights_id
    assert datetime.fromisoformat(response["last_check_in"]) > host.last_check_in
    assert datetime.fromisoformat(response["stale_timestamp"]) > host.stale_timestamp
    assert (
        datetime.fromisoformat(response["stale_warning_timestamp"]) > host.stale_warning_timestamp
    )
    assert datetime.fromisoformat(response["culled_timestamp"]) > host.culled_timestamp


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_host_checkin(host_inventory: ApplicationHostInventory) -> None:
    """POST /hosts/checkin updates the host's last_check_in and staleness timestamps.

    metadata:

        assignee: aarif
        importance: medium
        title: POST /hosts/checkin updates last_check_in and staleness timestamps
    """
    host = host_inventory.kafka.create_host()

    response = host_inventory.apis.hosts.host_checkin_response(
        insights_id=host.insights_id,
    )

    assert response.status_code == 201
    assert_checkin_response(response.json(), host)


@pytest.mark.ephemeral
def test_host_checkin_with_frequency(host_inventory: ApplicationHostInventory) -> None:
    """POST /hosts/checkin with an explicit checkin_frequency updates staleness timestamps.

    metadata:

        assignee: aarif
        importance: medium
        title: POST /hosts/checkin with custom checkin_frequency updates staleness timestamps
    """
    host = host_inventory.kafka.create_host()

    response = host_inventory.apis.hosts.host_checkin_response(
        insights_id=host.insights_id,
        checkin_frequency=60,
    )

    assert response.status_code == 201
    assert_checkin_response(response.json(), host)


def test_host_checkin_requires_canonical_fact(host_inventory: ApplicationHostInventory) -> None:
    """POST /hosts/checkin requires at least one canonical fact.

    metadata:

        assignee: aarif
        importance: low
        title: POST /hosts/checkin rejects requests with no canonical facts
    """
    response = host_inventory.apis.hosts.host_checkin_response()
    assert response.status_code == 400
