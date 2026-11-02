from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_view_url
from tests.helpers.db_utils import db_create_host_app_data

_APP_FILTER_CASES = [
    pytest.param("patch", "advisories_rhsa_installable", 5, 10, id="patch-advisories_rhsa_installable"),
    pytest.param("advisor", "recommendations", 3, 8, id="advisor-recommendations"),
    pytest.param("vulnerability", "total_cves", 10, 20, id="vulnerability-total_cves"),
    pytest.param("vulnerability", "moderate_cves", 4, 9, id="vulnerability-moderate_cves"),
    pytest.param("vulnerability", "low_cves", 2, 6, id="vulnerability-low_cves"),
    pytest.param("remediations", "remediations_plans", 3, 7, id="remediations-remediations_plans"),
    pytest.param("malware", "last_matches", 0, 5, id="malware-last_matches"),
    pytest.param(
        "malware",
        "last_scan",
        datetime(2024, 3, 1, 10, 0, 0, tzinfo=UTC),
        datetime(2024, 9, 15, 10, 0, 0, tzinfo=UTC),
        id="malware-last_scan",
    ),
    pytest.param(
        "compliance",
        "last_scan",
        datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        id="compliance-last_scan",
    ),
]
_VALUE_OPERATORS = [
    pytest.param("eq", "a", "a", id="eq"),
    pytest.param("ne", "a", "b", id="ne"),
    pytest.param("gt", "a", "b", id="gt"),
    pytest.param("gte", "a", "a,b", id="gte"),
    pytest.param("lt", "b", "a", id="lt"),
    pytest.param("lte", "a", "a", id="lte"),
    pytest.param("gt", "b", "", id="gt-none"),
]


