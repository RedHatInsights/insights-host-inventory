"""
Tests for RHINENG-21231: SAP endpoints cartesian product fix.

This module tests the fix for cartesian products that occur when rbac_filter
with groups is used along with filter/registered_with parameters in SAP endpoints.
"""

import pytest

from tests.helpers.api_utils import RBACFilterOperation
from tests.helpers.api_utils import build_system_profile_sap_sids_url
from tests.helpers.api_utils import build_system_profile_sap_system_url
from tests.helpers.api_utils import create_custom_rbac_response
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host


@pytest.mark.usefixtures("enable_rbac")
def test_sap_system_with_rbac_groups_and_filter(
    mocker,
    mq_create_or_update_host,
    api_get,
    db_create_group,
    db_create_host_group_assoc,
):
    """
    Test that get_sap_system_info does not create cartesian product when using
    rbac_filter with groups along with filter parameter.

    This test verifies the fix for RHINENG-21231 where query_filters creates
    group joins but not HostDynamicSystemProfile join, causing duplicate results.
    """
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Create a group
    group = db_create_group("test-group")
    group_id = str(group.id)

    # Create hosts with SAP system data and assign to group
    sap_hosts = []
    for sap_system_value in [True, False, True]:
        insights_id = generate_uuid()
        host = mq_create_or_update_host(
            minimal_host(
                insights_id=insights_id,
                system_profile={"workloads": {"sap": {"sap_system": sap_system_value}}},
            )
        )
        db_create_host_group_assoc(host.id, group_id)
        sap_hosts.append((host, sap_system_value))

    # Create RBAC response with group filter
    mock_rbac_response = create_custom_rbac_response(
        group_ids=[group_id],
        operation=RBACFilterOperation.IN,
        hosts_permission="read",
    )
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Call SAP system endpoint with filter parameter (e.g., staleness filter)
    url = build_system_profile_sap_system_url(query="?staleness=fresh")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert "results" in response_data

    # Verify we get exactly 2 unique SAP system values (True and False)
    # without duplicates caused by cartesian product
    assert len(response_data["results"]) == 2

    # Verify the counts are correct
    expected_counts = {True: 2, False: 1}
    for result in response_data["results"]:
        sap_value = result["value"]
        assert result["count"] == expected_counts[sap_value]


@pytest.mark.usefixtures("enable_rbac")
def test_sap_system_with_rbac_groups_and_registered_with(
    mocker,
    mq_create_or_update_host,
    api_get,
    db_create_group,
    db_create_host_group_assoc,
):
    """
    Test that get_sap_system_info does not create cartesian product when using
    rbac_filter with groups along with registered_with parameter.

    This test verifies the fix for RHINENG-21231 with the registered_with parameter.
    """
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Create a group
    group = db_create_group("test-group-registered")

    # Create hosts with SAP system data and assign to group
    sap_hosts = []
    for sap_system_value in [True, True, False]:
        insights_id = generate_uuid()
        host = mq_create_or_update_host(
            minimal_host(
                insights_id=insights_id,
                system_profile={"workloads": {"sap": {"sap_system": sap_system_value}}},
            )
        )
        db_create_host_group_assoc(host.id, group.id)
        sap_hosts.append((host, sap_system_value))

    # Create RBAC response with group filter
    mock_rbac_response = create_custom_rbac_response(
        group_ids=[str(group.id)],
        operation=RBACFilterOperation.IN,
        hosts_permission="read",
    )
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Call SAP system endpoint with registered_with parameter
    url = build_system_profile_sap_system_url(query="?registered_with=insights")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert "results" in response_data

    # Verify we get exactly 2 unique SAP system values (True and False)
    # without duplicates caused by cartesian product
    assert len(response_data["results"]) == 2

    # Verify the counts are correct
    expected_counts = {True: 2, False: 1}
    for result in response_data["results"]:
        sap_value = result["value"]
        assert result["count"] == expected_counts[sap_value]


