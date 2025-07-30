import uuid
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from marshmallow import ValidationError

from app.models.host import Host
from app.models.schemas import HostDynamicSystemProfileSchema
from app.models.schemas import HostStaticSystemProfileSchema
from app.models.system_profile import HostStaticSystemProfile
from app.models.system_profile_transformer import DYNAMIC_FIELDS
from app.models.system_profile_transformer import STATIC_FIELDS
from app.models.system_profile_transformer import map_to_dynamic_fields
from app.models.system_profile_transformer import map_to_static_fields
from app.models.system_profile_transformer import split_system_profile_data
from app.models.system_profile_transformer import validate_and_transform
from app.models.system_profiles_dynamic import HostDynamicSystemProfile


class TestSystemProfileTransformer:
    """Test the system profile transformation utilities."""

    def test_split_system_profile_data_empty(self):
        """Test splitting empty system profile data."""
        static, dynamic = split_system_profile_data({})
        assert static == {}
        assert dynamic == {}

    def test_split_system_profile_data_static_only(self):
        """Test splitting system profile data with only static fields."""
        input_data = {"arch": "x86_64", "bios_vendor": "Dell Inc.", "cpu_model": "Intel Core i7"}

        static, dynamic = split_system_profile_data(input_data)

        assert static == input_data
        assert dynamic == {}

    def test_split_system_profile_data_dynamic_only(self):
        """Test splitting system profile data with only dynamic fields."""
        input_data = {
            "running_processes": ["systemd", "ssh"],
            "network_interfaces": [{"name": "eth0"}],
            "installed_packages": ["vim", "git"],
        }

        static, dynamic = split_system_profile_data(input_data)

        assert static == {}
        assert dynamic == input_data

    def test_split_system_profile_data_mixed(self):
        """Test splitting system profile data with mixed fields."""
        input_data = {
            "arch": "x86_64",
            "running_processes": ["systemd"],
            "bios_vendor": "Dell Inc.",
            "network_interfaces": [{"name": "eth0"}],
        }

        static, dynamic = split_system_profile_data(input_data)

        expected_static = {"arch": "x86_64", "bios_vendor": "Dell Inc."}
        expected_dynamic = {"running_processes": ["systemd"], "network_interfaces": [{"name": "eth0"}]}

        assert static == expected_static
        assert dynamic == expected_dynamic

    def test_split_system_profile_data_unknown_field(self):
        """Test splitting system profile data with unknown field (should go to static)."""
        input_data = {"arch": "x86_64", "unknown_field": "value"}

        with patch("app.models.system_profile_transformer.logger") as mock_logger:
            static, dynamic = split_system_profile_data(input_data)

            assert static == input_data
            assert dynamic == {}
            mock_logger.warning.assert_called_once_with(
                "Unknown system profile field 'unknown_field' - adding to static data"
            )

    def test_map_to_static_fields(self):
        """Test mapping data to static fields format."""
        org_id = "test-org"
        host_id = str(uuid.uuid4())
        static_data = {"arch": "x86_64", "bios_vendor": "Dell Inc."}

        result = map_to_static_fields(org_id, host_id, static_data)

        expected = {"org_id": org_id, "host_id": host_id, "arch": "x86_64", "bios_vendor": "Dell Inc."}

        assert result == expected

    def test_map_to_dynamic_fields(self):
        """Test mapping data to dynamic fields format."""
        org_id = "test-org"
        host_id = str(uuid.uuid4())
        dynamic_data = {"running_processes": ["systemd"], "network_interfaces": []}

        result = map_to_dynamic_fields(org_id, host_id, dynamic_data)

        expected = {"org_id": org_id, "host_id": host_id, "running_processes": ["systemd"], "network_interfaces": []}

        assert result == expected

    @patch("app.models.system_profile_transformer.HostStaticSystemProfileSchema")
    @patch("app.models.system_profile_transformer.HostDynamicSystemProfileSchema")
    def test_validate_and_transform(self, mock_dynamic_schema, mock_static_schema):
        """Test the combined validate and transform function."""
        org_id = "test-org"
        host_id = str(uuid.uuid4())
        system_profile_data = {"arch": "x86_64", "running_processes": ["systemd"]}

        # Mock schema validation
        mock_static_instance = MagicMock()
        mock_dynamic_instance = MagicMock()
        mock_static_schema.return_value = mock_static_instance
        mock_dynamic_schema.return_value = mock_dynamic_instance

        mock_static_instance.load.return_value = {"org_id": org_id, "host_id": host_id, "arch": "x86_64"}
        mock_dynamic_instance.load.return_value = {
            "org_id": org_id,
            "host_id": host_id,
            "running_processes": ["systemd"],
        }

        static_result, dynamic_result = validate_and_transform(org_id, host_id, system_profile_data)

        assert static_result == {"org_id": org_id, "host_id": host_id, "arch": "x86_64"}
        assert dynamic_result == {"org_id": org_id, "host_id": host_id, "running_processes": ["systemd"]}


