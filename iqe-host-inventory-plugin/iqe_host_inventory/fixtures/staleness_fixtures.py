from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest

from iqe_host_inventory import ApplicationHostInventory


@contextmanager
def staleness_cleanup(hbi: ApplicationHostInventory) -> Generator[None]:
    with hbi.apis.account_staleness.cleanup_before_and_after():
        yield


@pytest.fixture(scope="session")
def hbi_staleness_defaults(host_inventory: ApplicationHostInventory) -> dict[str, int]:
    """
    Returns the default staleness settings
    """
    return host_inventory.apis.account_staleness.get_default_staleness()


@pytest.fixture()
def hbi_staleness_cleanup(host_inventory: ApplicationHostInventory) -> Generator[None]:
    with staleness_cleanup(host_inventory):
        yield


@pytest.fixture(scope="class")
def hbi_staleness_cleanup_class(host_inventory: ApplicationHostInventory) -> Generator[None]:
    with staleness_cleanup(host_inventory):
        yield


@pytest.fixture(scope="module")
def hbi_staleness_cleanup_module(host_inventory: ApplicationHostInventory) -> Generator[None]:
    with staleness_cleanup(host_inventory):
        yield


@pytest.fixture()
def hbi_staleness_secondary_cleanup(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[None]:
    with staleness_cleanup(host_inventory_secondary):
        yield
