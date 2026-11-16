from __future__ import annotations

import pytest

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_view_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.db_utils import db_create_host_app_data


def _advisor_hosts(db_create_host):
    """Seed every Advisor row shape the filters can distinguish.

    Counts are written directly. No Advisor service is called.
    """
    rows = {
        "critical_only": {"critical": 2, "important": 0, "moderate": 0, "low": 0, "incidents": 0},
        "important_present": {"critical": 0, "important": 3, "moderate": 0, "low": 0, "incidents": 2},
        "moderate_only": {"critical": 0, "important": 0, "moderate": 4, "low": 0, "incidents": 0},
        "low_present": {"critical": 0, "important": 0, "moderate": 0, "low": 5, "incidents": 1},
        "all_zero": {"critical": 0, "important": 0, "moderate": 0, "low": 0, "incidents": 0},
        "all_present": {"critical": 1, "important": 1, "moderate": 1, "low": 1, "incidents": 4},
        "null_incidents": {"critical": 1, "important": 0, "moderate": 0, "low": 0, "incidents": None},
    }
    hosts = {}
    for name, data in rows.items():
        host = db_create_host(extra_data={"display_name": name})
        db_create_host_app_data(host.id, host.org_id, "advisor", recommendations=1, **data)
        hosts[name] = host
    hosts["not_analyzed"] = db_create_host(extra_data={"display_name": "not-analyzed"})
    return hosts


def _assert_advisor_filter(api_get, hosts, query, expected):
    response_status, response_data = api_get(build_host_view_url(query=query))
    assert_response_status(response_status, 200)
    result_ids = {str(row["id"]) for row in response_data["results"]}
    expected_ids = {str(hosts[name].id) for name in expected}
    assert result_ids == expected_ids
    assert response_data["total"] == len(expected)


class TestRecommendationSeverityFilter:
    """recommendation_severity is a repeated query param. Values are OR."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("?recommendation_severity=critical", {"critical_only", "all_present", "null_incidents"}),
            ("?recommendation_severity=important", {"important_present", "all_present"}),
            ("?recommendation_severity=moderate", {"moderate_only", "all_present"}),
            ("?recommendation_severity=low", {"low_present", "all_present"}),
            ("?recommendation_severity=not_analyzed", {"not_analyzed"}),
            (
                "?recommendation_severity=critical&recommendation_severity=low",
                {"critical_only", "low_present", "all_present", "null_incidents"},
            ),
            (
                "?recommendation_severity=critical&recommendation_severity=not_analyzed",
                {"critical_only", "all_present", "null_incidents", "not_analyzed"},
            ),
            (
                "?recommendation_severity=important&recommendation_severity=moderate",
                {"important_present", "moderate_only", "all_present"},
            ),
            (
                "?recommendation_severity=critical&recommendation_severity=important"
                "&recommendation_severity=moderate&recommendation_severity=low",
                {
                    "critical_only",
                    "important_present",
                    "moderate_only",
                    "low_present",
                    "all_present",
                    "null_incidents",
                },
            ),
            (
                "?recommendation_severity=critical&recommendation_severity=important"
                "&recommendation_severity=moderate&recommendation_severity=low"
                "&recommendation_severity=not_analyzed",
                {
                    "critical_only",
                    "important_present",
                    "moderate_only",
                    "low_present",
                    "all_present",
                    "null_incidents",
                    "not_analyzed",
                },
            ),
        ],
    )
    def test_severity_combinations(self, api_get, db_create_host, query, expected):
        hosts = _advisor_hosts(db_create_host)
        _assert_advisor_filter(api_get, hosts, query, expected)

    def test_no_severity_selected_returns_all(self, api_get, db_create_host):
        hosts = _advisor_hosts(db_create_host)
        _assert_advisor_filter(api_get, hosts, "", set(hosts))

    def test_matching_host_returns_full_advisor_payload(self, api_get, db_create_host):
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

        response_status, response_data = api_get(build_host_view_url(query="?recommendation_severity=critical"))

        assert_response_status(response_status, 200)
        advisor_data = response_data["results"][0]["app_data"]["advisor"]
        assert advisor_data["critical"] == 2
        assert advisor_data["important"] == 3
        assert advisor_data["moderate"] == 1
        assert advisor_data["low"] == 4
        assert advisor_data["incidents"] == 1

    @pytest.mark.parametrize(
        "query",
        [
            "?recommendation_severity=extreme",
            "?recommendation_severity=critical,low",
            "?recommendation_severity=incident",
        ],
    )
    def test_invalid_severity_returns_400(self, api_get, query):
        response_status, _ = api_get(build_host_view_url(query=query))
        assert_response_status(response_status, 400)


class TestIncidentStatusFilter:
    """incident_status is a repeated query param. Values are OR."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("?incident_status=present", {"important_present", "low_present", "all_present"}),
            (
                "?incident_status=not_present",
                {"critical_only", "moderate_only", "all_zero"},
            ),
            ("?incident_status=not_analyzed", {"not_analyzed"}),
            (
                "?incident_status=present&incident_status=not_present",
                {
                    "critical_only",
                    "important_present",
                    "moderate_only",
                    "low_present",
                    "all_zero",
                    "all_present",
                },
            ),
            (
                "?incident_status=present&incident_status=not_analyzed",
                {"important_present", "low_present", "all_present", "not_analyzed"},
            ),
            (
                "?incident_status=not_present&incident_status=not_analyzed",
                {"critical_only", "moderate_only", "all_zero", "not_analyzed"},
            ),
            (
                "?incident_status=present&incident_status=not_present&incident_status=not_analyzed",
                {
                    "critical_only",
                    "important_present",
                    "moderate_only",
                    "low_present",
                    "all_zero",
                    "all_present",
                    "not_analyzed",
                },
            ),
        ],
    )
    def test_incident_combinations(self, api_get, db_create_host, query, expected):
        hosts = _advisor_hosts(db_create_host)
        _assert_advisor_filter(api_get, hosts, query, expected)

    @pytest.mark.parametrize(
        "query",
        [
            "?incident_status=maybe",
            "?incident_status=incident",
            "?incident_status=no_incident",
            "?incident_status=present,not_analyzed",
        ],
    )
    def test_invalid_incident_status_returns_400(self, api_get, query):
        response_status, _ = api_get(build_host_view_url(query=query))
        assert_response_status(response_status, 400)


