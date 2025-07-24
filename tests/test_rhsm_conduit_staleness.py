"""
Test the rhsm-conduit-only hosts functionality to ensure they stay fresh forever.
"""

from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest

from api.host_query import staleness_timestamps
from app.models import Host
from app.models.constants import EDGE_HOST_STALE_TIMESTAMP
from app.models.host import should_host_stay_fresh_forever
from app.serialization import _serialize_per_reporter_staleness
from app.staleness_serialization import get_reporter_staleness_timestamps
from app.staleness_serialization import get_staleness_timestamps
from app.staleness_serialization import get_sys_default_staleness
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid


class TestRhsmConduitUtilityFunctions:
    """Test the utility functions for rhsm-conduit-only hosts."""

    def test_should_host_stay_fresh_forever_true(self, flask_app):
        """Test that rhsm-conduit-only hosts should stay fresh forever."""
        with flask_app.app.app_context():
            host = Host(
                canonical_facts={"subscription_manager_id": generate_uuid()},
                reporter="rhsm-conduit",
                stale_timestamp=datetime.now(timezone.utc),
                org_id=USER_IDENTITY["org_id"],
            )
            host.per_reporter_staleness = {
                "rhsm-conduit": {
                    "last_check_in": datetime.now(timezone.utc).isoformat(),
                    "stale_timestamp": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                    "check_in_succeeded": True,
                }
            }

            assert should_host_stay_fresh_forever(host) is True

    def test_should_host_stay_fresh_forever_false(self):
        """Test that hosts with multiple reporters should not stay fresh forever."""
        host = Host(
            canonical_facts={"subscription_manager_id": generate_uuid()},
            reporter="puptoo",
            stale_timestamp=datetime.now(timezone.utc),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "rhsm-conduit": {
                "last_check_in": datetime.now(timezone.utc).isoformat(),
                "stale_timestamp": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "check_in_succeeded": True,
            },
            "puptoo": {
                "last_check_in": datetime.now(timezone.utc).isoformat(),
                "stale_timestamp": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "check_in_succeeded": True,
            },
        }

        assert should_host_stay_fresh_forever(host) is False


class TestRhsmConduitStalenessTimestamps:
    """Test staleness timestamp calculation for rhsm-conduit-only hosts."""

    def test_get_staleness_timestamps_rhsm_conduit_only(self, mocker):
        """Test that rhsm-conduit-only hosts get far-future timestamps."""
        host = Host(
            canonical_facts={"subscription_manager_id": generate_uuid()},
            reporter="rhsm-conduit",
            stale_timestamp=datetime.now(timezone.utc),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "rhsm-conduit": {"last_check_in": datetime.now(timezone.utc).isoformat(), "check_in_succeeded": True}
        }

        # Mock the flag to test both code paths
        mocker.patch("app.staleness_serialization.get_flag_value", return_value=True)

        st = staleness_timestamps()
        staleness = get_sys_default_staleness()

        result = get_staleness_timestamps(host, st, staleness)
        far_future = EDGE_HOST_STALE_TIMESTAMP

        assert result["stale_timestamp"] == far_future
        assert result["stale_warning_timestamp"] == far_future
        assert result["culled_timestamp"] == far_future

    def test_get_staleness_timestamps_normal_host(self, mocker):
        """Test that normal hosts get regular timestamps."""
        host = Host(
            canonical_facts={"subscription_manager_id": generate_uuid()},
            reporter="puptoo",
            stale_timestamp=datetime.now(timezone.utc),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "puptoo": {"last_check_in": datetime.now(timezone.utc).isoformat(), "check_in_succeeded": True}
        }

        mocker.patch("app.staleness_serialization.get_flag_value", return_value=True)

        st = staleness_timestamps()
        staleness = get_sys_default_staleness()

        result = get_staleness_timestamps(host, st, staleness)
        far_future = EDGE_HOST_STALE_TIMESTAMP

        # These should NOT be far future timestamps
        assert result["stale_timestamp"] != far_future
        assert result["stale_warning_timestamp"] != far_future
        assert result["culled_timestamp"] != far_future

    def test_get_reporter_staleness_timestamps_rhsm_conduit_only(self, mocker):
        """Test that per-reporter staleness for rhsm-conduit-only hosts gets far-future timestamps."""
        host = Host(
            canonical_facts={"subscription_manager_id": generate_uuid()},
            reporter="rhsm-conduit",
            stale_timestamp=datetime.now(timezone.utc),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "rhsm-conduit": {"last_check_in": datetime.now(timezone.utc).isoformat(), "check_in_succeeded": True}
        }

        mocker.patch("app.staleness_serialization.get_flag_value", return_value=True)

        st = staleness_timestamps()
        staleness = get_sys_default_staleness()

        result = get_reporter_staleness_timestamps(host, st, staleness, "rhsm-conduit")
        far_future = EDGE_HOST_STALE_TIMESTAMP

        assert result["stale_timestamp"] == far_future
        assert result["stale_warning_timestamp"] == far_future
        assert result["culled_timestamp"] == far_future


