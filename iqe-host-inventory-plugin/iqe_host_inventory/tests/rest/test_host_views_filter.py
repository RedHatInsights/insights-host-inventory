"""Integration tests for app data filtering on the /beta/hosts-view endpoint.

These tests verify the deep-object ``filter`` query parameter, which allows
consumers to filter hosts by application data fields using comparison operators
(eq, ne, gt, lt, gte, lte) and nullability checks (nil, not_nil).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from iqe_host_inventory.fixtures.host_views_fixtures import add_app_data_to_host
from iqe_host_inventory.utils.datagen_utils import generate_host_app_data
from iqe_host_inventory_api import ApiException

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend, pytest.mark.ephemeral]


# ---------------------------------------------------------------------------
# Parametrize helpers
# ---------------------------------------------------------------------------

_INT_OPERATORS: dict[str, tuple[int, int, str]] = {
    "eq": (5, 10, "5"),
    "ne": (10, 5, "5"),
    "gt": (10, 2, "5"),
    "lt": (2, 10, "5"),
    "gte": (10, 2, "5"),
    "lte": (2, 10, "5"),
}


def _int_filter_params(fields: list[str]) -> list:
    """Generate pytest.param entries for every field x integer-operator combination."""
    return [
        pytest.param(field, match, no_match, filt, op, id=f"{field}-{op}")
        for field in fields
        for op, (match, no_match, filt) in _INT_OPERATORS.items()
    ]


_STR_OPERATORS: dict[str, tuple[str, str, str]] = {
    "eq": ("alpha", "bravo", "alpha"),
    "ne": ("bravo", "alpha", "alpha"),
}


def _str_filter_params(fields: list[str]) -> list:
    """Generate pytest.param entries for every field x string-operator combination."""
    return [
        pytest.param(field, match, no_match, filt, op, id=f"{field}-{op}")
        for field in fields
        for op, (match, no_match, filt) in _STR_OPERATORS.items()
    ]


def _nil_filter_params(fields_with_seed: list[tuple[str, int | str]]) -> list:
    """Generate pytest.param entries for nil/not_nil tests on each field."""
    return [pytest.param(field, seed, id=field) for field, seed in fields_with_seed]


# ---------------------------------------------------------------------------
# Per-App Test Classes
# ---------------------------------------------------------------------------


class TestAdvisor:
    APP_NAME = "advisor"

    @pytest.mark.parametrize(
        "field,match_val,no_match_val,filter_val,operator",
        _int_filter_params([
            "recommendations",
            "incidents",
            "critical",
            "important",
            "moderate",
            "low",
        ]),
    )
    def test_filter_integer_operators(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        match_val: int,
        no_match_val: int,
        filter_val: str,
        operator: str,
    ):
        """Verify integer comparison operators filter hosts correctly.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test integer comparison operators on advisor host-view filter
        """
        host_match = setup_host_with_app_data(self.APP_NAME, {field: match_val})
        host_no_match = setup_host_with_app_data(self.APP_NAME, {field: no_match_val})

        filter_param = [f"[{self.APP_NAME}][{field}][{operator}]={filter_val}"]
        logger.info("Filtering with: %s", filter_param)

        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_param)
        response_ids = {h.id for h in response.results}

        assert host_match.id in response_ids, (
            f"Expected host {host_match.id} ({field}={match_val}) in results"
        )
        assert host_no_match.id not in response_ids, (
            f"Expected host {host_no_match.id} ({field}={no_match_val}) NOT in results"
        )

    @pytest.mark.parametrize(
        "field,seed_val",
        _nil_filter_params([
            ("recommendations", 1),
            ("incidents", 1),
            ("critical", 1),
            ("important", 1),
            ("moderate", 1),
            ("low", 1),
        ]),
    )
    def test_filter_nil_and_not_nil(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        seed_val: int | str,
    ):
        """Verify nil and not_nil operators for advisor data presence/absence.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test nil and not_nil operators on advisor host-view filter
        """
        host_with_data = setup_host_with_app_data(self.APP_NAME, {field: seed_val})
        host_without_data = host_inventory.kafka.create_host()
        logger.info(
            "Host with data: %s, host without: %s", host_with_data.id, host_without_data.id
        )

        # not_nil: only the host with data
        filter_not_nil = [f"[{self.APP_NAME}][{field}][not_nil]=true"]
        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_not_nil)
        response_ids = {h.id for h in response.results}
        assert host_with_data.id in response_ids
        assert host_without_data.id not in response_ids

        # nil: only the host without data
        filter_nil = [f"[{self.APP_NAME}][{field}][nil]=true"]
        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_nil)
        response_ids = {h.id for h in response.results}
        assert host_without_data.id in response_ids
        assert host_with_data.id not in response_ids

    def test_filter_multiple_fields(
        self, host_inventory: ApplicationHostInventory, setup_host_with_app_data
    ):
        """Verify that multiple filters on advisor use AND logic.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test multiple field filters on advisor (AND logic)
        """
        filters = [
            f"[{self.APP_NAME}][recommendations][gte]=5",
            f"[{self.APP_NAME}][incidents][gte]=3",
        ]
        host_match = setup_host_with_app_data(
            self.APP_NAME, {"recommendations": 10, "incidents": 5}
        )
        host_no_match = setup_host_with_app_data(
            self.APP_NAME, {"recommendations": 10, "incidents": 1}
        )

        logger.info("Filtering with: %s", filters)
        response = host_inventory.apis.host_views.get_host_views_response(filter=filters)
        response_ids = {h.id for h in response.results}

        assert host_match.id in response_ids, f"Expected host {host_match.id} in results"
        assert host_no_match.id not in response_ids, (
            f"Expected host {host_no_match.id} NOT in results"
        )


class TestVulnerability:
    APP_NAME = "vulnerability"

    @pytest.mark.parametrize(
        "field,match_val,no_match_val,filter_val,operator",
        _int_filter_params([
            "total_cves",
            "critical_cves",
            "important_cves",
            "cves_with_security_rules",
            "cves_with_known_exploits",
        ]),
    )
    def test_filter_integer_operators(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        match_val: int,
        no_match_val: int,
        filter_val: str,
        operator: str,
    ):
        """Verify integer comparison operators filter hosts correctly.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test integer comparison operators on vulnerability host-view filter
        """
        host_match = setup_host_with_app_data(self.APP_NAME, {field: match_val})
        host_no_match = setup_host_with_app_data(self.APP_NAME, {field: no_match_val})

        filter_param = [f"[{self.APP_NAME}][{field}][{operator}]={filter_val}"]
        logger.info("Filtering with: %s", filter_param)

        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_param)
        response_ids = {h.id for h in response.results}

        assert host_match.id in response_ids, (
            f"Expected host {host_match.id} ({field}={match_val}) in results"
        )
        assert host_no_match.id not in response_ids, (
            f"Expected host {host_no_match.id} ({field}={no_match_val}) NOT in results"
        )

    @pytest.mark.parametrize(
        "field,seed_val",
        _nil_filter_params([
            ("total_cves", 1),
            ("critical_cves", 1),
            ("important_cves", 1),
            ("cves_with_security_rules", 1),
            ("cves_with_known_exploits", 1),
        ]),
    )
    def test_filter_nil_and_not_nil(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        seed_val: int | str,
    ):
        """Verify nil and not_nil operators for vulnerability data presence/absence.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test nil and not_nil operators on vulnerability host-view filter
        """
        host_with_data = setup_host_with_app_data(self.APP_NAME, {field: seed_val})
        host_without_data = host_inventory.kafka.create_host()
        logger.info(
            "Host with data: %s, host without: %s", host_with_data.id, host_without_data.id
        )

        filter_not_nil = [f"[{self.APP_NAME}][{field}][not_nil]=true"]
        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_not_nil)
        response_ids = {h.id for h in response.results}
        assert host_with_data.id in response_ids
        assert host_without_data.id not in response_ids

        filter_nil = [f"[{self.APP_NAME}][{field}][nil]=true"]
        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_nil)
        response_ids = {h.id for h in response.results}
        assert host_without_data.id in response_ids
        assert host_with_data.id not in response_ids

    def test_filter_multiple_fields(
        self, host_inventory: ApplicationHostInventory, setup_host_with_app_data
    ):
        """Verify that multiple filters on vulnerability use AND logic.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test multiple field filters on vulnerability (AND logic)
        """
        filters = [
            f"[{self.APP_NAME}][critical_cves][gte]=3",
            f"[{self.APP_NAME}][total_cves][lte]=100",
        ]
        host_match = setup_host_with_app_data(
            self.APP_NAME, {"critical_cves": 5, "total_cves": 50}
        )
        host_no_match = setup_host_with_app_data(
            self.APP_NAME, {"critical_cves": 5, "total_cves": 200}
        )

        logger.info("Filtering with: %s", filters)
        response = host_inventory.apis.host_views.get_host_views_response(filter=filters)
        response_ids = {h.id for h in response.results}

        assert host_match.id in response_ids, f"Expected host {host_match.id} in results"
        assert host_no_match.id not in response_ids, (
            f"Expected host {host_no_match.id} NOT in results"
        )


class TestPatch:
    APP_NAME = "patch"

    @pytest.mark.parametrize(
        "field,match_val,no_match_val,filter_val,operator",
        _int_filter_params([
            "advisories_rhsa_installable",
            "advisories_rhba_installable",
            "advisories_rhea_installable",
            "advisories_other_installable",
            "advisories_rhsa_applicable",
            "advisories_rhba_applicable",
            "advisories_rhea_applicable",
            "advisories_other_applicable",
            "packages_installable",
            "packages_applicable",
            "packages_installed",
        ]),
    )
    def test_filter_integer_operators(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        match_val: int,
        no_match_val: int,
        filter_val: str,
        operator: str,
    ):
        """Verify integer comparison operators filter hosts correctly.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test integer comparison operators on patch host-view filter
        """
        host_match = setup_host_with_app_data(self.APP_NAME, {field: match_val})
        host_no_match = setup_host_with_app_data(self.APP_NAME, {field: no_match_val})

        filter_param = [f"[{self.APP_NAME}][{field}][{operator}]={filter_val}"]
        logger.info("Filtering with: %s", filter_param)

        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_param)
        response_ids = {h.id for h in response.results}

        assert host_match.id in response_ids, (
            f"Expected host {host_match.id} ({field}={match_val}) in results"
        )
        assert host_no_match.id not in response_ids, (
            f"Expected host {host_no_match.id} ({field}={no_match_val}) NOT in results"
        )

    @pytest.mark.parametrize(
        "field,seed_val",
        _nil_filter_params([
            ("advisories_rhsa_installable", 1),
            ("advisories_rhba_installable", 1),
            ("advisories_rhea_installable", 1),
            ("advisories_other_installable", 1),
            ("advisories_rhsa_applicable", 1),
            ("advisories_rhba_applicable", 1),
            ("advisories_rhea_applicable", 1),
            ("advisories_other_applicable", 1),
            ("packages_installable", 1),
            ("packages_applicable", 1),
            ("packages_installed", 1),
            ("template_name", "test"),
        ]),
    )
    def test_filter_nil_and_not_nil(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        seed_val: int | str,
    ):
        """Verify nil and not_nil operators for patch data presence/absence.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test nil and not_nil operators on patch host-view filter
        """
        host_with_data = setup_host_with_app_data(self.APP_NAME, {field: seed_val})
        host_without_data = host_inventory.kafka.create_host()
        logger.info(
            "Host with data: %s, host without: %s", host_with_data.id, host_without_data.id
        )

        filter_not_nil = [f"[{self.APP_NAME}][{field}][not_nil]=true"]
        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_not_nil)
        response_ids = {h.id for h in response.results}
        assert host_with_data.id in response_ids
        assert host_without_data.id not in response_ids

        filter_nil = [f"[{self.APP_NAME}][{field}][nil]=true"]
        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_nil)
        response_ids = {h.id for h in response.results}
        assert host_without_data.id in response_ids
        assert host_with_data.id not in response_ids

    @pytest.mark.parametrize(
        "field,match_val,no_match_val,filter_val,operator",
        _str_filter_params(["template_name"]),
    )
    def test_filter_string_operators(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        match_val: str,
        no_match_val: str,
        filter_val: str,
        operator: str,
    ):
        """Verify string comparison operators filter hosts correctly.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: medium
            title: Test string comparison operators on patch host-view filter
        """
        host_match = setup_host_with_app_data(self.APP_NAME, {field: match_val})
        host_no_match = setup_host_with_app_data(self.APP_NAME, {field: no_match_val})

        filter_param = [f"[{self.APP_NAME}][{field}][{operator}]={filter_val}"]
        logger.info("String filter: %s", filter_param)

        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_param)
        response_ids = {h.id for h in response.results}

        assert host_match.id in response_ids, (
            f"Expected host {host_match.id} ({field}={match_val!r}) in results"
        )
        assert host_no_match.id not in response_ids, (
            f"Expected host {host_no_match.id} ({field}={no_match_val!r}) NOT in results"
        )


class TestRemediations:
    APP_NAME = "remediations"

    @pytest.mark.parametrize(
        "field,match_val,no_match_val,filter_val,operator",
        _int_filter_params(["remediations_plans"]),
    )
    def test_filter_integer_operators(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        match_val: int,
        no_match_val: int,
        filter_val: str,
        operator: str,
    ):
        """Verify integer comparison operators filter hosts correctly.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test integer comparison operators on remediations host-view filter
        """
        host_match = setup_host_with_app_data(self.APP_NAME, {field: match_val})
        host_no_match = setup_host_with_app_data(self.APP_NAME, {field: no_match_val})

        filter_param = [f"[{self.APP_NAME}][{field}][{operator}]={filter_val}"]
        logger.info("Filtering with: %s", filter_param)

        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_param)
        response_ids = {h.id for h in response.results}

        assert host_match.id in response_ids, (
            f"Expected host {host_match.id} ({field}={match_val}) in results"
        )
        assert host_no_match.id not in response_ids, (
            f"Expected host {host_no_match.id} ({field}={no_match_val}) NOT in results"
        )

    @pytest.mark.parametrize(
        "field,seed_val",
        _nil_filter_params([("remediations_plans", 1)]),
    )
    def test_filter_nil_and_not_nil(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        seed_val: int | str,
    ):
        """Verify nil and not_nil operators for remediations data presence/absence.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test nil and not_nil operators on remediations host-view filter
        """
        host_with_data = setup_host_with_app_data(self.APP_NAME, {field: seed_val})
        host_without_data = host_inventory.kafka.create_host()
        logger.info(
            "Host with data: %s, host without: %s", host_with_data.id, host_without_data.id
        )

        filter_not_nil = [f"[{self.APP_NAME}][{field}][not_nil]=true"]
        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_not_nil)
        response_ids = {h.id for h in response.results}
        assert host_with_data.id in response_ids
        assert host_without_data.id not in response_ids

        filter_nil = [f"[{self.APP_NAME}][{field}][nil]=true"]
        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_nil)
        response_ids = {h.id for h in response.results}
        assert host_without_data.id in response_ids
        assert host_with_data.id not in response_ids


class TestMalware:
    APP_NAME = "malware"

    @pytest.mark.parametrize(
        "field,match_val,no_match_val,filter_val,operator",
        _int_filter_params(["last_matches", "total_matches"]),
    )
    def test_filter_integer_operators(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        match_val: int,
        no_match_val: int,
        filter_val: str,
        operator: str,
    ):
        """Verify integer comparison operators filter hosts correctly.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test integer comparison operators on malware host-view filter
        """
        host_match = setup_host_with_app_data(self.APP_NAME, {field: match_val})
        host_no_match = setup_host_with_app_data(self.APP_NAME, {field: no_match_val})

        filter_param = [f"[{self.APP_NAME}][{field}][{operator}]={filter_val}"]
        logger.info("Filtering with: %s", filter_param)

        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_param)
        response_ids = {h.id for h in response.results}

        assert host_match.id in response_ids, (
            f"Expected host {host_match.id} ({field}={match_val}) in results"
        )
        assert host_no_match.id not in response_ids, (
            f"Expected host {host_no_match.id} ({field}={no_match_val}) NOT in results"
        )

    @pytest.mark.parametrize(
        "field,seed_val",
        _nil_filter_params([
            ("last_matches", 1),
            ("total_matches", 1),
            ("last_status", "test"),
        ]),
    )
    def test_filter_nil_and_not_nil(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        seed_val: int | str,
    ):
        """Verify nil and not_nil operators for malware data presence/absence.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: high
            title: Test nil and not_nil operators on malware host-view filter
        """
        host_with_data = setup_host_with_app_data(self.APP_NAME, {field: seed_val})
        host_without_data = host_inventory.kafka.create_host()
        logger.info(
            "Host with data: %s, host without: %s", host_with_data.id, host_without_data.id
        )

        filter_not_nil = [f"[{self.APP_NAME}][{field}][not_nil]=true"]
        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_not_nil)
        response_ids = {h.id for h in response.results}
        assert host_with_data.id in response_ids
        assert host_without_data.id not in response_ids

        filter_nil = [f"[{self.APP_NAME}][{field}][nil]=true"]
        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_nil)
        response_ids = {h.id for h in response.results}
        assert host_without_data.id in response_ids
        assert host_with_data.id not in response_ids

    @pytest.mark.parametrize(
        "field,match_val,no_match_val,filter_val,operator",
        _str_filter_params(["last_status"]),
    )
    def test_filter_string_operators(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
        field: str,
        match_val: str,
        no_match_val: str,
        filter_val: str,
        operator: str,
    ):
        """Verify string comparison operators filter hosts correctly.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: medium
            title: Test string comparison operators on malware host-view filter
        """
        host_match = setup_host_with_app_data(self.APP_NAME, {field: match_val})
        host_no_match = setup_host_with_app_data(self.APP_NAME, {field: no_match_val})

        filter_param = [f"[{self.APP_NAME}][{field}][{operator}]={filter_val}"]
        logger.info("String filter: %s", filter_param)

        response = host_inventory.apis.host_views.get_host_views_response(filter=filter_param)
        response_ids = {h.id for h in response.results}

        assert host_match.id in response_ids, (
            f"Expected host {host_match.id} ({field}={match_val!r}) in results"
        )
        assert host_no_match.id not in response_ids, (
            f"Expected host {host_no_match.id} ({field}={no_match_val!r}) NOT in results"
        )


# ---------------------------------------------------------------------------
# Combined / Cross-App Tests
# ---------------------------------------------------------------------------


class TestCombinedApps:
    def test_filter_across_multiple_apps(
        self, host_inventory: ApplicationHostInventory, setup_host_with_app_data
    ):
        """Verify filtering across multiple apps uses AND logic.

        Creates three hosts with different combinations of advisor and vulnerability
        data.  Only the host matching both cross-app filters should be returned.

        - Host A: advisor recommendations=10, vulnerability critical_cves=5  -> matches
        - Host B: advisor recommendations=10, vulnerability critical_cves=0  -> fails vuln
        - Host C: advisor recommendations=1,  vulnerability critical_cves=5  -> fails advisor

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: critical
            title: Test cross-app combined filtering
        """
        # Host A: matches both filters
        host_a = setup_host_with_app_data("advisor", {"recommendations": 10})
        host_inventory.kafka.produce_host_app_message(
            application="vulnerability",
            org_id=host_a.org_id,
            hosts_app_data=[
                {
                    "id": host_a.id,
                    "data": generate_host_app_data("vulnerability") | {"critical_cves": 5},
                }
            ],
        )
        host_inventory.apis.host_views.wait_for_host_view_app_data(
            insights_id=host_a.insights_id, app_name="vulnerability"
        )

        # Host B: matches advisor, fails vulnerability
        host_b = setup_host_with_app_data("advisor", {"recommendations": 10})
        host_inventory.kafka.produce_host_app_message(
            application="vulnerability",
            org_id=host_b.org_id,
            hosts_app_data=[
                {
                    "id": host_b.id,
                    "data": generate_host_app_data("vulnerability") | {"critical_cves": 0},
                }
            ],
        )
        host_inventory.apis.host_views.wait_for_host_view_app_data(
            insights_id=host_b.insights_id, app_name="vulnerability"
        )

        # Host C: fails advisor, matches vulnerability
        host_c = setup_host_with_app_data("advisor", {"recommendations": 1})
        host_inventory.kafka.produce_host_app_message(
            application="vulnerability",
            org_id=host_c.org_id,
            hosts_app_data=[
                {
                    "id": host_c.id,
                    "data": generate_host_app_data("vulnerability") | {"critical_cves": 5},
                }
            ],
        )
        host_inventory.apis.host_views.wait_for_host_view_app_data(
            insights_id=host_c.insights_id, app_name="vulnerability"
        )

        filters = [
            "[advisor][recommendations][gte]=5",
            "[vulnerability][critical_cves][gte]=3",
        ]
        logger.info("Cross-app filter: %s", filters)

        response = host_inventory.apis.host_views.get_host_views_response(filter=filters)
        response_ids = {h.id for h in response.results}

        assert host_a.id in response_ids, "Host A should match both filters"
        assert host_b.id not in response_ids, "Host B should fail vulnerability filter"
        assert host_c.id not in response_ids, "Host C should fail advisor filter"

    def test_filter_combined_with_display_name(
        self, host_inventory: ApplicationHostInventory, setup_host_with_app_data
    ):
        """Verify that app data filters work together with display_name filtering.

        Creates two hosts with matching advisor data but different display_names.
        Filtering by display_name + app data filter should return only the one host
        that matches both criteria.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: medium
            title: Test filter combined with display_name
        """
        host_a = setup_host_with_app_data("advisor", {"recommendations": 10})
        host_b = setup_host_with_app_data("advisor", {"recommendations": 10})

        filter_param = ["[advisor][recommendations][gte]=5"]
        logger.info("Combining display_name=%s with filter=%s", host_a.display_name, filter_param)

        response = host_inventory.apis.host_views.get_host_views_response(
            display_name=host_a.display_name,
            filter=filter_param,
        )
        response_ids = {h.id for h in response.results}

        assert host_a.id in response_ids, "Host A should match both display_name and filter"
        assert host_b.id not in response_ids, "Host B should be excluded by display_name filter"

    @pytest.mark.parametrize(
        "filter_str,expected_status,expected_msg",
        [
            pytest.param(
                "[fake_app][field][eq]=5", 400, "filter key is invalid", id="invalid-app"
            ),
            pytest.param(
                "[advisor][nonexistent_field][eq]=5",
                400,
                "Invalid filter field",
                id="invalid-field",
            ),
        ],
    )
    def test_filter_validation_errors(
        self,
        host_inventory: ApplicationHostInventory,
        filter_str: str,
        expected_status: int,
        expected_msg: str,
    ):
        """Verify that invalid filter parameters return proper error responses.

        metadata:
            requirements: inv-host-views-filter, inv-api-validation
            assignee: jramos
            importance: medium
            negative: true
            title: Test filter validation error responses
        """
        with pytest.raises(ApiException) as excinfo:
            host_inventory.apis.host_views.get_host_views_response(filter=[filter_str])

        assert excinfo.value.status == expected_status, (
            f"Expected status {expected_status}, got {excinfo.value.status}"
        )
        assert expected_msg in excinfo.value.body, (
            f"Expected '{expected_msg}' in body: {excinfo.value.body}"
        )

    def test_filter_bad_operator(self, host_inventory: ApplicationHostInventory):
        """Verify that an invalid operator returns a 400 error.

        metadata:
            requirements: inv-host-views-filter
            assignee: jramos
            importance: medium
            negative: true
            title: Test filter bad operator
        """
        with pytest.raises(ApiException) as excinfo:
            host_inventory.apis.host_views.get_host_views_response(
                filter=["[advisor][recommendations][bad_op]=5"]
            )
            assert excinfo.value.status == 400
            assert "Invalid operator" in excinfo.value.body


# ---------------------------------------------------------------------------
# System Profile Filter Tests
# ---------------------------------------------------------------------------


class TestSystemProfileFilter:
    """Test filter[system_profile][...] on the hosts-view endpoint."""

    def test_filter_by_host_type(
        self,
        host_inventory: ApplicationHostInventory,
    ):
        """filter[system_profile][host_type][eq]=edge returns only edge hosts.

        metadata:
            requirements: inv-host-views-sp-filter
            assignee: rantunes
            importance: high
            title: Test SP filter by host_type on hosts-view
        """
        host_data = host_inventory.datagen.create_host_data()
        host_data["system_profile"]["host_type"] = "edge"
        edge_host = host_inventory.kafka.create_host(host_data=host_data)

        host_data2 = host_inventory.datagen.create_host_data()
        host_data2["system_profile"].pop("host_type", None)
        non_edge_host = host_inventory.kafka.create_host(host_data=host_data2)

        response = host_inventory.apis.host_views.get_host_views_response(
            filter=["[system_profile][host_type][eq]=edge"],
        )
        response_ids = {h.id for h in response.results}

        assert edge_host.id in response_ids
        assert non_edge_host.id not in response_ids

    def test_sp_filter_combined_with_app_filter(
        self,
        host_inventory: ApplicationHostInventory,
        setup_host_with_app_data,
    ):
        """SP filter + app data filter use AND logic.

        metadata:
            requirements: inv-host-views-sp-filter
            assignee: rantunes
            importance: high
            title: Test SP filter combined with app data filter
        """
        host_data = host_inventory.datagen.create_host_data()
        host_data["system_profile"]["host_type"] = "edge"
        edge_host = host_inventory.kafka.create_host(host_data=host_data)
        add_app_data_to_host(host_inventory, edge_host, "vulnerability", {"critical_cves": 5})

        host_data2 = host_inventory.datagen.create_host_data()
        host_data2["system_profile"].pop("host_type", None)
        non_edge_host = host_inventory.kafka.create_host(host_data=host_data2)
        add_app_data_to_host(host_inventory, non_edge_host, "vulnerability", {"critical_cves": 10})

        response = host_inventory.apis.host_views.get_host_views_response(
            filter=[
                "[system_profile][host_type][eq]=edge",
                "[vulnerability][critical_cves][gte]=1",
            ],
        )
        response_ids = {h.id for h in response.results}

        assert edge_host.id in response_ids
        assert non_edge_host.id not in response_ids

    def test_sp_filter_with_sp_fields(
        self,
        host_inventory: ApplicationHostInventory,
    ):
        """SP filter and SP sparse fields work together.

        metadata:
            requirements: inv-host-views-sp-filter, inv-host-views-sp-fields
            assignee: rantunes
            importance: high
            title: Test SP filter combined with SP sparse fields
        """
        host_data = host_inventory.datagen.create_host_data()
        host_data["system_profile"]["host_type"] = "edge"
        host_data["system_profile"]["arch"] = "x86_64"
        edge_host = host_inventory.kafka.create_host(host_data=host_data)

        response = host_inventory.apis.host_views.get_host_views_response(
            insights_id=edge_host.insights_id,
            filter=["[system_profile][host_type][eq]=edge"],
            fields=["[system_profile]=arch"],
        )

        assert response.total == 1
        result = response.results[0]

        sp = result.to_dict().get("system_profile", {})
        sp_fields = {k for k, v in sp.items() if v is not None}
        assert "arch" in sp_fields
        assert "host_type" not in sp_fields
