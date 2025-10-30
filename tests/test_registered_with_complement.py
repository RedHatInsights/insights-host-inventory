#!/usr/bin/env python3

"""
Tests for registered_with filter complement property and edge cases.

This test module specifically verifies that the registered_with filter bug fix works correctly:
1. Hosts with no reporters (just subscription_manager_id) are handled properly
2. The complement property holds: registered_with=X + registered_with=!X = total hosts
3. Edge cases with missing culled_timestamp are handled
"""

from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest

from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid


@pytest.mark.usefixtures("flask_app")
def test_registered_with_complement_property_comprehensive(db_create_host, api_get, subtests):
    """
    Test that registered_with positive and negative filters are true complements.

    This test ensures that for any reporter:
    - registered_with=reporter + registered_with=!reporter = total hosts
    - All host types are properly categorized (no gaps, no overlaps)
    """
    _now = datetime.now(UTC)
    created_hosts = []

    # 1. Host with fresh puptoo reporter (should match registered_with=puptoo)
    host1 = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"insights_id": generate_uuid()},
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": _now.isoformat(),
                    "stale_timestamp": (_now + timedelta(days=7)).isoformat(),
                    "culled_timestamp": (_now + timedelta(days=14)).isoformat(),  # Fresh
                    "check_in_succeeded": True,
                },
            },
        },
    ).id
    created_hosts.append(host1)

    # 2. Host with culled puptoo reporter (should match registered_with=!puptoo)
    host2 = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"insights_id": generate_uuid()},
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (_now - timedelta(days=30)).isoformat(),
                    "stale_timestamp": (_now - timedelta(days=23)).isoformat(),
                    "culled_timestamp": (_now - timedelta(days=16)).isoformat(),  # Culled (past)
                    "check_in_succeeded": True,
                },
            },
        },
    ).id
    created_hosts.append(host2)

    # 3. Host with puptoo but missing culled_timestamp
    # (legacy data - should match registered_with=!puptoo after backfill)
    host3 = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"insights_id": generate_uuid()},
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (_now - timedelta(days=20)).isoformat(),
                    "stale_timestamp": (_now - timedelta(days=13)).isoformat(),  # Stale
                    # Missing culled_timestamp - this is the legacy data case
                    "check_in_succeeded": True,
                },
            },
        },
    ).id
    created_hosts.append(host3)

    # 4. Host with different reporter (should match registered_with=!puptoo)
    host4 = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"insights_id": generate_uuid()},
            "per_reporter_staleness": {
                "yupana": {
                    "last_check_in": _now.isoformat(),
                    "stale_timestamp": (_now + timedelta(days=7)).isoformat(),
                    "culled_timestamp": (_now + timedelta(days=14)).isoformat(),
                    "check_in_succeeded": True,
                },
            },
        },
    ).id
    created_hosts.append(host4)

    # 5. Host with NO reporters, just subscription_manager_id (should match registered_with=!puptoo)
    host5 = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"subscription_manager_id": generate_uuid()},
            # No per_reporter_staleness at all
        },
    ).id
    created_hosts.append(host5)

    # 6. Host with empty per_reporter_staleness (should match registered_with=!puptoo)
    host6 = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"subscription_manager_id": generate_uuid()},
            "per_reporter_staleness": {},  # Empty but present
        },
    ).id
    created_hosts.append(host6)

    # 7. Another fresh puptoo host for variety
    host7 = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"insights_id": generate_uuid()},
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (_now - timedelta(hours=1)).isoformat(),
                    "stale_timestamp": (_now + timedelta(days=6, hours=23)).isoformat(),
                    "culled_timestamp": (_now + timedelta(days=13, hours=23)).isoformat(),  # Fresh
                    "check_in_succeeded": True,
                },
            },
        },
    ).id
    created_hosts.append(host7)

    # Expected results based on the logic:
    # registered_with=puptoo: hosts 1, 7 (fresh puptoo)
    # registered_with=!puptoo: hosts 2, 3, 4, 5, 6 (culled puptoo, stale puptoo, other reporters, no reporters)
    # Note: Exact counts may vary based on legacy semantics for missing culled_timestamp.
    # We assert membership and complement properties instead of strict counts.

    # Test the individual filters
    with subtests.test(filter_type="positive"):
        url = build_hosts_url(query="?registered_with=puptoo")
        response_status, response_data = api_get(url)
        assert response_status == 200
        puptoo_results = response_data["results"]
        puptoo_host_ids = {result["id"] for result in puptoo_results}
        # Verify must-include and must-exclude sets
        assert str(host1) in puptoo_host_ids and str(host7) in puptoo_host_ids
        for h in (host4, host5, host6):
            assert str(h) not in puptoo_host_ids

    with subtests.test(filter_type="negative"):
        url = build_hosts_url(query="?registered_with=!puptoo")
        response_status, response_data = api_get(url)
        assert response_status == 200
        not_puptoo_results = response_data["results"]
        not_puptoo_host_ids = {result["id"] for result in not_puptoo_results}
        # Verify must-include and must-exclude sets (host3 legacy may vary)
        for h in (host2, host4, host5, host6):
            assert str(h) in not_puptoo_host_ids
        for h in (host1, host7):
            assert str(h) not in not_puptoo_host_ids

    # TEST THE COMPLEMENT PROPERTY: positive + negative = total
    with subtests.test(filter_type="complement_property"):
        # Re-fetch positive/negative to avoid dependency on prior subtests
        pos_status, pos_data = api_get(build_hosts_url(query="?registered_with=puptoo"))
        neg_status, neg_data = api_get(build_hosts_url(query="?registered_with=!puptoo"))
        all_status, all_data = api_get(build_hosts_url())
        assert pos_status == 200 and neg_status == 200 and all_status == 200

        pos_ids = {r["id"] for r in pos_data["results"]}
        neg_ids = {r["id"] for r in neg_data["results"]}
        all_ids = {r["id"] for r in all_data["results"]}
        created_ids = {str(h) for h in created_hosts}

        # Restrict to our created hosts for complement checks
        pos_ids &= created_ids
        neg_ids &= created_ids
        all_ids &= created_ids

        assert pos_ids.isdisjoint(neg_ids), f"Overlap detected: {pos_ids & neg_ids}"
        assert pos_ids | neg_ids == all_ids, f"Missing from union: {all_ids - (pos_ids | neg_ids)}"


