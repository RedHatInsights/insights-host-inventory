import logging
from datetime import datetime
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils import datetimes_equal
from iqe_host_inventory.utils.datagen_utils import DYNAMIC_SYSTEM_PROFILE_FIELDS
from iqe_host_inventory.utils.datagen_utils import STATIC_SYSTEM_PROFILE_FIELDS
from iqe_host_inventory.utils.datagen_utils import generate_dynamic_profile_test_data
from iqe_host_inventory.utils.datagen_utils import generate_static_profile_test_data

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


def _is_datetime_value(value: Any) -> bool:
    """Check if a value is a datetime or an ISO datetime string."""
    if isinstance(value, datetime):
        return True
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return False
        else:
            return True
    return False


def _assert_source_data_in_response(
    field_name: str, source_value: Any, response_value: Any
) -> None:
    """
    Assert that the source data is contained in the API response.

    For simple values, this checks equality.
    For dicts (like workloads), this recursively checks that all source keys/values
    are present in the response, allowing the response to have additional keys
    (e.g., 'sap': None).
    For datetimes, uses datetimes_equal utility to handle string vs datetime comparison.
    """
    if source_value is None:
        return

    assert response_value is not None, f"Field {field_name} should be present in API response"

    # Use hasattr to handle dict-like objects (not just pure dict instances)
    source_is_dict = hasattr(source_value, "items") and hasattr(source_value, "__getitem__")
    response_is_dict = hasattr(response_value, "items") and hasattr(response_value, "__getitem__")

    if source_is_dict and response_is_dict:
        # For dicts, recursively verify all source keys are present with matching values
        for key, expected in source_value.items():
            assert key in response_value, (
                f"Field {field_name}.{key} should be present in API response"
            )
            actual = response_value[key]
            # Recursively check nested structures
            _assert_source_data_in_response(f"{field_name}.{key}", expected, actual)
    elif _is_datetime_value(source_value) and _is_datetime_value(response_value):
        # Use existing utility for datetime comparison (handles strings and datetime objects)
        assert datetimes_equal(source_value, response_value), (
            f"Field {field_name} datetime mismatch: "
            f"expected {source_value!r}, got {response_value!r}"
        )
    else:
        # For other types, direct comparison
        assert response_value == source_value, (
            f"Field {field_name} value mismatch: expected {source_value!r}, got {response_value!r}"
        )


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


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_api_response_merges_static_and_dynamic_tables(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test that API responses correctly merge data from both static and dynamic tables.

    This test verifies that when fetching system profile via API, the response
    correctly combines fields from both system_profiles_static and system_profiles_dynamic
    tables into a unified system_profile object with correct values.

    JIRA: https://issues.redhat.com/browse/RHINENG-19460

    metadata:
        requirements: inv-system-profile-tables
        assignee: rantunes
        importance: critical
        title: Test API response merges static and dynamic system profile tables
    """
    # Generate mixed profile data with both static and dynamic fields
    static_profile_data = generate_static_profile_test_data()
    dynamic_profile_data = generate_dynamic_profile_test_data()
    mixed_profile_data = {**static_profile_data, **dynamic_profile_data}

    # Create host with mixed system profile data
    host_data = host_inventory.datagen.create_host_data(
        system_profile=mixed_profile_data, include_sp=False
    )
    created_host = host_inventory.kafka.create_host(host_data=host_data)

    # Fetch system profile via API
    system_profile_response = host_inventory.apis.hosts.get_host_system_profile(created_host.id)
    assert system_profile_response is not None

    response_system_profile = system_profile_response.to_dict()["system_profile"]

    # Verify static fields are present and values match
    for field_name in STATIC_SYSTEM_PROFILE_FIELDS:
        if field_name in mixed_profile_data:
            assert field_name in response_system_profile, (
                f"Static field {field_name} should be in API response"
            )
            _assert_source_data_in_response(
                field_name, mixed_profile_data[field_name], response_system_profile[field_name]
            )

    # Verify dynamic fields are present and values match
    for field_name in DYNAMIC_SYSTEM_PROFILE_FIELDS:
        if field_name in mixed_profile_data:
            assert field_name in response_system_profile, (
                f"Dynamic field {field_name} should be in API response"
            )
            _assert_source_data_in_response(
                field_name, mixed_profile_data[field_name], response_system_profile[field_name]
            )


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_api_response_with_only_static_fields(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test that API responses work correctly when only static fields are present.

    This test verifies the merge logic works when only the system_profiles_static
    table has data (no dynamic fields provided).

    JIRA: https://issues.redhat.com/browse/RHINENG-19460

    metadata:
        requirements: inv-system-profile-tables
        assignee: rantunes
        importance: high
        title: Test API response with only static system profile fields
    """
    # Generate only static profile data
    static_profile_data = generate_static_profile_test_data()

    # Create host with only static system profile data
    host_data = host_inventory.datagen.create_host_data(
        system_profile=static_profile_data, include_sp=False
    )
    created_host = host_inventory.kafka.create_host(host_data=host_data)

    # Fetch system profile via API
    system_profile_response = host_inventory.apis.hosts.get_host_system_profile(created_host.id)
    assert system_profile_response is not None

    response_system_profile = system_profile_response.to_dict()["system_profile"]

    # Verify static fields are present and values match
    for field_name in STATIC_SYSTEM_PROFILE_FIELDS:
        if field_name in static_profile_data:
            assert field_name in response_system_profile, (
                f"Static field {field_name} should be in API response"
            )
            _assert_source_data_in_response(
                field_name, static_profile_data[field_name], response_system_profile[field_name]
            )


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_api_response_with_only_dynamic_fields(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test that API responses work correctly when only dynamic fields are present.

    This test verifies the merge logic works when only the system_profiles_dynamic
    table has data (no static fields provided).

    JIRA: https://issues.redhat.com/browse/RHINENG-19460

    metadata:
        requirements: inv-system-profile-tables
        assignee: rantunes
        importance: high
        title: Test API response with only dynamic system profile fields
    """
    # Generate only dynamic profile data
    dynamic_profile_data = generate_dynamic_profile_test_data()

    # Create host with only dynamic system profile data
    host_data = host_inventory.datagen.create_host_data(
        system_profile=dynamic_profile_data, include_sp=False
    )
    created_host = host_inventory.kafka.create_host(host_data=host_data)

    # Fetch system profile via API
    system_profile_response = host_inventory.apis.hosts.get_host_system_profile(created_host.id)
    assert system_profile_response is not None

    response_system_profile = system_profile_response.to_dict()["system_profile"]

    # Verify dynamic fields are present and values match
    for field_name in DYNAMIC_SYSTEM_PROFILE_FIELDS:
        if field_name in dynamic_profile_data:
            assert field_name in response_system_profile, (
                f"Dynamic field {field_name} should be in API response"
            )
            _assert_source_data_in_response(
                field_name, dynamic_profile_data[field_name], response_system_profile[field_name]
            )


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_multiple_workloads_in_api_response(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test that multiple workloads are correctly returned in API responses.

    This test verifies that hosts with multiple workload types have all
    workload data correctly returned via API. This is not covered by validation
    tests which only test individual workload types.

    JIRA: https://issues.redhat.com/browse/RHINENG-19460

    metadata:
        requirements: inv-system-profile-tables
        assignee: rantunes
        importance: high
        title: Test multiple workloads are returned in API response
    """
    workloads_data = {
        "sap": {
            "sap_system": True,
            "sids": ["ABC", "XYZ"],
        },
        "ansible": {
            "controller_version": "4.5.6",
        },
        "mssql": {
            "version": "15.0.0",
        },
    }

    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["workloads"] = workloads_data

    created_host = host_inventory.kafka.create_host(host_data=host_data)

    # Fetch system profile via API
    fetched_host = host_inventory.apis.hosts.get_hosts_system_profile_response(created_host.id)

    system_profile_dict = fetched_host.results[0].system_profile.to_dict()
    assert "workloads" in system_profile_dict

    response_workloads = system_profile_dict["workloads"]

    # Verify all workloads are present and all fields match source data
    for workload_name, expected_workload in workloads_data.items():
        assert workload_name in response_workloads, (
            f"Workload {workload_name} should be present in API response"
        )

        response_workload = response_workloads[workload_name]

        # Verify each field in the expected workload is present and matches
        for field_name, expected_value in expected_workload.items():
            assert field_name in response_workload, (
                f"Field {field_name} should be present in workload {workload_name}"
            )
            assert response_workload[field_name] == expected_value, (
                f"Workload {workload_name}.{field_name} value mismatch: "
                f"expected {expected_value!r}, got {response_workload[field_name]!r}"
            )
