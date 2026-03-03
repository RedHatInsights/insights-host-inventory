# mypy: disallow-untyped-defs
from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.datagen_utils import generate_canonical_facts
from iqe_host_inventory.utils.datagen_utils import generate_uuid

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def _assert_canonical_fact_equals(
    fact_name: str, api_value: object, expected_value: object
) -> None:
    """
    Assert that a canonical fact value from the API matches the expected value.

    Handles string comparison (case-insensitive due to lowercasing) and
    list comparison for ip_addresses/mac_addresses.
    """
    if expected_value is None:
        return

    assert api_value is not None, f"Canonical fact {fact_name} should be present in API response"

    if isinstance(expected_value, str) and isinstance(api_value, str):
        # String facts are lowercased by the API
        assert api_value.lower() == expected_value.lower(), (
            f"Canonical fact {fact_name} mismatch: expected {expected_value}, got {api_value}"
        )
    elif isinstance(expected_value, list) and isinstance(api_value, list):
        # List facts (ip_addresses, mac_addresses) - compare as sets of lowercased values
        expected_set = {str(v).lower() for v in expected_value}
        api_set = {str(v).lower() for v in api_value}
        assert api_set == expected_set, (
            f"Canonical fact {fact_name} mismatch: expected {expected_value}, got {api_value}"
        )
    else:
        # Other types - direct comparison
        assert api_value == expected_value, (
            f"Canonical fact {fact_name} mismatch: expected {expected_value}, got {api_value}"
        )


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_all_canonical_facts_in_api_response(host_inventory: ApplicationHostInventory) -> None:
    """
    Test that all canonical facts are correctly returned in API responses.

    This test creates a host with all canonical facts populated and verifies
    that the API response includes all of them together.

    JIRA: https://issues.redhat.com/browse/RHINENG-19460

    metadata:
        requirements: inv-canonical-facts-columns
        assignee: rantunes
        importance: critical
        title: Test all canonical facts are in API response
    """
    # Generate all canonical facts
    canonical_facts = generate_canonical_facts()

    # Create host with all canonical facts
    host_data = host_inventory.datagen.create_host_data(**canonical_facts)
    created_host = host_inventory.kafka.create_host(host_data=host_data)

    # Fetch host via API
    response_host = host_inventory.apis.hosts.get_host_by_id(created_host.id)

    # Verify all canonical facts are present and match expected values
    # Derive fact names from generated canonical_facts to automatically cover new facts
    for fact_name, expected_value in canonical_facts.items():
        api_value = getattr(response_host, fact_name)
        _assert_canonical_fact_equals(fact_name, api_value, expected_value)


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_canonical_facts_preserved_on_host_update(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test that canonical facts are preserved when updating a host.

    This test verifies that when updating a host with new data, existing
    canonical facts are not overwritten if not provided in the update.

    JIRA: https://issues.redhat.com/browse/RHINENG-19460

    metadata:
        requirements: inv-canonical-facts-columns
        assignee: rantunes
        importance: high
        title: Test canonical facts are preserved on host update
    """
    # Create host with satellite_id and bios_uuid
    satellite_id = generate_uuid()
    bios_uuid = generate_uuid()
    host_data = host_inventory.datagen.create_host_data(
        satellite_id=satellite_id,
        bios_uuid=bios_uuid,
    )
    created_host = host_inventory.kafka.create_host(host_data=host_data)

    # Update host with only a new display_name (no canonical facts in update)
    update_data = dict(host_data)
    update_data["display_name"] = "updated-display-name"
    # Remove canonical facts that we want to verify are preserved
    update_data.pop("satellite_id", None)
    update_data.pop("bios_uuid", None)

    updated_host = host_inventory.kafka.create_host(host_data=update_data)

    # Verify the host was updated (same ID)
    assert str(updated_host.id) == str(created_host.id)

    # Fetch via API and verify canonical facts are preserved
    response_host = host_inventory.apis.hosts.get_host_by_id(updated_host.id)

    # satellite_id and bios_uuid should still be present
    assert response_host.satellite_id is not None
    assert response_host.bios_uuid is not None
    assert response_host.satellite_id == satellite_id
    assert response_host.bios_uuid == bios_uuid


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_host_creation_with_minimal_canonical_facts(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test that hosts can be created with only one ID fact.

    This test verifies that the canonical facts column architecture works
    correctly when only one ID fact is provided (minimum requirement).

    JIRA: https://issues.redhat.com/browse/RHINENG-19460

    metadata:
        requirements: inv-canonical-facts-columns
        assignee: rantunes
        importance: high
        title: Test host creation with minimal canonical facts
    """
    # Create host with only subscription_manager_id (one ID fact is enough)
    subscription_manager_id = generate_uuid()
    host_data = host_inventory.datagen.create_minimal_host_data(
        subscription_manager_id=subscription_manager_id
    )

    created_host = host_inventory.kafka.create_host(
        host_data=host_data,
        field_to_match=HostWrapper.subscription_manager_id,
    )

    # Verify host was created and subscription_manager_id is correct
    response_host = host_inventory.apis.hosts.get_host_by_id(created_host.id)
    assert response_host.subscription_manager_id is not None
    assert response_host.subscription_manager_id == subscription_manager_id


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_canonical_facts_in_hosts_list_response(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test that canonical facts are included in GET /hosts list response.

    This test verifies that when fetching multiple hosts via the list endpoint,
    each host includes all its canonical facts with correct values.

    JIRA: https://issues.redhat.com/browse/RHINENG-19460

    metadata:
        requirements: inv-canonical-facts-columns
        assignee: rantunes
        importance: high
        title: Test canonical facts in hosts list API response
    """
    # Create host with all canonical facts
    canonical_facts = generate_canonical_facts()
    host_data = host_inventory.datagen.create_host_data(**canonical_facts)
    created_host = host_inventory.kafka.create_host(host_data=host_data)

    # Fetch hosts list
    response_hosts = host_inventory.apis.hosts.get_hosts(
        insights_id=canonical_facts["insights_id"]
    )

    assert len(response_hosts) == 1
    response_host = response_hosts[0]

    # Verify the returned host is the one we created
    assert str(response_host.id) == str(created_host.id)

    # Verify all canonical facts match the original data
    for fact_name, expected_value in canonical_facts.items():
        api_value = getattr(response_host, fact_name)
        _assert_canonical_fact_equals(fact_name, api_value, expected_value)
