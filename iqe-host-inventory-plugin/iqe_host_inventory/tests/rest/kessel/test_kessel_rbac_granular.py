import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBacResources
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission

"""
REVISIT: Kessel still requires a special setup for the EE (see below).

To run in the EE:

1. Run insights-service-deployer:
    - Clone https://github.com/project-kessel/insights-service-deployer
    - Run deploy.sh deploy_with_hbi_demo

2. Run the tests with --kessel option
"""

pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent]
logger = logging.getLogger(__name__)


# These are essentially the same null group tests that live in test_rbac_granular_hosts.py
# and test_rbac_granular_groups.py.  The only difference is that we use the ungrouped
# group in the attributeFilter.  Continuing the theme of isolating kessel-specific
# tests under the kessel directory.  Once the migration is complete (Prod-deployed)
# and we no longer need the feature flag, we should integrate these tests into the
# proper modules.


def test_kessel_rbac_granular_hosts_read_permission_ungrouped_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    is_kessel_phase_1_enabled: bool,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped group permissions can
          only access ungrouped hosts
    """
    # Setup
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_READ], hbi_groups=[ungrouped_group]
    )

    # Test
    hosts = flatten(rbac_setup_resources_for_granular_rbac[0])
    correct_hosts_ids = {host.id for host in rbac_setup_resources_for_granular_rbac[0][3]}
    other_hosts_ids = {host.id for host in hosts if host.id not in correct_hosts_ids}

    response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(
        correct_hosts_ids if is_kessel_phase_1_enabled else hosts
    )
    response_hosts_ids = {host.id for host in response.results}
    assert response.count == len(correct_hosts_ids)
    assert response.total == len(correct_hosts_ids)
    assert response_hosts_ids == correct_hosts_ids

    if is_kessel_phase_1_enabled:
        for host_id in other_hosts_ids:
            with raises_apierror(403):
                host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(host_id)


def test_kessel_rbac_granular_hosts_write_permission_ungrouped_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped group can edit ungrouped hosts
    """
    # Setup
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=[ungrouped_group]
    )

    # Test
    host = rbac_setup_resources_for_granular_rbac[0][3][0]
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.hosts.patch_hosts(
        host.id, display_name=new_name, wait_for_updated=False
    )
    host_inventory.apis.hosts.wait_for_updated(host.id, display_name=new_name)

    # Teardown
    host_inventory.apis.hosts.patch_hosts(host.id, display_name=host.display_name)