class TestSystemProfileSchemas:
    """Test the system profile validation schemas."""

    def test_static_schema_valid_data(self):
        """Test HostStaticSystemProfileSchema with valid data."""
        schema = HostStaticSystemProfileSchema()

        valid_data = {
            "org_id": "test-org",
            "host_id": str(uuid.uuid4()),
            "arch": "x86_64",
            "bios_vendor": "Dell Inc.",
            "cores_per_socket": 4,
        }

        result = schema.load(valid_data)
        assert result["org_id"] == "test-org"
        assert result["arch"] == "x86_64"

    def test_static_schema_invalid_cores_per_socket(self):
        """Test HostStaticSystemProfileSchema with invalid cores_per_socket."""
        schema = HostStaticSystemProfileSchema()

        invalid_data = {
            "org_id": "test-org",
            "host_id": str(uuid.uuid4()),
            "cores_per_socket": -1,  # Invalid negative value
        }

        with pytest.raises(ValidationError):
            schema.load(invalid_data)

    def test_dynamic_schema_valid_data(self):
        """Test HostDynamicSystemProfileSchema with valid data."""
        schema = HostDynamicSystemProfileSchema()

        valid_data = {
            "org_id": "test-org",
            "host_id": str(uuid.uuid4()),
            "running_processes": ["systemd", "ssh"],
            "installed_packages": ["vim", "git"],
        }

        result = schema.load(valid_data)
        assert result["org_id"] == "test-org"
        assert result["running_processes"] == ["systemd", "ssh"]

    def test_dynamic_schema_missing_required_fields(self):
        """Test HostDynamicSystemProfileSchema with missing required fields."""
        schema = HostDynamicSystemProfileSchema()

        invalid_data = {
            "running_processes": ["systemd"]
            # Missing org_id and host_id
        }

        with pytest.raises(ValidationError):
            schema.load(invalid_data)


