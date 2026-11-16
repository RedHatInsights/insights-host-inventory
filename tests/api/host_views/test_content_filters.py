from __future__ import annotations

from uuid import uuid4

import pytest

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_view_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.db_utils import db_create_host_app_data


def _content_hosts(db_create_host):
    """Seed every Content row shape the filters can distinguish.

    Counts are written directly. No Patch service is called.
    """
    rows = {
        "security_only": {
            "advisories_rhsa_installable": 2,
            "advisories_rhba_installable": 0,
            "advisories_rhea_installable": 0,
            "advisories_other_installable": 0,
            "template_uuid": uuid4(),
        },
        "bugfix_only": {
            "advisories_rhsa_installable": 0,
            "advisories_rhba_installable": 3,
            "advisories_rhea_installable": 0,
            "advisories_other_installable": 0,
            "template_uuid": None,
        },
        "enhancement_only": {
            "advisories_rhsa_installable": 0,
            "advisories_rhba_installable": 0,
            "advisories_rhea_installable": 4,
            "advisories_other_installable": 0,
            "template_uuid": uuid4(),
        },
        "other_only": {
            "advisories_rhsa_installable": 0,
            "advisories_rhba_installable": 0,
            "advisories_rhea_installable": 0,
            "advisories_other_installable": 5,
            "template_uuid": None,
        },
        "all_zero": {
            "advisories_rhsa_installable": 0,
            "advisories_rhba_installable": 0,
            "advisories_rhea_installable": 0,
            "advisories_other_installable": 0,
            "template_uuid": None,
        },
        "all_types": {
            "advisories_rhsa_installable": 1,
            "advisories_rhba_installable": 1,
            "advisories_rhea_installable": 1,
            "advisories_other_installable": 1,
            "template_uuid": uuid4(),
        },
        "null_counts": {
            "advisories_rhsa_installable": None,
            "advisories_rhba_installable": None,
            "advisories_rhea_installable": None,
            "advisories_other_installable": None,
            "template_uuid": uuid4(),
        },
    }
    hosts = {}
    for name, data in rows.items():
        host = db_create_host(extra_data={"display_name": name})
        db_create_host_app_data(host.id, host.org_id, "patch", **data)
        hosts[name] = host
    hosts["not_evaluated"] = db_create_host(extra_data={"display_name": "not_evaluated"})
    return hosts


def _assert_content_filter(api_get, hosts, query, expected):
    response_status, response_data = api_get(build_host_view_url(query=query))
    assert_response_status(response_status, 200)
    result_ids = {str(row["id"]) for row in response_data["results"]}
    expected_ids = {str(hosts[name].id) for name in expected}
    assert result_ids == expected_ids
    assert response_data["total"] == len(expected)


class TestInstallableAdvisoryTypeFilter:
    """installable_advisory_type is a repeated query param. Values are OR."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("?installable_advisory_type=security", {"security_only", "all_types"}),
            ("?installable_advisory_type=bugfix", {"bugfix_only", "all_types"}),
            ("?installable_advisory_type=enhancement", {"enhancement_only", "all_types"}),
            ("?installable_advisory_type=other", {"other_only", "all_types"}),
            ("?installable_advisory_type=not_evaluated", {"not_evaluated"}),
            (
                "?installable_advisory_type=security&installable_advisory_type=bugfix",
                {"security_only", "bugfix_only", "all_types"},
            ),
            (
                "?installable_advisory_type=security&installable_advisory_type=not_evaluated",
                {"security_only", "all_types", "not_evaluated"},
            ),
            (
                "?installable_advisory_type=security&installable_advisory_type=bugfix"
                "&installable_advisory_type=enhancement&installable_advisory_type=other"
                "&installable_advisory_type=not_evaluated",
                {
                    "security_only",
                    "bugfix_only",
                    "enhancement_only",
                    "other_only",
                    "all_types",
                    "not_evaluated",
                },
            ),
        ],
    )
    def test_advisory_type_combinations(self, api_get, db_create_host, query, expected):
        hosts = _content_hosts(db_create_host)
        _assert_content_filter(api_get, hosts, query, expected)

    @pytest.mark.parametrize(
        "query",
        [
            "?installable_advisory_type=unknown",
            "?installable_advisory_type=unspecified",
            "?installable_advisory_type=security,bugfix",
        ],
    )
    def test_invalid_advisory_type_returns_400(self, api_get, query):
        response_status, _ = api_get(build_host_view_url(query=query))
        assert_response_status(response_status, 400)


class TestTemplateFilter:
    """template is a single value. present and not_present are the only choices."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            (
                "?template=present",
                {"security_only", "enhancement_only", "all_types", "null_counts"},
            ),
            (
                "?template=not_present",
                {"bugfix_only", "other_only", "all_zero"},
            ),
        ],
    )
    def test_template_values(self, api_get, db_create_host, query, expected):
        hosts = _content_hosts(db_create_host)
        _assert_content_filter(api_get, hosts, query, expected)

    @pytest.mark.parametrize(
        "query",
        [
            "?template=maybe",
            "?template=present,not_present",
            "?template=not_evaluated",
            "?template=present&template=not_present",
        ],
    )
    def test_invalid_template_returns_400(self, api_get, query):
        response_status, _ = api_get(build_host_view_url(query=query))
        assert_response_status(response_status, 400)


class TestCombinedContentFilters:
    """The two Content params are AND. Advisory values inside one param stay OR."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            (
                "?installable_advisory_type=security&template=present",
                {"security_only", "all_types"},
            ),
            (
                "?installable_advisory_type=security&template=not_present",
                set(),
            ),
            (
                "?installable_advisory_type=bugfix&template=not_present",
                {"bugfix_only"},
            ),
            (
                "?installable_advisory_type=not_evaluated&template=present",
                set(),
            ),
            (
                "?installable_advisory_type=not_evaluated&template=not_present",
                set(),
            ),
            (
                "?installable_advisory_type=other&installable_advisory_type=not_evaluated&template=not_present",
                {"other_only"},
            ),
        ],
    )
    def test_combined_filters(self, api_get, db_create_host, query, expected):
        hosts = _content_hosts(db_create_host)
        _assert_content_filter(api_get, hosts, query, expected)


@pytest.mark.usefixtures("enable_rbac")
class TestContentFilterRBAC:
    """Content filters require the patch read permission."""

    def _mock_rbac(self, mocker, response_file):
        mock_data = create_mock_rbac_response(response_file)
        mocker.patch("lib.middleware.get_rbac_permissions", return_value=mock_data)
        mocker.patch("lib.middleware.get_flag_value", return_value=True)

    @pytest.mark.parametrize(
        "query",
        [
            "?installable_advisory_type=security",
            "?installable_advisory_type=not_evaluated",
            "?template=present",
            "?template=not_present",
        ],
    )
    def test_content_filters_denied_without_permission(self, api_get, mocker, query):
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json")
        response_status, _ = api_get(build_host_view_url(query=query))
        assert_response_status(response_status, 403)

    def test_content_filters_allowed_with_permission(self, api_get, db_create_host, mocker):
        db_create_host()
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-all-apps.json")
        response_status, _ = api_get(build_host_view_url(query="?installable_advisory_type=security&template=present"))
        assert_response_status(response_status, 200)
