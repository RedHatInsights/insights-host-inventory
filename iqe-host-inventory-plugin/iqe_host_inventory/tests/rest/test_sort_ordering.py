# mypy: disallow-untyped-defs

import logging
from collections.abc import Callable
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.test_pagination import in_order
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend, pytest.mark.ephemeral]


@pytest.fixture
def get_hosts_with_ordering(
    host_inventory: ApplicationHostInventory,
) -> Callable[..., list[HostOut]]:
    def _get_hosts(
        function_name: str,
        *func_args: Any,
        order_by: str,
        order_how: str | None = None,
        **func_kwargs: Any,
    ) -> list[HostOut]:
        order_params = {}
        if order_by == "operating_system":
            order_params["order_by"] = order_by
            if order_how is not None:
                order_params["order_how"] = order_how

            api_func = getattr(host_inventory.apis.hosts, function_name)
            response = api_func(
                *func_args, fields=["operating_system"], **order_params, **func_kwargs
            )
            return response.results

        api_func = getattr(host_inventory.apis.hosts, function_name)
        if order_how is None:
            response = api_func(*func_args, order_by=order_by, **func_kwargs)
        else:
            response = api_func(*func_args, order_by=order_by, order_how=order_how, **func_kwargs)
        return response.results

    return _get_hosts


class TestHostsSortOrdering:
    @pytest.mark.smoke
    @pytest.mark.usefixtures("hbi_kafka_setup_hosts_for_sort_ordering")
    @pytest.mark.parametrize(
        "order_by", ["updated", "display_name", "operating_system", "group_name", "last_check_in"]
    )
    @pytest.mark.parametrize("order_how", ["ASC", "DESC"])
    def test_sort_ordering_get_hosts_list(
        self,
        order_by: str,
        order_how: str,
        get_hosts_with_ordering: Callable[..., list[HostOut]],
    ) -> None:
        """
        Test Sort Ordering Parameters for GET /hosts.

        Confirm sort ordering parameters for GET of /hosts work as expected.

        metadata:
            requirements: inv-hosts-sorting, inv-hosts-get-list
            assignee: fstavela
            importance: critical
            title: Inventory: Confirm sort ordering for GET of /hosts works as expected
        """
        list_of_hosts = get_hosts_with_ordering(
            "get_hosts_response", order_by=order_by, order_how=order_how
        )
        assert in_order(None, list_of_hosts, ascending=(order_how == "ASC"), sort_field=order_by)

    @pytest.mark.parametrize(
        "order_by", ["updated", "display_name", "operating_system", "group_name", "last_check_in"]
    )
    @pytest.mark.parametrize("order_how", ["ASC", "DESC"])
    def test_sort_ordering_get_hosts_by_id(
        self,
        order_by: str,
        order_how: str,
        hbi_kafka_setup_hosts_for_sort_ordering: list[HostWrapper],
        get_hosts_with_ordering: Callable[..., list[HostOut]],
    ) -> None:
        """
        Test Sort Ordering Parameters for GET /hosts/{host_id_list}.

        Confirm sort ordering parameters for GET of /hosts/{host_id_list} work as expected.

        metadata:
            requirements: inv-hosts-sorting, inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            title: Inventory: Confirm sort ordering for GET of /hosts/{host_id_list}
                works as expected
        """
        hosts_ids = [host.id for host in hbi_kafka_setup_hosts_for_sort_ordering]
        list_of_hosts = get_hosts_with_ordering(
            "get_hosts_by_id_response", hosts_ids, order_by=order_by, order_how=order_how
        )
        assert len(list_of_hosts) == len(hosts_ids)
        assert in_order(None, list_of_hosts, ascending=(order_how == "ASC"), sort_field=order_by)

    @pytest.mark.parametrize(
        "order_by", ["updated", "display_name", "operating_system", "group_name", "last_check_in"]
    )
    @pytest.mark.parametrize("order_how", ["ASC", "DESC"])
    def test_sort_ordering_parameters_for_get_system_profile(
        self,
        order_by: str,
        order_how: str,
        host_inventory: ApplicationHostInventory,
        hbi_kafka_setup_hosts_for_sort_ordering: list[HostWrapper],
    ) -> None:
        """
        Test Sort Ordering Parameters for GET /hosts/{host_id_list}/system_profile.

        Confirm sort ordering parameters for GET of /hosts/{host_id_list}/system_profile work as
        expected.

        metadata:
            requirements: inv-hosts-sorting, inv-hosts-get-system_profile
            assignee: fstavela
            importance: high
            title: Inventory: Confirm sort ordering for GET of
                /hosts/{host_id_list}/system_profile works as expected
        """
        hosts_ids = [host.id for host in hbi_kafka_setup_hosts_for_sort_ordering]

        response = host_inventory.apis.hosts.get_hosts_system_profile_response(
            hosts_ids,
            order_how=order_how,
            order_by=order_by,
        )

        response2 = host_inventory.apis.hosts.get_hosts_by_id_response(
            hosts_ids,
            order_how=order_how,
            order_by=order_by,
        )

        properly_sorted_ids = [host.id for host in response2.results]
        system_profile_ids = [host.id for host in response.results]
        assert properly_sorted_ids == system_profile_ids

    @pytest.mark.parametrize(
        "order_by", ["updated", "display_name", "operating_system", "group_name", "last_check_in"]
    )
    def test_sort_omitted_ordering_parameters(
        self,
        order_by: str,
        hbi_kafka_setup_hosts_for_sort_ordering: list[HostWrapper],
        host_inventory: ApplicationHostInventory,
        get_hosts_with_ordering: Callable[..., list[HostOut]],
    ) -> None:
        """
        Test Omission of Sort order_how Parameter.

        When order_how is omitted, confirm that the default sort order is used.
        If order_by is "display_name" or "group_name", sort order defaults to ascending.
        If order_by is "updated", "last_check_in" or "operating_system", sort
        order defaults to descending.

        metadata:
            requirements: inv-hosts-sorting
            assignee: fstavela
            importance: high
            title: Inventory: Omission of Sort order_how Parameter
        """
        hosts_ids = [host.id for host in hbi_kafka_setup_hosts_for_sort_ordering]
        ascending_flag = order_by in ("display_name", "group_name")

        list_of_hosts = get_hosts_with_ordering("get_hosts_response", order_by=order_by)
        assert in_order(None, list_of_hosts, sort_field=order_by, ascending=ascending_flag)

        list_of_hosts2 = get_hosts_with_ordering(
            "get_hosts_by_id_response", hosts_ids, order_by=order_by
        )
        assert len(list_of_hosts2) == len(hosts_ids)
        assert in_order(None, list_of_hosts2, sort_field=order_by, ascending=ascending_flag)

        response3 = host_inventory.apis.hosts.get_hosts_system_profile_response(
            hosts_ids, order_by=order_by
        )
        list_of_hosts3 = response3.results
        properly_sorted_ids = [host.id for host in list_of_hosts2]
        system_profile_ids = [host.id for host in list_of_hosts3]
        assert properly_sorted_ids == system_profile_ids


