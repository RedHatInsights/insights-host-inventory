# mypy: disallow-untyped-defs

import logging

import pytest
from iqe.utils.blockers import iqe_blocker

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


@iqe_blocker(iqe_blocker.jira("RHINENG-17920", category=iqe_blocker.PRODUCT_ISSUE))
@pytest.mark.smoke
@pytest.mark.ephemeral
def test_system_profile_facts_update_single_field(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    E2E test: Kafka → Processing → Database → API for system profile facts.

    Tests the complete flow:
    1. Create a host via Kafka with complete system profile data
    2. Update a single system_profile field via Kafka
    3. Verify the update merged correctly (didn't overwrite other fields)
    4. Verify the API returns the correct merged data

    This test validates:
    - System profile creation via MQ
    - System profile updates via MQ (partial updates)
    - System profile retrieval via API
    - Field merging logic (RHINENG-17920)

    metadata:
        requirements: inv-host-create, inv-host-update, inv-hosts-get-system_profile
        assignee: fstavela
        importance: critical
        title: E2E: System Profile Facts - Create, Update, and Retrieve
    """
    host_data = host_inventory.datagen.create_complete_host_data()
    host = host_inventory.kafka.create_host(host_data)

    new_rhsm_field = {"environment_ids": [generate_uuid()]}
    expected_system_profile = dict(host_data["system_profile"])
    expected_system_profile["rhsm"].update(new_rhsm_field)
    new_display_name = generate_display_name()
    # Send only one system profile field in the update message
    host_data["system_profile"] = {"rhsm": new_rhsm_field}
    host_data["display_name"] = new_display_name
    updated_host = host_inventory.kafka.create_host(host_data)

    # The new field value should be merged with the original system profile
    assert updated_host.id == host.id
    assert updated_host.system_profile == expected_system_profile

    host_inventory.apis.hosts.wait_for_updated(updated_host, display_name=new_display_name)
    response_host = host_inventory.apis.hosts.get_host_system_profile(updated_host)
    assert response_host.system_profile.rhsm.environment_ids == new_rhsm_field["environment_ids"]
    # Check that random other field wasn't overwritten
    assert (
        response_host.system_profile.insights_client_version
        == expected_system_profile["insights_client_version"]
    )