class TestRhsmConduitHostModel:
    """Test Host model behavior for rhsm-conduit-only hosts."""

    def test_reporter_stale_rhsm_conduit_only_always_false(self, db_create_host):
        """Test that rhsm-conduit-only hosts never report as stale."""
        host = Host(
            canonical_facts={"subscription_manager_id": generate_uuid()},
            reporter="rhsm-conduit",
            stale_timestamp=datetime.now(timezone.utc) - timedelta(days=10),  # Way in the past
            org_id=USER_IDENTITY["org_id"],
        )

        # Set per_reporter_staleness with past timestamp to simulate stale condition
        past_time = datetime.now(timezone.utc) - timedelta(days=5)
        host.per_reporter_staleness = {
            "rhsm-conduit": {
                "last_check_in": past_time.isoformat(),
                "stale_timestamp": past_time.isoformat(),
                "check_in_succeeded": True,
            }
        }

        created_host = db_create_host(host=host)

        # Even with past timestamp, should not be stale
        assert created_host.reporter_stale("rhsm-conduit") is False

    def test_reporter_stale_normal_host_can_be_stale(self, db_create_host):
        """Test that normal hosts can be stale."""
        host = Host(
            canonical_facts={"subscription_manager_id": generate_uuid()},
            reporter="puptoo",
            stale_timestamp=datetime.now(timezone.utc) - timedelta(days=10),
            org_id=USER_IDENTITY["org_id"],
        )

        # Set per_reporter_staleness with past timestamp to simulate stale condition
        past_time = datetime.now(timezone.utc) - timedelta(days=5)
        host.per_reporter_staleness = {
            "puptoo": {
                "last_check_in": past_time.isoformat(),
                "stale_timestamp": past_time.isoformat(),
                "check_in_succeeded": True,
            }
        }

        created_host = db_create_host(host=host)

        # Should be stale due to past timestamp
        assert created_host.reporter_stale("puptoo") is True


class TestRhsmConduitSerialization:
    """Test serialization behavior for rhsm-conduit-only hosts."""

    def test_serialize_per_reporter_staleness_rhsm_conduit_only(self):
        """Test that per-reporter staleness serialization uses far-future timestamps for rhsm-conduit-only hosts."""
        host = Host(
            canonical_facts={"subscription_manager_id": generate_uuid()},
            reporter="rhsm-conduit",
            stale_timestamp=datetime.now(timezone.utc),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "rhsm-conduit": {"last_check_in": datetime.now(timezone.utc).isoformat(), "check_in_succeeded": True}
        }

        staleness = get_sys_default_staleness()
        st = staleness_timestamps()

        result = _serialize_per_reporter_staleness(host, staleness, st)
        far_future = EDGE_HOST_STALE_TIMESTAMP

        rhsm_data = result["rhsm-conduit"]
        assert datetime.fromisoformat(rhsm_data["stale_timestamp"]) == far_future
        assert datetime.fromisoformat(rhsm_data["stale_warning_timestamp"]) == far_future
        assert datetime.fromisoformat(rhsm_data["culled_timestamp"]) == far_future

    def test_serialize_per_reporter_staleness_normal_host(self):
        """Test that per-reporter staleness serialization uses normal timestamps for regular hosts."""
        host = Host(
            canonical_facts={"subscription_manager_id": generate_uuid()},
            reporter="puptoo",
            stale_timestamp=datetime.now(timezone.utc),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "puptoo": {"last_check_in": datetime.now(timezone.utc).isoformat(), "check_in_succeeded": True}
        }

        staleness = get_sys_default_staleness()
        st = staleness_timestamps()

        result = _serialize_per_reporter_staleness(host, staleness, st)
        far_future = EDGE_HOST_STALE_TIMESTAMP

        puptoo_data = result["puptoo"]
        # Should NOT have far-future timestamps
        assert datetime.fromisoformat(puptoo_data["stale_timestamp"]) != far_future
        assert datetime.fromisoformat(puptoo_data["stale_warning_timestamp"]) != far_future
        assert datetime.fromisoformat(puptoo_data["culled_timestamp"]) != far_future


@pytest.mark.parametrize("reporter", ["rhsm-conduit"])
def test_rhsm_conduit_reporter_parametrized(reporter):
    """Parametrized test to ensure rhsm-conduit behavior."""
    host = Host(
        canonical_facts={"subscription_manager_id": generate_uuid()},
        reporter=reporter,
        stale_timestamp=datetime.now(timezone.utc),
        org_id=USER_IDENTITY["org_id"],
    )
    host.per_reporter_staleness = {
        reporter: {"last_check_in": datetime.now(timezone.utc).isoformat(), "check_in_succeeded": True}
    }

    assert should_host_stay_fresh_forever(host) is True


@pytest.mark.parametrize(
    "reporters",
    [
        ["rhsm-conduit", "puptoo"],
        ["rhsm-conduit", "cloud-connector"],
        ["rhsm-conduit", "yuptoo", "puptoo"],
        ["puptoo"],
        ["cloud-connector"],
        ["discovery", "satellite"],
    ],
)
def test_multiple_reporters_parametrized(reporters):
    """Parametrized test to ensure hosts with multiple reporters don't stay fresh forever."""
    host = Host(
        canonical_facts={"subscription_manager_id": generate_uuid()},
        reporter=reporters[0],
        stale_timestamp=datetime.now(timezone.utc),
        org_id=USER_IDENTITY["org_id"],
    )

    per_reporter_staleness = {
        reporter: {
            "last_check_in": datetime.now(timezone.utc).isoformat(),
            "check_in_succeeded": True,
        }
        for reporter in reporters
    }
    host.per_reporter_staleness = per_reporter_staleness

    if len(reporters) == 1 and reporters[0] == "rhsm-conduit":
        assert should_host_stay_fresh_forever(host) is True
    else:
        assert should_host_stay_fresh_forever(host) is False
