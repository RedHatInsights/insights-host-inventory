# mypy: disallow-untyped-defs

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import attrs
import pytest

from iqe_host_inventory import ApplicationHostInventory


@attrs.define
class HBICleanupRegistry:
    _scope: str
    _applications: list[ApplicationHostInventory] = attrs.field(factory=list)

    def __enter__(self) -> HBICleanupRegistry:
        return self

    def __exit__(self, *_: Any) -> None:
        for host_inventory_app in self._applications:
            host_inventory_app.cleanup.clean_all(self._scope)

    def __call__(self, app_host_inventory: ApplicationHostInventory) -> None:
        """register an application for cleanup in the given scope"""
        if app_host_inventory not in self._applications:
            self._applications.append(app_host_inventory)


@pytest.fixture(scope="session")
def hbi_cleanup_session() -> Generator[HBICleanupRegistry, None, None]:
    with HBICleanupRegistry("session") as cleanup:
        yield cleanup


@pytest.fixture(scope="package")
def hbi_cleanup_package() -> Generator[HBICleanupRegistry, None, None]:
    with HBICleanupRegistry("package") as cleanup:
        yield cleanup


@pytest.fixture(scope="module")
def hbi_cleanup_module() -> Generator[HBICleanupRegistry, None, None]:
    with HBICleanupRegistry("module") as cleanup:
        yield cleanup


@pytest.fixture(scope="class")
def hbi_cleanup_class() -> Generator[HBICleanupRegistry, None, None]:
    with HBICleanupRegistry("class") as cleanup:
        yield cleanup


@pytest.fixture(scope="function")
def hbi_cleanup_function() -> Generator[HBICleanupRegistry, None, None]:
    with HBICleanupRegistry("function") as cleanup:
        yield cleanup
