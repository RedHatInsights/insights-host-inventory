# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from collections.abc import Generator
from random import choice
from random import randint

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.datagen_utils import generate_display_name

logger = logging.getLogger(__name__)


@pytest.fixture
def hbi_kafka_setup_hosts_for_sap_sids_endpoint(
    host_inventory: ApplicationHostInventory,
) -> list[HostWrapper]:
    hosts_data = [host_inventory.datagen.create_host_data_for_sap_filtering() for _ in range(2)]

    hosts_data[0]["system_profile"]["sap_sids"] = ["ABC"]
    hosts_data[0]["system_profile"]["sap_system"] = True
    hosts_data[0]["system_profile"]["sap_instance_number"] = "03"
    hosts_data[0]["system_profile"]["sap_version"] = "1.00.122.04.1478575636"

    hosts_data[0]["system_profile"]["workloads"] = {
        "sap": {
            "sids": ["ABC"],
            "sap_system": True,
            "instance_number": "03",
            "version": "1.00.122.04.1478575636",
        }
    }

    hosts_data[1]["system_profile"]["sap_sids"] = ["ABC", "C1E"]
    hosts_data[1]["system_profile"]["sap_system"] = True
    hosts_data[1]["system_profile"]["sap_instance_number"] = "02"
    hosts_data[1]["system_profile"]["sap_version"] = "2.00.122.03.1478575636"

    hosts_data[1]["system_profile"]["workloads"] = {
        "sap": {
            "sids": ["ABC", "C1E"],
            "sap_system": True,
            "instance_number": "02",
            "version": "2.00.122.03.1478575636",
        }
    }

    return host_inventory.kafka.create_hosts(hosts_data=hosts_data)


@pytest.fixture(scope="module")
def hbi_kafka_setup_hosts_for_sort_ordering(
    host_inventory: ApplicationHostInventory,
) -> list[HostWrapper]:
    hosts_data = host_inventory.datagen.create_n_hosts_data(10)
    for data in hosts_data:
        data["display_name"] = generate_display_name()
        os_field = {
            "name": choice(["RHEL", "CentOS", "CentOS Linux"]),
            "major": randint(0, 99),
            "minor": randint(0, 99),
        }
        data["system_profile"]["operating_system"] = os_field

    # Same display_name
    hosts_data[3]["display_name"] = hosts_data[0]["display_name"]
    hosts_data[4]["display_name"] = hosts_data[0]["display_name"].upper()

    # Without operating system
    hosts_data[4]["system_profile"].pop("operating_system")
    hosts_data[9]["system_profile"].pop("operating_system")

    # Same OS name, different OS versions
    hosts_data[0]["system_profile"]["operating_system"]["name"] = "RHEL"
    hosts_data[5]["system_profile"]["operating_system"]["name"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]["name"]

    # Same OS version, different OS name
    hosts_data[6]["system_profile"]["operating_system"]["name"] = "CentOS Linux"
    hosts_data[6]["system_profile"]["operating_system"]["major"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]["major"]
    hosts_data[6]["system_profile"]["operating_system"]["minor"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]["minor"]

    # Same OS name and major, different minor
    hosts_data[7]["system_profile"]["operating_system"]["name"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]["name"]
    hosts_data[7]["system_profile"]["operating_system"]["major"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]["major"]

    # Same OS
    hosts_data[8]["system_profile"]["operating_system"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]

    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data, cleanup_scope="module")

    def _gen_group_name() -> str:
        # Make some group names uppercase
        if choice([True, False]):
            return generate_display_name().upper()
        return generate_display_name()

    # Hosts 0 and 9 are in the same group, Hosts 1 and 8 are without group
    groups_data = [GroupData(name=_gen_group_name(), hosts=[hosts[0], hosts[9]])]
    groups_data += [GroupData(name=_gen_group_name(), hosts=host) for host in hosts[2:8]]
    host_inventory.apis.groups.create_groups(groups_data, cleanup_scope="module")

    return hosts


@pytest.fixture
def hbi_kafka_prepare_host(host_inventory: ApplicationHostInventory) -> Generator[HostWrapper]:
    host = host_inventory.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="class")
def hbi_kafka_prepare_host_class(
    host_inventory: ApplicationHostInventory,
) -> Generator[HostWrapper]:
    host = host_inventory.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="module")
def hbi_kafka_prepare_host_module(
    host_inventory: ApplicationHostInventory,
) -> Generator[HostWrapper]:
    host = host_inventory.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture
def hbi_secondary_kafka_prepare_host(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostWrapper]:
    host = host_inventory_secondary.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="class")
def hbi_secondary_kafka_prepare_host_class(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostWrapper]:
    host = host_inventory_secondary.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="module")
def hbi_secondary_kafka_prepare_host_module(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostWrapper]:
    host = host_inventory_secondary.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)
