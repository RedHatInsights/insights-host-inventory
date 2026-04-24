"""Integration tests for sparse fieldsets on the /beta/hosts-view endpoint.

These tests verify the ``fields`` query parameter, which allows consumers to
request specific application data fields using JSON:API sparse fieldsets syntax:

- fields[app]=true                     → return all fields for that app
- fields[app]=field1,field2            → return only specified fields
- fields[app]=                         → return empty object (per JSON:API spec)
- fields[app_data]=true                → return all apps with all fields

Per JSON:API spec: https://jsonapi.org/format/#fetching-sparse-fieldsets
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


class TestSparseFieldsSingleApp:
    """Test sparse fieldsets for a single application."""

    def test_request_single_app_all_fields(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Requesting fields[advisor]=true returns only advisor with all fields.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: high
            title: Test sparse fields - single app all fields
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})
        add_app_data_to_host(host_inventory, host, "vulnerability")

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[advisor]=true"],
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.advisor is not None
        assert result.app_data.vulnerability is None

        assert result.app_data.advisor.recommendations == 5
        assert result.app_data.advisor.incidents == 2

    def test_request_single_app_specific_fields(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Requesting fields[vulnerability]=critical_cves returns only that field.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: high
            title: Test sparse fields - single app specific fields
        """
        host = setup_host_with_app_data(
            "vulnerability",
            {"total_cves": 10, "critical_cves": 2, "high_severity_cves": 3},
        )

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[vulnerability]=critical_cves"],
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.vulnerability is not None

        vuln_data = result.app_data.vulnerability.to_dict()
        assert "critical_cves" in vuln_data
        assert vuln_data["critical_cves"] == 2

        assert vuln_data.get("total_cves") is None
        assert vuln_data.get("high_severity_cves") is None


class TestSparseFieldsMultipleApps:
    """Test sparse fieldsets for multiple applications."""

    def test_request_multiple_apps_all_fields(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Requesting fields[advisor]=true&fields[vulnerability]=true returns both apps.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: high
            title: Test sparse fields - multiple apps all fields
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})
        add_app_data_to_host(
            host_inventory, host, "vulnerability", {"total_cves": 10, "critical_cves": 2}
        )
        add_app_data_to_host(host_inventory, host, "patch")

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[advisor]=true", "[vulnerability]=true"],
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.advisor is not None
        assert result.app_data.vulnerability is not None
        assert result.app_data.patch is None

    def test_request_multiple_apps_specific_fields(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Request specific fields from multiple apps.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: high
            title: Test sparse fields - multiple apps specific fields
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})
        add_app_data_to_host(
            host_inventory, host, "vulnerability", {"total_cves": 10, "critical_cves": 2}
        )

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=[
                "[advisor]=recommendations",
                "[vulnerability]=critical_cves,total_cves",
            ],
        )

        assert response.total == 1
        result = response.results[0]

        advisor_data = result.app_data.advisor.to_dict()
        assert advisor_data.get("recommendations") == 5
        assert advisor_data.get("incidents") is None

        vuln_data = result.app_data.vulnerability.to_dict()
        assert vuln_data.get("critical_cves") == 2
        assert vuln_data.get("total_cves") == 10
        assert vuln_data.get("high_severity_cves") is None


class TestSparseFieldsMetaKey:
    """Test the fields[app_data]=true meta-key behavior."""

    def test_app_data_true_returns_all_apps(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """fields[app_data]=true returns all available app data.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: high
            title: Test sparse fields - app_data meta-key
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})

        for app_name in ["vulnerability", "remediations"]:
            add_app_data_to_host(host_inventory, host, app_name)

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[app_data]=true"],
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.advisor is not None
        assert result.app_data.vulnerability is not None
        assert result.app_data.remediations is not None

        assert result.app_data.advisor.recommendations == 5
        assert result.app_data.advisor.incidents == 2

    def test_app_data_true_with_app_specific_fields(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """fields[app_data]=true combined with app-specific fields.

        When both are specified, app_data=true takes precedence and returns
        all apps with all fields (the meta-key overrides app-specific selections).

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: medium
            title: Test sparse fields - app_data meta-key with app-specific fields
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})
        add_app_data_to_host(
            host_inventory, host, "vulnerability", {"total_cves": 10, "critical_cves": 2}
        )

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[app_data]=true", "[advisor]=recommendations"],
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.advisor is not None
        assert result.app_data.vulnerability is not None

        assert result.app_data.advisor.recommendations == 5
        assert result.app_data.advisor.incidents == 2
        assert result.app_data.vulnerability.total_cves == 10
        assert result.app_data.vulnerability.critical_cves == 2


