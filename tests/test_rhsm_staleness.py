"""
Test the rhsm-system-profile-bridge-only hosts functionality to ensure they stay fresh forever.
"""

from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest

from api.host_query import staleness_timestamps
from app.culling import should_host_stay_fresh_forever
from app.models import Host
from app.models.constants import FAR_FUTURE_STALE_TIMESTAMP
from app.serialization import _serialize_per_reporter_staleness
from app.staleness_serialization import get_reporter_staleness_timestamps
from app.staleness_serialization import get_staleness_timestamps
from app.staleness_serialization import get_sys_default_staleness
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid


class TestRhsmSpBridgeUtilityFunctions:
    """Test the utility functions for rhsm-system-profile-bridge-only hosts."""

    def test_should_host_stay_fresh_forever_true(self, flask_app):
        """Test that rhsm-system-profile-bridge-only hosts should stay fresh forever."""
        with flask_app.app.app_context():
            host = Host(
                subscription_manager_id=generate_uuid(),
                reporter="rhsm-system-profile-bridge",
                stale_timestamp=datetime.now(UTC),
                org_id=USER_IDENTITY["org_id"],
            )
            host.per_reporter_staleness = {
                "rhsm-system-profile-bridge": {
                    "last_check_in": datetime.now(UTC).isoformat(),
                    "stale_timestamp": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                    "check_in_succeeded": True,
                }
            }

            assert should_host_stay_fresh_forever(host) is True

    def test_should_host_stay_fresh_forever_false(self):
        """Test that hosts with multiple reporters should not stay fresh forever."""
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="puptoo",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "rhsm-system-profile-bridge": {
                "last_check_in": datetime.now(UTC).isoformat(),
                "stale_timestamp": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "check_in_succeeded": True,
            },
            "puptoo": {
                "last_check_in": datetime.now(UTC).isoformat(),
                "stale_timestamp": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "check_in_succeeded": True,
            },
        }

        assert should_host_stay_fresh_forever(host) is False


