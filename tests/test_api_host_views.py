from __future__ import annotations

from datetime import UTC
from datetime import datetime

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_view_url


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

    def test_host_with_advisor_data(self, api_get, db_create_host, db_create_host_app_data):
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

    def test_host_with_vulnerability_data(self, api_get, db_create_host, db_create_host_app_data):
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

    def test_host_with_patch_data(self, api_get, db_create_host, db_create_host_app_data):
        """Host with patch data should return patch in app_data."""
        host = db_create_host()
        db_create_host_app_data(
            host.id,
            host.org_id,
            "patch",
            installable_advisories=15,
            template="test-template",
            rhsm_locked_version="8.6",
        )

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "patch" in result["app_data"]
        assert result["app_data"]["patch"]["installable_advisories"] == 15
        assert result["app_data"]["patch"]["template"] == "test-template"

    def test_host_with_multiple_app_data(self, api_get, db_create_host, db_create_host_app_data):
        """Host with multiple app_data types should return all in app_data."""
        host = db_create_host()
        db_create_host_app_data(
            host.id,
            host.org_id,
            "patch",
            installable_advisories=15,
            template="baseline-template",
            rhsm_locked_version="8.6",
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

    def test_multiple_hosts_with_different_app_data(self, api_get, db_create_host, db_create_host_app_data):
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
            installable_advisories=15,
            template="baseline-template",
            rhsm_locked_version="8.6",
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

    def test_mixed_hosts_some_with_app_data_some_without(self, api_get, db_create_host, db_create_host_app_data):
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
            installable_advisories=10,
            template="production",
            rhsm_locked_version="9.0",
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

    def test_filter_by_display_name(self, api_get, db_create_host, db_create_host_app_data):
        """Filter by display_name should work."""
        host1 = db_create_host(extra_data={"display_name": "unique-host-name.example.com"})
        db_create_host(extra_data={"display_name": "other-host.example.com"})  # Second host for filtering

        db_create_host_app_data(
            host1.id,
            host1.org_id,
            "patch",
            installable_advisories=12,
            template="dev-template",
            rhsm_locked_version="8.8",
        )

        url = build_host_view_url(query="?display_name=unique-host")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["display_name"] == "unique-host-name.example.com"
        assert "patch" in response_data["results"][0]["app_data"]
        assert response_data["results"][0]["app_data"]["patch"]["installable_advisories"] == 12

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

    def test_patch_data(self, api_get, db_create_host, db_create_host_app_data):
        """Patch data should include installable_advisories, template, and rhsm_locked_version."""
        host = db_create_host()
        host_id = str(host.id)
        host_org_id = host.org_id
        db_create_host_app_data(
            host_id,
            host_org_id,
            "patch",
            installable_advisories=25,
            template="production-baseline",
            rhsm_locked_version="9.2",
        )

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "patch" in result["app_data"]
        assert result["app_data"]["patch"]["installable_advisories"] == 25
        assert result["app_data"]["patch"]["template"] == "production-baseline"
        assert result["app_data"]["patch"]["rhsm_locked_version"] == "9.2"

    def test_compliance_data(self, api_get, db_create_host, db_create_host_app_data):
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

    def test_malware_data(self, api_get, db_create_host, db_create_host_app_data):
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

    def test_remediations_data(self, api_get, db_create_host, db_create_host_app_data):
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

    def test_image_builder_data(self, api_get, db_create_host, db_create_host_app_data):
        """Image Builder data should include image_name and image_status."""
        host = db_create_host()
        host_id = str(host.id)
        host_org_id = host.org_id
        db_create_host_app_data(host_id, host_org_id, "image_builder", image_name="rhel-9-base", image_status="ready")

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "image_builder" in result["app_data"]
        assert result["app_data"]["image_builder"]["image_name"] == "rhel-9-base"
        assert result["app_data"]["image_builder"]["image_status"] == "ready"
