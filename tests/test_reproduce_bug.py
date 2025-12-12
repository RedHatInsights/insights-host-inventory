"""
Test to reproduce the host_count bug on master branch
"""
import pytest
from tests.helpers.test_utils import generate_uuid


@pytest.mark.usefixtures("enable_kessel")
def test_patch_group_invalid_host_bug_reproduction(
    db_create_group_with_hosts,
    api_patch_group,
    db_get_hosts_for_group,
    db_get_group_by_id,
    event_producer,
    mocker,
):
    """
    Reproduce the bug where PATCH with only invalid host incorrectly clears all hosts.

    Test scenario (from defect description):
    - Group starts with 3 hosts
    - PATCH with [invalid_host_id] (only 1 invalid host)
    - This should remove all 3 existing hosts and add invalid host (which should fail validation)

    Expected behavior:
    - PATCH returns 400 error (invalid host detected)
    - Entire operation rolls back
    - Group should still have all 3 original hosts

    Actual behavior on master (BUG?):
    - PATCH returns 400 error ✓
    - All 3 hosts removed and added to ungrouped (due to early flush)
    - Invalid host validation fails
    - Rollback only prevents invalid host from being added
    - Result: Group has 0 hosts (all 3 incorrectly removed)
    """
    mocker.patch.object(event_producer, "write_event")

    # Create a group with 3 hosts
    group = db_create_group_with_hosts("test_group", 3)
    group_id = group.id

    # Verify initial state
    initial_hosts = db_get_hosts_for_group(group_id)
    assert len(initial_hosts) == 3, "Group should start with 3 hosts"
    print(f"✓ Initial state: Group has {len(initial_hosts)} hosts")

    # Get the group and check host_count (should be 3)
    from lib.group_repository import serialize_group
    group_before_patch = db_get_group_by_id(group_id)
    group_data_before = serialize_group(group_before_patch)
    print(f"✓ Before PATCH: group host_count = {group_data_before['host_count']}")
    assert group_data_before['host_count'] == 3, "host_count should be 3 before PATCH"

    # Generate an invalid host ID
    invalid_host_id = generate_uuid()

    # Attempt to PATCH with ONLY invalid host
    # This will try to remove all 3 existing hosts and add the invalid one
    patch_doc = {"host_ids": [invalid_host_id]}
    response_status, response_data = api_patch_group(group_id, patch_doc)

    # Should return 400 error
    assert response_status == 400, "Should return 400 for invalid host"
    print(f"✓ PATCH returned 400 error as expected")
    print(f"  Error detail: {response_data.get('detail', 'N/A')}")

    # Check host_count after failed PATCH
    group_after_patch = db_get_group_by_id(group_id)
    group_data_after = serialize_group(group_after_patch)
    print(f"\n⚠️  After PATCH: group host_count = {group_data_after['host_count']}")

    # Check if bug is reproduced
    if group_data_after['host_count'] != 3:
        print(f"\n🐛 BUG REPRODUCED!")
        print(f"   Expected host_count: 3")
        print(f"   Actual host_count: {group_data_after['host_count']}")
        print(f"   The failed PATCH incorrectly cleared the host associations!")
        assert False, f"BUG: host_count is {group_data_after['host_count']} but should be 3"
    else:
        print(f"\n✅ NO BUG: Rollback worked correctly, host_count still 3")

    # Also verify via db_get_hosts_for_group
    hosts_after = db_get_hosts_for_group(group_id)
    print(f"  db_get_hosts_for_group returns {len(hosts_after)} hosts")
    assert len(hosts_after) == 3, "Group should still have 3 hosts in HostGroupAssoc table"
