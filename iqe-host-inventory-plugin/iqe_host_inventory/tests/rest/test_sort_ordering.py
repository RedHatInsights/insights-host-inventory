# mypy: disallow-untyped-defs

import logging
from collections.abc import Callable
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.test_pagination import in_order
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