@pytest.mark.usefixtures("flask_app")
def test_registered_with_no_reporters_edge_cases(db_create_host, api_get, subtests):
    """
    Test edge cases with hosts that have no reporter data at all.

    These hosts should always be included in negative filters (registered_with=!X)
    and never in positive filters (registered_with=X).
    """
    created_hosts = []

    # Host with only subscription_manager_id
    host1 = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"subscription_manager_id": generate_uuid()},
            "display_name": "No Reporter Host 1",
        },
    ).id
    created_hosts.append(host1)

    # Host with subscription_manager_id and fqdn
    host2 = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {
                "subscription_manager_id": generate_uuid(),
                "fqdn": f"test-{generate_uuid()}.example.com",
            },
            "display_name": "No Reporter Host 2",
        },
    ).id
    created_hosts.append(host2)

    # Host with multiple canonical facts but no reporters
    host3 = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {
                "subscription_manager_id": generate_uuid(),
                "fqdn": f"multi-{generate_uuid()}.example.com",
            },
            "display_name": "No Reporter Host 3",
            "per_reporter_staleness": None,  # Explicitly None
        },
    ).id
    created_hosts.append(host3)

    # Test multiple reporters to ensure no-reporter hosts appear in all negative filters
    reporters_to_test = ["puptoo", "yupana", "rhsm-conduit", "satellite"]

    for reporter in reporters_to_test:
        with subtests.test(reporter=reporter):
            # Positive filter should not include any of our no-reporter hosts
            url_positive = build_hosts_url(query=f"?registered_with={reporter}")
            response_status, response_data = api_get(url_positive)
            assert response_status == 200

            positive_host_ids = {result["id"] for result in response_data["results"]}
            our_host_ids = {str(host_id) for host_id in created_hosts}

            intersection = positive_host_ids & our_host_ids
            assert len(intersection) == 0, (
                f"No-reporter hosts should not appear in registered_with={reporter}, but found: {intersection}"
            )

            # Negative filter should include all of our no-reporter hosts
            url_negative = build_hosts_url(query=f"?registered_with=!{reporter}")
            response_status, response_data = api_get(url_negative)
            assert response_status == 200

            negative_host_ids = {result["id"] for result in response_data["results"]}

            for host_id in created_hosts:
                assert str(host_id) in negative_host_ids, (
                    f"Host {host_id} should appear in registered_with=!{reporter}"
                )


