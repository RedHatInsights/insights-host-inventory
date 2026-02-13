"""Unit tests for api/filtering/app_data_sorting.py module."""

from __future__ import annotations

import pytest

from api.filtering.app_data_sorting import get_app_sort_field_map
from api.filtering.app_data_sorting import get_app_sort_model
from api.filtering.app_data_sorting import get_app_sort_model_and_column
from api.filtering.app_data_sorting import is_app_sort_field
from app.models.host_app_data import HostAppDataAdvisor
from app.models.host_app_data import HostAppDataCompliance
from app.models.host_app_data import HostAppDataMalware
from app.models.host_app_data import HostAppDataPatch
from app.models.host_app_data import HostAppDataRemediations
from app.models.host_app_data import HostAppDataVulnerability


class TestIsAppSortField:
    """Tests for is_app_sort_field function."""

    def test_valid_advisor_field(self):
        """Valid advisor:recommendations should return True."""
        assert is_app_sort_field("advisor:recommendations") is True

    def test_valid_vulnerability_field(self):
        """Valid vulnerability:critical_cves should return True."""
        assert is_app_sort_field("vulnerability:critical_cves") is True

    def test_valid_patch_field(self):
        """Valid patch:advisories_rhsa_installable should return True."""
        assert is_app_sort_field("patch:advisories_rhsa_installable") is True

    def test_valid_remediations_field(self):
        """Valid remediations:remediations_plans should return True."""
        assert is_app_sort_field("remediations:remediations_plans") is True

    def test_valid_compliance_field(self):
        """Valid compliance:last_scan should return True."""
        assert is_app_sort_field("compliance:last_scan") is True

    def test_valid_malware_field(self):
        """Valid malware:last_matches should return True."""
        assert is_app_sort_field("malware:last_matches") is True

    def test_none_returns_false(self):
        """None should return False."""
        assert is_app_sort_field(None) is False

    def test_standard_host_field_returns_false(self):
        """Standard host fields like display_name should return False."""
        assert is_app_sort_field("display_name") is False
        assert is_app_sort_field("updated") is False
        assert is_app_sort_field("operating_system") is False

    def test_invalid_app_field_returns_false(self):
        """Invalid app:field combinations should return False."""
        assert is_app_sort_field("advisor:invalid_field") is False
        assert is_app_sort_field("unknown_app:field") is False

    def test_empty_string_returns_false(self):
        """Empty string should return False."""
        assert is_app_sort_field("") is False

    def test_colon_only_returns_false(self):
        """Just a colon should return False."""
        assert is_app_sort_field(":") is False


def parse_app_sort_field(order_by: str) -> tuple[str, str]:
    """
    Parse an app sort field into its app name and field name components.

    This function is only used for testing purposes.

    Args:
        order_by: The order_by parameter value (e.g., "vulnerability:critical_cves")

    Returns:
        Tuple of (app_name, field_name)

    Raises:
        ValueError: If order_by is not in valid app:field format
    """
    if ":" not in order_by:
        raise ValueError(f"Invalid app sort field format: '{order_by}'. Expected 'app:field' format.")

    parts = order_by.split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid app sort field format: '{order_by}'. Expected 'app:field' format.")

    return parts[0], parts[1]


