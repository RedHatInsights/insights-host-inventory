"""Integration tests for sorting on the /beta/hosts-view endpoint.

These tests cover end-to-end sort behaviour that unit tests cannot verify:
actual HTTP response ordering by app data fields, NULLS LAST semantics,
and cross-app sort + filter combinations.

Field-map completeness, resolve_app_sort logic, validation errors, pagination,
and standard host-field sorting are already covered in unit tests
(test_filtering_app_data_sorting.py, test_api_host_views.py).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from iqe_host_inventory.fixtures.host_views_fixtures import add_app_data_to_host

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend, pytest.mark.ephemeral]


class TestHostViewAppDataSort:
    """E2E sort ordering by app data fields on /beta/hosts-view."""

    @pytest.mark.parametrize(
        "app_name,field,low_val,high_val",
        [
            pytest.param("advisor", "recommendations", 2, 20, id="advisor"),
            pytest.param("vulnerability", "critical_cves", 1, 10, id="vulnerability"),
        ],
    )
    @pytest.mark.parametrize("order_how", ["ASC", "DESC"])
    def test_sort_by_app_field(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        app_name: str,
        field: str,
        low_val: int,
        high_val: int,
        order_how: str,
    ):
        """Two hosts with distinct values appear in the expected order.

        metadata:
            requirements: inv-host-views-sorting
            assignee: adubey
            importance: high
            title: Test sort by app data field ASC/DESC
        """
        host_low = setup_host_with_app_data(app_name, {field: low_val})
        host_high = setup_host_with_app_data(app_name, {field: high_val})

        response = host_inventory.apis.host_views.get_host_views_response(
            order_by=f"{app_name}:{field}",
            order_how=order_how,
        )
        result_ids = [h.id for h in response.results]

        idx_low = result_ids.index(host_low.id)
        idx_high = result_ids.index(host_high.id)

        if order_how == "ASC":
            assert idx_low < idx_high, f"ASC: {field}={low_val} should precede {field}={high_val}"
        else:
            assert idx_high < idx_low, f"DESC: {field}={high_val} should precede {field}={low_val}"

    def test_sort_three_hosts(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Three hosts with distinct values are fully ordered.

        metadata:
            requirements: inv-host-views-sorting
            assignee: adubey
            importance: high
            title: Test full sort ordering with three hosts
        """
        host_a = setup_host_with_app_data("advisor", {"recommendations": 5})
        host_b = setup_host_with_app_data("advisor", {"recommendations": 15})
        host_c = setup_host_with_app_data("advisor", {"recommendations": 10})

        response = host_inventory.apis.host_views.get_host_views_response(
            order_by="advisor:recommendations",
            order_how="ASC",
        )
        result_ids = [h.id for h in response.results]

        idx_a = result_ids.index(host_a.id)
        idx_b = result_ids.index(host_b.id)
        idx_c = result_ids.index(host_c.id)

        assert idx_a < idx_c < idx_b, (
            f"Expected 5 < 10 < 15, got indices {idx_a}, {idx_c}, {idx_b}"
        )

    def test_nulls_last(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Hosts without app data appear after those with data (NULLS LAST).

        metadata:
            requirements: inv-host-views-sorting
            assignee: adubey
            importance: high
            title: Test NULLS LAST for app data sorting
        """
        host_with = setup_host_with_app_data("advisor", {"recommendations": 10})
        host_without = host_inventory.kafka.create_host()

        response = host_inventory.apis.host_views.get_host_views_response(
            order_by="advisor:recommendations",
            order_how="ASC",
        )
        result_ids = [h.id for h in response.results]

        if host_without.id in result_ids:
            assert result_ids.index(host_with.id) < result_ids.index(host_without.id), (
                "Host with data should appear before host without (NULLS LAST)"
            )

    def test_sort_one_app_filter_another(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Filter by advisor but sort by vulnerability — independent operations.

        metadata:
            requirements: inv-host-views-sorting, inv-host-views-filter
            assignee: adubey
            importance: high
            title: Test cross-app sort + filter
        """
        host_a = setup_host_with_app_data("advisor", {"recommendations": 10})
        add_app_data_to_host(host_inventory, host_a, "vulnerability", {"critical_cves": 20})

        host_b = setup_host_with_app_data("advisor", {"recommendations": 8})
        add_app_data_to_host(host_inventory, host_b, "vulnerability", {"critical_cves": 5})

        # This host should be filtered out (recommendations < 5)
        host_c = setup_host_with_app_data("advisor", {"recommendations": 1})
        add_app_data_to_host(host_inventory, host_c, "vulnerability", {"critical_cves": 50})

        response = host_inventory.apis.host_views.get_host_views_response(
            filter=["[advisor][recommendations][gte]=5"],
            order_by="vulnerability:critical_cves",
            order_how="DESC",
        )
        result_ids = [h.id for h in response.results]

        assert host_c.id not in result_ids, "host_c should be filtered out"
        assert host_a.id in result_ids
        assert host_b.id in result_ids

        assert result_ids.index(host_a.id) < result_ids.index(host_b.id), (
            "DESC by critical_cves: host_a(20) before host_b(5)"
        )
