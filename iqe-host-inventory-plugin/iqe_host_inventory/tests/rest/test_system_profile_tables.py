import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import DYNAMIC_SYSTEM_PROFILE_FIELDS
from iqe_host_inventory.utils.datagen_utils import STATIC_SYSTEM_PROFILE_FIELDS
from iqe_host_inventory.utils.datagen_utils import generate_dynamic_profile_test_data
from iqe_host_inventory.utils.datagen_utils import generate_static_profile_test_data

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_host_lifecycle_with_system_profile_tables(host_inventory: ApplicationHostInventory):
    """
    Test complete host CRUD lifecycle with system profile tables.

    This test validates the success path for host operations with the new
    system profile table storage architecture. Ensures that static and dynamic
    fields are correctly routed to their respective tables while maintaining
    API transparency.

    JIRA: https://issues.redhat.com/browse/ESSNTL-3824

    metadata:
        requirements: inv-system-profile-tables
        assignee: fstavela
        importance: high
        title: Test host lifecycle with system profile table separation
    """
    # Generate test data with both static and dynamic fields
    static_profile_data = generate_static_profile_test_data()
    dynamic_profile_data = generate_dynamic_profile_test_data()
    mixed_profile_data = {**static_profile_data, **dynamic_profile_data}

    # Create host with mixed system profile data
    host_data = host_inventory.datagen.create_host_data(
        system_profile=mixed_profile_data, include_sp=False
    )
    created_host = host_inventory.kafka.create_host(host_data=host_data)

    # Verify host was created and system profile data is present in response
    system_profile_response = host_inventory.apis.hosts.get_host_system_profile(created_host.id)
    assert system_profile_response is not None

    # Verify API response format is unchanged - system_profile should contain all fields
    response_system_profile = system_profile_response.to_dict()["system_profile"]
    assert response_system_profile is not None

    # Verify both static and dynamic fields are present in response
    for field_name in STATIC_SYSTEM_PROFILE_FIELDS:
        if field_name in mixed_profile_data:
            assert field_name in response_system_profile

    for field_name in DYNAMIC_SYSTEM_PROFILE_FIELDS:
        if field_name in mixed_profile_data:
            assert field_name in response_system_profile

    # Test host update with mixed fields (both static and dynamic)
    update_static_data = {"arch": "updated_arch", "cpu_model": "Updated CPU Model"}
    update_dynamic_data = {
        "running_processes": ["updated_process"],
        "system_memory_bytes": 8589934592,
    }
    update_mixed_data = {**update_static_data, **update_dynamic_data}

    updated_host_data = dict(host_data, system_profile=update_mixed_data)

    updated_host = host_inventory.kafka.create_host(host_data=updated_host_data)

    assert created_host.id == updated_host.id

    # Verify updated host response includes changes
    updated_system_profile = host_inventory.apis.hosts.get_host_system_profile(updated_host.id)
    updated_system_profile = updated_system_profile.to_dict()["system_profile"]

    for field_name, expected_value in update_mixed_data.items():
        assert updated_system_profile[field_name] == expected_value

    # Test host deletion
    host_inventory.apis.hosts.delete_by_id(updated_host.id)
    host_inventory.apis.hosts.wait_for_deleted(updated_host)
