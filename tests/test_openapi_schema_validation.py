"""
Test OpenAPI schema validation consistency with backend Marshmallow schemas.

This test ensures that the OpenAPI specification validation constraints
match the backend validation logic to prevent frontend initialization issues.

Related to RHINENG-25439: Workspace Create Modal starts with invalid state.
"""

import pytest
import yaml
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate
from marshmallow import ValidationError as MarshmallowValidationError

from app.models import InputGroupSchema


def load_openapi_spec():
    """Load the OpenAPI specification."""
    with open("swagger/api.spec.yaml") as f:
        return yaml.safe_load(f)


def get_group_in_schema():
    """Extract the GroupIn schema from OpenAPI spec."""
    spec = load_openapi_spec()

    # Get the GroupIn schema
    group_in_schema = spec["components"]["schemas"]["GroupIn"]

    # Resolve the GroupName reference
    group_name_schema = spec["components"]["schemas"]["GroupName"]

    # Create a resolved schema for validation
    resolved_schema = {
        "type": "object",
        "required": group_in_schema.get("required", []),
        "properties": {"name": group_name_schema, "host_ids": spec["components"]["schemas"]["HostIds"]},
    }

    return resolved_schema


class TestOpenAPISchemaValidation:
    """Test that OpenAPI schema validation matches backend validation."""

    def test_group_name_validation_constraints_exist(self):
        """Test that GroupName schema has proper validation constraints."""
        spec = load_openapi_spec()
        group_name_schema = spec["components"]["schemas"]["GroupName"]

        # Verify validation constraints exist
        assert "minLength" in group_name_schema, "GroupName schema missing minLength constraint"
        assert "maxLength" in group_name_schema, "GroupName schema missing maxLength constraint"

        # Verify constraints match backend validation
        assert group_name_schema["minLength"] == 1, "GroupName minLength should be 1"
        assert group_name_schema["maxLength"] == 255, "GroupName maxLength should be 255"

        # Verify other properties
        assert group_name_schema["type"] == "string"
        assert group_name_schema["nullable"] is False

    def test_group_in_required_fields(self):
        """Test that GroupIn schema marks name as required."""
        spec = load_openapi_spec()
        group_in_schema = spec["components"]["schemas"]["GroupIn"]

        # Verify required field exists and includes name
        assert "required" in group_in_schema, "GroupIn schema missing required array"
        assert "name" in group_in_schema["required"], "GroupIn schema should require name field"

    @pytest.mark.parametrize(
        "test_data,backend_should_be_valid,openapi_should_be_valid",
        [
            # Valid cases for both
            ({"name": "valid-group"}, True, True),
            ({"name": "a"}, True, True),  # Minimum length
            ({"name": "a" * 255}, True, True),  # Maximum length
            ({"name": "valid-group", "host_ids": []}, True, True),
            # Backend allows empty dict (name is optional), but OpenAPI should require name for UI
            ({}, True, False),  # Missing name - backend allows, OpenAPI should reject for UI clarity
            # Both should reject invalid cases
            ({"name": ""}, False, False),  # Empty name (violates minLength: 1)
            ({"name": "a" * 256}, False, False),  # Too long (violates maxLength: 255)
        ],
    )
    def test_validation_behavior(self, test_data, backend_should_be_valid, openapi_should_be_valid):
        """Test validation behavior for both backend and OpenAPI."""

        # Test backend validation
        backend_valid = True
        try:
            InputGroupSchema().load(test_data)
        except MarshmallowValidationError:
            backend_valid = False

        # Test OpenAPI validation
        openapi_schema = get_group_in_schema()
        openapi_valid = True
        try:
            validate(instance=test_data, schema=openapi_schema)
        except JsonSchemaValidationError:
            openapi_valid = False

        # Check expected behavior
        assert backend_valid == backend_should_be_valid, f"Backend validation mismatch for {test_data}"
        assert openapi_valid == openapi_should_be_valid, f"OpenAPI validation mismatch for {test_data}"

    def test_specific_rhineng_25439_case(self):
        """Test the specific case from RHINENG-25439.

        The issue was that the frontend modal started with an invalid state
        (empty name) but showed the Create button as enabled. This suggests
        the frontend didn't know that the name field was required.

        The OpenAPI schema should make it clear that name is required for
        workspace creation, even if the backend schema is more lenient.
        """

        # Empty name should be invalid for OpenAPI (frontend needs this constraint)
        empty_name_data = {"name": ""}

        # Backend should reject empty name
        with pytest.raises(MarshmallowValidationError):
            InputGroupSchema().load(empty_name_data)

        # OpenAPI should also reject empty name due to minLength: 1
        openapi_schema = get_group_in_schema()
        with pytest.raises(JsonSchemaValidationError):
            validate(instance=empty_name_data, schema=openapi_schema)

        # Missing name should be invalid for OpenAPI (frontend needs this constraint)
        # even though backend allows it
        missing_name_data = {}

        # Backend allows missing name (it's optional in the schema)
        try:
            result = InputGroupSchema().load(missing_name_data)
            # This should succeed - backend allows optional name
        except MarshmallowValidationError:
            pytest.fail("Backend should allow missing name field")

        # OpenAPI should reject missing name due to required: [name]
        # This helps the frontend know that name is required for workspace creation
        with pytest.raises(JsonSchemaValidationError):
            validate(instance=missing_name_data, schema=openapi_schema)

    def test_frontend_form_validation_guidance(self):
        """Test that OpenAPI schema provides proper guidance for frontend form validation.

        This test ensures the OpenAPI schema gives the frontend enough information
        to properly initialize and validate the workspace creation form.
        """
        spec = load_openapi_spec()
        group_in_schema = spec["components"]["schemas"]["GroupIn"]
        group_name_schema = spec["components"]["schemas"]["GroupName"]

        # Frontend should know name is required
        assert "name" in group_in_schema.get("required", [])

        # Frontend should know name constraints
        assert group_name_schema.get("minLength") == 1
        assert group_name_schema.get("maxLength") == 255
        assert group_name_schema.get("type") == "string"

        # This information should prevent the frontend from:
        # 1. Starting with an enabled Create button when name is empty
        # 2. Showing confusing validation states
        # 3. Displaying em dashes or other placeholder content incorrectly
