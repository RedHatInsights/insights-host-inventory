from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_view_url
from tests.helpers.db_utils import db_create_host_app_data


class TestHostViewBasicResponse:
    """Test basic response structure of the hosts-view endpoint."""

    def test_empty_response_when_no_hosts(self, api_get):
        """When no hosts exist, return empty results with correct structure."""
        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 0
        assert response_data["count"] == 0
        assert response_data["page"] == 1
        assert response_data["per_page"] == 50
        assert response_data["results"] == []

    def test_host_without_app_data_returns_empty_app_data(self, api_get, db_create_host):
        """Host without any app_data should return empty app_data object."""
        host = db_create_host()
        host_id = str(host.id)  # Save ID before session closes

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["count"] == 1
        assert len(response_data["results"]) == 1

        result = response_data["results"][0]
        assert str(result["id"]) == host_id
        assert result["app_data"] == {}

    def test_response_includes_standard_host_fields(self, api_get, db_create_host):
        """Response should include all standard host fields."""
        db_create_host()

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]

        # Verify standard host fields are present
        assert "id" in result
        assert "display_name" in result
        assert "org_id" in result
        assert "created" in result
        assert "updated" in result
        assert "stale_timestamp" in result
        assert "reporter" in result
        assert "groups" in result
        assert "app_data" in result


class TestHostViewWithAppData:
    """Test hosts-view endpoint with app_data populated."""

    def test_host_with_advisor_data(self, api_get, db_create_host):
        """Host with advisor data should return advisor in app_data."""
        host = db_create_host()
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "advisor" in result["app_data"]
        assert result["app_data"]["advisor"]["recommendations"] == 5
        assert result["app_data"]["advisor"]["incidents"] == 2

    def test_host_with_vulnerability_data(self, api_get, db_create_host):
        """Host with vulnerability data should return vulnerability in app_data."""
        host = db_create_host()
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            high_severity_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=1,
        )

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "vulnerability" in result["app_data"]
        assert result["app_data"]["vulnerability"]["total_cves"] == 10
        assert result["app_data"]["vulnerability"]["critical_cves"] == 2

    def test_host_with_patch_data(self, api_get, db_create_host):
        """Host with patch data should return patch in app_data."""
        host = db_create_host()
        db_create_host_app_data(
            host.id,
            host.org_id,
            "patch",
            advisories_rhsa_installable=8,
            advisories_rhba_installable=4,
            advisories_rhea_installable=2,
            advisories_other_installable=1,
            template_name="test-template",
        )

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "patch" in result["app_data"]
        # API returns all patch fields directly
        assert result["app_data"]["patch"]["advisories_rhsa_installable"] == 8
        assert result["app_data"]["patch"]["advisories_rhba_installable"] == 4
        assert result["app_data"]["patch"]["advisories_rhea_installable"] == 2
        assert result["app_data"]["patch"]["advisories_other_installable"] == 1
        assert result["app_data"]["patch"]["template_name"] == "test-template"

    def test_host_with_multiple_app_data(self, api_get, db_create_host):
        """Host with multiple app_data types should return all in app_data."""
        host = db_create_host()
        db_create_host_app_data(
            host.id,
            host.org_id,
            "patch",
            advisories_rhsa_installable=10,
            advisories_rhba_installable=5,
            template_name="baseline-template",
        )
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            high_severity_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=1,
        )
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "patch" in result["app_data"]
        assert "vulnerability" in result["app_data"]
        assert "advisor" in result["app_data"]
        assert len(result["app_data"]) == 3