def test_kessel_rbac_granular_hosts_write_permission_ungrouped_group_wrong(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    is_kessel_phase_1_enabled: bool,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        negative: true
        title: Test that users with granular RBAC ungrouped group can't edit grouped hosts
    """
    # Setup
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=[ungrouped_group]
    )

    # Test
    host = rbac_setup_resources_for_granular_rbac[0][2][0]
    new_name = generate_display_name()
    with raises_apierror(404):
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            host.id, display_name=new_name, wait_for_updated=False
        )
    host_inventory.apis.hosts.verify_not_updated(host.id, display_name=host.display_name)


def test_kessel_rbac_granular_hosts_read_permission_ungrouped_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    is_kessel_phase_1_enabled: bool,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped and normal groups can
          access correct hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac.groups
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_READ], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    hosts = flatten(rbac_setup_resources_for_granular_rbac.host_groups)
    correct_hosts_ids = {
        host.id
        for host in rbac_setup_resources_for_granular_rbac[0][0]
        + rbac_setup_resources_for_granular_rbac[0][3]
    }
    other_hosts_ids = {host.id for host in hosts if host.id not in correct_hosts_ids}

    response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(
        correct_hosts_ids if is_kessel_phase_1_enabled else hosts
    )
    response_hosts_ids = {host.id for host in response.results}
    assert response.count == len(correct_hosts_ids)
    assert response.total == len(correct_hosts_ids)
    assert response_hosts_ids == correct_hosts_ids

    if is_kessel_phase_1_enabled:
        for host_id in other_hosts_ids:
            with raises_apierror(403):
                host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(host_id)


def test_kessel_rbac_granular_hosts_write_permission_ungrouped_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped and normal groups can edit
          correct hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    host1 = rbac_setup_resources_for_granular_rbac[0][0][0]
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.hosts.patch_hosts(
        host1.id, display_name=new_name, wait_for_updated=False
    )
    host_inventory.apis.hosts.wait_for_updated(host1.id, display_name=new_name)

    host2 = rbac_setup_resources_for_granular_rbac[0][3][0]
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.hosts.patch_hosts(
        host2.id, display_name=new_name, wait_for_updated=False
    )
    host_inventory.apis.hosts.wait_for_updated(host2.id, display_name=new_name)

    # Teardown
    host_inventory.apis.hosts.patch_hosts(host1.id, display_name=host1.display_name)
    host_inventory.apis.hosts.patch_hosts(host2.id, display_name=host2.display_name)


def test_kessel_rbac_granular_hosts_write_permission_ungrouped_and_normal_group_wrong(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    is_kessel_phase_1_enabled: bool,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        negative: true
        title: Test that users with granular RBAC ungrouped and normal groups can't edit
          incorrect hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    host = rbac_setup_resources_for_granular_rbac[0][2][0]
    new_name = generate_display_name()
    with raises_apierror(404):
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            host.id, display_name=new_name, wait_for_updated=False
        )
    host_inventory.apis.hosts.verify_not_updated(host.id, display_name=host.display_name)


def test_rbac_granular_groups_read_permission_ungrouped_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: fstavela
        importance: medium
        negative: true
        title: Test that users with granular RBAC ungrouped group can't access groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_READ], hbi_groups=[ungrouped_group]
    )

    # Test
    with raises_apierror(403, "You do not have access to the the following groups: "):
        host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(groups)


def test_rbac_granular_groups_write_permission_ungrouped_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: medium
        negative: true
        title: Test that users with granular RBAC ungrouped group can't edit groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_WRITE], hbi_groups=[ungrouped_group]
    )

    # Test
    new_name = generate_display_name()
    with raises_apierror(
        403,
        f"You do not have access to the the following groups: {groups[2].id}",
    ):
        host_inventory_non_org_admin.apis.groups.patch_group(
            groups[2], name=new_name, wait_for_updated=False
        )

    host_inventory.apis.groups.verify_not_updated(groups[2], name=groups[2].name)


def test_rbac_granular_groups_read_permission_ungrouped_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped and normal groups can access
          correct groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_READ], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    response = host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(groups[0])
    assert response.count == 1
    assert response.total == 1
    assert len(response.results) == 1
    assert response.results[0].id == groups[0].id

    for group in groups[1:]:
        with raises_apierror(
            403,
            f"You do not have access to the the following groups: {group.id}",
        ):
            host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(group)


def test_rbac_granular_groups_write_permission_ungrouped_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped and normal groups can edit
          correct groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_WRITE], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.groups.patch_group(
        groups[0], name=new_name, wait_for_updated=False
    )
    host_inventory.apis.groups.verify_updated(groups[0], name=new_name)

    # Teardown
    host_inventory.apis.groups.patch_group(groups[0], name=groups[0].name)


def test_rbac_granular_groups_write_permission_ungrouped_and_normal_group_wrong(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        negative: true
        title: Test that users with granular RBAC ungrouped and normal groups can't edit
          incorrect groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_WRITE], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    new_name = generate_display_name()
    with raises_apierror(
        403,
        f"You do not have access to the the following groups: {groups[2].id}",
    ):
        host_inventory_non_org_admin.apis.groups.patch_group(
            groups[2], name=new_name, wait_for_updated=False
        )

    host_inventory.apis.groups.verify_not_updated(groups[2], name=groups[2].name)
