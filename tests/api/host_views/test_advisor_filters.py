from __future__ import annotations

import pytest

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_view_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.db_utils import db_create_host_app_data


class TestRecommendationSeverityFilter:
    """Tests for the recommendation_severity query parameter."""

    def test_single_severity_critical(self, api_get, db_create_host):
        """Only hosts with critical > 0 are returned."""
        host_match = db_create_host(extra_data={"display_name": "host-critical"})
        host_no_match = db_create_host(extra_data={"display_name": "host-no-critical"})
        host_no_data = db_create_host(extra_data={"display_name": "host-no-advisor"})

        db_create_host_app_data(
            host_match.id, host_match.org_id, "advisor", critical=3, important=0, moderate=0, low=0
        )
        db_create_host_app_data(
            host_no_match.id, host_no_match.org_id, "advisor", critical=0, important=5, moderate=2, low=1
        )

        url = build_host_view_url(query="?recommendation_severity=critical")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_ids = {str(r["id"]) for r in response_data["results"]}
        assert str(host_match.id) in result_ids
        assert str(host_no_match.id) not in result_ids
        assert str(host_no_data.id) not in result_ids

    def test_multiple_severities_or_logic(self, api_get, db_create_host):
        """Multiple severities use OR: critical + low returns hosts with either."""
        host_critical = db_create_host(extra_data={"display_name": "host-critical"})
        host_low = db_create_host(extra_data={"display_name": "host-low"})
        host_important = db_create_host(extra_data={"display_name": "host-important-only"})

        db_create_host_app_data(
            host_critical.id, host_critical.org_id, "advisor", critical=2, important=0, moderate=0, low=0
        )
        db_create_host_app_data(host_low.id, host_low.org_id, "advisor", critical=0, important=0, moderate=0, low=4)
        db_create_host_app_data(
            host_important.id, host_important.org_id, "advisor", critical=0, important=3, moderate=0, low=0
        )

        url = build_host_view_url(query="?recommendation_severity=critical&recommendation_severity=low")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_ids = {str(r["id"]) for r in response_data["results"]}
        assert str(host_critical.id) in result_ids
        assert str(host_low.id) in result_ids
        assert str(host_important.id) not in result_ids

    def test_no_severity_selected_returns_all(self, api_get, db_create_host):
        """No recommendation_severity param returns all hosts."""
        host_a = db_create_host(extra_data={"display_name": "host-a"})
        host_b = db_create_host(extra_data={"display_name": "host-b"})

        db_create_host_app_data(host_a.id, host_a.org_id, "advisor", critical=1, important=0, moderate=0, low=0)

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_ids = {str(r["id"]) for r in response_data["results"]}
        assert str(host_a.id) in result_ids
        assert str(host_b.id) in result_ids

    def test_null_severity_excluded(self, api_get, db_create_host):
        """Hosts with no advisor data are excluded when severity filter is active."""
        host_with_data = db_create_host(extra_data={"display_name": "host-with"})
        host_no_data = db_create_host(extra_data={"display_name": "host-without"})

        db_create_host_app_data(
            host_with_data.id, host_with_data.org_id, "advisor", critical=1, important=0, moderate=0, low=0
        )

        url = build_host_view_url(query="?recommendation_severity=critical")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_ids = {str(r["id"]) for r in response_data["results"]}
        assert str(host_with_data.id) in result_ids
        assert str(host_no_data.id) not in result_ids

    def test_all_data_returned_for_matching_host(self, api_get, db_create_host):
        """Matching hosts return all advisor fields, not just the filtered severity."""
        host = db_create_host(extra_data={"display_name": "host-full-data"})
        db_create_host_app_data(
            host.id,
            host.org_id,
            "advisor",
            critical=2,
            important=3,
            moderate=1,
            low=4,
            incidents=1,
            recommendations=10,
        )

        url = build_host_view_url(query="?recommendation_severity=critical")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = response_data["results"][0]
        advisor_data = result["app_data"]["advisor"]
        assert advisor_data["critical"] == 2
        assert advisor_data["important"] == 3
        assert advisor_data["moderate"] == 1
        assert advisor_data["low"] == 4
        assert advisor_data["incidents"] == 1

    def test_invalid_severity_returns_400(self, api_get, db_create_host):
        """Invalid severity value returns 400."""
        db_create_host()
        url = build_host_view_url(query="?recommendation_severity=extreme")
        response_status, _ = api_get(url)
        assert_response_status(response_status, 400)


