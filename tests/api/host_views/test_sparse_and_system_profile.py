from __future__ import annotations

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_view_url
from tests.helpers.db_utils import db_create_host_app_data


class TestHostViewSparseFieldsets:
    """Test sparse fieldsets functionality for hosts-view endpoint."""

    def test_request_single_app_all_fields(self, api_get, db_create_host):
        """Request a single app with all its fields."""
        host = db_create_host()
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
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            important_cves=3,
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
        assert result["app_data"]["advisor"]["critical"] == 3
        assert result["app_data"]["advisor"]["important"] == 2
        assert result["app_data"]["advisor"]["moderate"] == 0
        assert result["app_data"]["advisor"]["low"] == 0

    def test_request_single_app_specific_fields(self, api_get, db_create_host):
        """Request specific fields from a single app."""
        host = db_create_host()
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            important_cves=3,
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
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            important_cves=3,
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
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            important_cves=3,
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
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            important_cves=3,
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

        db_create_host_app_data(
            host1.id,
            host1.org_id,
            "advisor",
            recommendations=5,
            incidents=2,
            critical=3,
            important=2,
            moderate=0,
            low=0,
        )
        db_create_host_app_data(
            host2.id,
            host2.org_id,
            "advisor",
            recommendations=10,
            incidents=5,
            critical=5,
            important=3,
            moderate=1,
            low=1,
        )

        # Filter by display_name and request specific fields
        url = build_host_view_url(query="?display_name=filtered-host&fields[advisor]=recommendations")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        result = response_data["results"][0]
        assert result["display_name"] == "filtered-host.example.com"
        assert result["app_data"]["advisor"] == {"recommendations": 5}

    def test_invalid_app_name_returns_400(self, api_get, db_create_host):
        """Unknown app name in fields parameter should return 400."""
        db_create_host()

        url = build_host_view_url(query="?fields[invalid_app]=something")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 400)

    def test_invalid_field_returns_empty_for_app(self, api_get, db_create_host):
        """Valid app with invalid field should return empty object for that app."""
        host = db_create_host()
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

        # Request mix of valid and invalid fields
        url = build_host_view_url(query="?fields[advisor]=recommendations,invalid_field")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        # Only valid field returned
        assert result["app_data"]["advisor"] == {"recommendations": 5}


class TestHostViewSystemProfileSparseFields:
    """Test system_profile sparse fields support on the hosts-view endpoint."""

    SP_DATA = {
        "system_profile_facts": {
            "arch": "x86_64",
            "os_kernel_version": "4.18.2",
            "host_type": "edge",
            "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        }
    }

    def test_sp_fields_returns_requested_fields_only(self, api_get, db_create_multiple_hosts):
        """fields[system_profile]=arch,host_type should return only those SP fields."""
        db_create_multiple_hosts(how_many=2, extra_data={**self.SP_DATA})

        url = build_host_view_url(query="?fields[system_profile]=arch,host_type")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        for result in response_data["results"]:
            assert "system_profile" in result
            assert "arch" in result["system_profile"]
            assert "host_type" in result["system_profile"]
            assert "os_kernel_version" not in result["system_profile"]
            assert "owner_id" not in result["system_profile"]

    def test_no_sp_fields_omits_system_profile(self, api_get, db_create_multiple_hosts):
        """When fields[system_profile] is not requested, system_profile should not appear."""
        db_create_multiple_hosts(how_many=2, extra_data={**self.SP_DATA})

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        for result in response_data["results"]:
            assert "system_profile" not in result

    def test_sp_fields_with_app_data_fields(self, api_get, db_create_host):
        """Both fields[system_profile] and fields[advisor] should work together."""
        host = db_create_host(extra_data={**self.SP_DATA})
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)

        url = build_host_view_url(query="?fields[system_profile]=arch&fields[advisor]=recommendations")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]

        assert "system_profile" in result
        assert result["system_profile"]["arch"] == "x86_64"
        assert "host_type" not in result["system_profile"]

        assert "advisor" in result["app_data"]
        assert result["app_data"]["advisor"]["recommendations"] == 5
        assert "incidents" not in result["app_data"]["advisor"]

    def test_sp_fields_app_data_still_defaults_to_all(self, api_get, db_create_host):
        """Requesting only fields[system_profile] should still return all app_data by default."""
        host = db_create_host(extra_data={**self.SP_DATA})
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=5, incidents=2)

        url = build_host_view_url(query="?fields[system_profile]=arch")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]

        assert "system_profile" in result
        assert result["system_profile"]["arch"] == "x86_64"

        # app_data should default to all apps when only SP fields are specified
        assert "advisor" in result["app_data"]
        assert "recommendations" in result["app_data"]["advisor"]
        assert "incidents" in result["app_data"]["advisor"]

    def test_host_without_sp_data_returns_empty_sp(self, api_get, db_create_host):
        """Host without system_profile data should return an empty system_profile object."""
        db_create_host()

        url = build_host_view_url(query="?fields[system_profile]=arch,host_type")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        assert "system_profile" in result
        assert result["system_profile"] == {}
