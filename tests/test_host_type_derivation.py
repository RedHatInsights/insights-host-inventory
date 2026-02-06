"""
Tests for host_type derivation logic.

This module tests that host_type is correctly derived from system profile data
according to the priority rules defined in Host._derive_host_type().

Note: The system profile schema only allows 'edge' or 'cluster' as host_type values.
When bootc_status is present, the transformer sets host_type to 'bootc'.
"""

import pytest

from app.serialization import _map_host_type_for_backward_compatibility
from tests.helpers.test_utils import generate_uuid


class TestHostTypeDerivation:
    """Test host_type derivation from system profile."""

    def test_derive_host_type_cluster_explicit(self, db_create_host):
        """Test that explicit cluster type takes highest priority."""
        host = db_create_host(extra_data={"system_profile_facts": {"host_type": "cluster"}})

        assert host.host_type == "cluster"
        assert host.static_system_profile is not None
        assert host.static_system_profile.host_type == "cluster"

    def test_derive_host_type_cluster_from_openshift_cluster_id(self, db_create_host):
        """Test that cluster is derived when openshift_cluster_id is set."""
        host = db_create_host(extra_data={"openshift_cluster_id": generate_uuid()})

        assert host.host_type == "cluster"

    @pytest.mark.parametrize("host_type", ["edge", "cluster", "conventional"])
    def test_derive_host_type_cluster_from_openshift_cluster_id_and_explicit_host_type(
        self, db_create_host, host_type
    ):
        """Test that cluster is derived when openshift_cluster_id is set and explicit cluster type is present."""
        host = db_create_host(
            extra_data={"openshift_cluster_id": generate_uuid(), "system_profile_facts": {"host_type": host_type}}
        )
        assert host.host_type == "cluster"

    def test_derive_host_type_edge_explicit(self, db_create_host):
        """Test that explicit edge type is recognized."""
        host = db_create_host(extra_data={"system_profile_facts": {"host_type": "edge"}})

        assert host.host_type == "edge"
        assert host.static_system_profile.host_type == "edge"

    def test_derive_host_type_bootc_from_bootc_status(self, db_create_host):
        """Test that bootc is derived when bootc_status with image_digest is present."""
        host = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "bootc_status": {
                        "booted": {
                            "image_digest": "sha256:1234567890abcdef",
                            "image": "quay.io/example/edge-image:latest",
                        }
                    }
                }
            }
        )

        # When bootc_status is present, transformer sets host_type to 'bootc'
        assert host.host_type == "bootc"
        assert host.static_system_profile.bootc_status is not None

    def test_derive_host_type_no_system_profile(self, db_create_host):
        """Test host_type defaults to conventional when minimal system profile is provided."""
        host = db_create_host(extra_data={"system_profile_facts": {"number_of_cpus": 4}})

        # Should have static profile and default to conventional
        assert host.static_system_profile is not None
        assert host.host_type == "conventional"

    def test_host_type_updates_on_system_profile_change(self, db_create_host, db_get_host):
        """Test that host_type updates when system profile is updated."""
        # Create with edge
        host = db_create_host(extra_data={"system_profile_facts": {"host_type": "edge"}})

        initial_id = host.id
        assert host.host_type == "edge"

        # Update to cluster
        host.update_system_profile({"host_type": "cluster"})

        # Verify update
        assert host.host_type == "cluster"

        # Verify it persists after refresh
        updated_host = db_get_host(initial_id)
        assert updated_host.host_type == "cluster"

    def test_host_type_priority_cluster_with_bootc(self, db_create_host):
        """Test that explicit cluster type is used even with bootc_status."""
        host = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "host_type": "cluster",
                    "bootc_status": {"booted": {"image_digest": "sha256:test"}},
                }
            }
        )

        # Explicit cluster should be used
        assert host.host_type == "cluster"

    def test_host_type_bootc_from_bootc_status_fallback(self, db_create_host):
        """Test that bootc is derived when only bootc_status is present."""
        host = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "bootc_status": {"booted": {"image_digest": "sha256:edgeimage"}},
                    "number_of_cpus": 2,
                }
            }
        )

        # Should be bootc when bootc_status is present
        assert host.host_type == "bootc"

    def test_host_type_with_bootc_status_but_no_digest(self, db_create_host):
        """Test that bootc_status without image_digest defaults to conventional."""
        host = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "bootc_status": {
                        "booted": {
                            "image": "some-image"
                            # No image_digest
                        }
                    }
                }
            }
        )

        # Should default to conventional without image_digest
        assert host.host_type == "conventional"

    def test_host_type_with_empty_image_digest(self, db_create_host):
        """Test that bootc_status with empty image_digest defaults to conventional."""
        host = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "bootc_status": {
                        "booted": {
                            "image_digest": ""  # Empty string
                        }
                    }
                }
            }
        )

        # Should default to conventional with empty image_digest
        # Matches SYSTEM_TYPE_FILTERS logic: image_digest != ""
        assert host.host_type == "conventional"

    def test_host_type_persists_through_host_update(self, db_create_host):
        """Test that host_type is maintained correctly through Host.update()."""
        from app.models import Host

        # Create initial host with edge
        host = db_create_host(extra_data={"system_profile_facts": {"host_type": "edge"}})

        assert host.host_type == "edge"

        # Create update host with cluster type
        update_host = Host(
            insights_id=host.insights_id,
            reporter=host.reporter,
            org_id=host.org_id,
            system_profile_facts={"host_type": "cluster"},
        )

        # Apply update
        host.update(update_host, update_system_profile=True)

        # Verify host_type updated
        assert host.host_type == "cluster"

    def test_host_type_derivation_called_on_creation(self, db_create_host):
        """Test that _update_derived_host_type is called during host creation."""
        host = db_create_host(
            extra_data={"system_profile_facts": {"bootc_status": {"booted": {"image_digest": "sha256:test123"}}}}
        )

        # Should be derived immediately on creation (bootc when bootc_status present)
        assert host.host_type == "bootc"
        # Should not be None
        assert host.host_type is not None

    def test_host_type_not_overwritten_if_unchanged(self, db_create_host):
        """Test that host_type is only modified if it actually changes."""
        from unittest.mock import patch

        host = db_create_host(extra_data={"system_profile_facts": {"host_type": "edge"}})

        assert host.host_type == "edge"

        # Update with same type - should not trigger flag_modified
        with patch("sqlalchemy.orm.attributes.flag_modified") as mock_flag:
            host._update_derived_host_type()

            # Should not call flag_modified since value didn't change
            mock_flag.assert_not_called()

    def test_host_type_bootc_status_with_empty_booted(self, db_create_host):
        """Test bootc_status with empty booted dict."""
        host = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "bootc_status": {
                        "booted": {}  # Empty booted section
                    }
                }
            }
        )

        # Should not be bootc without image_digest
        assert host.host_type != "bootc"