class TestParseAppSortField:
    """Tests for parse_app_sort_field function."""

    def test_parse_valid_field(self):
        """Valid app:field should parse correctly."""
        app_name, field_name = parse_app_sort_field("vulnerability:critical_cves")
        assert app_name == "vulnerability"
        assert field_name == "critical_cves"

    def test_parse_advisor_field(self):
        """Advisor field should parse correctly."""
        app_name, field_name = parse_app_sort_field("advisor:recommendations")
        assert app_name == "advisor"
        assert field_name == "recommendations"

    def test_no_colon_raises_error(self):
        """Field without colon should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid app sort field format"):
            parse_app_sort_field("display_name")

    def test_empty_app_name_raises_error(self):
        """Empty app name should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid app sort field format"):
            parse_app_sort_field(":field_name")

    def test_empty_field_name_raises_error(self):
        """Empty field name should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid app sort field format"):
            parse_app_sort_field("app_name:")

    def test_field_with_multiple_colons(self):
        """Field with multiple colons should only split on first."""
        app_name, field_name = parse_app_sort_field("app:field:with:colons")
        assert app_name == "app"
        assert field_name == "field:with:colons"


class TestGetAppSortModelAndColumn:
    """Tests for get_app_sort_model_and_column function."""

    def test_advisor_recommendations(self):
        """advisor:recommendations should return correct model and column."""
        model, column = get_app_sort_model_and_column("advisor:recommendations")
        assert model is HostAppDataAdvisor
        assert column.key == "recommendations"

    def test_vulnerability_critical_cves(self):
        """vulnerability:critical_cves should return correct model and column."""
        model, column = get_app_sort_model_and_column("vulnerability:critical_cves")
        assert model is HostAppDataVulnerability
        assert column.key == "critical_cves"

    def test_patch_advisories_rhsa_installable(self):
        """patch:advisories_rhsa_installable should return correct model and column."""
        model, column = get_app_sort_model_and_column("patch:advisories_rhsa_installable")
        assert model is HostAppDataPatch
        assert column.key == "advisories_rhsa_installable"

    def test_remediations_plans(self):
        """remediations:remediations_plans should return correct model and column."""
        model, column = get_app_sort_model_and_column("remediations:remediations_plans")
        assert model is HostAppDataRemediations
        assert column.key == "remediations_plans"

    def test_compliance_last_scan(self):
        """compliance:last_scan should return correct model and column."""
        model, column = get_app_sort_model_and_column("compliance:last_scan")
        assert model is HostAppDataCompliance
        assert column.key == "last_scan"

    def test_malware_last_matches(self):
        """malware:last_matches should return correct model and column."""
        model, column = get_app_sort_model_and_column("malware:last_matches")
        assert model is HostAppDataMalware
        assert column.key == "last_matches"

    def test_invalid_field_raises_error(self):
        """Invalid app sort field should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported app sort field"):
            get_app_sort_model_and_column("invalid:field")

    def test_standard_field_raises_error(self):
        """Standard host field should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported app sort field"):
            get_app_sort_model_and_column("display_name")


class TestGetAppSortModel:
    """Tests for get_app_sort_model function."""

    def test_advisor_model(self):
        """advisor:recommendations should return HostAppDataAdvisor."""
        model = get_app_sort_model("advisor:recommendations")
        assert model is HostAppDataAdvisor

    def test_vulnerability_model(self):
        """vulnerability:critical_cves should return HostAppDataVulnerability."""
        model = get_app_sort_model("vulnerability:critical_cves")
        assert model is HostAppDataVulnerability

    def test_patch_model(self):
        """patch:advisories_rhsa_installable should return HostAppDataPatch."""
        model = get_app_sort_model("patch:advisories_rhsa_installable")
        assert model is HostAppDataPatch

    def test_invalid_field_raises_error(self):
        """Invalid app sort field should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported app sort field"):
            get_app_sort_model("invalid:field")


class TestAppSortFieldMap:
    """Tests for get_app_sort_field_map() completeness."""

    def test_all_advisor_fields_present(self):
        """All expected advisor fields should be in the map."""
        assert "advisor:recommendations" in get_app_sort_field_map()
        assert "advisor:incidents" in get_app_sort_field_map()

    def test_all_vulnerability_fields_present(self):
        """All expected vulnerability fields should be in the map."""
        expected_fields = [
            "vulnerability:total_cves",
            "vulnerability:critical_cves",
            "vulnerability:high_severity_cves",
            "vulnerability:cves_with_security_rules",
            "vulnerability:cves_with_known_exploits",
        ]
        for field in expected_fields:
            assert field in get_app_sort_field_map()

    def test_all_patch_fields_present(self):
        """All expected patch fields should be in the map."""
        expected_fields = [
            "patch:advisories_rhsa_installable",
            "patch:advisories_rhba_installable",
            "patch:advisories_rhea_installable",
            "patch:advisories_other_installable",
            "patch:advisories_rhsa_applicable",
            "patch:advisories_rhba_applicable",
            "patch:advisories_rhea_applicable",
            "patch:advisories_other_applicable",
            "patch:packages_installable",
            "patch:packages_applicable",
            "patch:packages_installed",
        ]
        for field in expected_fields:
            assert field in get_app_sort_field_map()

    def test_all_compliance_fields_present(self):
        """All expected compliance fields should be in the map."""
        assert "compliance:last_scan" in get_app_sort_field_map()

    def test_all_malware_fields_present(self):
        """All expected malware fields should be in the map."""
        assert "malware:last_matches" in get_app_sort_field_map()
        assert "malware:total_matches" in get_app_sort_field_map()
        assert "malware:last_scan" in get_app_sort_field_map()

    def test_remediations_field_present(self):
        """Remediations field should be in the map."""
        assert "remediations:remediations_plans" in get_app_sort_field_map()