class TestIncidentStatusFilter:
    """Tests for the incident_status query parameter."""

    def test_incident_filter(self, api_get, db_create_host):
        """incident_status=incident returns only hosts with incidents > 0."""
        host_with = db_create_host(extra_data={"display_name": "host-incidents"})
        host_without = db_create_host(extra_data={"display_name": "host-no-incidents"})
        host_no_data = db_create_host(extra_data={"display_name": "host-no-advisor"})

        db_create_host_app_data(host_with.id, host_with.org_id, "advisor", incidents=3)
        db_create_host_app_data(host_without.id, host_without.org_id, "advisor", incidents=0)

        url = build_host_view_url(query="?incident_status=incident")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_ids = {str(r["id"]) for r in response_data["results"]}
        assert str(host_with.id) in result_ids
        assert str(host_without.id) not in result_ids
        assert str(host_no_data.id) not in result_ids

    def test_no_incident_filter(self, api_get, db_create_host):
        """incident_status=no_incident returns only hosts with incidents = 0."""
        host_with = db_create_host(extra_data={"display_name": "host-incidents"})
        host_without = db_create_host(extra_data={"display_name": "host-no-incidents"})
        host_no_data = db_create_host(extra_data={"display_name": "host-no-advisor"})

        db_create_host_app_data(host_with.id, host_with.org_id, "advisor", incidents=3)
        db_create_host_app_data(host_without.id, host_without.org_id, "advisor", incidents=0)

        url = build_host_view_url(query="?incident_status=no_incident")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_ids = {str(r["id"]) for r in response_data["results"]}
        assert str(host_without.id) in result_ids
        assert str(host_with.id) not in result_ids
        assert str(host_no_data.id) not in result_ids

    def test_null_incidents_excluded_from_no_incident(self, api_get, db_create_host):
        """Hosts with no advisor data (NULL incidents) are excluded from no_incident."""
        host_zero = db_create_host(extra_data={"display_name": "host-zero"})
        host_null = db_create_host(extra_data={"display_name": "host-null"})

        db_create_host_app_data(host_zero.id, host_zero.org_id, "advisor", incidents=0)

        url = build_host_view_url(query="?incident_status=no_incident")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_ids = {str(r["id"]) for r in response_data["results"]}
        assert str(host_zero.id) in result_ids
        assert str(host_null.id) not in result_ids

    def test_invalid_incident_status_returns_400(self, api_get, db_create_host):
        """Invalid incident_status value returns 400."""
        db_create_host()
        url = build_host_view_url(query="?incident_status=maybe")
        response_status, _ = api_get(url)
        assert_response_status(response_status, 400)


class TestCombinedSeverityAndIncidentFilters:
    """Tests for using both recommendation_severity and incident_status together."""

    def test_severity_and_incident_combined(self, api_get, db_create_host):
        """Both filters are ANDed: host must have critical > 0 AND incidents > 0."""
        host_both = db_create_host(extra_data={"display_name": "host-both"})
        host_critical_only = db_create_host(extra_data={"display_name": "host-critical-only"})
        host_incident_only = db_create_host(extra_data={"display_name": "host-incident-only"})

        db_create_host_app_data(host_both.id, host_both.org_id, "advisor", critical=2, incidents=3)
        db_create_host_app_data(host_critical_only.id, host_critical_only.org_id, "advisor", critical=1, incidents=0)
        db_create_host_app_data(host_incident_only.id, host_incident_only.org_id, "advisor", critical=0, incidents=5)

        url = build_host_view_url(query="?recommendation_severity=critical&incident_status=incident")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_ids = {str(r["id"]) for r in response_data["results"]}
        assert str(host_both.id) in result_ids
        assert str(host_critical_only.id) not in result_ids
        assert str(host_incident_only.id) not in result_ids


@pytest.mark.usefixtures("enable_rbac")
class TestAdvisorFilterRBAC:
    """Tests for RBAC enforcement on recommendation_severity and incident_status."""

    def _mock_rbac(self, mocker, response_file):
        mock_data = create_mock_rbac_response(response_file)
        mocker.patch("lib.middleware.get_rbac_permissions", return_value=mock_data)
        mocker.patch("lib.middleware.get_flag_value", return_value=True)

    def test_severity_filter_denied_without_advisor_permission(self, api_get, mocker):
        """recommendation_severity returns 403 when user lacks advisor read permission."""
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-no-apps.json")

        url = build_host_view_url(query="?recommendation_severity=critical")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 403)

    def test_incident_filter_denied_without_advisor_permission(self, api_get, mocker):
        """incident_status returns 403 when user lacks advisor read permission."""
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-no-apps.json")

        url = build_host_view_url(query="?incident_status=incident")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 403)

    def test_severity_filter_allowed_with_advisor_permission(self, api_get, db_create_host, mocker):
        """recommendation_severity returns 200 when user has advisor read permission."""
        db_create_host()
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json")

        url = build_host_view_url(query="?recommendation_severity=critical")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 200)

    def test_incident_filter_allowed_with_advisor_permission(self, api_get, db_create_host, mocker):
        """incident_status returns 200 when user has advisor read permission."""
        db_create_host()
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json")

        url = build_host_view_url(query="?incident_status=no_incident")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 200)