class TestCombinedSeverityAndIncidentFilters:
    """The two Advisor params are AND. Values inside each param stay OR."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            (
                "?recommendation_severity=critical&incident_status=present",
                {"all_present"},
            ),
            (
                "?recommendation_severity=critical&incident_status=not_present",
                {"critical_only"},
            ),
            (
                "?recommendation_severity=critical&incident_status=not_analyzed",
                set(),
            ),
            (
                "?recommendation_severity=not_analyzed&incident_status=not_analyzed",
                {"not_analyzed"},
            ),
            (
                "?recommendation_severity=not_analyzed&incident_status=present",
                set(),
            ),
            (
                "?recommendation_severity=low&incident_status=not_present",
                set(),
            ),
            (
                "?recommendation_severity=low&incident_status=present",
                {"low_present", "all_present"},
            ),
            (
                "?recommendation_severity=critical&recommendation_severity=not_analyzed&incident_status=not_analyzed",
                {"not_analyzed"},
            ),
            (
                "?recommendation_severity=critical&recommendation_severity=important"
                "&incident_status=present&incident_status=not_present",
                {"critical_only", "important_present", "all_present"},
            ),
            (
                "?recommendation_severity=moderate&recommendation_severity=low"
                "&incident_status=present&incident_status=not_analyzed",
                {"low_present", "all_present"},
            ),
            (
                "?recommendation_severity=critical&recommendation_severity=important"
                "&recommendation_severity=moderate&recommendation_severity=low"
                "&recommendation_severity=not_analyzed"
                "&incident_status=present&incident_status=not_present&incident_status=not_analyzed",
                {
                    "critical_only",
                    "important_present",
                    "moderate_only",
                    "low_present",
                    "all_present",
                    "not_analyzed",
                },
            ),
        ],
    )
    def test_combined_filters(self, api_get, db_create_host, query, expected):
        hosts = _advisor_hosts(db_create_host)
        _assert_advisor_filter(api_get, hosts, query, expected)


@pytest.mark.usefixtures("enable_rbac")
class TestAdvisorFilterRBAC:
    """Tests for RBAC enforcement on recommendation_severity and incident_status."""

    def _mock_rbac(self, mocker, response_file):
        mock_data = create_mock_rbac_response(response_file)
        mocker.patch("lib.middleware.get_rbac_permissions", return_value=mock_data)
        mocker.patch("lib.middleware.get_flag_value", return_value=True)

    @pytest.mark.parametrize(
        "query",
        [
            "?recommendation_severity=critical",
            "?recommendation_severity=not_analyzed",
            "?incident_status=present",
            "?incident_status=not_present&incident_status=not_analyzed",
        ],
    )
    def test_advisor_filters_denied_without_advisor_permission(self, api_get, mocker, query):
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-no-apps.json")
        response_status, _ = api_get(build_host_view_url(query=query))
        assert_response_status(response_status, 403)

    @pytest.mark.parametrize(
        "query",
        [
            "?recommendation_severity=critical&recommendation_severity=not_analyzed",
            "?incident_status=present&incident_status=not_analyzed",
        ],
    )
    def test_advisor_filters_allowed_with_advisor_permission(self, api_get, db_create_host, mocker, query):
        db_create_host()
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json")
        response_status, _ = api_get(build_host_view_url(query=query))
        assert_response_status(response_status, 200)
