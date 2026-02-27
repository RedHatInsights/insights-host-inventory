"""Unit tests for api/filtering/app_data_sorting.py module."""

from __future__ import annotations

import pytest

from api.filtering.app_data_sorting import get_app_sort_field_map
from api.filtering.app_data_sorting import resolve_app_sort
from app.models.host_app_data import HostAppDataAdvisor
from app.models.host_app_data import HostAppDataCompliance
from app.models.host_app_data import HostAppDataMalware
from app.models.host_app_data import HostAppDataPatch
from app.models.host_app_data import HostAppDataRemediations
from app.models.host_app_data import HostAppDataVulnerability


class TestResolveAppSort:
    """Tests for resolve_app_sort function."""

    # --- Valid fields return (model, column) ---

    def test_advisor_recommendations(self):
        """advisor:recommendations should resolve to correct model and column."""
        result = resolve_app_sort("advisor:recommendations")
        assert result is not None
        model, column = result
        assert model is HostAppDataAdvisor
        assert column.key == "recommendations"

    def test_vulnerability_critical_cves(self):
        """vulnerability:critical_cves should resolve to correct model and column."""
        result = resolve_app_sort("vulnerability:critical_cves")
        assert result is not None
        model, column = result
        assert model is HostAppDataVulnerability
        assert column.key == "critical_cves"

    def test_patch_advisories_rhsa_installable(self):
        """patch:advisories_rhsa_installable should resolve to correct model and column."""
        result = resolve_app_sort("patch:advisories_rhsa_installable")
        assert result is not None
        model, column = result
        assert model is HostAppDataPatch
        assert column.key == "advisories_rhsa_installable"

    def test_remediations_plans(self):
        """remediations:remediations_plans should resolve to correct model and column."""
        result = resolve_app_sort("remediations:remediations_plans")
        assert result is not None
        model, column = result
        assert model is HostAppDataRemediations
        assert column.key == "remediations_plans"

    def test_compliance_last_scan(self):
        """compliance:last_scan should resolve to correct model and column."""
        result = resolve_app_sort("compliance:last_scan")
        assert result is not None
        model, column = result
        assert model is HostAppDataCompliance
        assert column.key == "last_scan"

    def test_malware_last_matches(self):
        """malware:last_matches should resolve to correct model and column."""
        result = resolve_app_sort("malware:last_matches")
        assert result is not None
        model, column = result
        assert model is HostAppDataMalware
        assert column.key == "last_matches"

    # --- Non-app fields return None ---

    def test_none_returns_none(self):
        """None should return None."""
        assert resolve_app_sort(None) is None

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        assert resolve_app_sort("") is None

    def test_standard_host_field_returns_none(self):
        """Standard host fields like display_name should return None."""
        assert resolve_app_sort("display_name") is None
        assert resolve_app_sort("updated") is None
        assert resolve_app_sort("operating_system") is None

    # --- Invalid app:field format raises ValueError ---

    def test_invalid_app_field_raises_error(self):
        """Invalid app:field with colon should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported app sort field"):
            resolve_app_sort("advisor:invalid_field")

    def test_unknown_app_raises_error(self):
        """Unknown app name with colon should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported app sort field"):
            resolve_app_sort("unknown_app:field")

    def test_colon_only_raises_error(self):
        """Just a colon should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported app sort field"):
            resolve_app_sort(":")


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


class TestAppSortFieldMap:
    """Tests for get_app_sort_field_map() completeness.

    Each per-app test asserts exact set equality so that additions, removals,
    or renames of sortable fields are caught immediately.
    """

    def test_exact_advisor_fields(self):
        """Advisor sortable fields must match the expected contract exactly."""
        field_map = get_app_sort_field_map()
        advisor_keys = {k for k in field_map if k.startswith("advisor:")}
        assert advisor_keys == {
            "advisor:recommendations",
            "advisor:incidents",
            "advisor:critical",
            "advisor:important",
            "advisor:moderate",
            "advisor:low",
        }

    def test_exact_vulnerability_fields(self):
        """Vulnerability sortable fields must match the expected contract exactly."""
        field_map = get_app_sort_field_map()
        vuln_keys = {k for k in field_map if k.startswith("vulnerability:")}
        assert vuln_keys == {
            "vulnerability:total_cves",
            "vulnerability:critical_cves",
            "vulnerability:high_severity_cves",
            "vulnerability:cves_with_security_rules",
            "vulnerability:cves_with_known_exploits",
        }

    def test_exact_patch_fields(self):
        """Patch sortable fields must match the expected contract exactly."""
        field_map = get_app_sort_field_map()
        patch_keys = {k for k in field_map if k.startswith("patch:")}
        assert patch_keys == {
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
        }

    def test_exact_remediations_fields(self):
        """Remediations sortable fields must match the expected contract exactly."""
        field_map = get_app_sort_field_map()
        rem_keys = {k for k in field_map if k.startswith("remediations:")}
        assert rem_keys == {
            "remediations:remediations_plans",
        }

    def test_exact_compliance_fields(self):
        """Compliance sortable fields must match the expected contract exactly."""
        field_map = get_app_sort_field_map()
        comp_keys = {k for k in field_map if k.startswith("compliance:")}
        assert comp_keys == {
            "compliance:last_scan",
        }

    def test_exact_malware_fields(self):
        """Malware sortable fields must match the expected contract exactly."""
        field_map = get_app_sort_field_map()
        malware_keys = {k for k in field_map if k.startswith("malware:")}
        assert malware_keys == {
            "malware:last_matches",
            "malware:total_matches",
            "malware:last_scan",
        }

    def test_no_unexpected_app_namespaces(self):
        """The field map should only contain keys from known app namespaces."""
        field_map = get_app_sort_field_map()
        expected_prefixes = {"advisor", "vulnerability", "patch", "remediations", "compliance", "malware"}
        actual_prefixes = {k.split(":")[0] for k in field_map}
        assert actual_prefixes == expected_prefixes
