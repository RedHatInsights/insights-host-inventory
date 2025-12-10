# mypy: disallow-untyped-defs

from __future__ import annotations

from typing import NamedTuple

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.datagen_utils import gen_tag_with_parameters
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut


class ExportResources(NamedTuple):
    hosts: list[HostOut]
    groups: list[GroupOutWithHostCount]
    host_groups: dict[str, list[HostWrapper]]


@pytest.fixture(scope="class")
def exports_setup_resources(host_inventory: ApplicationHostInventory) -> ExportResources:
    host_inventory.apis.hosts.confirm_delete_all()

    hosts_data = host_inventory.datagen.create_n_hosts_data(100)
    hosts_data.extend(host_inventory.datagen.create_n_hosts_data(70, host_type="edge"))
    hosts_data.extend(host_inventory.datagen.create_n_minimal_hosts_data(4))
    hosts_data.append(host_inventory.datagen.create_complete_host_data())
    hosts_data.extend(host_inventory.datagen.create_n_hosts_data_with_tags(24))

    # Add 1 more that has some null values
    tags = [
        gen_tag_with_parameters("key1", "namespace1", "val1"),
        gen_tag_with_parameters("key2", "namespace2", None),
        gen_tag_with_parameters("key3", None, "val2"),
    ]
    hosts_data.append(host_inventory.datagen.create_host_data(tags=tags))
    hosts = host_inventory.kafka.create_hosts(
        hosts_data=hosts_data, timeout=30, cleanup_scope="class"
    )

    groups_data = [
        GroupData(hosts=hosts[:50]),
        GroupData(hosts=hosts[50:100]),
        GroupData(hosts=hosts[100:150]),
    ]
    groups = host_inventory.apis.groups.create_groups(groups_data, cleanup_scope="class")

    host_groups = {}
    host_groups[groups[0].id] = hosts[:50]
    host_groups[groups[1].id] = hosts[50:100]
    host_groups[groups[2].id] = hosts[100:150]
    host_groups["ungrouped"] = hosts[150:]

    # Need to retrieve the hosts again since host.updated will change after
    # hosts are added to a group:
    #    https://issues.redhat.com/browse/RHINENG-11171
    refreshed_hosts = host_inventory.apis.hosts.get_hosts_by_id(hosts)

    # Host groupings aren't currently used, but I anticipate them being
    # useful for filtering tests (filters aren't yet supported).
    return ExportResources(
        hosts=refreshed_hosts,
        groups=groups,
        host_groups=host_groups,
    )
