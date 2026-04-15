import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.staleness_utils import get_staleness_fields
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
    pytest.mark.usefixtures("hbi_staleness_cleanup"),
]


def test_rbac_inventory_with_rhel_roles(
    host_inventory: ApplicationHostInventory,
    host_inventory_non_org_admin: ApplicationHostInventory,
    rbac_setup_resources,
    hbi_staleness_defaults: dict[str, int],
    rbac_setup_user_with_rhel_role: str,
):
    """
    Test that user with RHEL roles has required inventory permissions.
    RHEL admin and RHEL operator roles have inventory read and wrrite permissions.
    RHEL viewer has only inventory read permissions.

    https://issues.redhat.com/browse/RHINENG-16109
    https://issues.redhat.com/browse/RHCLOUD-35891

    metadata:
        importance: high
        requirements: inv-rbac
        assignee: zabikeno
        title: Test that user with RHEL roles has required inventory permissions
    """
    role = rbac_setup_user_with_rhel_role
    role_with_write_permissions = role in ["RHEL operator", "RHEL admin"]

    # Hosts
    # check RHEL viewer's inventory read access
    hosts = rbac_setup_resources[0]
    expected_hosts_ids = {host.id for host in hosts}

    response = host_inventory_non_org_admin.apis.hosts.get_hosts_response()
    response_hosts_ids = {host.id for host in response.results}

    assert len(response.results) >= 2
    assert expected_hosts_ids.issubset(response_hosts_ids)

    # check at least one hosts edit operation to make sure user has write access
    if role_with_write_permissions:
        new_display_name = generate_display_name()
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            hosts[0].id, display_name=new_display_name
        )

    # Groups
    # check RHEL viewer's inventory read access
    groups = rbac_setup_resources[1]
    expected_groups_ids = {group.id for group in groups}

    response = host_inventory_non_org_admin.apis.groups.get_groups()
    response_groups_ids = {group.id for group in response}

    assert len(response) >= 2
    assert expected_groups_ids.issubset(response_groups_ids)

    # check at least one groups edit operation to make sure user has write access
    if role_with_write_permissions:
        new_group_name = generate_display_name()
        host_inventory_non_org_admin.apis.groups.patch_group(groups[0], name=new_group_name)

    # Staleness
    # check RHEL viewer's inventory read access
    response = host_inventory_non_org_admin.apis.account_staleness.get_staleness_response()
    validate_staleness_response(response.to_dict(), hbi_staleness_defaults)

    # check at least one staleness edit operation to make sure user has write access
    if role_with_write_permissions:
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        original = host_inventory.apis.account_staleness.create_staleness(**settings).to_dict()

        settings = dict(zip(get_staleness_fields(), [4, 5, 6], strict=False))
        response = host_inventory_non_org_admin.apis.account_staleness.update_staleness(**settings)
        validate_staleness_response(response.to_dict(), original, settings)
