from copy import deepcopy
from http import HTTPStatus

from tests.helpers.api_utils import GROUP_URL
from tests.helpers.api_utils import assert_response_status
from tests.helpers.test_utils import SYSTEM_IDENTITY


class TestGroupNameValidation:
    """Test cases for the group name validation endpoint."""

    def test_validate_valid_name(self, api_get):
        """Test validation of a valid, available group name."""
        url = f"{GROUP_URL}/validate-name"
        response_status, response_data = api_get(url, query_parameters={"name": "valid-group-name"})

        assert_response_status(response_status, HTTPStatus.OK)

        assert response_data["valid"] is True
        assert response_data["name"] == "valid-group-name"
        assert "available" in response_data["message"].lower()

    def test_validate_existing_name(self, api_get, db_create_group):
        """Test validation of a name that already exists."""
        # Create a group first
        db_create_group("existing-group")

        url = f"{GROUP_URL}/validate-name"
        response_status, response_data = api_get(url, query_parameters={"name": "existing-group"})

        assert_response_status(response_status, HTTPStatus.OK)

        assert response_data["valid"] is False
        assert response_data["error"] == "name_exists"
        assert response_data["name"] == "existing-group"
        assert "already exists" in response_data["message"]

    def test_validate_empty_name(self, api_get):
        """Test validation of an empty name - should be rejected by OpenAPI validation."""
        url = f"{GROUP_URL}/validate-name"
        response_status, response_data = api_get(url, query_parameters={"name": ""})

        # OpenAPI validation should reject empty strings before reaching our endpoint
        assert_response_status(response_status, HTTPStatus.BAD_REQUEST)

    def test_validate_whitespace_only_name(self, api_get):
        """Test validation of a name with only whitespace."""
        url = f"{GROUP_URL}/validate-name"
        response_status, response_data = api_get(url, query_parameters={"name": "   "})

        assert_response_status(response_status, HTTPStatus.OK)

        assert response_data["valid"] is False
        assert response_data["error"] == "validation_error"

    def test_validate_name_with_leading_trailing_whitespace(self, api_get):
        """Test validation of a name with leading/trailing whitespace."""
        url = f"{GROUP_URL}/validate-name"
        response_status, response_data = api_get(url, query_parameters={"name": "  valid-name  "})

        assert_response_status(response_status, HTTPStatus.OK)

        assert response_data["valid"] is True
        assert response_data["name"] == "valid-name"  # Should be trimmed
        assert "available" in response_data["message"].lower()

    def test_validate_too_long_name(self, api_get):
        """Test validation of a name that exceeds maximum length - should be rejected by OpenAPI validation."""
        long_name = "a" * 256  # Exceeds 255 character limit
        url = f"{GROUP_URL}/validate-name"
        response_status, response_data = api_get(url, query_parameters={"name": long_name})

        # OpenAPI validation should reject too-long strings before reaching our endpoint
        assert_response_status(response_status, HTTPStatus.BAD_REQUEST)

    def test_validate_name_missing_parameter(self, api_get):
        """Test validation endpoint without name parameter."""
        url = f"{GROUP_URL}/validate-name"
        response_status, response_data = api_get(url)

        assert_response_status(response_status, HTTPStatus.BAD_REQUEST)

    def test_validate_name_case_insensitive_check(self, api_get, db_create_group):
        """Test that name existence check is case-insensitive."""
        # Create a group with lowercase name
        db_create_group("lowercase-group")

        url = f"{GROUP_URL}/validate-name"
        response_status, response_data = api_get(url, query_parameters={"name": "LOWERCASE-GROUP"})

        assert_response_status(response_status, HTTPStatus.OK)

        assert response_data["valid"] is False
        assert response_data["error"] == "name_exists"
        assert "already exists" in response_data["message"]

    def test_validate_name_different_org_isolation(self, api_get, db_create_group):
        """Test that groups from different orgs don't conflict."""
        # Create a group in the default org
        db_create_group("shared-name")

        # Test with a different org_id
        different_identity = deepcopy(SYSTEM_IDENTITY)
        different_identity["org_id"] = "different-org"
        different_identity["account"] = "different-account"

        url = f"{GROUP_URL}/validate-name"
        response_status, response_data = api_get(
            url, query_parameters={"name": "shared-name"}, identity=different_identity
        )

        assert_response_status(response_status, HTTPStatus.OK)

        # Should be valid since it's a different org
        assert response_data["valid"] is True
        assert response_data["name"] == "shared-name"