class TestHostTypeBackwardCompatibilityMapping:
    """
    Tests for host_type backward compatibility in Kafka events.

    Context:
        Downstream apps (like cyndi) only recognize:
        - "edge" - Edge systems (special handling)
        - "" or other values - All other systems (conventional handling)

        New host_type values (bootc, conventional, cluster) are NOT recognized
        by downstream, so they must be mapped to empty string.
    """

    def test_map_edge_unchanged(self):
        """Test that 'edge' value is preserved."""
        result = _map_host_type_for_backward_compatibility("edge")
        assert result == "edge"

    def test_map_bootc_to_empty(self):
        """Test that 'bootc' is mapped to empty string (not recognized by downstream)."""
        result = _map_host_type_for_backward_compatibility("bootc")
        assert result == ""

    def test_map_cluster_to_empty(self):
        """Test that 'cluster' is mapped to empty string (not recognized by downstream)."""
        result = _map_host_type_for_backward_compatibility("cluster")
        assert result == ""

    def test_map_conventional_to_empty(self):
        """Test that 'conventional' is mapped to empty string."""
        result = _map_host_type_for_backward_compatibility("conventional")
        assert result == ""

    def test_map_none_to_empty(self):
        """Test that None is mapped to empty string."""
        result = _map_host_type_for_backward_compatibility(None)
        assert result == ""

    def test_map_unknown_to_empty(self):
        """Test that unknown values are mapped to empty string."""
        result = _map_host_type_for_backward_compatibility("unknown-type")
        assert result == ""

    def test_only_edge_is_preserved(self):
        """Test that ONLY 'edge' is preserved, everything else maps to empty."""
        # Only edge should map to "edge"
        assert _map_host_type_for_backward_compatibility("edge") == "edge"

        # Everything else should map to empty string
        non_edge_types = ["bootc", "cluster", "conventional", None, "", "unknown"]

        for host_type in non_edge_types:
            result = _map_host_type_for_backward_compatibility(host_type)
            assert result == "", f"{host_type} should map to '' since only 'edge' is recognized by downstream"
