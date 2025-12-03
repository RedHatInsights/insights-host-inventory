from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from time import sleep

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


@pytest.fixture()
def hbi_staleness_cleanup_culled(host_inventory: ApplicationHostInventory) -> Generator[None]:
    """
    Staleness cleanup fixture with delay for tests that create culled hosts.

    This fixture MUST be used instead of hbi_staleness_cleanup for any test that:
    - Creates hosts in "culling" state using create_hosts_in_state(..., host_state="culling")
    - Tests operations on culled hosts (DELETE, PATCH, PUT on culled hosts)
    - Changes staleness settings that would make hosts become culled

    Why the delay is necessary:
    When staleness settings are deleted, an async job updates all host timestamps.
    Without this delay, the cleanup tries to delete hosts while they're still marked
    as "culled" (404), but by the time verification runs, they've become fresh again,
    causing cleanup failures.

    The 5-second delay after staleness cleanup ensures the async job completes before
    standard host cleanup attempts to delete the hosts.
    """
    with staleness_cleanup(host_inventory):
        yield

    sleep(5)
