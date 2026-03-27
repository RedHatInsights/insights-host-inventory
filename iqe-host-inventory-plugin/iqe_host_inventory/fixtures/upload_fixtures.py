from __future__ import annotations

import logging
from collections.abc import Generator

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory_api.models.host_out import HostOut

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def hbi_setup_hosts_for_pagination(
    host_inventory: ApplicationHostInventory,
) -> Generator[list[HostOut]]:
    hosts_data = [HostData(display_name_prefix="pagination") for _ in range(20)]
    hosts = host_inventory.upload.create_hosts(hosts_data=hosts_data, register_for_cleanup=False)
    yield hosts

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(hosts)


@pytest.fixture
def hbi_upload_prepare_host(host_inventory: ApplicationHostInventory) -> Generator[HostOut]:
    host = host_inventory.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="class")
def hbi_upload_prepare_host_class(host_inventory: ApplicationHostInventory) -> Generator[HostOut]:
    host = host_inventory.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="module")
def hbi_upload_prepare_host_module(host_inventory: ApplicationHostInventory) -> Generator[HostOut]:
    host = host_inventory.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture
def hbi_secondary_upload_prepare_host(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_secondary.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="class")
def hbi_secondary_upload_prepare_host_class(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_secondary.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="module")
def hbi_secondary_upload_prepare_host_module(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_secondary.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)


@pytest.fixture()
def hbi_cert_auth_upload_prepare_host(
    host_inventory_cert_auth: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_cert_auth.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_cert_auth.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="class")
def hbi_cert_auth_upload_prepare_host_class(
    host_inventory_cert_auth: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_cert_auth.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_cert_auth.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="module")
def hbi_cert_auth_upload_prepare_host_module(
    host_inventory_cert_auth: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_cert_auth.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_cert_auth.apis.hosts.delete_by_id(host)
