# mypy: disallow-untyped-defs

from __future__ import annotations

import warnings
from collections.abc import Generator
from typing import Self

import attrs
import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.deprecations import DEPRECATE_PRIMARY_GROUPS_CLEANUP_FUNCTION
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory_api import GroupOutWithHostCount


@attrs.define
class HBIGroupCleanupRegistry:
    _scope: str
    _applications: list[ApplicationHostInventory] = attrs.field(factory=list)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        for host_inventory_app in self._applications:
            host_inventory_app.cleanup.clean_groups(self._scope)

    def __call__(self, app_host_inventory: ApplicationHostInventory) -> None:
        """register an application for group cleanup in the given scope"""
        if app_host_inventory not in self._applications:
            self._applications.append(app_host_inventory)


@pytest.fixture(scope="function")
def hbi_groups_cleanup_function() -> Generator[HBIGroupCleanupRegistry, None, None]:
    warnings.warn(DEPRECATE_PRIMARY_GROUPS_CLEANUP_FUNCTION, stacklevel=2)
    with HBIGroupCleanupRegistry("function") as cleanup:
        yield cleanup


@pytest.fixture(scope="function")
def hbi_primary_groups_cleanup_function(
    host_inventory: ApplicationHostInventory, hbi_groups_cleanup_function: HBIGroupCleanupRegistry
) -> None:
    """
    Deletes all groups from primary account registered for cleanup
    at the end of the test function
    """
    warnings.warn(DEPRECATE_PRIMARY_GROUPS_CLEANUP_FUNCTION, stacklevel=2)
    hbi_groups_cleanup_function(host_inventory)


@pytest.fixture(scope="class")
def setup_empty_groups_primary(
    host_inventory: ApplicationHostInventory,
) -> list[GroupOutWithHostCount]:
    return host_inventory.apis.groups.create_n_empty_groups(110, cleanup_scope="class")


@pytest.fixture
def setup_groups_for_ordering(
    host_inventory: ApplicationHostInventory,
) -> list[GroupOutWithHostCount]:
    hosts = host_inventory.kafka.create_random_hosts(20)

    # Create 10 groups, 2 with 0 hosts, 2 with 1 host, ..., 2 with 4 hosts.
    # 20 hosts required in total
    groups_data = []
    for i in range(5):
        for _ in range(2):
            group_hosts = [hosts.pop() for _ in range(i)]
            groups_data.append(
                GroupData(name=generate_display_name("hbi-ordering-test"), hosts=group_hosts)
            )

    return host_inventory.apis.groups.create_groups(groups_data)