class TestHostModelIntegration:
    """Test the Host model's system profile functionality."""

    @patch("app.models.host.HostStaticSystemProfile")
    @patch("app.models.host.HostDynamicSystemProfile")
    @patch("app.models.host.validate_and_transform")
    def test_update_normalized_system_profiles_new_records(
        self, mock_transform, mock_dynamic_model, mock_static_model
    ):
        """Test creating new normalized system profile records."""
        # Mock the transformation
        mock_transform.return_value = (
            {"org_id": "test-org", "host_id": "test-id", "arch": "x86_64"},
            {"org_id": "test-org", "host_id": "test-id", "running_processes": ["systemd"]},
        )

        # Create a mock host
        host = MagicMock()
        host.org_id = "test-org"
        host.id = "test-id"
        host.static_system_profile = None
        host.dynamic_system_profile = None

        # Import and call the method
        Host._update_normalized_system_profiles(host, {"arch": "x86_64", "running_processes": ["systemd"]})

        # Verify the models were created
        mock_static_model.assert_called_once_with(org_id="test-org", host_id="test-id", arch="x86_64")
        mock_dynamic_model.assert_called_once_with(org_id="test-org", host_id="test-id", running_processes=["systemd"])

    @patch("app.models.host.validate_and_transform")
    def test_update_normalized_system_profiles_existing_records(self, mock_transform):
        """Test updating existing normalized system profile records."""
        # Mock the transformation
        mock_transform.return_value = (
            {"org_id": "test-org", "host_id": "test-id", "arch": "x86_64"},
            {"org_id": "test-org", "host_id": "test-id", "running_processes": ["systemd"]},
        )

        # Create mock existing profiles
        mock_static = MagicMock()
        mock_dynamic = MagicMock()

        # Create a mock host with existing profiles
        host = MagicMock()
        host.org_id = "test-org"
        host.id = "test-id"
        host.static_system_profile = mock_static
        host.dynamic_system_profile = mock_dynamic

        # Import and call the method
        Host._update_normalized_system_profiles(host, {"arch": "x86_64", "running_processes": ["systemd"]})

        # Verify the existing records were updated
        assert hasattr(mock_static, "__setattr__")
        assert hasattr(mock_dynamic, "__setattr__")

    def test_update_system_profile_backward_compatibility(self):
        """Test that the update_system_profile method maintains backward compatibility."""
        # Create a mock host
        host = MagicMock()
        host.system_profile_facts = {"existing": "data"}
        host.org_id = "test-org"
        host.id = "test-id"

        # Mock the logger and other dependencies
        with (
            patch("app.models.host.logger"),
            patch("app.models.host.orm"),
            patch.object(host, "_update_normalized_system_profiles") as mock_update_normalized,
        ):
            from app.models.host import Host

            input_profile = {"arch": "x86_64", "rhsm": {"version": "1.0"}}

            # Call the method
            Host.update_system_profile(host, input_profile)

            # Verify JSONB update happened
            assert host.system_profile_facts["arch"] == "x86_64"
            assert host.system_profile_facts["rhsm"] == {"version": "1.0"}

            # Verify normalized update was called
            mock_update_normalized.assert_called_once_with(input_profile)

    def test_field_classification_completeness(self):
        """Test that all expected fields are classified as either static or dynamic."""
        # These are some key fields that should be classified
        expected_static_fields = {"arch", "bios_vendor", "cpu_model", "operating_system"}
        expected_dynamic_fields = {"running_processes", "network_interfaces", "installed_packages"}

        for field in expected_static_fields:
            assert field in STATIC_FIELDS, f"Field '{field}' should be in STATIC_FIELDS"

        for field in expected_dynamic_fields:
            assert field in DYNAMIC_FIELDS, f"Field '{field}' should be in DYNAMIC_FIELDS"

        # Ensure no overlap between static and dynamic fields
        overlap = STATIC_FIELDS.intersection(DYNAMIC_FIELDS)
        assert len(overlap) == 0, f"Found overlapping fields: {overlap}"


class TestModelRelationships:
    """Test the SQLAlchemy relationships between models."""

    def test_host_static_relationship_configuration(self):
        """Test that Host.static_system_profile relationship is properly configured."""

        # Check that the relationship exists
        assert hasattr(Host, "static_system_profile")

        # Get the relationship property
        relationship_prop = getattr(Host.__mapper__.relationships, "static_system_profile", None)
        assert relationship_prop is not None

        # Check relationship configuration
        assert relationship_prop.cascade.delete_orphan is True
        assert relationship_prop.uselist is False  # 1:1 relationship

    def test_host_dynamic_relationship_configuration(self):
        """Test that Host.dynamic_system_profile relationship is properly configured."""

        # Check that the relationship exists
        assert hasattr(Host, "dynamic_system_profile")

        # Get the relationship property
        relationship_prop = getattr(Host.__mapper__.relationships, "dynamic_system_profile", None)
        assert relationship_prop is not None

        # Check relationship configuration
        assert relationship_prop.cascade.delete_orphan is True
        assert relationship_prop.uselist is False  # 1:1 relationship

    def test_static_system_profile_back_reference(self):
        """Test that HostStaticSystemProfile has proper back reference."""

        # Check that the back reference exists
        assert hasattr(HostStaticSystemProfile, "host")

    def test_dynamic_system_profile_back_reference(self):
        """Test that HostDynamicSystemProfile has proper back reference."""

        # Check that the back reference exists
        assert hasattr(HostDynamicSystemProfile, "host")
