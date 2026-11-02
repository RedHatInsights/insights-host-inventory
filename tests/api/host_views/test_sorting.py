from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_view_url


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

    @pytest.mark.parametrize("field_name", ["moderate_cves", "low_cves"])
    def test_sort_by_vulnerability_moderate_and_low_cves(
        self, api_get, db_create_host, db_create_host_app_data, field_name
    ):
        """Sort by vulnerability:moderate_cves / vulnerability:low_cves should order hosts by that count."""
        host_low = db_create_host(extra_data={"display_name": "host-low.example.com"})
        host_high = db_create_host(extra_data={"display_name": "host-high.example.com"})

        db_create_host_app_data(host_low.id, host_low.org_id, "vulnerability", **{field_name: 4})
        db_create_host_app_data(host_high.id, host_high.org_id, "vulnerability", **{field_name: 12})

        url = build_host_view_url(query=f"?order_by=vulnerability:{field_name}&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["vulnerability"][field_name] == 12
        assert results[1]["app_data"]["vulnerability"][field_name] == 4

        url = build_host_view_url(query=f"?order_by=vulnerability:{field_name}&order_how=ASC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["vulnerability"][field_name] == 4
        assert results[1]["app_data"]["vulnerability"][field_name] == 12

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

    @pytest.mark.parametrize("order_how,expected_order", [("ASC", [0, 2, 5]), ("DESC", [5, 2, 0])])
    def test_sort_by_patch_advisories_total_installable(
        self, api_get, db_create_host, db_create_host_app_data, order_how, expected_order
    ):
        """Sort by patch:advisories_total_installable should sort by the sum of all installable types."""
        hosts_data = [
            {"name": "host-0.example.com", "rhsa": 0, "rhba": 0, "rhea": 0, "other": 0},
            {"name": "host-2.example.com", "rhsa": 0, "rhba": 1, "rhea": 0, "other": 1},
            {"name": "host-5.example.com", "rhsa": 3, "rhba": 1, "rhea": 1, "other": 0},
        ]

        for hd in hosts_data:
            host = db_create_host(extra_data={"display_name": hd["name"]})
            db_create_host_app_data(
                host.id,
                host.org_id,
                "patch",
                advisories_rhsa_installable=hd["rhsa"],
                advisories_rhba_installable=hd["rhba"],
                advisories_rhea_installable=hd["rhea"],
                advisories_other_installable=hd["other"],
            )

        url = build_host_view_url(query=f"?order_by=patch:advisories_total_installable&order_how={order_how}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        result_names = [r["display_name"] for r in results]
        expected_names = [f"host-{t}.example.com" for t in expected_order]
        assert result_names == expected_names

    @pytest.mark.parametrize("order_how", ["ASC", "DESC"])
    def test_sort_by_patch_advisories_total_installable_nulls_last(
        self, api_get, db_create_host, db_create_host_app_data, order_how
    ):
        """Hosts without patch data should appear last regardless of sort direction."""
        host_with_data = db_create_host(extra_data={"display_name": "host-with-data.example.com"})
        db_create_host(extra_data={"display_name": "host-no-data.example.com"})

        db_create_host_app_data(
            host_with_data.id,
            host_with_data.org_id,
            "patch",
            advisories_rhsa_installable=0,
            advisories_rhba_installable=0,
            advisories_rhea_installable=0,
            advisories_other_installable=0,
        )

        url = build_host_view_url(query=f"?order_by=patch:advisories_total_installable&order_how={order_how}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["display_name"] == "host-with-data.example.com"
        assert results[1]["display_name"] == "host-no-data.example.com"

    @pytest.mark.parametrize("order_how,expected_order", [("ASC", [0, 9, 15]), ("DESC", [15, 9, 0])])
    def test_sort_by_patch_advisories_total_applicable(
        self, api_get, db_create_host, db_create_host_app_data, order_how, expected_order
    ):
        """Sort by patch:advisories_total_applicable should sort by the sum of all applicable types."""
        hosts_data = [
            {"name": "host-0.example.com", "rhsa": 0, "rhba": 0, "rhea": 0, "other": 0},
            {"name": "host-9.example.com", "rhsa": 3, "rhba": 4, "rhea": 2, "other": 0},
            {"name": "host-15.example.com", "rhsa": 10, "rhba": 5, "rhea": 0, "other": 0},
        ]

        for hd in hosts_data:
            host = db_create_host(extra_data={"display_name": hd["name"]})
            db_create_host_app_data(
                host.id,
                host.org_id,
                "patch",
                advisories_rhsa_applicable=hd["rhsa"],
                advisories_rhba_applicable=hd["rhba"],
                advisories_rhea_applicable=hd["rhea"],
                advisories_other_applicable=hd["other"],
            )

        url = build_host_view_url(query=f"?order_by=patch:advisories_total_applicable&order_how={order_how}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        result_names = [r["display_name"] for r in results]
        expected_names = [f"host-{t}.example.com" for t in expected_order]
        assert result_names == expected_names

    @pytest.mark.parametrize("order_how", ["ASC", "DESC"])
    def test_sort_by_patch_advisories_total_applicable_nulls_last(
        self, api_get, db_create_host, db_create_host_app_data, order_how
    ):
        """Hosts without patch data should appear last regardless of sort direction."""
        host_with_data = db_create_host(extra_data={"display_name": "host-with-data.example.com"})
        db_create_host(extra_data={"display_name": "host-no-data.example.com"})

        db_create_host_app_data(
            host_with_data.id,
            host_with_data.org_id,
            "patch",
            advisories_rhsa_applicable=0,
            advisories_rhba_applicable=0,
            advisories_rhea_applicable=0,
            advisories_other_applicable=0,
        )

        url = build_host_view_url(query=f"?order_by=patch:advisories_total_applicable&order_how={order_how}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["display_name"] == "host-with-data.example.com"
        assert results[1]["display_name"] == "host-no-data.example.com"

    @pytest.mark.parametrize("order_how", ["ASC", "DESC"])
    def test_sort_by_advisor_severity_priority(self, api_get, db_create_host, db_create_host_app_data, order_how):
        """Sort by advisor:severity_priority uses multi-column priority: critical > important > moderate > low."""
        hosts_data = [
            {"name": "host-zero.example.com", "critical": 0, "important": 0, "moderate": 0, "low": 0},
            {"name": "host-low-only.example.com", "critical": 0, "important": 0, "moderate": 0, "low": 3},
            {"name": "host-imp.example.com", "critical": 0, "important": 2, "moderate": 1, "low": 0},
            {"name": "host-crit.example.com", "critical": 2, "important": 3, "moderate": 1, "low": 0},
        ]
        expected_asc = [
            "host-zero.example.com",
            "host-low-only.example.com",
            "host-imp.example.com",
            "host-crit.example.com",
        ]
        expected_desc = list(reversed(expected_asc))

        for hd in hosts_data:
            host = db_create_host(extra_data={"display_name": hd["name"]})
            db_create_host_app_data(
                host.id,
                host.org_id,
                "advisor",
                critical=hd["critical"],
                important=hd["important"],
                moderate=hd["moderate"],
                low=hd["low"],
                recommendations=hd["critical"] + hd["important"] + hd["moderate"] + hd["low"],
            )

        url = build_host_view_url(query=f"?order_by=advisor:severity_priority&order_how={order_how}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_names = [r["display_name"] for r in response_data["results"]]
        assert result_names == (expected_asc if order_how == "ASC" else expected_desc)

    def test_sort_by_advisor_severity_priority_critical_beats_any_lower(
        self, api_get, db_create_host, db_create_host_app_data
    ):
        """One critical recommendation must sort above any number of important/moderate/low."""
        hosts_data = [
            {"name": "host-many-imp.example.com", "critical": 0, "important": 999, "moderate": 999, "low": 999},
            {"name": "host-one-crit.example.com", "critical": 1, "important": 0, "moderate": 0, "low": 0},
        ]

        for hd in hosts_data:
            host = db_create_host(extra_data={"display_name": hd["name"]})
            db_create_host_app_data(
                host.id,
                host.org_id,
                "advisor",
                critical=hd["critical"],
                important=hd["important"],
                moderate=hd["moderate"],
                low=hd["low"],
                recommendations=hd["critical"] + hd["important"] + hd["moderate"] + hd["low"],
            )

        url = build_host_view_url(query="?order_by=advisor:severity_priority&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["display_name"] == "host-one-crit.example.com"
        assert results[1]["display_name"] == "host-many-imp.example.com"

    def test_sort_by_advisor_severity_priority_tiebreak_on_next_level(
        self, api_get, db_create_host, db_create_host_app_data
    ):
        """When critical counts are equal, important breaks the tie, then moderate, then low."""
        hosts_data = [
            {"name": "host-a.example.com", "critical": 1, "important": 0, "moderate": 5, "low": 0},
            {"name": "host-b.example.com", "critical": 1, "important": 3, "moderate": 0, "low": 0},
            {"name": "host-c.example.com", "critical": 1, "important": 3, "moderate": 2, "low": 0},
            {"name": "host-d.example.com", "critical": 1, "important": 3, "moderate": 2, "low": 7},
        ]

        for hd in hosts_data:
            host = db_create_host(extra_data={"display_name": hd["name"]})
            db_create_host_app_data(
                host.id,
                host.org_id,
                "advisor",
                critical=hd["critical"],
                important=hd["important"],
                moderate=hd["moderate"],
                low=hd["low"],
                recommendations=hd["critical"] + hd["important"] + hd["moderate"] + hd["low"],
            )

        url = build_host_view_url(query="?order_by=advisor:severity_priority&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_names = [r["display_name"] for r in response_data["results"]]
        assert result_names == [
            "host-d.example.com",  # 1 crit, 3 imp, 2 mod, 7 low
            "host-c.example.com",  # 1 crit, 3 imp, 2 mod, 0 low
            "host-b.example.com",  # 1 crit, 3 imp, 0 mod, 0 low
            "host-a.example.com",  # 1 crit, 0 imp, 5 mod, 0 low
        ]

    @pytest.mark.parametrize("order_how", ["ASC", "DESC"])
    def test_sort_by_advisor_severity_priority_nulls_last(
        self, api_get, db_create_host, db_create_host_app_data, order_how
    ):
        """Hosts without advisor data should appear last regardless of sort direction."""
        host_with_data = db_create_host(extra_data={"display_name": "host-with-data.example.com"})
        db_create_host(extra_data={"display_name": "host-no-data.example.com"})

        db_create_host_app_data(
            host_with_data.id,
            host_with_data.org_id,
            "advisor",
            critical=0,
            important=0,
            moderate=0,
            low=0,
            recommendations=0,
        )

        url = build_host_view_url(query=f"?order_by=advisor:severity_priority&order_how={order_how}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["display_name"] == "host-with-data.example.com"
        assert results[1]["display_name"] == "host-no-data.example.com"

    @pytest.mark.parametrize("order_how", ["ASC", "DESC"])
    def test_sort_by_vulnerability_severity_priority(
        self, api_get, db_create_host, db_create_host_app_data, order_how
    ):
        """Sort by vulnerability:severity_priority: critical > important > moderate > low."""
        hosts_data = [
            {"name": "host-zero.example.com", "critical": 0, "important": 0, "moderate": 0, "low": 0},
            {"name": "host-low-only.example.com", "critical": 0, "important": 0, "moderate": 0, "low": 3},
            {"name": "host-imp.example.com", "critical": 0, "important": 2, "moderate": 1, "low": 0},
            {"name": "host-crit.example.com", "critical": 2, "important": 3, "moderate": 1, "low": 0},
        ]
        expected_asc = [
            "host-zero.example.com",
            "host-low-only.example.com",
            "host-imp.example.com",
            "host-crit.example.com",
        ]
        expected_desc = list(reversed(expected_asc))

        for hd in hosts_data:
            host = db_create_host(extra_data={"display_name": hd["name"]})
            db_create_host_app_data(
                host.id,
                host.org_id,
                "vulnerability",
                critical_cves=hd["critical"],
                important_cves=hd["important"],
                moderate_cves=hd["moderate"],
                low_cves=hd["low"],
                total_cves=hd["critical"] + hd["important"] + hd["moderate"] + hd["low"],
            )

        url = build_host_view_url(query=f"?order_by=vulnerability:severity_priority&order_how={order_how}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_names = [r["display_name"] for r in response_data["results"]]
        assert result_names == (expected_asc if order_how == "ASC" else expected_desc)

    def test_sort_by_vulnerability_severity_priority_critical_beats_any_lower(
        self, api_get, db_create_host, db_create_host_app_data
    ):
        """One critical CVE must sort above any number of important/moderate/low."""
        hosts_data = [
            {"name": "host-many-imp.example.com", "critical": 0, "important": 999, "moderate": 999, "low": 999},
            {"name": "host-one-crit.example.com", "critical": 1, "important": 0, "moderate": 0, "low": 0},
        ]

        for hd in hosts_data:
            host = db_create_host(extra_data={"display_name": hd["name"]})
            db_create_host_app_data(
                host.id,
                host.org_id,
                "vulnerability",
                critical_cves=hd["critical"],
                important_cves=hd["important"],
                moderate_cves=hd["moderate"],
                low_cves=hd["low"],
                total_cves=hd["critical"] + hd["important"] + hd["moderate"] + hd["low"],
            )

        url = build_host_view_url(query="?order_by=vulnerability:severity_priority&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["display_name"] == "host-one-crit.example.com"
        assert results[1]["display_name"] == "host-many-imp.example.com"

    def test_sort_by_vulnerability_severity_priority_tiebreak_on_next_level(
        self, api_get, db_create_host, db_create_host_app_data
    ):
        """When critical counts are equal, important breaks the tie, then moderate, then low."""
        hosts_data = [
            {"name": "host-a.example.com", "critical": 1, "important": 0, "moderate": 5, "low": 0},
            {"name": "host-b.example.com", "critical": 1, "important": 3, "moderate": 0, "low": 0},
            {"name": "host-c.example.com", "critical": 1, "important": 3, "moderate": 2, "low": 0},
            {"name": "host-d.example.com", "critical": 1, "important": 3, "moderate": 2, "low": 7},
        ]

        for hd in hosts_data:
            host = db_create_host(extra_data={"display_name": hd["name"]})
            db_create_host_app_data(
                host.id,
                host.org_id,
                "vulnerability",
                critical_cves=hd["critical"],
                important_cves=hd["important"],
                moderate_cves=hd["moderate"],
                low_cves=hd["low"],
                total_cves=hd["critical"] + hd["important"] + hd["moderate"] + hd["low"],
            )

        url = build_host_view_url(query="?order_by=vulnerability:severity_priority&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_names = [r["display_name"] for r in response_data["results"]]
        assert result_names == [
            "host-d.example.com",  # 1 crit, 3 imp, 2 mod, 7 low
            "host-c.example.com",  # 1 crit, 3 imp, 2 mod, 0 low
            "host-b.example.com",  # 1 crit, 3 imp, 0 mod, 0 low
            "host-a.example.com",  # 1 crit, 0 imp, 5 mod, 0 low
        ]

    @pytest.mark.parametrize("order_how", ["ASC", "DESC"])
    def test_sort_by_vulnerability_severity_priority_nulls_last(
        self, api_get, db_create_host, db_create_host_app_data, order_how
    ):
        """Hosts without vulnerability data should appear last regardless of sort direction."""
        host_with_data = db_create_host(extra_data={"display_name": "host-with-data.example.com"})
        db_create_host(extra_data={"display_name": "host-no-data.example.com"})

        db_create_host_app_data(
            host_with_data.id,
            host_with_data.org_id,
            "vulnerability",
            critical_cves=0,
            important_cves=0,
            moderate_cves=0,
            low_cves=0,
            total_cves=0,
        )

        url = build_host_view_url(query=f"?order_by=vulnerability:severity_priority&order_how={order_how}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["display_name"] == "host-with-data.example.com"
        assert results[1]["display_name"] == "host-no-data.example.com"

    def test_sort_by_vulnerability_severity_priority_incomplete_row_coalesces(
        self, api_get, db_create_host, db_create_host_app_data
    ):
        """Existing vulnerability rows with NULL severity columns coalesce to 0; missing rows stay last."""
        host_partial = db_create_host(extra_data={"display_name": "host-partial.example.com"})
        host_imp = db_create_host(extra_data={"display_name": "host-imp.example.com"})
        db_create_host(extra_data={"display_name": "host-no-row.example.com"})

        # Row exists but severity columns left NULL — should sort like all zeros
        db_create_host_app_data(host_partial.id, host_partial.org_id, "vulnerability")
        db_create_host_app_data(
            host_imp.id,
            host_imp.org_id,
            "vulnerability",
            critical_cves=0,
            important_cves=2,
            moderate_cves=0,
            low_cves=0,
            total_cves=2,
        )

        url = build_host_view_url(query="?order_by=vulnerability:severity_priority&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result_names = [r["display_name"] for r in response_data["results"]]
        assert result_names == [
            "host-imp.example.com",
            "host-partial.example.com",
            "host-no-row.example.com",
        ]

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

    def test_sort_by_malware_last_status(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by malware:last_status should work correctly."""
        host1 = db_create_host(extra_data={"display_name": "host1.example.com"})
        host2 = db_create_host(extra_data={"display_name": "host2.example.com"})

        db_create_host_app_data(host1.id, host1.org_id, "malware", last_status="clean")
        db_create_host_app_data(host2.id, host2.org_id, "malware", last_status="infected")

        url = build_host_view_url(query="?order_by=malware:last_status&order_how=ASC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["malware"]["last_status"] == "clean"
        assert results[1]["app_data"]["malware"]["last_status"] == "infected"

    def test_sort_by_compliance_policies_count(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by compliance:policies_count should order hosts by number of policies."""
        host_few = db_create_host(extra_data={"display_name": "host-few.example.com"})
        host_many = db_create_host(extra_data={"display_name": "host-many.example.com"})

        db_create_host_app_data(host_few.id, host_few.org_id, "compliance", policies=[{"name": "alpha"}])
        db_create_host_app_data(
            host_many.id, host_many.org_id, "compliance", policies=[{"name": "beta"}, {"name": "gamma"}]
        )

        url = build_host_view_url(query="?order_by=compliance:policies_count&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["display_name"] == "host-many.example.com"
        assert results[1]["display_name"] == "host-few.example.com"

    def test_sort_by_patch_template_name(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by patch:template_name should work correctly."""
        host1 = db_create_host(extra_data={"display_name": "host1.example.com"})
        host2 = db_create_host(extra_data={"display_name": "host2.example.com"})

        db_create_host_app_data(host1.id, host1.org_id, "patch", template_name="alpha-template")
        db_create_host_app_data(host2.id, host2.org_id, "patch", template_name="zeta-template")

        url = build_host_view_url(query="?order_by=patch:template_name&order_how=ASC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["patch"]["template_name"] == "alpha-template"
        assert results[1]["app_data"]["patch"]["template_name"] == "zeta-template"

    def test_sort_by_vulnerability_important_cves(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by vulnerability:important_cves should work correctly."""
        host1 = db_create_host(extra_data={"display_name": "host1.example.com"})
        host2 = db_create_host(extra_data={"display_name": "host2.example.com"})

        db_create_host_app_data(host1.id, host1.org_id, "vulnerability", important_cves=3)
        db_create_host_app_data(host2.id, host2.org_id, "vulnerability", important_cves=15)

        url = build_host_view_url(query="?order_by=vulnerability:important_cves&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["vulnerability"]["important_cves"] == 15
        assert results[1]["app_data"]["vulnerability"]["important_cves"] == 3

    def test_sort_by_vulnerability_cves_with_security_rules(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by vulnerability:cves_with_security_rules should work correctly."""
        host1 = db_create_host(extra_data={"display_name": "host1.example.com"})
        host2 = db_create_host(extra_data={"display_name": "host2.example.com"})

        db_create_host_app_data(host1.id, host1.org_id, "vulnerability", cves_with_security_rules=1)
        db_create_host_app_data(host2.id, host2.org_id, "vulnerability", cves_with_security_rules=8)

        url = build_host_view_url(query="?order_by=vulnerability:cves_with_security_rules&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["vulnerability"]["cves_with_security_rules"] == 8
        assert results[1]["app_data"]["vulnerability"]["cves_with_security_rules"] == 1

    def test_sort_by_vulnerability_cves_with_known_exploits(self, api_get, db_create_host, db_create_host_app_data):
        """Sort by vulnerability:cves_with_known_exploits should work correctly."""
        host1 = db_create_host(extra_data={"display_name": "host1.example.com"})
        host2 = db_create_host(extra_data={"display_name": "host2.example.com"})

        db_create_host_app_data(host1.id, host1.org_id, "vulnerability", cves_with_known_exploits=2)
        db_create_host_app_data(host2.id, host2.org_id, "vulnerability", cves_with_known_exploits=12)

        url = build_host_view_url(query="?order_by=vulnerability:cves_with_known_exploits&order_how=DESC")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        results = response_data["results"]
        assert results[0]["app_data"]["vulnerability"]["cves_with_known_exploits"] == 12
        assert results[1]["app_data"]["vulnerability"]["cves_with_known_exploits"] == 2

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

    def test_sort_and_filter_same_app(self, api_get, db_create_host, db_create_host_app_data):
        """Filter and sort on the same app should work without duplicate join errors."""
        host_low = db_create_host(extra_data={"display_name": "host-low.example.com"})
        host_high = db_create_host(extra_data={"display_name": "host-high.example.com"})
        host_excluded = db_create_host(extra_data={"display_name": "host-excluded.example.com"})

        db_create_host_app_data(
            host_low.id,
            host_low.org_id,
            "patch",
            advisories_rhsa_installable=5,
            packages_installable=50,
            packages_installed=500,
        )
        db_create_host_app_data(
            host_high.id,
            host_high.org_id,
            "patch",
            advisories_rhsa_installable=20,
            packages_installable=200,
            packages_installed=100,
        )
        db_create_host_app_data(
            host_excluded.id,
            host_excluded.org_id,
            "patch",
            advisories_rhsa_installable=1,
            packages_installable=10,
            packages_installed=50,
        )

        # Filter: advisories >= 5, Sort: packages_installable DESC
        url = build_host_view_url(
            query="?filter[patch][advisories_rhsa_installable][gte]=5"
            "&order_by=patch:packages_installable&order_how=DESC"
        )
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 2  # host_excluded filtered out
        results = response_data["results"]
        assert results[0]["app_data"]["patch"]["packages_installable"] == 200
        assert results[1]["app_data"]["patch"]["packages_installable"] == 50
