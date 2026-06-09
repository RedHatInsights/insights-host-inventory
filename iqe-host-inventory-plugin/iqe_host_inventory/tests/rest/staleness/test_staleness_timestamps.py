from __future__ import annotations

import logging
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.staleness_utils import gen_staleness_settings
from iqe_host_inventory.utils.staleness_utils import validate_host_timestamps
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response

pytestmark = [pytest.mark.backend, pytest.mark.usefixtures("hbi_staleness_cleanup")]
logger = logging.getLogger(__name__)


def create_hosts_and_validate(
    host_inventory_app: ApplicationHostInventory,
    host_type: str,
    host_count: int = 1,
) -> list[HostWrapper]:
    """
    Helper function that creates hosts and verifies that each host's set
    of staleness timestamps are correct.

    :param host_inventory_app: application object
    :param host_type: "conventional" or "edge"
    :param host_count: number of hosts to create
    :return hosts: list of host objects
    """
    hosts_data = host_inventory_app.datagen.create_n_hosts_data(host_count)
    if host_type == "edge":
        for host_data in hosts_data:
            host_data["system_profile"]["host_type"] = "edge"
    hosts = host_inventory_app.kafka.create_hosts(hosts_data=hosts_data)
    assert len(hosts) == host_count

    for host in hosts:
        retrieved_host = host_inventory_app.apis.hosts.get_host_by_id(host)
        wrapper = HostWrapper(retrieved_host.to_dict())
        validate_host_timestamps(host_inventory_app, wrapper, host_type)

    return hosts


@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.ephemeral
def test_staleness_timestamps_default_settings(
    host_inventory: ApplicationHostInventory,
    host_type: str,
) -> None:
    """
    metadata:
      requirements: inv-staleness-hosts
      assignee: msager
      importance: high
      title: Validate host timestamps without custom staleness settings
    """
    response = host_inventory.apis.account_staleness.get_staleness_response()
    assert response.id.actual_instance == "system_default"

    create_hosts_and_validate(host_inventory, host_type, host_count=3)


@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.ephemeral
def test_staleness_timestamps_custom_settings(
    host_inventory: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
    host_type: str,
) -> None:
    """
    metadata:
      requirements: inv-staleness-hosts, inv-staleness-post
      assignee: msager
      importance: high
      title: Validate host timestamps with custom staleness settings
    """

    settings = gen_staleness_settings()
    logger.info(f"Creating account record with:\n{settings}")
    host_inventory.apis.account_staleness.create_staleness(**settings)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, settings)

    create_hosts_and_validate(
        host_inventory,
        host_type,
        host_count=3,
    )


@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.ephemeral
def test_staleness_timestamps_update_settings(
    host_inventory: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
    host_type: str,
) -> None:
    """
    metadata:
      requirements: inv-staleness-hosts, inv-staleness-patch
      assignee: msager
      importance: high
      title: Validate host timestamps when custom staleness settings are updated
    """

    hosts = create_hosts_and_validate(
        host_inventory,
        host_type,
        host_count=3,
    )

    settings = gen_staleness_settings()
    host_inventory.apis.account_staleness.create_staleness(**settings)
    original = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(original, hbi_staleness_defaults, settings)

    for host in hosts:
        retrieved_host = host_inventory.apis.hosts.get_host_by_id(host)
        validate_host_timestamps(host_inventory, retrieved_host, host_type)

    updated_settings = gen_staleness_settings()
    host_inventory.apis.account_staleness.update_staleness(**updated_settings)
    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, original, updated_settings)

    for host in hosts:
        retrieved_host = host_inventory.apis.hosts.get_host_by_id(host)
        validate_host_timestamps(host_inventory, retrieved_host, host_type)


@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.ephemeral
def test_staleness_timestamps_delete_settings(
    host_inventory: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
    host_type: str,
) -> None:
    """
    metadata:
      requirements: inv-staleness-hosts, inv-staleness-delete
      assignee: msager
      importance: high
      title: Validate host timestamps when custom staleness settings are reset
    """

    settings = gen_staleness_settings()
    host_inventory.apis.account_staleness.create_staleness(**settings)
    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, settings)

    hosts = create_hosts_and_validate(
        host_inventory,
        host_type,
        host_count=3,
    )

    host_inventory.apis.account_staleness.delete_staleness()
    stale_response = host_inventory.apis.account_staleness.get_staleness_response()
    assert stale_response.id.actual_instance == "system_default"

    for host in hosts:
        retrieved_host = host_inventory.apis.hosts.get_host_by_id(host)
        validate_host_timestamps(host_inventory, retrieved_host, host_type)


