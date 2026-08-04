import pytest
from iqe.base.application import Application

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBACResources
from iqe_host_inventory.modeling.groups_api import GroupData


@pytest.fixture(scope="package")
def rbac_setup_resources(
    application: Application,
    host_inventory: ApplicationHostInventory,
    host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
) -> RBACResources:
    """WARNING: This will delete all existing hosts and groups and create new ones

    Prepares hosts and groups for RBAC tests. If used in granular RBAC tests, this should be done:
    Group1 and group2 should be in attributeFilter, group3 shouldn't be.
    First 3 hosts should be accessible. Host from group3 and host without group shouldn't be.
    The same applies to tags.

    Returns: (
        [hosts in group1 (1), hosts in group2 (2), hosts in group3 (1), hosts without group (1)],
        [tags of hosts in group1, tags of hosts in group2, ...]
        [group1 (with 1 host), group2 (with 2 hosts), group3 (with 1 host), group4 (without hosts)]
    )"""
    host_inventory.apis.hosts.confirm_delete_all()
    host_inventory.apis.groups.delete_all_groups()

    if application.config.current_env.lower() not in ("clowder_smoke", "ephemeral"):
        hosts = host_inventory_non_org_admin_cert_auth.upload.create_hosts(
            5, cleanup_scope="package"
        )
    else:
        # We can't use cert-auth in ephemeral
        hosts = host_inventory.upload.create_hosts(5, cleanup_scope="package")

    tags = host_inventory.apis.hosts.get_host_tags(hosts)
    host_tags = []
    for host in hosts:
        host_tags.append(tags[host.id])

    groups_data = [
        GroupData(hosts=[hosts[0]]),
        GroupData(hosts=hosts[1:3]),
        GroupData(hosts=[hosts[3]]),
        GroupData(hosts=[]),
    ]
    groups = host_inventory.apis.groups.create_groups(groups_data, cleanup_scope="package")

    return RBACResources(
        hosts=[hosts[:1], hosts[1:3], [hosts[3]], [hosts[4]]],
        tags=[host_tags[:1], host_tags[1:3], [host_tags[3]], [host_tags[4]]],
        groups=groups,
    )