@pytest.mark.usefixtures("enable_rbac")
def test_sap_sids_with_rbac_groups_and_filter(
    mocker,
    mq_create_or_update_host,
    api_get,
    db_create_group,
    db_create_host_group_assoc,
):
    """
    Test that get_sap_sids_info does not create cartesian product when using
    rbac_filter with groups along with filter parameter.

    This test verifies the fix for RHINENG-21231 for the SAP SIDS endpoint.
    """
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Create a group
    group = db_create_group("test-group-sids")

    # Create hosts with SAP SIDS data and assign to group
    sap_sids_data = [["ABC", "XYZ"], ["ABC"], ["DEF", "XYZ"]]
    sap_hosts = []

    for sids in sap_sids_data:
        insights_id = generate_uuid()
        host = mq_create_or_update_host(
            minimal_host(
                insights_id=insights_id,
                system_profile={"workloads": {"sap": {"sids": sids}}},
            )
        )
        db_create_host_group_assoc(host.id, group.id)
        sap_hosts.append((host, sids))

    # Create RBAC response with group filter
    mock_rbac_response = create_custom_rbac_response(
        group_ids=[str(group.id)],
        operation=RBACFilterOperation.IN,
        hosts_permission="read",
    )
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Call SAP SIDS endpoint with filter parameter (e.g., staleness filter)
    url = build_system_profile_sap_sids_url(query="?staleness=fresh")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert "results" in response_data

    # Verify we get exactly 4 unique SAP SIDS (ABC, XYZ, DEF)
    # without duplicates caused by cartesian product
    # ABC: 2 hosts, XYZ: 2 hosts, DEF: 1 host
    assert len(response_data["results"]) == 3

    # Verify the counts are correct
    expected_counts = {"ABC": 2, "XYZ": 2, "DEF": 1}
    for result in response_data["results"]:
        sid_value = result["value"]
        assert result["count"] == expected_counts[sid_value]


@pytest.mark.usefixtures("enable_rbac")
def test_sap_sids_with_rbac_groups_and_registered_with(
    mocker,
    mq_create_or_update_host,
    api_get,
    db_create_group,
    db_create_host_group_assoc,
):
    """
    Test that get_sap_sids_info does not create cartesian product when using
    rbac_filter with groups along with registered_with parameter.

    This test verifies the fix for RHINENG-21231 for the SAP SIDS endpoint
    with the registered_with parameter.
    """
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Create a group
    group = db_create_group("test-group-sids-registered")

    # Create hosts with SAP SIDS data and assign to group
    sap_sids_data = [["FOO", "BAR"], ["FOO"], ["BAZ"]]
    sap_hosts = []

    for sids in sap_sids_data:
        insights_id = generate_uuid()
        host = mq_create_or_update_host(
            minimal_host(
                insights_id=insights_id,
                system_profile={"workloads": {"sap": {"sids": sids}}},
            )
        )
        db_create_host_group_assoc(host.id, group.id)
        sap_hosts.append((host, sids))

    # Create RBAC response with group filter
    mock_rbac_response = create_custom_rbac_response(
        group_ids=[str(group.id)],
        operation=RBACFilterOperation.IN,
        hosts_permission="read",
    )
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Call SAP SIDS endpoint with registered_with parameter
    url = build_system_profile_sap_sids_url(query="?registered_with=insights")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert "results" in response_data

    # Verify we get exactly 3 unique SAP SIDS (FOO, BAR, BAZ)
    # without duplicates caused by cartesian product
    # FOO: 2 hosts, BAR: 1 host, BAZ: 1 host
    assert len(response_data["results"]) == 3

    # Verify the counts are correct
    expected_counts = {"FOO": 2, "BAR": 1, "BAZ": 1}
    for result in response_data["results"]:
        sid_value = result["value"]
        assert result["count"] == expected_counts[sid_value]