class TestHostsSortOrderingInvalidParams:
    @pytest.mark.usefixtures("hbi_kafka_setup_hosts_for_sort_ordering")
    @pytest.mark.parametrize("order_how,order_by", [("DESC", None), ("ASC", None)])
    def test_sort_invalid_parameters_get_hosts_list(
        self,
        order_how: str,
        order_by: str | None,
        host_inventory: ApplicationHostInventory,
    ) -> None:
        """
        Test Invalid Sort Parameter Values for GET of /hosts.

        Confirm that invalid combinations of sort ordering parameters cause a 400 status.
        Omission of the order_by value triggers a 400 status code when order_how is specified.

        metadata:
            requirements:
                - inv-hosts-sorting
                - inv-hosts-get-list
                - inv-api-validation
            assignee: fstavela
            importance: low
            negative: true
            title: Inventory: Invalid Sort Parameter Values for GET of /hosts
        """
        with raises_apierror(400):
            host_inventory.apis.hosts.get_hosts(order_how=order_how, order_by=order_by)

    @pytest.mark.parametrize("order_how,order_by", [("DESC", None), ("ASC", None)])
    def test_sort_invalid_parameters_get_hosts_by_id(
        self,
        order_how: str,
        order_by: str | None,
        host_inventory: ApplicationHostInventory,
        hbi_kafka_setup_hosts_for_sort_ordering: list[HostWrapper],
    ) -> None:
        """
        Test Invalid Sort Parameter Values for GET of /hosts/{host_id_list}

        Confirm that invalid combinations of sort ordering parameters cause a 400 status.
        Omission of the order_by value triggers a 400 status code when order_how is specified.

        metadata:
            requirements:
                - inv-hosts-sorting
                - inv-hosts-get-by-id
                - inv-api-validation
            assignee: fstavela
            importance: low
            negative: true
            title: Inventory: Invalid Sort Parameter Values for GET of /hosts/{host_id_list}
        """
        hosts_ids = [host.id for host in hbi_kafka_setup_hosts_for_sort_ordering]
        with raises_apierror((400, 404)):
            # TODO: figure why the 404 comes in
            host_inventory.apis.hosts.get_hosts_by_id(
                hosts_ids,
                order_how=order_how,
                order_by=order_by,
            )

    @pytest.mark.parametrize("order_how,order_by", [("DESC", None), ("ASC", None)])
    def test_sort_invalid_parameters_get_system_profile(
        self,
        order_how: str,
        order_by: str | None,
        host_inventory: ApplicationHostInventory,
        hbi_kafka_setup_hosts_for_sort_ordering: list[HostWrapper],
    ) -> None:
        """
        Test Invalid Sort Parameter Values for GET of
        /hosts/{host_id}/system_profile.

        Confirm that invalid combinations of sort ordering parameters cause a 400 status.
        Omission of the order_by value triggers a 400 status code when order_how is specified.

        metadata:
            requirements:
                - inv-hosts-sorting
                - inv-hosts-get-system_profile
                - inv-api-validation
            assignee: fstavela
            importance: low
            negative: true
            title: Inventory: Invalid Sort Parameter Values for GET of
                /hosts/{host_id}/system_profile
        """
        hosts_ids = [host.id for host in hbi_kafka_setup_hosts_for_sort_ordering]
        with raises_apierror(400):
            host_inventory.apis.hosts.get_hosts_system_profile(
                hosts_ids, order_how=order_how, order_by=order_by
            )