class TestHostViewWithMultipleHosts:
    """Test hosts-view endpoint with multiple hosts."""

    def test_multiple_hosts_with_different_app_data(self, api_get, db_create_host):
        """Multiple hosts should each have their own app_data."""
        host1 = db_create_host()
        host1_id = str(host1.id)
        host1_org_id = host1.org_id
        host2 = db_create_host()
        host2_id = str(host2.id)
        host2_org_id = host2.org_id

        # Host 1 has patch data
        db_create_host_app_data(
            host1_id,
            host1_org_id,
            "patch",
            advisories_rhsa_installable=10,
            advisories_rhba_installable=5,
            template_name="baseline-template",
        )

        # Host 2 has vulnerability data
        db_create_host_app_data(
            host2_id,
            host2_org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            high_severity_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=1,
        )

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 2

        # Find each host in results
        results_by_id = {str(r["id"]): r for r in response_data["results"]}

        assert "patch" in results_by_id[host1_id]["app_data"]
        assert "vulnerability" not in results_by_id[host1_id]["app_data"]

        assert "vulnerability" in results_by_id[host2_id]["app_data"]
        assert "patch" not in results_by_id[host2_id]["app_data"]

    def test_mixed_hosts_some_with_app_data_some_without(self, api_get, db_create_host):
        """Some hosts with app_data, some without."""
        host_with_data = db_create_host()
        host_with_data_id = str(host_with_data.id)
        host_with_data_org_id = host_with_data.org_id
        host_without_data = db_create_host()
        host_without_data_id = str(host_without_data.id)

        db_create_host_app_data(
            host_with_data_id,
            host_with_data_org_id,
            "patch",
            advisories_rhsa_installable=6,
            advisories_rhba_installable=4,
            template_name="production",
        )

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 2

        results_by_id = {str(r["id"]): r for r in response_data["results"]}

        assert results_by_id[host_with_data_id]["app_data"] != {}
        assert "patch" in results_by_id[host_with_data_id]["app_data"]
        assert results_by_id[host_without_data_id]["app_data"] == {}


