from __future__ import annotations

from datetime import UTC
from datetime import datetime

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