class TestRhsmSpBridgeStalenessTimestamps:
    """Test staleness timestamp calculation for rhsm-system-profile-bridge-only hosts."""

    def test_get_staleness_timestamps_rhsm_sp_bridge_only(self):
        """Test that rhsm-system-profile-bridge-only hosts get far-future timestamps."""
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="rhsm-system-profile-bridge",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "rhsm-system-profile-bridge": {
                "last_check_in": datetime.now(UTC).isoformat(),
                "check_in_succeeded": True,
            }
        }

        st = staleness_timestamps()
        staleness = get_sys_default_staleness()

        result = get_staleness_timestamps(host, st, staleness)

        assert result["stale_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP
        assert result["stale_warning_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP
        assert result["culled_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP

    def test_get_staleness_timestamps_normal_host(self):
        """Test that normal hosts get regular timestamps."""
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="puptoo",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "puptoo": {"last_check_in": datetime.now(UTC).isoformat(), "check_in_succeeded": True}
        }

        st = staleness_timestamps()
        staleness = get_sys_default_staleness()

        result = get_staleness_timestamps(host, st, staleness)

        # These should NOT be far future timestamps
        assert result["stale_timestamp"] != FAR_FUTURE_STALE_TIMESTAMP
        assert result["stale_warning_timestamp"] != FAR_FUTURE_STALE_TIMESTAMP
        assert result["culled_timestamp"] != FAR_FUTURE_STALE_TIMESTAMP

    def test_get_reporter_staleness_timestamps_rhsm_sp_bridge_only(self):
        """Test that per-reporter staleness for rhsm-system-profile-bridge-only hosts gets far-future timestamps."""
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="rhsm-system-profile-bridge",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "rhsm-system-profile-bridge": {
                "last_check_in": datetime.now(UTC).isoformat(),
                "check_in_succeeded": True,
            }
        }

        st = staleness_timestamps()
        staleness = get_sys_default_staleness()

        result = get_reporter_staleness_timestamps(host, st, staleness, "rhsm-system-profile-bridge")

        assert result["stale_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP
        assert result["stale_warning_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP
        assert result["culled_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP


class TestRhsmSpBridgeHostModel:
    """Test Host model behavior for rhsm-system-profile-bridge-only hosts."""

    def test_reporter_stale_rhsm_conduit_only_always_false(self, db_create_host):
        """Test that rhsm-system-profile-bridge-only hosts never report as stale."""
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="rhsm-system-profile-bridge",
            stale_timestamp=datetime.now(UTC) - timedelta(days=10),  # Way in the past
            org_id=USER_IDENTITY["org_id"],
        )

        # Set per_reporter_staleness with past timestamp to simulate stale condition
        past_time = datetime.now(UTC) - timedelta(days=5)
        host.per_reporter_staleness = {
            "rhsm-system-profile-bridge": {
                "last_check_in": past_time.isoformat(),
                "stale_timestamp": past_time.isoformat(),
                "check_in_succeeded": True,
            }
        }

        created_host = db_create_host(host=host)

        # Even with past timestamp, should not be stale
        assert created_host.reporter_stale("rhsm-system-profile-bridge") is False

    def test_reporter_stale_normal_host_can_be_stale(self, db_create_host):
        """Test that normal hosts can be stale."""
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="puptoo",
            stale_timestamp=datetime.now(UTC) - timedelta(days=10),
            org_id=USER_IDENTITY["org_id"],
        )

        # Set per_reporter_staleness with past timestamp to simulate stale condition
        past_time = datetime.now(UTC) - timedelta(days=5)
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


class TestRhsmSpBridgeSerialization:
    """Test serialization behavior for rhsm-system-profile-bridge-only hosts."""

    def test_serialize_per_reporter_staleness_rhsm_sp_bridge_only(self):
        """Test that per-reporter staleness serialization uses far-future timestamps for rhsm-only hosts."""
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="rhsm-system-profile-bridge",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "rhsm-system-profile-bridge": {
                "last_check_in": datetime.now(UTC).isoformat(),
                "check_in_succeeded": True,
            }
        }

        staleness = get_sys_default_staleness()
        st = staleness_timestamps()

        result = _serialize_per_reporter_staleness(host, staleness, st)

        rhsm_data = result["rhsm-system-profile-bridge"]
        assert datetime.fromisoformat(rhsm_data["stale_timestamp"]) == FAR_FUTURE_STALE_TIMESTAMP
        assert datetime.fromisoformat(rhsm_data["stale_warning_timestamp"]) == FAR_FUTURE_STALE_TIMESTAMP
        assert datetime.fromisoformat(rhsm_data["culled_timestamp"]) == FAR_FUTURE_STALE_TIMESTAMP

    def test_serialize_per_reporter_staleness_normal_host(self):
        """Test that per-reporter staleness serialization uses normal timestamps for regular hosts."""
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="puptoo",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "puptoo": {"last_check_in": datetime.now(UTC).isoformat(), "check_in_succeeded": True}
        }

        staleness = get_sys_default_staleness()
        st = staleness_timestamps()

        result = _serialize_per_reporter_staleness(host, staleness, st)

        puptoo_data = result["puptoo"]
        # Should NOT have far-future timestamps
        assert datetime.fromisoformat(puptoo_data["stale_timestamp"]) != FAR_FUTURE_STALE_TIMESTAMP
        assert datetime.fromisoformat(puptoo_data["stale_warning_timestamp"]) != FAR_FUTURE_STALE_TIMESTAMP
        assert datetime.fromisoformat(puptoo_data["culled_timestamp"]) != FAR_FUTURE_STALE_TIMESTAMP


def test_rhsm_conduit_reporter():
    """Parametrized test to ensure rhsm-system-profile-bridge behavior."""
    host = Host(
        subscription_manager_id=generate_uuid(),
        reporter="rhsm-system-profile-bridge",
        stale_timestamp=datetime.now(UTC),
        org_id=USER_IDENTITY["org_id"],
    )
    host.per_reporter_staleness = {
        "rhsm-system-profile-bridge": {
            "last_check_in": datetime.now(UTC).isoformat(),
            "check_in_succeeded": True,
        }
    }

    assert should_host_stay_fresh_forever(host) is True


@pytest.mark.parametrize(
    "reporters",
    [
        ["rhsm-system-profile-bridge", "puptoo"],
        ["rhsm-system-profile-bridge", "cloud-connector"],
        ["rhsm-system-profile-bridge", "yuptoo", "puptoo"],
        ["puptoo"],
        ["cloud-connector"],
        ["discovery", "satellite"],
    ],
)
def test_multiple_reporters_parametrized(reporters):
    """Parametrized test to ensure hosts with multiple reporters don't stay fresh forever."""
    host = Host(
        subscription_manager_id=generate_uuid(),
        reporter=reporters[0],
        stale_timestamp=datetime.now(UTC),
        org_id=USER_IDENTITY["org_id"],
    )

    per_reporter_staleness = {
        reporter: {
            "last_check_in": datetime.now(UTC).isoformat(),
            "check_in_succeeded": True,
        }
        for reporter in reporters
    }
    host.per_reporter_staleness = per_reporter_staleness

    assert should_host_stay_fresh_forever(host) is False