class TestHostViewFilters:
    """Test hosts-view endpoint filters."""

    def test_filter_by_display_name(self, api_get, db_create_host):
        """Filter by display_name should work."""
        host1 = db_create_host(extra_data={"display_name": "unique-host-name.example.com"})
        db_create_host(extra_data={"display_name": "other-host.example.com"})  # Second host for filtering

        db_create_host_app_data(
            host1.id,
            host1.org_id,
            "patch",
            advisories_rhsa_installable=7,
            advisories_rhba_installable=5,
            template_name="dev-template",
        )

        url = build_host_view_url(query="?display_name=unique-host")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["display_name"] == "unique-host-name.example.com"
        assert "patch" in response_data["results"][0]["app_data"]
        assert response_data["results"][0]["app_data"]["patch"]["advisories_rhsa_installable"] == 7
        assert response_data["results"][0]["app_data"]["patch"]["advisories_rhba_installable"] == 5

    def test_pagination(self, api_get, db_create_multiple_hosts):
        """Pagination should work correctly."""
        db_create_multiple_hosts(how_many=5)

        url = build_host_view_url(query="?per_page=2&page=1")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 5
        assert response_data["count"] == 2
        assert response_data["page"] == 1
        assert response_data["per_page"] == 2
        assert len(response_data["results"]) == 2

    def test_ordering_by_display_name(self, api_get, db_create_host):
        """Ordering by display_name should work."""
        db_create_host(extra_data={"display_name": "z-host.example.com"})
        db_create_host(extra_data={"display_name": "a-host.example.com"})

        url = build_host_view_url(query="?order_by=display_name&order_how=ASC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["results"][0]["display_name"] == "a-host.example.com"
        assert response_data["results"][1]["display_name"] == "z-host.example.com"


class TestHostViewAppDataEdgeCases:
    """Test edge cases for app_data in hosts-view endpoint."""

    def test_patch_data(self, api_get, db_create_host):
        """Patch data should include all advisory and package fields."""
        host = db_create_host()
        host_id = str(host.id)
        host_org_id = host.org_id
        db_create_host_app_data(
            host_id,
            host_org_id,
            "patch",
            advisories_rhsa_applicable=20,
            advisories_rhba_applicable=10,
            advisories_rhea_applicable=5,
            advisories_other_applicable=3,
            advisories_rhsa_installable=15,
            advisories_rhba_installable=5,
            advisories_rhea_installable=3,
            advisories_other_installable=2,
            packages_applicable=100,
            packages_installable=50,
            packages_installed=500,
            template_name="production-baseline",
        )

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "patch" in result["app_data"]
        patch_data = result["app_data"]["patch"]
        # Verify all fields are returned
        assert patch_data["advisories_rhsa_applicable"] == 20
        assert patch_data["advisories_rhba_applicable"] == 10
        assert patch_data["advisories_rhea_applicable"] == 5
        assert patch_data["advisories_other_applicable"] == 3
        assert patch_data["advisories_rhsa_installable"] == 15
        assert patch_data["advisories_rhba_installable"] == 5
        assert patch_data["advisories_rhea_installable"] == 3
        assert patch_data["advisories_other_installable"] == 2
        assert patch_data["packages_applicable"] == 100
        assert patch_data["packages_installable"] == 50
        assert patch_data["packages_installed"] == 500
        assert patch_data["template_name"] == "production-baseline"
        # template_uuid is not set, so it should not be in the response
        assert "template_uuid" not in patch_data

    def test_compliance_data(self, api_get, db_create_host):
        """Compliance data should include policies and last_scan."""
        host = db_create_host()
        host_id = str(host.id)
        host_org_id = host.org_id
        scan_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        db_create_host_app_data(host_id, host_org_id, "compliance", policies=5, last_scan=scan_time)

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "compliance" in result["app_data"]
        assert result["app_data"]["compliance"]["policies"] == 5
        assert result["app_data"]["compliance"]["last_scan"] is not None

    def test_malware_data(self, api_get, db_create_host):
        """Malware data should include status, matches, and last_scan."""
        host = db_create_host()
        host_id = str(host.id)
        host_org_id = host.org_id
        scan_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        db_create_host_app_data(
            host_id, host_org_id, "malware", last_status="clean", last_matches=0, last_scan=scan_time
        )

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "malware" in result["app_data"]
        assert result["app_data"]["malware"]["last_status"] == "clean"
        assert result["app_data"]["malware"]["last_matches"] == 0
        assert result["app_data"]["malware"]["last_scan"] is not None

    def test_remediations_data(self, api_get, db_create_host):
        """Remediations data should include remediations_plans."""
        host = db_create_host()
        host_id = str(host.id)
        host_org_id = host.org_id
        db_create_host_app_data(host_id, host_org_id, "remediations", remediations_plans=7)

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "remediations" in result["app_data"]
        assert result["app_data"]["remediations"]["remediations_plans"] == 7


class TestHostViewSparseFieldsets:
    """Test sparse fieldsets functionality for hosts-view endpoint."""

    def test_request_single_app_all_fields(self, api_get, db_create_host):
        """Request a single app with all its fields."""
        host = db_create_host()
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            high_severity_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=1,
        )

        # Request only advisor data (all fields)
        url = build_host_view_url(query="?fields[advisor]=true")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        # Only advisor should be present
        assert "advisor" in result["app_data"]
        assert "vulnerability" not in result["app_data"]
        # All advisor fields should be present
        assert result["app_data"]["advisor"]["recommendations"] == 5
        assert result["app_data"]["advisor"]["incidents"] == 2

    def test_request_single_app_specific_fields(self, api_get, db_create_host):
        """Request specific fields from a single app."""
        host = db_create_host()
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            high_severity_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=1,
        )

        # Request only critical_cves from vulnerability
        url = build_host_view_url(query="?fields[vulnerability]=critical_cves")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "vulnerability" in result["app_data"]
        # Only requested fields should be present
        assert result["app_data"]["vulnerability"] == {"critical_cves": 2}
        assert "total_cves" not in result["app_data"]["vulnerability"]

    def test_request_multiple_apps(self, api_get, db_create_host):
        """Request multiple apps at once."""
        host = db_create_host()
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            high_severity_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=1,
        )
        db_create_host_app_data(
            host.id,
            host.org_id,
            "patch",
            advisories_rhsa_installable=8,
            advisories_rhba_installable=4,
            template_name="test-template",
        )

        # Request advisor and vulnerability (all fields), but not patch
        url = build_host_view_url(query="?fields[advisor]=true&fields[vulnerability]=true")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "advisor" in result["app_data"]
        assert "vulnerability" in result["app_data"]
        assert "patch" not in result["app_data"]

    def test_request_multiple_specific_fields(self, api_get, db_create_host):
        """Request multiple specific fields from multiple apps."""
        host = db_create_host()
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            high_severity_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=1,
        )

        # Request specific fields from both apps
        url = build_host_view_url(
            query="?fields[advisor]=recommendations&fields[vulnerability]=critical_cves,total_cves"
        )
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        # Only requested fields should be present
        assert result["app_data"]["advisor"] == {"recommendations": 5}
        assert set(result["app_data"]["vulnerability"].keys()) == {"critical_cves", "total_cves"}
        assert result["app_data"]["vulnerability"]["critical_cves"] == 2
        assert result["app_data"]["vulnerability"]["total_cves"] == 10

    def test_request_app_with_no_data_in_db(self, api_get, db_create_host):
        """Request an app that has no data in DB should return empty for that app."""
        host = db_create_host()
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)

        # Request vulnerability (all fields) which has no data
        url = build_host_view_url(query="?fields[vulnerability]=true")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        # vulnerability was requested but no data exists
        assert "vulnerability" not in result["app_data"]
        # advisor was not requested
        assert "advisor" not in result["app_data"]

    def test_empty_fields_returns_no_fields(self, api_get, db_create_host):
        """Per JSON:API spec, empty fields value means no fields should be returned."""
        host = db_create_host()
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)

        # Empty value means no fields (per JSON:API spec)
        url = build_host_view_url(query="?fields[advisor]=")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        # advisor key should be present but with empty object
        assert result["app_data"]["advisor"] == {}

    def test_app_data_true_returns_all_apps(self, api_get, db_create_host):
        """fields[app_data]=true should return all available app data."""
        host = db_create_host()
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            high_severity_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=1,
        )
        db_create_host_app_data(host.id, host.org_id, "remediations", remediations_plans=3)

        url = build_host_view_url(query="?fields[app_data]=true")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        # All apps with data should be present
        assert "advisor" in result["app_data"]
        assert "vulnerability" in result["app_data"]
        assert "remediations" in result["app_data"]

    def test_sparse_fields_with_filtering(self, api_get, db_create_host):
        """Sparse fields should work together with host filtering."""
        host1 = db_create_host(extra_data={"display_name": "filtered-host.example.com"})
        host2 = db_create_host(extra_data={"display_name": "other-host.example.com"})

        db_create_host_app_data(host1.id, host1.org_id, "advisor", recommendations=5, incidents=2)
        db_create_host_app_data(host2.id, host2.org_id, "advisor", recommendations=10, incidents=5)

        # Filter by display_name and request specific fields
        url = build_host_view_url(query="?display_name=filtered-host&fields[advisor]=recommendations")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        result = response_data["results"][0]
        assert result["display_name"] == "filtered-host.example.com"
        assert result["app_data"]["advisor"] == {"recommendations": 5}

    def test_invalid_app_name_ignored(self, api_get, db_create_host):
        """Invalid app name in fields parameter should be gracefully ignored."""
        host = db_create_host()
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)

        # Request an invalid app name
        url = build_host_view_url(query="?fields[invalid_app]=something")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        # Invalid app ignored, returns all apps by default (per design doc)
        assert "advisor" in result["app_data"]
        assert "invalid_app" not in result["app_data"]

    def test_invalid_field_returns_empty_for_app(self, api_get, db_create_host):
        """Valid app with invalid field should return empty object for that app."""
        host = db_create_host()
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)

        # Request valid app with invalid field
        url = build_host_view_url(query="?fields[advisor]=nonexistent_field")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        # App key is present but empty (no valid fields matched)
        assert "advisor" in result["app_data"]
        assert result["app_data"]["advisor"] == {}

    def test_mix_valid_and_invalid_fields(self, api_get, db_create_host):
        """Mix of valid and invalid fields should return only valid fields."""
        host = db_create_host()
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)

        # Request mix of valid and invalid fields
        url = build_host_view_url(query="?fields[advisor]=recommendations,invalid_field")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        # Only valid field returned
        assert result["app_data"]["advisor"] == {"recommendations": 5}


