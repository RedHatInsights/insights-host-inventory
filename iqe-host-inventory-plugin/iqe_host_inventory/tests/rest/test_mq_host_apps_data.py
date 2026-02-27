"""Integration tests for host-apps topic message consumption.

These tests simulate downstream applications (Advisor, Vulnerability, Patch, etc.)
sending messages to the platform.inventory.host-apps topic, which are consumed by
the HostAppMessageConsumer to populate the inventory read-model tables.

The /hosts-view endpoint (GET /beta/hosts-view) returns aggregated host + app data.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from iqe_host_inventory.utils.datagen_utils import generate_all_host_apps_data

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend, pytest.mark.ephemeral]


APPLICATION_TEST_DATA = [
    pytest.param(app_name, sample_data, id=app_name)
    for app_name, sample_data in generate_all_host_apps_data().items()
]


def _get_app_data_dict(app_data_obj: object) -> dict:
    """Convert an app data model object to a dict, dropping None values.

    Datetime values are converted to ISO format strings so that
    comparisons against the test data (which uses ISO strings) work directly.
    """
    if app_data_obj is None:
        return {}
    if not hasattr(app_data_obj, "to_dict"):
        return {}
    result = {}
    for k, v in app_data_obj.to_dict().items():
        if v is None:
            continue
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        result[k] = v
    return result


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

    app_data = host_inventory.apis.host_views.wait_for_host_view_app_data(
        insights_id=host.insights_id,
        app_name=app_name,
    )
    app_data_dict = _get_app_data_dict(app_data)
    logger.info(f"Retrieved {app_name} app data: {app_data_dict}")

    for key, expected_value in sample_data.items():
        actual = app_data_dict.get(key)
        assert actual is not None, (
            f"Field '{key}' missing from {app_name} app_data: {app_data_dict}"
        )
        assert str(actual) == str(expected_value), (
            f"{app_name}.{key}: expected {expected_value}, got {actual}"
        )


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
    per_host_expected: dict[str, dict] = {}
    for i, host in enumerate(hosts):
        # Create slightly different data for each host
        host_data = sample_data.copy()
        for key, value in host_data.items():
            if isinstance(value, int):
                host_data[key] = value + i
        hosts_app_data.append({"id": host.id, "data": host_data})
        per_host_expected[host.id] = host_data

    host_inventory.kafka.produce_host_app_message(
        application=app_name,
        org_id=hosts[0].org_id,
        hosts_app_data=hosts_app_data,
    )
    logger.info(f"Produced host-apps message for {app_name} with {len(hosts_app_data)} hosts")

    for host in hosts:
        app_data = host_inventory.apis.host_views.wait_for_host_view_app_data(
            insights_id=host.insights_id,
            app_name=app_name,
        )
        app_data_dict = _get_app_data_dict(app_data)
        expected = per_host_expected[host.id]

        for key, expected_value in expected.items():
            actual = app_data_dict.get(key)
            assert actual is not None, (
                f"Host {host.id}: field '{key}' missing from {app_name} app_data"
            )
            assert str(actual) == str(expected_value), (
                f"Host {host.id}: {app_name}.{key}: expected {expected_value}, got {actual}"
            )


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

    app_data = host_inventory.apis.host_views.wait_for_host_view_app_data(
        insights_id=host.insights_id,
        app_name=app_name,
    )
    app_data_dict = _get_app_data_dict(app_data)
    logger.info(f"Retrieved {app_name} app data for host {host.id}: {app_data_dict}")

    for key, expected_value in sample_data.items():
        actual = app_data_dict.get(key)
        assert actual is not None, f"Field '{key}' missing from {app_name} app_data"
        assert str(actual) == str(expected_value), (
            f"{app_name}.{key}: expected {expected_value}, got {actual}"
        )


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

    app_data = host_inventory.apis.host_views.wait_for_host_view_app_data(
        insights_id=host.insights_id,
        app_name="advisor",
    )
    app_data_dict = _get_app_data_dict(app_data)
    assert str(app_data_dict.get("recommendations")) == str(initial_data["recommendations"])
    assert str(app_data_dict.get("incidents")) == str(initial_data["incidents"])
    logger.info(f"Verified initial advisor data: {app_data_dict}")

    # Send updated advisor data
    updated_data = {"recommendations": 10, "incidents": 5}
    host_inventory.kafka.produce_host_app_message(
        application="advisor",
        org_id=host.org_id,
        hosts_app_data=[{"id": host.id, "data": updated_data}],
    )
    logger.info(f"Sent updated advisor data: {updated_data}")

    from iqe_host_inventory.utils.api_utils import accept_when

    def get_advisor_data() -> dict:
        data = host_inventory.apis.host_views.get_host_view_app_data(
            insights_id=host.insights_id,
            app_name="advisor",
        )
        return _get_app_data_dict(data)

    def data_updated(data: dict) -> bool:
        return str(data.get("recommendations")) == str(updated_data["recommendations"]) and str(
            data.get("incidents")
        ) == str(updated_data["incidents"])

    final_data = accept_when(
        get_advisor_data,
        is_valid=data_updated,
        delay=0.5,
        retries=40,
        error=Exception("Advisor data was not updated"),
    )
    logger.info(f"Verified updated advisor data: {final_data}")


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

    expected_data: dict[str, dict] = {}
    for param in APPLICATION_TEST_DATA:
        app_name = param.values[0]
        sample_data = param.values[1]

        host_inventory.kafka.produce_host_app_message(
            application=app_name,
            org_id=host.org_id,
            hosts_app_data=[{"id": host.id, "data": sample_data}],
        )
        logger.info(f"Sent {app_name} data")
        expected_data[app_name] = sample_data

    retrieved_hosts = host_inventory.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(retrieved_hosts) == 1
    assert retrieved_hosts[0].id == host.id

    last_app = APPLICATION_TEST_DATA[-1].values[0]
    host_inventory.apis.host_views.wait_for_host_view_app_data(
        insights_id=host.insights_id,
        app_name=last_app,
    )

    host_view = host_inventory.apis.host_views.get_host_view(
        insights_id=host.insights_id,
    )
    assert host_view.app_data is not None, "app_data should not be None"

    for app_name, sample_data in expected_data.items():
        app_obj = getattr(host_view.app_data, app_name, None)
        assert app_obj is not None, f"{app_name} data should be present in app_data"
        app_data_dict = _get_app_data_dict(app_obj)
        logger.info(f"Verifying {app_name}: {app_data_dict}")

        for key, expected_value in sample_data.items():
            actual = app_data_dict.get(key)
            assert actual is not None, (
                f"Field '{key}' missing from {app_name} app_data: {app_data_dict}"
            )
            assert str(actual) == str(expected_value), (
                f"{app_name}.{key}: expected {expected_value}, got {actual}"
            )