class TestSparseFieldsEdgeCases:
    """Test edge cases for sparse fieldsets."""

    def test_empty_fields_returns_empty_object(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Per JSON:API spec, fields[advisor]= (empty) returns empty object.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: medium
            title: Test sparse fields - empty value returns empty object
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[advisor]="],
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.advisor is not None
        advisor_data = result.app_data.advisor.to_dict()
        assert advisor_data.get("recommendations") is None
        assert advisor_data.get("incidents") is None

    def test_request_app_with_no_data(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Requesting an app that has no data returns nothing for that app.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: medium
            title: Test sparse fields - app with no data
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[vulnerability]=true"],
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.vulnerability is None
        assert result.app_data.advisor is None

    def test_invalid_app_name_ignored(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Unrecognized app name in fields parameter falls back to default (all app data returned).

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: medium
            title: Test sparse fields - unrecognized app name falls back to default
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[invalid_app]=something"],
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.advisor is not None
        assert result.app_data.advisor.recommendations == 5

    def test_invalid_field_returns_empty(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Valid app with invalid field returns empty object for that app.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: medium
            title: Test sparse fields - invalid field returns empty
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[advisor]=nonexistent_field"],
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.advisor is not None
        advisor_data = result.app_data.advisor.to_dict()
        assert advisor_data.get("recommendations") is None
        assert advisor_data.get("incidents") is None

    def test_mix_valid_and_invalid_fields(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Mix of valid and invalid fields returns only valid fields.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: medium
            title: Test sparse fields - mixed valid and invalid fields
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[advisor]=recommendations,invalid_field"],
        )

        assert response.total == 1
        result = response.results[0]

        advisor_data = result.app_data.advisor.to_dict()
        assert advisor_data.get("recommendations") == 5
        assert advisor_data.get("incidents") is None


class TestSparseFieldsWithFiltering:
    """Test sparse fields combined with app data filtering."""

    def test_sparse_fields_with_filter(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Sparse fields work together with host filtering.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: high
            title: Test sparse fields combined with filtering
        """
        host1 = setup_host_with_app_data("advisor", {"recommendations": 10, "incidents": 5})
        host2 = setup_host_with_app_data("advisor", {"recommendations": 2, "incidents": 1})

        response = host_inventory.apis.host_views.get_host_views_response(
            filter=["[advisor][recommendations][gte]=5"],
            fields=["[advisor]=recommendations"],
        )

        response_ids = {h.id for h in response.results}
        assert host1.id in response_ids
        assert host2.id not in response_ids

        for result in response.results:
            advisor_data = result.app_data.advisor.to_dict()
            assert advisor_data.get("recommendations") is not None
            assert advisor_data.get("recommendations") >= 5
            assert advisor_data.get("incidents") is None

    def test_sparse_fields_with_display_name_filter(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Sparse fields work with display_name filtering.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: medium
            title: Test sparse fields with display_name filter
        """
        host1 = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})
        setup_host_with_app_data("advisor", {"recommendations": 10, "incidents": 5})

        response = host_inventory.apis.host_views.get_host_views_response(
            display_name=host1.display_name,
            fields=["[advisor]=recommendations"],
        )

        assert response.total == 1
        result = response.results[0]
        assert result.id == host1.id

        advisor_data = result.app_data.advisor.to_dict()
        assert advisor_data.get("recommendations") == 5
        assert advisor_data.get("incidents") is None

    def test_filter_on_one_app_sparse_fields_on_another(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Filter on advisor but request only vulnerability fields.

        This confirms that filtering logic is independent of sparse-field projection.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: high
            title: Test filter on one app with sparse fields on another
        """
        host1 = setup_host_with_app_data("advisor", {"recommendations": 10, "incidents": 5})
        add_app_data_to_host(
            host_inventory, host1, "vulnerability", {"total_cves": 20, "critical_cves": 3}
        )

        host2 = setup_host_with_app_data("advisor", {"recommendations": 2, "incidents": 1})
        add_app_data_to_host(
            host_inventory, host2, "vulnerability", {"total_cves": 5, "critical_cves": 1}
        )

        response = host_inventory.apis.host_views.get_host_views_response(
            filter=["[advisor][recommendations][gte]=5"],
            fields=["[vulnerability]=critical_cves"],
        )

        response_ids = {h.id for h in response.results}
        assert host1.id in response_ids
        assert host2.id not in response_ids

        for result in response.results:
            if result.id == host1.id:
                assert result.app_data.advisor is None
                assert result.app_data.vulnerability is not None

                vuln_data = result.app_data.vulnerability.to_dict()
                assert vuln_data.get("critical_cves") == 3
                assert vuln_data.get("total_cves") is None


class TestSparseFieldsAllApps:
    """Test sparse fields across all supported applications."""

    @pytest.mark.parametrize(
        "app_name,field,other_field",
        [
            pytest.param("advisor", "recommendations", "incidents", id="advisor-recommendations"),
            pytest.param(
                "vulnerability", "critical_cves", "total_cves", id="vulnerability-critical_cves"
            ),
            pytest.param(
                "patch",
                "advisories_rhsa_installable",
                "advisories_rhba_installable",
                id="patch-advisories_rhsa",
            ),
            pytest.param("malware", "last_matches", "total_matches", id="malware-last_matches"),
        ],
    )
    def test_sparse_fields_per_app(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        app_name: str,
        field: str,
        other_field: str,
    ):
        """Verify sparse fields work for each supported application.

        Also asserts that non-requested fields are omitted/null.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: high
            title: Test sparse fields for each app
        """
        host = setup_host_with_app_data(app_name, {field: 7, other_field: 99})

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=[f"[{app_name}]={field}"],
        )

        assert response.total == 1
        result = response.results[0]

        app_data_obj = getattr(result.app_data, app_name, None)
        assert app_data_obj is not None

        app_data_dict = app_data_obj.to_dict()
        assert app_data_dict.get(field) == 7
        assert app_data_dict.get(other_field) is None

    def test_sparse_fields_remediations(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """Verify sparse fields work for remediations (single-field app).

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: high
            title: Test sparse fields for remediations
        """
        host = setup_host_with_app_data("remediations", {"remediations_plans": 7})

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
            fields=["[remediations]=remediations_plans"],
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.remediations is not None
        assert result.app_data.remediations.remediations_plans == 7


class TestSparseFieldsDefaultBehavior:
    """Test default behavior when fields parameter is omitted."""

    def test_no_fields_returns_all_apps(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """When fields is not specified, all app data is returned.

        metadata:
            requirements: inv-host-views-sparse-fields
            assignee: adubey
            importance: high
            title: Test default behavior without fields parameter
        """
        host = setup_host_with_app_data("advisor", {"recommendations": 5, "incidents": 2})
        add_app_data_to_host(
            host_inventory, host, "vulnerability", {"total_cves": 10, "critical_cves": 2}
        )

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=host.insights_id,
        )

        assert response.total == 1
        result = response.results[0]

        assert result.app_data.advisor is not None
        assert result.app_data.vulnerability is not None

        assert result.app_data.advisor.recommendations == 5
        assert result.app_data.advisor.incidents == 2
        assert result.app_data.vulnerability.total_cves == 10
        assert result.app_data.vulnerability.critical_cves == 2
