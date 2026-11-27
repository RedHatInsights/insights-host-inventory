# mypy: disallow-untyped-defs
from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
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
def test_host_creation_with_minimal_canonical_facts(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test that hosts can be created with only one ID fact.

    This test verifies that the canonical facts column architecture works
    correctly when only one ID fact is provided (minimum requirement).

    JIRA: https://issues.redhat.com/browse/RHINENG-19460

    metadata:
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