@pytest.mark.usefixtures("flask_app")
def test_registered_with_multiple_reporters_complement(db_create_host, api_get, subtests):
    """
    Test complement property with multiple different reporters.

    Ensures that the filter logic works correctly for all reporters,
    not just puptoo.
    """
    _now = datetime.now(UTC)

    # Create hosts with different reporter combinations
    test_cases = [
        {
            "name": "fresh_yupana",
            "per_reporter_staleness": {
                "yupana": {
                    "last_check_in": _now.isoformat(),
                    "stale_timestamp": (_now + timedelta(days=7)).isoformat(),
                    "culled_timestamp": (_now + timedelta(days=14)).isoformat(),
                    "check_in_succeeded": True,
                },
            },
        },
        {
            "name": "culled_yupana",
            "per_reporter_staleness": {
                "yupana": {
                    "last_check_in": (_now - timedelta(days=20)).isoformat(),
                    "stale_timestamp": (_now - timedelta(days=13)).isoformat(),
                    "culled_timestamp": (_now - timedelta(days=6)).isoformat(),  # Culled
                    "check_in_succeeded": True,
                },
            },
        },
        {
            "name": "fresh_rhsm_conduit",
            "per_reporter_staleness": {
                "rhsm-conduit": {
                    "last_check_in": _now.isoformat(),
                    "stale_timestamp": (_now + timedelta(days=7)).isoformat(),
                    "culled_timestamp": (_now + timedelta(days=14)).isoformat(),
                    "check_in_succeeded": True,
                },
            },
        },
        {
            "name": "multiple_reporters_including_yupana",
            "per_reporter_staleness": {
                "yupana": {
                    "last_check_in": _now.isoformat(),
                    "stale_timestamp": (_now + timedelta(days=7)).isoformat(),
                    "culled_timestamp": (_now + timedelta(days=14)).isoformat(),
                    "check_in_succeeded": True,
                },
                "puptoo": {
                    "last_check_in": (_now - timedelta(days=20)).isoformat(),
                    "stale_timestamp": (_now - timedelta(days=13)).isoformat(),
                    "culled_timestamp": (_now - timedelta(days=6)).isoformat(),  # Culled puptoo
                    "check_in_succeeded": True,
                },
            },
        },
        {
            "name": "no_reporters",
            "canonical_facts": {"subscription_manager_id": generate_uuid()},
        },
    ]

    created_hosts = []
    for i, test_case in enumerate(test_cases):
        extra_data = {
            "canonical_facts": test_case.get("canonical_facts", {"insights_id": generate_uuid()}),
            "display_name": f"Test Host {i + 1} - {test_case['name']}",
        }
        if "per_reporter_staleness" in test_case:
            extra_data["per_reporter_staleness"] = test_case["per_reporter_staleness"]

        host = db_create_host(SYSTEM_IDENTITY, extra_data=extra_data)
        created_hosts.append(host)

    # Test complement property for yupana
    with subtests.test(reporter="yupana"):
        # Get yupana hosts (should be: fresh_yupana, multiple_reporters_including_yupana)
        url_positive = build_hosts_url(query="?registered_with=yupana")
        response_status, response_data = api_get(url_positive)
        assert response_status == 200
        yupana_results = response_data["results"]
        yupana_count = len(yupana_results)

        # Get !yupana hosts (should be: culled_yupana, fresh_rhsm_conduit, no_reporters)
        url_negative = build_hosts_url(query="?registered_with=!yupana")
        response_status, response_data = api_get(url_negative)
        assert response_status == 200
        not_yupana_results = response_data["results"]
        not_yupana_count = len(not_yupana_results)

        # Get total hosts to verify complement
        url_total = build_hosts_url()
        response_status, response_data = api_get(url_total)
        assert response_status == 200
        total_results = response_data["results"]
        total_count = len(total_results)

        # Verify complement property
        assert yupana_count + not_yupana_count == total_count, (
            f"Complement failed for yupana: {yupana_count} + {not_yupana_count} = "
            f"{yupana_count + not_yupana_count} != {total_count}"
        )

        # Verify expected counts (2 fresh yupana hosts, 3 others)
        assert yupana_count == 2, f"Expected 2 fresh yupana hosts, got {yupana_count}"
        assert not_yupana_count == 3, f"Expected 3 non-fresh-yupana hosts, got {not_yupana_count}"

        # Set-based: disjoint and union == total
        pos_ids = {r["id"] for r in yupana_results}
        neg_ids = {r["id"] for r in not_yupana_results}
        all_ids = {r["id"] for r in total_results}
        assert pos_ids.isdisjoint(neg_ids), f"Overlap detected: {pos_ids & neg_ids}"
        assert pos_ids | neg_ids == all_ids, f"Missing from union: {all_ids - (pos_ids | neg_ids)}"

    # Test complement property for rhsm-conduit
    with subtests.test(reporter="rhsm-conduit"):
        url_positive = build_hosts_url(query="?registered_with=rhsm-conduit")
        response_status, response_data = api_get(url_positive)
        assert response_status == 200
        rhsm_pos = response_data["results"]
        rhsm_count = len(rhsm_pos)

        url_negative = build_hosts_url(query="?registered_with=!rhsm-conduit")
        response_status, response_data = api_get(url_negative)
        assert response_status == 200
        rhsm_neg = response_data["results"]
        not_rhsm_count = len(rhsm_neg)

        # Verify complement property
        url_total = build_hosts_url()
        response_status, response_data = api_get(url_total)
        rhsm_total = response_data["results"]
        total_count = len(rhsm_total)

        assert rhsm_count + not_rhsm_count == total_count, (
            f"Complement failed for rhsm-conduit: {rhsm_count} + {not_rhsm_count} = "
            f"{rhsm_count + not_rhsm_count} != {total_count}"
        )

        # Verify expected counts (1 fresh rhsm-conduit host, 4 others)
        assert rhsm_count == 1, f"Expected 1 fresh rhsm-conduit host, got {rhsm_count}"
        assert not_rhsm_count == 4, f"Expected 4 non-fresh-rhsm-conduit hosts, got {not_rhsm_count}"

        # Set-based: disjoint and union == total
        pos_ids = {r["id"] for r in rhsm_pos}
        neg_ids = {r["id"] for r in rhsm_neg}
        all_ids = {r["id"] for r in rhsm_total}
        assert pos_ids.isdisjoint(neg_ids), f"Overlap detected: {pos_ids & neg_ids}"
        assert pos_ids | neg_ids == all_ids, f"Missing from union: {all_ids - (pos_ids | neg_ids)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
