"""Fixtures for /beta/hosts-view and app-data filtering tests."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.datagen_utils import generate_host_app_data

logger = logging.getLogger(__name__)


@pytest.fixture
def setup_host_with_app_data(host_inventory: ApplicationHostInventory):
    """Factory fixture: create a host and produce app data for it via Kafka.

    Returns a callable(app_name, data_overrides=None) that returns the host
    once app data is confirmed available on /beta/hosts-view.
    """

    def _setup(
        app_name: str,
        data_overrides: dict[str, Any] | None = None,
    ) -> Any:
        host = host_inventory.kafka.create_host()
        logger.info("Created host %s (org_id=%s)", host.id, host.org_id)

        app_data = generate_host_app_data(app_name)
        if data_overrides:
            app_data.update(data_overrides)

        host_inventory.kafka.produce_host_app_message(
            application=app_name,
            org_id=host.org_id,
            hosts_app_data=[{"id": host.id, "data": app_data}],
        )
        logger.info("Produced %s data for host %s: %s", app_name, host.id, app_data)

        host_inventory.apis.host_views.wait_for_host_view_app_data(
            insights_id=host.insights_id,
            app_name=app_name,
        )
        return host

    return _setup


def add_app_data_to_host(
    host_inventory: ApplicationHostInventory,
    host: HostWrapper,
    app_name: str,
    data_overrides: dict[str, Any] | None = None,
):
    """Add app data to an existing host via Kafka and wait for it to appear."""
    app_data = generate_host_app_data(app_name)
    if data_overrides:
        app_data.update(data_overrides)

    host_inventory.kafka.produce_host_app_message(
        application=app_name,
        org_id=host.org_id,
        hosts_app_data=[{"id": host.id, "data": app_data}],
    )
    host_inventory.apis.host_views.wait_for_host_view_app_data(
        insights_id=host.insights_id, app_name=app_name
    )