@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.ephemeral
def test_staleness_timestamps_custom_settings_proper_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
    hbi_staleness_secondary_cleanup: Any,
    host_type: str,
) -> None:
    """
    metadata:
      requirements: inv-staleness-hosts, inv-staleness-post
      assignee: msager
      importance: high
      title: Validate host timestamps are set on the proper account
    """

    settings = gen_staleness_settings()
    logger.info(f"Creating primary account record with:\n{settings}")
    host_inventory.apis.account_staleness.create_staleness(**settings)
    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, settings)

    settings = gen_staleness_settings()
    logger.info(f"Creating secondary account record with:\n{settings}")
    host_inventory_secondary.apis.account_staleness.create_staleness(**settings)
    response = host_inventory_secondary.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, settings)

    # Primary account
    create_hosts_and_validate(
        host_inventory,
        host_type,
        host_count=1,
    )

    # Secondary account
    create_hosts_and_validate(
        host_inventory_secondary,
        host_type,
        host_count=1,
    )


@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.ephemeral
def test_staleness_timestamps_update_settings_proper_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
    hbi_staleness_secondary_cleanup: Any,
    host_type: str,
) -> None:
    """
    metadata:
      requirements: inv-staleness-hosts, inv-staleness-patch
      assignee: msager
      importance: high
      title: Validate host timestamps are updated on the proper account
    """

    settings = gen_staleness_settings()
    logger.info(f"Creating primary account record with:\n{settings}")
    host_inventory.apis.account_staleness.create_staleness(**settings)
    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, settings)
    primary_settings = response

    settings = gen_staleness_settings()
    logger.info(f"Creating secondary account record with:\n{settings}")
    host_inventory_secondary.apis.account_staleness.create_staleness(**settings)
    response = host_inventory_secondary.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, settings)

    # Primary account
    primary_hosts = create_hosts_and_validate(
        host_inventory,
        host_type,
        host_count=3,
    )

    # Secondary account
    secondary_hosts = create_hosts_and_validate(
        host_inventory_secondary,
        host_type,
        host_count=3,
    )

    # Update the staleness settings on the primary account only
    updated_settings = gen_staleness_settings()
    host_inventory.apis.account_staleness.update_staleness(**updated_settings)
    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, primary_settings, updated_settings)

    for host in primary_hosts:
        retrieved_host = host_inventory.apis.hosts.get_host_by_id(host)
        validate_host_timestamps(host_inventory, retrieved_host, host_type)

    for host in secondary_hosts:
        retrieved_host = host_inventory_secondary.apis.hosts.get_host_by_id(host)
        validate_host_timestamps(host_inventory_secondary, retrieved_host, host_type)


@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.ephemeral
def test_staleness_timestamps_delete_settings_proper_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
    hbi_staleness_secondary_cleanup: Any,
    host_type: str,
) -> None:
    """
    metadata:
      requirements: inv-staleness-hosts, inv-staleness-delete
      assignee: msager
      importance: high
      title: Validate host timestamps are reset on the proper account
    """

    settings = gen_staleness_settings()
    logger.info(f"Creating primary account record with:\n{settings}")
    host_inventory.apis.account_staleness.create_staleness(**settings)
    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, settings)

    settings = gen_staleness_settings()
    logger.info(f"Creating secondary account record with:\n{settings}")
    host_inventory_secondary.apis.account_staleness.create_staleness(**settings)
    response = host_inventory_secondary.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, settings)

    # Primary account
    primary_hosts = create_hosts_and_validate(
        host_inventory,
        host_type,
        host_count=3,
    )

    # Secondary account
    secondary_hosts = create_hosts_and_validate(
        host_inventory_secondary,
        host_type,
        host_count=3,
    )

    # Delete the staleness settings on the primary account only
    host_inventory.apis.account_staleness.delete_staleness()
    stale_response = host_inventory.apis.account_staleness.get_staleness_response()
    assert stale_response.id.actual_instance == "system_default"

    for host in primary_hosts:
        retrieved_host = host_inventory.apis.hosts.get_host_by_id(host)
        validate_host_timestamps(host_inventory, retrieved_host, host_type)

    for host in secondary_hosts:
        retrieved_host = host_inventory_secondary.apis.hosts.get_host_by_id(host)
        validate_host_timestamps(host_inventory_secondary, retrieved_host, host_type)


@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.ephemeral
def test_staleness_timestamps_verify_payload_ignored(
    host_inventory: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
    host_type: str,
) -> None:
    """
    metadata:
      requirements: inv-staleness-hosts, inv-staleness-post
      assignee: msager
      importance: low
      title: Verify that staleness settings are used even when host payload timestamps are set
    """

    settings = gen_staleness_settings()
    logger.info(f"Creating account record with:\n{settings}")
    host_inventory.apis.account_staleness.create_staleness(**settings)
    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, settings)

    host_data = host_inventory.datagen.create_host_data(host_type=host_type)
    host_data["stale_timestamp"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    host_data["stale_warning_timestamp"] = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    host_data["culled_timestamp"] = (datetime.now(UTC) + timedelta(days=3)).isoformat()

    host = host_inventory.kafka.create_host(host_data)
    validate_host_timestamps(host_inventory, host, host_type)

    retrieved_host = host_inventory.apis.hosts.get_host_by_id(host)
    validate_host_timestamps(host_inventory, retrieved_host, host_type)
