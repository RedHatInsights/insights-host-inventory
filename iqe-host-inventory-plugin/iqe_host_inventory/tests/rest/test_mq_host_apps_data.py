"""Integration tests for host-apps topic message consumption.

These tests simulate downstream applications (Advisor, Vulnerability, Patch, etc.)
sending messages to the platform.inventory.host-apps topic, which are consumed by
the HostAppMessageConsumer to populate the inventory read-model tables.

Note: The /hosts-view endpoint currently returns HTTP 501 (Not Implemented).
These tests are designed to work once the endpoint is fully implemented.
"""

from __future__ import annotations

import logging
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend, pytest.mark.ephemeral]


APPLICATION_TEST_DATA = [
    pytest.param(
        "advisor",
        {"recommendations": 5, "incidents": 2},
        id="advisor",
    ),
    pytest.param(
        "vulnerability",
        {
            "total_cves": 50,
            "critical_cves": 5,
            "high_severity_cves": 10,
            "cves_with_security_rules": 8,
            "cves_with_known_exploits": 3,
        },
        id="vulnerability",
    ),
    pytest.param(
        "patch",
        {
            "installable_advisories": 15,
            "template": "baseline-template",
            "rhsm_locked_version": "9.4",
        },
        id="patch",
    ),
    pytest.param(
        "remediations",
        {"remediations_plans": 7},
        id="remediations",
    ),
    pytest.param(
        "compliance",
        {"policies": 3, "last_scan": datetime.now(UTC).isoformat()},
        id="compliance",
    ),
    pytest.param(
        "malware",
        {"last_status": "clean", "last_matches": 0, "last_scan": datetime.now(UTC).isoformat()},
        id="malware",
    ),
    pytest.param(
        "image_builder",
        {"image_name": "rhel-9-base", "image_status": "active"},
        id="image_builder",
    ),
]


@pytest.mark.parametrize("app_name,sample_data", APPLICATION_TEST_DATA)
def test_produce_host_app_message_for_single_host(
    host_inventory: ApplicationHostInventory,
    app_name: str,
    sample_data: dict,
):
    """
    Test producing a host-apps message for a single host.

    1. Creates a host via the host-ingress topic
    2. Produces a host-apps message for that host
    3. Verify the data via the /hosts-view endpoint

    metadata:
        requirements: inv-host-create, inv-host-apps-topic
        assignee: rantunes
        importance: high
        title: Test producing host-apps message for single host
    """
    host = host_inventory.kafka.create_host()
    logger.info(f"Created host with ID: {host.id}, org_id: {host.org_id}")

    hosts_app_data = [{"id": host.id, "data": sample_data}]
    host_inventory.kafka.produce_host_app_message(
        application=app_name,
        org_id=host.org_id,
        hosts_app_data=hosts_app_data,
    )
    logger.info(f"Produced host-apps message for {app_name}: {hosts_app_data}")

    # TODO: Once /hosts-view is implemented, verify the data via API