@pytest.mark.usefixtures("enable_rbac")
def test_sap_system_with_rbac_groups_filter_and_registered_with(
    mocker,
    mq_create_or_update_host,
    api_get,
    db_create_group,
    db_create_host_group_assoc,
):
    """
    Test that get_sap_system_info does not create cartesian product when using
    rbac_filter with groups along with both filter and registered_with parameters.

    This test verifies the fix for RHINENG-21231 with multiple query parameters.
    """
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Create a group
    group = db_create_group("test-group-combined")

    # Create hosts with SAP system data and assign to group
    sap_hosts = []
    for sap_system_value in [True, False, True, False]:
        insights_id = generate_uuid()
        host = mq_create_or_update_host(
            minimal_host(
                insights_id=insights_id,
                system_profile={"workloads": {"sap": {"sap_system": sap_system_value}}},
            )
        )
        db_create_host_group_assoc(host.id, group.id)
        sap_hosts.append((host, sap_system_value))

    # Create RBAC response with group filter
    mock_rbac_response = create_custom_rbac_response(
        group_ids=[str(group.id)],
        operation=RBACFilterOperation.IN,
        hosts_permission="read",
    )
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Call SAP system endpoint with both filter and registered_with parameters
    url = build_system_profile_sap_system_url(query="?staleness=fresh&registered_with=insights")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert "results" in response_data

    # Verify we get exactly 2 unique SAP system values (True and False)
    # without duplicates caused by cartesian product
    assert len(response_data["results"]) == 2

    # Verify the counts are correct
    expected_counts = {True: 2, False: 2}
    for result in response_data["results"]:
        sap_value = result["value"]
        assert result["count"] == expected_counts[sap_value]


@pytest.mark.usefixtures("enable_rbac")
def test_sap_system_with_multiple_groups_and_filter(
    mocker,
    mq_create_or_update_host,
    api_get,
    db_create_group,
    db_create_host_group_assoc,
):
    """
    Test that get_sap_system_info works correctly with multiple groups in rbac_filter.

    This test ensures the fix handles scenarios with multiple groups without
    creating duplicate results.
    """
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Create two groups
    group1 = db_create_group("test-group-1")
    group2 = db_create_group("test-group-2")

    # Create hosts with SAP system data and assign to different groups
    sap_hosts_group1 = []
    for sap_system_value in [True, True]:
        insights_id = generate_uuid()
        host = mq_create_or_update_host(
            minimal_host(
                insights_id=insights_id,
                system_profile={"workloads": {"sap": {"sap_system": sap_system_value}}},
            )
        )
        db_create_host_group_assoc(host.id, group1.id)
        sap_hosts_group1.append((host, sap_system_value))

    sap_hosts_group2 = []
    for sap_system_value in [False, True]:
        insights_id = generate_uuid()
        host = mq_create_or_update_host(
            minimal_host(
                insights_id=insights_id,
                system_profile={"workloads": {"sap": {"sap_system": sap_system_value}}},
            )
        )
        db_create_host_group_assoc(host.id, group2.id)
        sap_hosts_group2.append((host, sap_system_value))

    # Create RBAC response with multiple group filters
    mock_rbac_response = create_custom_rbac_response(
        group_ids=[str(group1.id), str(group2.id)],
        operation=RBACFilterOperation.IN,
        hosts_permission="read",
    )
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Call SAP system endpoint with filter parameter
    url = build_system_profile_sap_system_url(query="?staleness=fresh")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert "results" in response_data

    # Verify we get exactly 2 unique SAP system values (True and False)
    # Total: 3 True (2 from group1, 1 from group2) and 1 False (from group2)
    assert len(response_data["results"]) == 2

    # Verify the counts are correct
    expected_counts = {True: 3, False: 1}
    for result in response_data["results"]:
        sap_value = result["value"]
        assert result["count"] == expected_counts[sap_value]