def _to_url_value(v):
    """Format a value for use in a query string parameter."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(v)


class TestHostViewSystemProfileFilters:
    """Test system_profile filtering on the /beta/hosts-view endpoint."""

    @pytest.mark.parametrize(
        "operator,filter_value,match_a,match_b",
        [
            ("eq", "5", True, False),
            ("ne", "5", False, True),
            ("gt", "5", False, True),
            ("gte", "5", True, True),
            ("lt", "10", True, False),
            ("lte", "5", True, False),
        ],
    )
    def test_filter_integer_operators(self, api_get, db_create_host, operator, filter_value, match_a, match_b):
        """Validate all comparison operators on an integer system_profile field."""
        host_a = db_create_host(extra_data={"system_profile_facts": {"number_of_cpus": 5}})
        host_a_id = str(host_a.id)
        host_b = db_create_host(extra_data={"system_profile_facts": {"number_of_cpus": 10}})
        host_b_id = str(host_b.id)

        url = build_host_view_url(query=f"?filter[system_profile][number_of_cpus][{operator}]={filter_value}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        response_ids = [r["id"] for r in response_data["results"]]
        assert (host_a_id in response_ids) == match_a
        assert (host_b_id in response_ids) == match_b

    def test_filter_nil_operator(self, api_get, db_create_host):
        """Filter by nil returns hosts where the field is null."""
        match_host = db_create_host(extra_data={"system_profile_facts": {}})
        match_host_id = str(match_host.id)
        nomatch_host = db_create_host(extra_data={"system_profile_facts": {"host_type": "edge"}})
        nomatch_host_id = str(nomatch_host.id)

        url = build_host_view_url(query="?filter[system_profile][host_type][eq]=nil")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        response_ids = [r["id"] for r in response_data["results"]]
        assert match_host_id in response_ids
        assert nomatch_host_id not in response_ids

    def test_filter_not_nil_operator(self, api_get, db_create_host):
        """Filter by not_nil returns hosts where the field is set."""
        nomatch_host = db_create_host(extra_data={"system_profile_facts": {}})
        nomatch_host_id = str(nomatch_host.id)
        match_host = db_create_host(extra_data={"system_profile_facts": {"host_type": "edge"}})
        match_host_id = str(match_host.id)

        url = build_host_view_url(query="?filter[system_profile][host_type][eq]=not_nil")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        response_ids = [r["id"] for r in response_data["results"]]
        assert match_host_id in response_ids
        assert nomatch_host_id not in response_ids

    def test_filter_string_field(self, api_get, db_create_host):
        """Filter by system_profile string field (arch eq)."""
        match_host = db_create_host(extra_data={"system_profile_facts": {"arch": "x86_64"}})
        match_host_id = str(match_host.id)
        nomatch_host = db_create_host(extra_data={"system_profile_facts": {"arch": "s390x"}})
        nomatch_host_id = str(nomatch_host.id)

        url = build_host_view_url(query="?filter[system_profile][arch][eq]=x86_64")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        response_ids = [r["id"] for r in response_data["results"]]
        assert match_host_id in response_ids
        assert nomatch_host_id not in response_ids

    def test_filter_boolean_field(self, api_get, db_create_host):
        """Filter by system_profile boolean field (is_marketplace)."""
        match_host = db_create_host(extra_data={"system_profile_facts": {"is_marketplace": True}})
        match_host_id = str(match_host.id)
        nomatch_host = db_create_host(extra_data={"system_profile_facts": {"is_marketplace": False}})
        nomatch_host_id = str(nomatch_host.id)

        url = build_host_view_url(query="?filter[system_profile][is_marketplace][eq]=true")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        response_ids = [r["id"] for r in response_data["results"]]
        assert match_host_id in response_ids
        assert nomatch_host_id not in response_ids

    def test_filter_jsonb_field(self, api_get, db_create_host):
        """Filter JSONB column (system_purpose) by nil/not_nil."""
        host_with_sp = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "system_purpose": {"role": "server", "usage": "Production"},
                }
            }
        )
        host_with_sp_id = str(host_with_sp.id)
        host_without_sp = db_create_host(extra_data={"system_profile_facts": {}})
        host_without_sp_id = str(host_without_sp.id)

        # not_nil should return only the host with system_purpose set
        url = build_host_view_url(query="?filter[system_profile][system_purpose][eq]=not_nil")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        response_ids = [r["id"] for r in response_data["results"]]
        assert host_with_sp_id in response_ids
        assert host_without_sp_id not in response_ids

        # nil should return only the host without system_purpose
        url = build_host_view_url(query="?filter[system_profile][system_purpose][eq]=nil")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        response_ids = [r["id"] for r in response_data["results"]]
        assert host_without_sp_id in response_ids
        assert host_with_sp_id not in response_ids

    def test_filter_combined_with_display_name(self, api_get, db_create_host):
        """System profile filter combined with display_name filter."""
        match_host = db_create_host(
            extra_data={
                "display_name": "target-host.example.com",
                "system_profile_facts": {"arch": "x86_64"},
            }
        )
        match_host_id = str(match_host.id)
        db_create_host(
            extra_data={
                "display_name": "other-host.example.com",
                "system_profile_facts": {"arch": "x86_64"},
            }
        )
        db_create_host(
            extra_data={
                "display_name": "target-host-2.example.com",
                "system_profile_facts": {"arch": "s390x"},
            }
        )

        url = build_host_view_url(query="?display_name=target-host&filter[system_profile][arch][eq]=x86_64")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        response_ids = [r["id"] for r in response_data["results"]]
        assert match_host_id in response_ids

    def test_filter_returns_app_data(self, api_get, db_create_host, db_create_host_app_data):
        """Filtered results should still include app_data."""
        host = db_create_host(extra_data={"system_profile_facts": {"arch": "x86_64"}})
        db_create_host_app_data(
            host.id,
            host.org_id,
            "advisor",
            recommendations=5,
            incidents=2,
            critical=3,
            important=2,
            moderate=0,
            low=0,
        )

        url = build_host_view_url(query="?filter[system_profile][arch][eq]=x86_64")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "app_data" in result
        assert result["app_data"]["advisor"]["recommendations"] == 5
        assert result["app_data"]["advisor"]["incidents"] == 2
        assert result["app_data"]["advisor"]["critical"] == 3
        assert result["app_data"]["advisor"]["important"] == 2
        assert result["app_data"]["advisor"]["moderate"] == 0
        assert result["app_data"]["advisor"]["low"] == 0

    def test_filter_combined_system_profile_and_app_data(self, api_get, db_create_host, db_create_host_app_data):
        """System profile and app data filters can be used together."""
        # Host that matches both filters
        match_host = db_create_host(extra_data={"system_profile_facts": {"arch": "x86_64"}})
        match_host_id = str(match_host.id)
        db_create_host_app_data(match_host.id, match_host.org_id, "patch", advisories_rhsa_installable=5)

        # Host that matches system_profile but has no patch data
        sp_only_host = db_create_host(extra_data={"system_profile_facts": {"arch": "x86_64"}})
        sp_only_host_id = str(sp_only_host.id)

        # Host that matches patch filter but not system_profile
        patch_only_host = db_create_host(extra_data={"system_profile_facts": {"arch": "s390x"}})
        db_create_host_app_data(patch_only_host.id, patch_only_host.org_id, "patch", advisories_rhsa_installable=3)
        patch_only_host_id = str(patch_only_host.id)

        url = build_host_view_url(
            query="?filter[system_profile][arch][eq]=x86_64&filter[patch][advisories_rhsa_installable][not_nil]=true"
        )
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        response_ids = [r["id"] for r in response_data["results"]]
        assert match_host_id in response_ids
        assert sp_only_host_id not in response_ids
        assert patch_only_host_id not in response_ids

    def test_filter_invalid_key_returns_400(self, api_get, db_create_host):
        """Invalid filter key should return 400."""
        db_create_host()

        url = build_host_view_url(query="?filter[invalid_key][field]=value")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 400)


class TestHostViewAppDataFilters:
    """Parametrized tests for app_data filtering across all apps."""

    @pytest.mark.parametrize("app_name,field_name,value_a,value_b", _APP_FILTER_CASES)
    @pytest.mark.parametrize("operator,compare_against,expected_ids", _VALUE_OPERATORS)
    def test_app_data_value_operators(
        self,
        api_get,
        db_create_host,
        db_create_host_app_data,
        app_name,
        field_name,
        value_a,
        value_b,
        operator,
        compare_against,
        expected_ids,
    ):
        """Parametrized test for all value operators across all app/field combinations."""
        host_a = db_create_host(extra_data={"display_name": "host-a.example.com"})
        host_a_id = str(host_a.id)
        host_b = db_create_host(extra_data={"display_name": "host-b.example.com"})
        host_b_id = str(host_b.id)

        db_create_host_app_data(host_a_id, host_a.org_id, app_name, **{field_name: value_a})
        db_create_host_app_data(host_b_id, host_b.org_id, app_name, **{field_name: value_b})

        compare_value = _to_url_value(value_a if compare_against == "a" else value_b)
        url = build_host_view_url(query=f"?filter[{app_name}][{field_name}][{operator}]={compare_value}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)

        result_ids = {str(r["id"]) for r in response_data["results"]}
        expected = set()
        if "a" in expected_ids:
            expected.add(host_a_id)
        if "b" in expected_ids:
            expected.add(host_b_id)
        assert result_ids == expected

    @pytest.mark.parametrize("app_name,field_name,value_a,value_b", _APP_FILTER_CASES)
    def test_app_data_nil(
        self,
        api_get,
        db_create_host,
        db_create_host_app_data,
        app_name,
        field_name,
        value_a,
        value_b,  # noqa: ARG002
    ):
        """nil operator returns hosts without app data (or with NULL field)."""
        host_with = db_create_host(extra_data={"display_name": "host-with.example.com"})
        host_with_id = str(host_with.id)
        host_without = db_create_host(extra_data={"display_name": "host-without.example.com"})
        host_without_id = str(host_without.id)

        db_create_host_app_data(host_with_id, host_with.org_id, app_name, **{field_name: value_a})

        url = build_host_view_url(query=f"?filter[{app_name}][{field_name}][nil]=true")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_ids = {str(r["id"]) for r in response_data["results"]}
        assert host_without_id in result_ids
        assert host_with_id not in result_ids

    @pytest.mark.parametrize("app_name,field_name,value_a,value_b", _APP_FILTER_CASES)
    def test_app_data_not_nil(
        self,
        api_get,
        db_create_host,
        db_create_host_app_data,
        app_name,
        field_name,
        value_a,
        value_b,  # noqa: ARG002
    ):
        """not_nil operator returns only hosts with non-NULL app data field."""
        host_with = db_create_host(extra_data={"display_name": "host-with.example.com"})
        host_with_id = str(host_with.id)
        host_without = db_create_host(extra_data={"display_name": "host-without.example.com"})
        host_without_id = str(host_without.id)

        db_create_host_app_data(host_with_id, host_with.org_id, app_name, **{field_name: value_a})

        url = build_host_view_url(query=f"?filter[{app_name}][{field_name}][not_nil]=true")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_ids = {str(r["id"]) for r in response_data["results"]}
        assert host_with_id in result_ids
        assert host_without_id not in result_ids


class TestHostViewAppDataFiltersPatchSpecific:
    """Tests for patch/malware-specific filter behaviors not covered by the parametrized matrix."""

    def test_filter_patch_string_field(self, api_get, db_create_host, db_create_host_app_data):
        """Filter on string field template_name with eq operator."""
        host_a = db_create_host(extra_data={"display_name": "host-a.example.com"})
        host_a_id = str(host_a.id)
        host_a_org_id = host_a.org_id
        host_b = db_create_host(extra_data={"display_name": "host-b.example.com"})
        host_b_id = str(host_b.id)
        host_b_org_id = host_b.org_id

        db_create_host_app_data(host_a_id, host_a_org_id, "patch", template_name="production")
        db_create_host_app_data(host_b_id, host_b_org_id, "patch", template_name="staging")

        url = build_host_view_url(query="?filter[patch][template_name][eq]=production")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert str(response_data["results"][0]["id"]) == host_a_id

    def test_filter_patch_combined_with_display_name(self, api_get, db_create_host, db_create_host_app_data):
        """App data filter combined with display_name filter."""
        host_a = db_create_host(extra_data={"display_name": "matching-host.example.com"})
        host_a_id = str(host_a.id)
        host_a_org_id = host_a.org_id
        host_b = db_create_host(extra_data={"display_name": "other-host.example.com"})
        host_b_id = str(host_b.id)
        host_b_org_id = host_b.org_id

        db_create_host_app_data(host_a_id, host_a_org_id, "patch", advisories_rhsa_installable=10)
        db_create_host_app_data(host_b_id, host_b_org_id, "patch", advisories_rhsa_installable=10)

        # Both hosts match the patch filter, but only one matches the display_name filter
        url = build_host_view_url(
            query="?filter[patch][advisories_rhsa_installable][gte]=5&display_name=matching-host"
        )
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert str(response_data["results"][0]["id"]) == host_a_id

    def test_filter_patch_multiple_fields(self, api_get, db_create_host, db_create_host_app_data):
        """Multiple fields on same app: both conditions must match (AND)."""
        host_a = db_create_host(extra_data={"display_name": "host-a.example.com"})
        host_a_id = str(host_a.id)
        host_a_org_id = host_a.org_id
        host_b = db_create_host(extra_data={"display_name": "host-b.example.com"})
        host_b_id = str(host_b.id)
        host_b_org_id = host_b.org_id

        db_create_host_app_data(
            host_a_id, host_a_org_id, "patch", advisories_rhsa_installable=10, packages_installed=500
        )
        db_create_host_app_data(
            host_b_id, host_b_org_id, "patch", advisories_rhsa_installable=10, packages_installed=50
        )

        # Both have rhsa >= 5, but only host_a has packages_installed > 100
        url = build_host_view_url(
            query=("?filter[patch][advisories_rhsa_installable][gte]=5&filter[patch][packages_installed][gt]=100")
        )
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert str(response_data["results"][0]["id"]) == host_a_id

    def test_filter_patch_invalid_field_returns_400(self, api_get, db_create_host):
        """Invalid field name should return 400."""
        db_create_host()

        url = build_host_view_url(query="?filter[patch][nonexistent_field][eq]=5")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 400)

    def test_filter_patch_invalid_operator_returns_400(self, api_get, db_create_host):
        """Invalid operator should return 400."""
        db_create_host()

        url = build_host_view_url(query="?filter[patch][advisories_rhsa_installable][badop]=5")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 400)

    def test_filter_malware_string_field(self, api_get, db_create_host, db_create_host_app_data):
        """Filter on string field last_status with eq operator."""
        host_a = db_create_host(extra_data={"display_name": "host-a.example.com"})
        host_a_id = str(host_a.id)
        host_a_org_id = host_a.org_id
        host_b = db_create_host(extra_data={"display_name": "host-b.example.com"})
        host_b_id = str(host_b.id)
        host_b_org_id = host_b.org_id

        db_create_host_app_data(host_a_id, host_a_org_id, "malware", last_status="clean")
        db_create_host_app_data(host_b_id, host_b_org_id, "malware", last_status="infected")

        url = build_host_view_url(query="?filter[malware][last_status][eq]=clean")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert str(response_data["results"][0]["id"]) == host_a_id


class TestHostViewSystemProfileFiltering:
    """Test system_profile filtering support on the hosts-view endpoint."""

    def test_filter_by_host_type(self, api_get, db_create_multiple_hosts):
        """filter[system_profile][host_type][eq]=edge should return only edge hosts."""
        db_create_multiple_hosts(how_many=2, extra_data={"system_profile_facts": {"host_type": "edge"}})
        db_create_multiple_hosts(how_many=1, extra_data={"system_profile_facts": {"host_type": None}})

        url = build_host_view_url(query="?filter[system_profile][host_type][eq]=edge")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 2

    def test_sp_filter_combined_with_app_filter(self, api_get, db_create_host):
        """system_profile and app_data filters should work together."""
        host_match = db_create_host(
            extra_data={"display_name": "matching-host.example.com", "system_profile_facts": {"host_type": "edge"}}
        )
        host_wrong_type = db_create_host(
            extra_data={"display_name": "wrong-type.example.com", "system_profile_facts": {"host_type": None}}
        )
        host_no_vuln = db_create_host(
            extra_data={"display_name": "no-vuln.example.com", "system_profile_facts": {"host_type": "edge"}}
        )

        db_create_host_app_data(host_match.id, host_match.org_id, "vulnerability", critical_cves=5)
        db_create_host_app_data(host_wrong_type.id, host_wrong_type.org_id, "vulnerability", critical_cves=10)
        db_create_host_app_data(host_no_vuln.id, host_no_vuln.org_id, "vulnerability", critical_cves=0)

        url = build_host_view_url(
            query="?filter[system_profile][host_type][eq]=edge&filter[vulnerability][critical_cves][gte]=1"
        )
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["display_name"] == "matching-host.example.com"

    def test_nested_sp_filter_combined_with_app_filter(self, api_get, db_create_host):
        """Nested system_profile filters should combine correctly with app filters."""
        host_match = db_create_host(
            extra_data={
                "display_name": "matching-rhel.example.com",
                "system_profile_facts": {"operating_system": {"name": "RHEL", "major": 9, "minor": 1}},
            }
        )
        host_wrong_os = db_create_host(
            extra_data={
                "display_name": "wrong-os.example.com",
                "system_profile_facts": {"operating_system": {"name": "CentOS Linux", "major": 8, "minor": 0}},
            }
        )
        host_no_vuln = db_create_host(
            extra_data={
                "display_name": "no-vuln-rhel.example.com",
                "system_profile_facts": {"operating_system": {"name": "RHEL", "major": 8, "minor": 8}},
            }
        )

        db_create_host_app_data(host_match.id, host_match.org_id, "vulnerability", critical_cves=5)
        db_create_host_app_data(host_wrong_os.id, host_wrong_os.org_id, "vulnerability", critical_cves=10)
        db_create_host_app_data(host_no_vuln.id, host_no_vuln.org_id, "vulnerability", critical_cves=0)

        url = build_host_view_url(
            query="?filter[system_profile][operating_system][name][eq]=RHEL"
            "&filter[vulnerability][critical_cves][gte]=1"
        )
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["display_name"] == "matching-rhel.example.com"

    def test_sp_filter_with_sp_fields(self, api_get, db_create_multiple_hosts):
        """SP filtering and SP sparse fields should work together."""
        db_create_multiple_hosts(
            how_many=2,
            extra_data={"system_profile_facts": {"host_type": "edge", "arch": "x86_64"}},
        )
        db_create_multiple_hosts(
            how_many=1, extra_data={"system_profile_facts": {"host_type": None, "arch": "aarch64"}}
        )

        url = build_host_view_url(query="?filter[system_profile][host_type][eq]=edge&fields[system_profile]=arch")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 2
        for result in response_data["results"]:
            assert "system_profile" in result
            assert result["system_profile"]["arch"] == "x86_64"
            assert "host_type" not in result["system_profile"]