@pytest.mark.parametrize("app_name,sample_data", APPLICATION_TEST_DATA)
def test_produce_host_app_message_for_multiple_hosts(
    host_inventory: ApplicationHostInventory,
    app_name: str,
    sample_data: dict,
):
    """
    Test producing a host-apps message containing multiple hosts.

    1. Creates multiple hosts via the host-ingress topic
    2. Produces a single host-apps message with data for all hosts
    3. Verify the data via the /hosts-view endpoint

    metadata:
        requirements: inv-host-create, inv-host-apps-topic
        assignee: rantunes
        importance: high
        title: Test producing host-apps message for multiple hosts
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data)
    logger.info(f"Created {len(hosts)} hosts")

    hosts_app_data = []
    for i, host in enumerate(hosts):
        # Create slightly different data for each host
        host_data = sample_data.copy()
        for key, value in host_data.items():
            if isinstance(value, int):
                host_data[key] = value + i
        hosts_app_data.append({"id": host.id, "data": host_data})

    host_inventory.kafka.produce_host_app_message(
        application=app_name,
        org_id=hosts[0].org_id,
        hosts_app_data=hosts_app_data,
    )
    logger.info(f"Produced host-apps message for {app_name} with {len(hosts_app_data)} hosts")

    # TODO: Once /hosts-view is implemented, verify the data via API


@pytest.mark.parametrize("app_name,sample_data", APPLICATION_TEST_DATA)
def test_create_host_then_send_app_data(
    host_inventory: ApplicationHostInventory,
    app_name: str,
    sample_data: dict,
):
    """
    Test the full flow from host creation to sending application data.

    1. A host is registered via the ingress topic
    2. HBI creates the host and produces an event to the events topic
    3. The application consumes the event and sends its data to the host-apps topic
    4. HBI consumes the host-apps message and stores the data
    5. The application data is available via the /hosts-view endpoint

    metadata:
        requirements: inv-host-apps-topic, inv-host-create
        assignee: rantunes
        importance: critical
        title: Test full flow from host creation to application data
    """
    host_data = host_inventory.datagen.create_host_data()
    event_messages = host_inventory.kafka.create_host_events([host_data])
    assert len(event_messages) == 1

    event_message = event_messages[0]
    assert event_message.value.get("type") == "created"

    host = event_message.host
    logger.info(f"Created host with ID: {host.id}")

    hosts_app_data = [{"id": host.id, "data": sample_data}]
    host_inventory.kafka.produce_host_app_message(
        application=app_name,
        org_id=host.org_id,
        hosts_app_data=hosts_app_data,
    )
    logger.info(f"Sent {app_name} data for host {host.id}")

    retrieved_hosts = host_inventory.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(retrieved_hosts) == 1
    assert retrieved_hosts[0].id == host.id

    # TODO: Once /hosts-view is implemented, verify the data via API


def test_update_application_data_for_existing_host(
    host_inventory: ApplicationHostInventory,
):
    """
    Test updating advisor data for a host that already has data.

    1. A host is registered via the ingress topic
    2. HBI creates the host and produces an event to the events topic
    3. The application consumes the event and sends its data to the host-apps topic
    4. HBI consumes the host-apps message and stores the data
    5. The application data is available via the /hosts-view endpoint
    6. The application updates the data and sends it to the host-apps topic
    7. HBI consumes the host-apps message and stores the data
    8. The updated application data is available via the /hosts-view endpoint

    metadata:
        requirements: inv-host-apps-topic, inv-host-create
        assignee: rantunes
        importance: high
        title: Test updating application data for existing host
    """
    host_data = host_inventory.datagen.create_host_data()
    event_messages = host_inventory.kafka.create_host_events([host_data])
    assert len(event_messages) == 1

    event_message = event_messages[0]
    assert event_message.value.get("type") == "created"

    host = event_message.host
    logger.info(f"Created host with ID: {host.id}, org_id: {host.org_id}")

    # Send initial advisor data
    initial_data = {"recommendations": 5, "incidents": 2}
    host_inventory.kafka.produce_host_app_message(
        application="advisor",
        org_id=host.org_id,
        hosts_app_data=[{"id": host.id, "data": initial_data}],
    )
    logger.info(f"Sent initial advisor data: {initial_data}")

    # TODO: Once /hosts-view is implemented, verify the data via API

    # Send updated advisor data
    updated_data = {"recommendations": 10, "incidents": 5}
    host_inventory.kafka.produce_host_app_message(
        application="advisor",
        org_id=host.org_id,
        hosts_app_data=[{"id": host.id, "data": updated_data}],
    )
    logger.info(f"Sent updated advisor data: {updated_data}")

    # TODO: Verify via /hosts-view that the data was updated


def test_send_data_from_multiple_applications(
    host_inventory: ApplicationHostInventory,
):
    """
    Test sending data from multiple applications for the same host.
    This simulates the real-world scenario where multiple downstream services
    (Advisor, Vulnerability, Patch, etc.) all send their data for the same host.

    metadata:
        requirements: inv-host-apps-topic, inv-host-create
        assignee: rantunes
        importance: critical
        title: Test sending data from multiple applications for same host
    """
    host = host_inventory.kafka.create_host()
    logger.info(f"Created host with ID: {host.id}")

    for param in APPLICATION_TEST_DATA:
        app_name = param.values[0]
        sample_data = param.values[1]

        host_inventory.kafka.produce_host_app_message(
            application=app_name,
            org_id=host.org_id,
            hosts_app_data=[{"id": host.id, "data": sample_data}],
        )
        logger.info(f"Sent {app_name} data")

    retrieved_hosts = host_inventory.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(retrieved_hosts) == 1
    assert retrieved_hosts[0].id == host.id

    # TODO: Once /hosts-view is implemented, verify that all application
    # data is present in the response