class TestHostViewAppDataSorting:
    """Test sorting hosts by application data fields."""

    def test_sort_by_vulnerability_critical_cves_desc(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by vulnerability:critical_cves DESC should order hosts by critical CVE count descending."""
        # Create hosts with different critical CVE counts
        host_low = db_create_host(extra_data={"display_name": "host-low.example.com"})
        host_high = db_create_host(extra_data={"display_name": "host-high.example.com"})
        host_mid = db_create_host(extra_data={"display_name": "host-mid.example.com"})

        db_create_host_app_data(host_low.id, host_low.org_id, "vulnerability", critical_cves=2)
        db_create_host_app_data(host_high.id, host_high.org_id, "vulnerability", critical_cves=10)
        db_create_host_app_data(host_mid.id, host_mid.org_id, "vulnerability", critical_cves=5)

        url = build_host_view_url(query="?order_by=vulnerability:critical_cves&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 3

        # Verify descending order by critical_cves
        results = response_data["results"]
        assert results[0]["app_data"]["vulnerability"]["critical_cves"] == 10
        assert results[1]["app_data"]["vulnerability"]["critical_cves"] == 5
        assert results[2]["app_data"]["vulnerability"]["critical_cves"] == 2

    def test_sort_by_vulnerability_critical_cves_asc(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by vulnerability:critical_cves ASC should order hosts by critical CVE count ascending."""
        host_low = db_create_host(extra_data={"display_name": "host-low.example.com"})
        host_high = db_create_host(extra_data={"display_name": "host-high.example.com"})

        db_create_host_app_data(host_low.id, host_low.org_id, "vulnerability", critical_cves=2)
        db_create_host_app_data(host_high.id, host_high.org_id, "vulnerability", critical_cves=10)

        url = build_host_view_url(query="?order_by=vulnerability:critical_cves&order_how=ASC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["vulnerability"]["critical_cves"] == 2
        assert results[1]["app_data"]["vulnerability"]["critical_cves"] == 10

    def test_sort_by_advisor_recommendations_desc(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by advisor:recommendations DESC should order hosts by recommendation count descending."""
        host_few = db_create_host(extra_data={"display_name": "host-few.example.com"})
        host_many = db_create_host(extra_data={"display_name": "host-many.example.com"})

        db_create_host_app_data(host_few.id, host_few.org_id, "advisor", recommendations=3)
        db_create_host_app_data(host_many.id, host_many.org_id, "advisor", recommendations=15)

        url = build_host_view_url(query="?order_by=advisor:recommendations&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["advisor"]["recommendations"] == 15
        assert results[1]["app_data"]["advisor"]["recommendations"] == 3

    def test_sort_nulls_last_behavior(self, api_get, db_create_host, db_create_host_app_data):
        """Hosts without app data should appear last when sorting by app fields."""
        host_with_data = db_create_host(extra_data={"display_name": "host-with-data.example.com"})
        db_create_host(extra_data={"display_name": "host-without-data.example.com"})

        # Only create vulnerability data for one host
        db_create_host_app_data(host_with_data.id, host_with_data.org_id, "vulnerability", critical_cves=5)

        url = build_host_view_url(query="?order_by=vulnerability:critical_cves&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        # Host with data should be first, host without data should be last
        assert results[0]["display_name"] == "host-with-data.example.com"
        assert results[1]["display_name"] == "host-without-data.example.com"
        assert "vulnerability" in results[0]["app_data"]
        # Only check that the sorted field is missing, not that app_data is entirely empty
        assert "vulnerability" not in results[1]["app_data"]

    def test_sort_nulls_last_asc(self, api_get, db_create_host, db_create_host_app_data):
        """Hosts without app data should appear last even when sorting ASC."""
        host_with_data = db_create_host(extra_data={"display_name": "host-with-data.example.com"})
        db_create_host(extra_data={"display_name": "host-without-data.example.com"})

        db_create_host_app_data(host_with_data.id, host_with_data.org_id, "vulnerability", critical_cves=5)

        url = build_host_view_url(query="?order_by=vulnerability:critical_cves&order_how=ASC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        # Host with data should be first (even with ASC), host without data should be last
        assert results[0]["display_name"] == "host-with-data.example.com"
        assert results[1]["display_name"] == "host-without-data.example.com"

    def test_sort_nulls_last_with_null_column_value(self, api_get, db_create_host, db_create_host_app_data):
        """Hosts with an app row but NULL sortable column should sort after non-NULL values (NULLS LAST).

        Distinguishes three cases:
        1. Host with a non-NULL value in the sorted column
        2. Host with an app data row but the sorted column is NULL
        3. Host with no app data row at all

        Both case 2 and 3 should appear after case 1 regardless of sort direction.
        """
        host_with_value = db_create_host(extra_data={"display_name": "host-with-value.example.com"})
        host_null_column = db_create_host(extra_data={"display_name": "host-null-column.example.com"})
        db_create_host(extra_data={"display_name": "host-no-row.example.com"})

        db_create_host_app_data(host_with_value.id, host_with_value.org_id, "vulnerability", critical_cves=5)
        # App row exists but critical_cves is not set (defaults to NULL)
        db_create_host_app_data(host_null_column.id, host_null_column.org_id, "vulnerability")

        # DESC: non-NULL value first, then NULL column and no-row hosts last
        url = build_host_view_url(query="?order_by=vulnerability:critical_cves&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 3
        results = response_data["results"]
        assert results[0]["display_name"] == "host-with-value.example.com"
        assert results[0]["app_data"]["vulnerability"]["critical_cves"] == 5
        # Both NULL-column and no-row hosts should be after the non-NULL host
        trailing_names = {results[1]["display_name"], results[2]["display_name"]}
        assert trailing_names == {"host-null-column.example.com", "host-no-row.example.com"}

        # ASC: non-NULL value first, then NULL column and no-row hosts last
        url = build_host_view_url(query="?order_by=vulnerability:critical_cves&order_how=ASC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["display_name"] == "host-with-value.example.com"
        trailing_names = {results[1]["display_name"], results[2]["display_name"]}
        assert trailing_names == {"host-null-column.example.com", "host-no-row.example.com"}

    def test_sort_by_patch_advisories_rhsa_installable(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by patch:advisories_rhsa_installable should work correctly."""
        host1 = db_create_host(extra_data={"display_name": "host1.example.com"})
        host2 = db_create_host(extra_data={"display_name": "host2.example.com"})

        db_create_host_app_data(host1.id, host1.org_id, "patch", advisories_rhsa_installable=20)
        db_create_host_app_data(host2.id, host2.org_id, "patch", advisories_rhsa_installable=5)

        url = build_host_view_url(query="?order_by=patch:advisories_rhsa_installable&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["patch"]["advisories_rhsa_installable"] == 20
        assert results[1]["app_data"]["patch"]["advisories_rhsa_installable"] == 5

    def test_sort_by_remediations_plans(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by remediations:remediations_plans should work correctly."""
        host1 = db_create_host(extra_data={"display_name": "host1.example.com"})
        host2 = db_create_host(extra_data={"display_name": "host2.example.com"})

        db_create_host_app_data(host1.id, host1.org_id, "remediations", remediations_plans=3)
        db_create_host_app_data(host2.id, host2.org_id, "remediations", remediations_plans=8)

        url = build_host_view_url(query="?order_by=remediations:remediations_plans&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["remediations"]["remediations_plans"] == 8
        assert results[1]["app_data"]["remediations"]["remediations_plans"] == 3

    def test_sort_by_compliance_last_scan(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by compliance:last_scan (datetime field) should work correctly."""
        host_old = db_create_host(extra_data={"display_name": "host-old.example.com"})
        host_new = db_create_host(extra_data={"display_name": "host-new.example.com"})

        # Create compliance data with different scan times
        old_scan = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        new_scan = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

        db_create_host_app_data(host_old.id, host_old.org_id, "compliance", last_scan=old_scan)
        db_create_host_app_data(host_new.id, host_new.org_id, "compliance", last_scan=new_scan)

        url = build_host_view_url(query="?order_by=compliance:last_scan&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        # Most recent scan should be first
        assert results[0]["display_name"] == "host-new.example.com"
        assert results[1]["display_name"] == "host-old.example.com"

    def test_standard_host_field_sorting_still_works(self, api_get, db_create_host):
        """Standard host field sorting (display_name) should still work."""
        db_create_host(extra_data={"display_name": "z-host.example.com"})
        db_create_host(extra_data={"display_name": "a-host.example.com"})

        url = build_host_view_url(query="?order_by=display_name&order_how=ASC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["results"][0]["display_name"] == "a-host.example.com"
        assert response_data["results"][1]["display_name"] == "z-host.example.com"

    def test_sort_by_malware_last_matches(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by malware:last_matches should work correctly."""
        host1 = db_create_host(extra_data={"display_name": "host1.example.com"})
        host2 = db_create_host(extra_data={"display_name": "host2.example.com"})

        db_create_host_app_data(host1.id, host1.org_id, "malware", last_matches=0)
        db_create_host_app_data(host2.id, host2.org_id, "malware", last_matches=5)

        url = build_host_view_url(query="?order_by=malware:last_matches&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["malware"]["last_matches"] == 5
        assert results[1]["app_data"]["malware"]["last_matches"] == 0

    def test_sort_default_order_how_is_asc(self, api_get, db_create_host, db_create_host_app_data):
        """When order_how is not specified, default to ASC for app sort fields."""
        host_low = db_create_host(extra_data={"display_name": "host-low.example.com"})
        host_high = db_create_host(extra_data={"display_name": "host-high.example.com"})

        db_create_host_app_data(host_low.id, host_low.org_id, "vulnerability", critical_cves=2)
        db_create_host_app_data(host_high.id, host_high.org_id, "vulnerability", critical_cves=10)

        # No order_how specified
        url = build_host_view_url(query="?order_by=vulnerability:critical_cves")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        # Should default to ASC
        assert results[0]["app_data"]["vulnerability"]["critical_cves"] == 2
        assert results[1]["app_data"]["vulnerability"]["critical_cves"] == 10

    def test_app_sort_secondary_ordering_for_pagination_stability(
        self, flask_app, api_get, db_create_host, db_create_host_app_data
    ):
        """
        Hosts with equal app field values should be ordered by modified_on DESC for pagination stability.

        When multiple hosts have the same app data value (e.g., same critical_cves count),
        the secondary sort by modified_on ensures consistent ordering across paginated requests.
        """
        from app.models import Host
        from app.models.database import db

        base_time = datetime.now(tz=UTC)

        # Create hosts with SAME vulnerability value but different modified_on times
        host_oldest = db_create_host(extra_data={"display_name": "host-oldest.example.com"})
        host_middle = db_create_host(extra_data={"display_name": "host-middle.example.com"})
        host_newest = db_create_host(extra_data={"display_name": "host-newest.example.com"})

        # Update modified_on times directly in the database
        # Order: oldest modified first, but we want most recently modified first in results
        with flask_app.app.app_context():
            db.session.query(Host).filter(Host.id == host_oldest.id).update(
                {"modified_on": base_time - timedelta(hours=3)}
            )
            db.session.query(Host).filter(Host.id == host_middle.id).update(
                {"modified_on": base_time - timedelta(hours=1)}
            )
            db.session.query(Host).filter(Host.id == host_newest.id).update({"modified_on": base_time})
            db.session.commit()

        # All hosts have the SAME critical_cves count
        same_cve_count = 5
        db_create_host_app_data(host_oldest.id, host_oldest.org_id, "vulnerability", critical_cves=same_cve_count)
        db_create_host_app_data(host_middle.id, host_middle.org_id, "vulnerability", critical_cves=same_cve_count)
        db_create_host_app_data(host_newest.id, host_newest.org_id, "vulnerability", critical_cves=same_cve_count)

        # Sort by vulnerability:critical_cves - since all values are equal,
        # secondary sort by modified_on DESC should determine order
        url = build_host_view_url(query="?order_by=vulnerability:critical_cves&order_how=ASC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]

        # All should have same critical_cves value
        assert all(r["app_data"]["vulnerability"]["critical_cves"] == same_cve_count for r in results)

        # Should be ordered by modified_on DESC (most recent first)
        assert results[0]["display_name"] == "host-newest.example.com"
        assert results[1]["display_name"] == "host-middle.example.com"
        assert results[2]["display_name"] == "host-oldest.example.com"

    def test_app_sort_invalid_order_how_returns_error(self, api_get, db_create_host, db_create_host_app_data):
        """Invalid order_how value should return 400 error for app field sorting."""
        host = db_create_host(extra_data={"display_name": "host.example.com"})
        db_create_host_app_data(host.id, host.org_id, "vulnerability", critical_cves=5)

        # Use invalid order_how value
        url = build_host_view_url(query="?order_by=vulnerability:critical_cves&order_how=down")
        response_status, _ = api_get(url)

        # Should return 400 error, not silently default to ASC
        assert_response_status(response_status, 400)

    def test_sort_by_nonexistent_field_returns_error(self, api_get, db_create_host):
        """Sorting by a non-existent field on a valid app should return 400."""
        db_create_host(extra_data={"display_name": "host.example.com"})

        # Valid app name, but non-existent field
        url = build_host_view_url(query="?order_by=vulnerability:nonexistent_field")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 400)

    def test_sort_by_unknown_app_returns_error(self, api_get, db_create_host):
        """Sorting by an unknown app name should return 400."""
        db_create_host(extra_data={"display_name": "host.example.com"})

        # Unknown app name
        url = build_host_view_url(query="?order_by=unknown_app:some_field")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 400)

    def test_sort_by_malformed_app_field_returns_error(self, api_get, db_create_host):
        """Sorting by a malformed app:field format should return 400."""
        db_create_host(extra_data={"display_name": "host.example.com"})

        # Malformed format (using hyphen instead of colon)
        url = build_host_view_url(query="?order_by=vulnerability-critical_cves")
        response_status, _ = api_get(url)

        # Should fail because it's not a valid app:field format and not a standard host field
        assert_response_status(response_status, 400)
