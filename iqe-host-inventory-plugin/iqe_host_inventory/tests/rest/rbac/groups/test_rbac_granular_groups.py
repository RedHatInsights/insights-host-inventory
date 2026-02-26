"""
metadata:
    requirements: inv-rbac-granular-groups
"""

from __future__ import annotations

import logging
from os import getenv

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBacResources
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import FORBIDDEN_OR_NOT_FOUND
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.api_utils import ungrouped_host_groups
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut

pytestmark = [
    pytest.mark.rbac_dependent,
    pytest.mark.backend,
    pytest.mark.skipif(
        getenv("ENV_FOR_DYNACONF", "stage_proxy").lower() == "clowder_smoke",
        reason="RBAC ignores HBI groups if RBAC V2 (Kessel) is disabled: "
        "https://redhat-internal.slack.com/archives/C0233N2MBU6/p1755699688749819",
        # TODO: Remove skipif when https://issues.redhat.com/browse/RHCLOUD-41427 is done
    ),
]


logger = logging.getLogger(__name__)


@pytest.fixture(
    params=[
        lf("rbac_inventory_groups_read_granular_user_setup_class"),
        lf("rbac_inventory_all_read_granular_user_setup_class"),
        lf("rbac_inventory_groups_all_granular_user_setup_class"),
        lf("rbac_inventory_admin_granular_user_setup_class"),
    ],
    scope="class",
)
def read_permission_user_setup(request: pytest.FixtureRequest):
    return request.param


@pytest.fixture(
    params=[
        lf("rbac_inventory_groups_write_granular_user_setup_class"),
        lf("rbac_inventory_groups_all_granular_user_setup_class"),
        lf("rbac_inventory_admin_granular_user_setup_class"),
    ],
    scope="class",
)
def write_permission_user_setup(request: pytest.FixtureRequest):
    return request.param


@pytest.fixture(scope="class")
def prepare_hosts(host_inventory: ApplicationHostInventory) -> list[HostOut]:
    return host_inventory.upload.create_hosts(2, cleanup_scope="class")


class TestRBACGranularGroupsReadPermission:
    def test_rbac_granular_groups_read_permission_get_groups_list(
        self,
        read_permission_user_setup,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        hbi_non_org_admin_user_org_id,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: high
          title: Test that users with granular RBAC access can get a correct list of groups
        """
        expected_groups = rbac_setup_resources_for_granular_rbac[1][:2]
        expected_groups_ids = {host.id for host in expected_groups}

        response = host_inventory_non_org_admin.apis.groups.get_groups_response()
        response_groups_ids = {group.id for group in response.results}

        assert response.count == len(expected_groups)
        assert response.total == len(expected_groups)
        assert len(response.results) == len(expected_groups)
        for group in response.results:
            assert group.org_id == hbi_non_org_admin_user_org_id
        assert response_groups_ids == expected_groups_ids

    def test_rbac_granular_groups_read_permission_get_groups_by_id(
        self,
        read_permission_user_setup,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          title: Test that users with granular RBAC access can get correct groups by IDs
        """
        expected_groups = rbac_setup_resources_for_granular_rbac[1][:2]
        expected_groups_ids = {host.id for host in expected_groups}

        response = host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(
            expected_groups
        )
        response_groups_ids = {group.id for group in response.results}

        assert response.count == len(expected_groups)
        assert response.total == len(expected_groups)
        assert len(response.results) == len(expected_groups)
        assert response_groups_ids == expected_groups_ids

    def test_rbac_granular_groups_read_permission_get_groups_by_id_wrong(
        self,
        read_permission_user_setup,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC access can't get incorrect groups by IDs
        """
        all_groups = rbac_setup_resources_for_granular_rbac[1]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(all_groups)


@pytest.mark.usefixtures("write_permission_user_setup")
class TestRBACGranularGroupsWritePermission:
    def test_rbac_granular_groups_write_permission_create_group(
        self,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-post
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with only granular RBAC access can't create new groups
        """
        group_name = generate_display_name()
        with raises_apierror(
            403,
            "Unfiltered inventory:groups:write RBAC permission is required "
            "in order to create new groups.",
        ):
            host_inventory_non_org_admin.apis.groups.create_group(
                group_name, wait_for_created=False
            )

        host_inventory.apis.groups.verify_not_created(group_name=group_name)

    def test_rbac_granular_groups_write_permission_patch_group(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-patch
          assignee: fstavela
          importance: high
          title: Test that users with granular RBAC access can patch correct groups
        """
        correct_groups = rbac_setup_resources_for_granular_rbac[1][:2]

        for group in correct_groups:
            new_group_name = generate_display_name()
            host_inventory_non_org_admin.apis.groups.patch_group(
                group, name=new_group_name, wait_for_updated=False
            )
            host_inventory.apis.groups.verify_updated(group, name=new_group_name)

        # Teardown
        for group in correct_groups:
            host_inventory.apis.groups.patch_group(group, name=group.name)

    def test_rbac_granular_groups_write_permission_remove_hosts(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
        prepare_hosts: list[HostOut],
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-remove-hosts
          assignee: fstavela
          importance: high
          title: Test that users with granular RBAC access can remove hosts from correct groups
        """
        groups = rbac_setup_resources_for_granular_rbac[1][:2]
        host1 = prepare_hosts[0]
        host2 = prepare_hosts[1]

        host_inventory.apis.groups.add_hosts_to_group(groups[0], host1)
        host_inventory.apis.groups.add_hosts_to_group(groups[1], host2)

        host_inventory_non_org_admin.apis.groups.remove_hosts_from_group(
            groups[0], hosts=host1, wait_for_removed=False
        )
        host_inventory_non_org_admin.apis.groups.remove_hosts_from_group(
            groups[1], hosts=host2, wait_for_removed=False
        )

        host_inventory.apis.groups.verify_hosts_removed(hosts=[host1, host2])

    def test_rbac_granular_groups_write_permission_remove_hosts_from_multiple_groups(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
        prepare_hosts: list[HostOut],
    ):
        """
        https://issues.redhat.com/browse/RHINENG-1655

        metadata:
          requirements: inv-groups-remove-hosts-multiple-groups
          assignee: fstavela
          importance: high
          title: Test that users with granular RBAC access can remove hosts from correct groups
                 via DELETE /groups/hosts/<host_ids> endpoint
        """
        groups = rbac_setup_resources_for_granular_rbac[1][:2]
        host1 = prepare_hosts[0]
        host2 = prepare_hosts[1]

        host_inventory.apis.groups.add_hosts_to_group(groups[0], host1)
        host_inventory.apis.groups.add_hosts_to_group(groups[1], host2)

        host_inventory_non_org_admin.apis.groups.remove_hosts_from_multiple_groups(
            [host1, host2], wait_for_removed=False
        )

        host_inventory.apis.groups.verify_hosts_removed(hosts=[host1, host2])

    def test_rbac_granular_groups_write_permission_add_hosts(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-add-hosts
          assignee: fstavela
          importance: high
          title: Test that users with granular RBAC access can add hosts to correct groups
        """
        groups = rbac_setup_resources_for_granular_rbac[1][:2]
        host1, host2 = host_inventory.upload.create_hosts(2)

        host_inventory_non_org_admin.apis.groups.add_hosts_to_group(
            groups[0], hosts=host1, wait_for_added=False
        )
        host_inventory_non_org_admin.apis.groups.add_hosts_to_group(
            groups[1], hosts=host2, wait_for_added=False
        )

        host_inventory.apis.groups.verify_hosts_added(groups[0], hosts=host1)
        host_inventory.apis.groups.verify_hosts_added(groups[1], hosts=host2)

    def test_rbac_granular_groups_write_permission_patch_group_wrong(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-patch
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC access can't patch incorrect groups
        """
        group = rbac_setup_resources_for_granular_rbac[1][2]
        original_group_name = host_inventory.apis.groups.get_group_by_id(group).name
        new_group_name = generate_display_name()

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.patch_group(
                group, name=new_group_name, wait_for_updated=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=original_group_name)

    def test_rbac_granular_groups_write_permission_remove_hosts_wrong(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-remove-hosts
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC access can't remove hosts from incorrect groups
        """
        group = rbac_setup_resources_for_granular_rbac[1][2]
        hosts = rbac_setup_resources_for_granular_rbac[0][2]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.remove_hosts_from_group(
                group, hosts=hosts, wait_for_removed=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=hosts)

    def test_rbac_granular_groups_write_permission_remove_hosts_from_multiple_groups_wrong(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-1655

        metadata:
          requirements: inv-groups-remove-hosts-multiple-groups
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC access can't remove hosts from incorrect groups
                 via DELETE /groups/hosts/<host_ids> endpoint
        """
        group = rbac_setup_resources_for_granular_rbac[1][2]
        hosts = rbac_setup_resources_for_granular_rbac[0][2]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.remove_hosts_from_multiple_groups(
                hosts=hosts, wait_for_removed=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=hosts)

    def test_rbac_granular_groups_write_permission_remove_hosts_from_multiple_groups_good_and_bad(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-1655

        metadata:
          requirements: inv-groups-remove-hosts-multiple-groups
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC access can't remove hosts from groups via
                 DELETE /groups/hosts/<host_ids> endpoint if the request includes good and bad hosts
        """  # NOQA: E501
        groups = rbac_setup_resources_for_granular_rbac.groups
        hosts_by_group = rbac_setup_resources_for_granular_rbac.host_groups[: len(groups)]
        all_hosts = flatten(hosts_by_group)

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.remove_hosts_from_multiple_groups(
                all_hosts, wait_for_removed=False
            )

        for i in range(len(groups)):
            host_inventory.apis.groups.verify_not_updated(groups[i], hosts=hosts_by_group[i])

    def test_rbac_granular_groups_write_permission_add_hosts_wrong(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-add-hosts
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC access can't add hosts to incorrect groups
        """
        group = rbac_setup_resources_for_granular_rbac[1][2]
        original_hosts = rbac_setup_resources_for_granular_rbac[0][2]
        new_hosts = rbac_setup_resources_for_granular_rbac[0][3]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.add_hosts_to_group(
                group, hosts=new_hosts, wait_for_added=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=original_hosts)

    def test_rbac_granular_groups_write_permission_delete_group_wrong(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-delete
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC access can't delete incorrect groups
        """
        group = rbac_setup_resources_for_granular_rbac[1][2]

        with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
            host_inventory_non_org_admin.apis.groups.delete_groups(group, wait_for_deleted=False)

        host_inventory.apis.groups.verify_not_deleted(group)


@pytest.fixture(
    params=[
        lf("rbac_inventory_groups_read_granular_user_setup_class"),
        lf("rbac_inventory_hosts_write_granular_user_setup_class"),
    ],
    scope="class",
)
def wrong_permission_setup_write_endpoints(request: pytest.FixtureRequest):
    return request.param


@pytest.fixture(
    params=[
        lf("rbac_inventory_groups_write_granular_user_setup_class"),
        lf("rbac_inventory_hosts_read_granular_user_setup_class"),
    ],
    scope="class",
)
def wrong_permission_setup_read_endpoints(request: pytest.FixtureRequest):
    return request.param


class TestRBACGranularGroupsWrongPermissionWriteEndpoints:
    def test_rbac_granular_groups_wrong_permission_patch_group(
        self,
        wrong_permission_setup_write_endpoints,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-patch
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC on wrong permission can't patch a group
        """
        group = rbac_setup_resources_for_granular_rbac[1][0]
        new_group_name = generate_display_name()

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.patch_group(
                group, name=new_group_name, wait_for_updated=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, retries=1)

    def test_rbac_granular_groups_wrong_permission_delete_group(
        self,
        wrong_permission_setup_write_endpoints,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-delete
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC on wrong permission can't delete a group
        """
        group = rbac_setup_resources_for_granular_rbac[1][0]

        with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
            host_inventory_non_org_admin.apis.groups.delete_groups(group, wait_for_deleted=False)

        host_inventory.apis.groups.verify_not_deleted(group, retries=1)

    def test_rbac_granular_groups_wrong_permission_remove_hosts(
        self,
        wrong_permission_setup_write_endpoints,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-remove-hosts
          assignee: fstavela
          importance: high
          negative: true
          title: Test users with granular RBAC on wrong permission can't remove hosts from a group
        """
        group = rbac_setup_resources_for_granular_rbac[1][0]
        hosts = rbac_setup_resources_for_granular_rbac[0][0]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.remove_hosts_from_group(
                group, hosts=hosts[0].id, wait_for_removed=False
            )

        host_inventory.apis.groups.verify_not_updated(
            group, name=group.name, hosts=hosts, retries=1
        )

    def test_rbac_granular_groups_wrong_permission_remove_hosts_from_multiple_groups(
        self,
        wrong_permission_setup_write_endpoints,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-1655

        metadata:
          requirements: inv-groups-remove-hosts-multiple-groups
          assignee: fstavela
          importance: high
          negative: true
          title: Test users with granular RBAC on wrong permission can't remove hosts from groups
                 via DELETE /groups/hosts/<host_ids> endpoint
        """
        group = rbac_setup_resources_for_granular_rbac[1][0]
        hosts = rbac_setup_resources_for_granular_rbac[0][0]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.remove_hosts_from_multiple_groups(
                hosts[0].id, wait_for_removed=False
            )

        host_inventory.apis.groups.verify_not_updated(
            group, name=group.name, hosts=hosts, retries=1
        )

    def test_rbac_granular_groups_wrong_permission_add_hosts(
        self,
        wrong_permission_setup_write_endpoints,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-add-hosts
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC on wrong permission can't add hosts to a group
        """
        group = rbac_setup_resources_for_granular_rbac[1][1]
        original_hosts = rbac_setup_resources_for_granular_rbac[0][1]
        new_host = rbac_setup_resources_for_granular_rbac[0][3][0]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.add_hosts_to_group(
                group, hosts=new_host, wait_for_added=False
            )

        host_inventory.apis.groups.verify_not_updated(
            group, name=group.name, hosts=original_hosts, retries=1
        )


class TestRBACGranularGroupsWrongPermissionReadEndpoints:
    def test_rbac_granular_groups_wrong_permission_get_groups_list(
        self,
        wrong_permission_setup_read_endpoints,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC on wrong permission can't get a list of groups
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.get_groups()

    def test_rbac_granular_groups_wrong_permission_get_groups_by_id(
        self,
        wrong_permission_setup_read_endpoints,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users with granular RBAC on wrong permission can't get groups by ID
        """
        groups = rbac_setup_resources_for_granular_rbac[1][:2]

        for group in groups:
            with raises_apierror(
                403,
                "You don't have the permission to access the requested resource. "
                "It is either read-protected or not readable by the server.",
            ):
                host_inventory_non_org_admin.apis.groups.get_groups_by_id(group)


@pytest.fixture(
    params=[
        RBACInventoryPermission.GROUPS_WRITE,
        RBACInventoryPermission.GROUPS_ALL,
        RBACInventoryPermission.ADMIN,
    ]
)
def write_permission_user_setup_for_group_delete(
    request: pytest.FixtureRequest,
    host_inventory,
    hbi_non_org_admin_user_rbac_setup,
) -> list[GroupOutWithHostCount]:
    groups = host_inventory.apis.groups.create_n_empty_groups(2)
    hbi_non_org_admin_user_rbac_setup(permissions=[request.param], hbi_groups=groups)
    return groups


def test_rbac_granular_groups_write_permission_delete_group(
    write_permission_user_setup_for_group_delete,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
      requirements: inv-groups-delete
      assignee: fstavela
      importance: high
      title: Test that users with granular RBAC access can delete correct groups
    """
    groups = write_permission_user_setup_for_group_delete
    for group in groups:
        host_inventory_non_org_admin.apis.groups.delete_groups(group, wait_for_deleted=False)
    host_inventory.apis.groups.verify_deleted(groups)


def test_rbac_granular_groups_read_permission_single_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
      requirements: inv-groups-get-by-id
      assignee: fstavela
      importance: high
      title: Test that users with granular RBAC single group can access correct groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_READ], hbi_groups=[groups[0]]
    )

    # Test
    response = host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(groups[0])
    assert response.count == 1
    assert response.total == 1
    assert len(response.results) == 1
    assert response.results[0].id == groups[0].id


def test_rbac_granular_groups_write_permission_single_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: high
      title: Test that users with granular RBAC single group can edit correct groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_WRITE], hbi_groups=[groups[0]]
    )

    # Test
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.groups.patch_group(
        groups[0], name=new_name, wait_for_updated=False
    )
    host_inventory.apis.groups.verify_updated(groups[0], name=new_name)

    # Teardown
    host_inventory.apis.groups.patch_group(groups[0], name=groups[0].name)


def test_rbac_granular_groups_read_permission_null_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
      requirements: inv-groups-get-by-id
      assignee: fstavela
      importance: medium
      negative: true
      title: Test that users with granular RBAC null group can't access groups
    """
    # Setup
    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [ungrouped_groups[0]["id"]] if len(ungrouped_groups) > 0 else [None]  # type: ignore[index]

    groups = rbac_setup_resources_for_granular_rbac[1]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_READ], hbi_groups=hbi_groups
    )

    # Test
    with raises_apierror(
        403,
        "You don't have the permission to access the requested resource. "
        "It is either read-protected or not readable by the server.",
    ):
        host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(groups)


def test_rbac_granular_groups_write_permission_null_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: medium
      negative: true
      title: Test that users with granular RBAC null group can't edit groups
    """
    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [ungrouped_groups[0]["id"]] if len(ungrouped_groups) > 0 else [None]  # type: ignore[index]

    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_WRITE], hbi_groups=hbi_groups
    )

    # Test
    new_name = generate_display_name()
    with raises_apierror(
        403,
        "You don't have the permission to access the requested resource. "
        "It is either read-protected or not readable by the server.",
    ):
        host_inventory_non_org_admin.apis.groups.patch_group(
            groups[2], name=new_name, wait_for_updated=False
        )

    host_inventory.apis.groups.verify_not_updated(groups[2], name=groups[2].name)


def test_rbac_granular_groups_read_permission_null_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
        requirements: inv-groups-get-by-id
        assignee: fstavela
        importance: high
        title: Test that users with granular RBAC null and normal group can access correct groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]

    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [groups[0], ungrouped_groups[0]["id"] if len(ungrouped_groups) > 0 else None]  # type: ignore[index]

    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_READ], hbi_groups=hbi_groups
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
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(group)


def test_rbac_granular_groups_write_permission_null_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
        requirements: inv-groups-patch
        assignee: fstavela
        importance: high
        title: Test that users with granular RBAC null and normal group can edit correct groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]

    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [groups[0], ungrouped_groups[0]["id"] if len(ungrouped_groups) > 0 else None]  # type: ignore[index]

    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_WRITE], hbi_groups=hbi_groups
    )

    # Test
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.groups.patch_group(
        groups[0], name=new_name, wait_for_updated=False
    )
    host_inventory.apis.groups.verify_updated(groups[0], name=new_name)

    # Teardown
    host_inventory.apis.groups.patch_group(groups[0], name=groups[0].name)


def test_rbac_granular_groups_write_permission_null_and_normal_group_wrong(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
        requirements: inv-groups-patch
        assignee: fstavela
        importance: high
        negative: true
        title: Test that users with granular RBAC null and normal group can't edit incorrect groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]

    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [groups[0], ungrouped_groups[0]["id"] if len(ungrouped_groups) > 0 else None]  # type: ignore[index]

    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_WRITE], hbi_groups=hbi_groups
    )

    # Test
    new_name = generate_display_name()
    with raises_apierror(
        403,
        "You don't have the permission to access the requested resource. "
        "It is either read-protected or not readable by the server.",
    ):
        host_inventory_non_org_admin.apis.groups.patch_group(
            groups[2], name=new_name, wait_for_updated=False
        )

    host_inventory.apis.groups.verify_not_updated(groups[2], name=groups[2].name)


@pytest.fixture(scope="class")
def setup_all_permissions(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    host_inventory: ApplicationHostInventory,
    hbi_non_org_admin_user_username: str,
):
    permissions = [
        RBACInventoryPermission.GROUPS_READ,
        RBACInventoryPermission.GROUPS_WRITE,
        RBACInventoryPermission.HOSTS_READ,
        RBACInventoryPermission.HOSTS_WRITE,
    ]
    hbi_groups = [rbac_setup_resources_for_granular_rbac[1][0]]

    group, roles = host_inventory.apis.rbac.setup_rbac_user(
        hbi_non_org_admin_user_username, permissions, hbi_groups=hbi_groups
    )

    host_inventory.apis.rbac.check_inventory_user_permission(
        hbi_non_org_admin_user_username,
        permissions,
        hbi_groups=hbi_groups,
    )

    yield

    for role in roles:
        host_inventory.apis.rbac.delete_role(role.uuid)
    host_inventory.apis.rbac.delete_group(group.uuid)


class TestRBACGranularAllPermissions:
    def test_rbac_granular_groups_all_permissions_read(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        setup_all_permissions,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          title: Test that users with granular RBAC all permissions can access correct groups
        """
        group = rbac_setup_resources_for_granular_rbac[1][0]

        response = host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(group)
        assert response.count == 1
        assert response.total == 1
        assert len(response.results) == 1
        assert response.results[0].id == group.id

    def test_rbac_granular_groups_all_permissions_write(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        setup_all_permissions,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-patch
          assignee: fstavela
          importance: high
          title: Test that users with granular RBAC all permissions can edit correct groups
        """
        groups = rbac_setup_resources_for_granular_rbac[1]

        new_name = generate_display_name()
        host_inventory_non_org_admin.apis.groups.patch_group(
            groups[0], name=new_name, wait_for_updated=False
        )
        host_inventory.apis.groups.verify_updated(groups[0], name=new_name)

        # Teardown
        host_inventory.apis.groups.patch_group(groups[0], name=groups[0].name)

    def test_rbac_granular_hosts_all_permissions_read(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        setup_all_permissions,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC all permissions can access correct hosts
        """
        hosts = flatten(rbac_setup_resources_for_granular_rbac.host_groups)
        correct_hosts_ids = {host.id for host in rbac_setup_resources_for_granular_rbac[0][0]}

        response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(hosts)
        response_hosts_ids = {host.id for host in response.results}
        assert response.count == len(correct_hosts_ids)
        assert response.total == len(correct_hosts_ids)
        assert response_hosts_ids == correct_hosts_ids

    def test_rbac_granular_hosts_all_permissions_write(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        setup_all_permissions,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-patch
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC all permissions can edit correct hosts
        """
        host = rbac_setup_resources_for_granular_rbac[0][0][0]
        new_name = generate_display_name()
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            host.id, display_name=new_name, wait_for_updated=False
        )
        host_inventory.apis.hosts.wait_for_updated(host.id, display_name=new_name)

        # Teardown
        host_inventory.apis.hosts.patch_hosts(host.id, display_name=host.display_name)


@pytest.fixture(scope="class", params=["first_with", "first_without"])
def setup_permissions_with_and_without_resource_definitions(
    request: pytest.FixtureRequest,
    rbac_setup_resources_for_granular_rbac: RBacResources,
    host_inventory: ApplicationHostInventory,
    hbi_non_org_admin_user_username: str,
):
    """Creates 2 roles, one with and one without resource definitions.
    User should have access to all resources."""
    hbi_groups = [rbac_setup_resources_for_granular_rbac[1][0]]
    host_inventory.apis.rbac.reset_user_groups(hbi_non_org_admin_user_username)

    group = host_inventory.apis.rbac.create_group(
        RBACInventoryPermission.ALL_READ, hbi_groups=hbi_groups
    )
    host_inventory.apis.rbac.add_user_to_a_group(hbi_non_org_admin_user_username, group.uuid)

    if request.param == "first_with":
        roles = [
            host_inventory.apis.rbac.create_role(
                RBACInventoryPermission.ALL_READ, hbi_groups=hbi_groups
            ),
            host_inventory.apis.rbac.create_role(RBACInventoryPermission.ALL_READ),
        ]
    else:
        roles = [
            host_inventory.apis.rbac.create_role(RBACInventoryPermission.ALL_READ),
            host_inventory.apis.rbac.create_role(
                RBACInventoryPermission.ALL_READ, hbi_groups=hbi_groups
            ),
        ]

    host_inventory.apis.rbac.add_roles_to_a_group(roles, group.uuid)

    yield

    for role in roles:
        host_inventory.apis.rbac.delete_role(role.uuid)
    host_inventory.apis.rbac.delete_group(group.uuid)


class TestRBACGranularWithAndWithoutResourceDefinitions:
    def test_rbac_granular_groups_with_and_without_resource_definitions(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        setup_permissions_with_and_without_resource_definitions,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          title: Test that users with and without granular RBAC can access all groups
        """
        groups = rbac_setup_resources_for_granular_rbac[1]
        groups_ids = {group.id for group in groups}

        response = host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(groups)
        response_ids = {group.id for group in response.results}
        assert response.count == len(groups)
        assert response.total == len(groups)
        assert response_ids == groups_ids

    def test_rbac_granular_hosts_with_and_without_resource_definitions(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        setup_permissions_with_and_without_resource_definitions,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            title: Test that users with and without granular RBAC can access all hosts
        """
        hosts = flatten(rbac_setup_resources_for_granular_rbac.host_groups)
        hosts_ids = {host.id for host in hosts}

        response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(hosts)
        response_hosts_ids = {host.id for host in response.results}
        assert response.count == len(hosts)
        assert response.total == len(hosts)
        assert response_hosts_ids == hosts_ids


@pytest.fixture(scope="class")
def setup_resource_definitions_in_multiple_roles(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    host_inventory: ApplicationHostInventory,
    hbi_non_org_admin_user_username: str,
):
    """Setup 2 roles with the same permission, but with different resourceDefinitions.
    User should have access to resources in both resourceDefinitions."""
    hbi_groups = rbac_setup_resources_for_granular_rbac[1][:2]
    host_inventory.apis.rbac.reset_user_groups(hbi_non_org_admin_user_username)

    group = host_inventory.apis.rbac.create_group(
        RBACInventoryPermission.ADMIN, hbi_groups=hbi_groups
    )
    host_inventory.apis.rbac.add_user_to_a_group(hbi_non_org_admin_user_username, group.uuid)

    roles = [
        host_inventory.apis.rbac.create_role(
            RBACInventoryPermission.ADMIN, hbi_groups=[hbi_groups[0]]
        ),
        host_inventory.apis.rbac.create_role(
            RBACInventoryPermission.ADMIN, hbi_groups=[hbi_groups[1]]
        ),
    ]

    host_inventory.apis.rbac.add_roles_to_a_group(roles, group.uuid)

    yield

    for role in roles:
        host_inventory.apis.rbac.delete_role(role.uuid)
    host_inventory.apis.rbac.delete_group(group.uuid)


class TestRBACGranularResourceDefinitionsInMultipleRoles:
    def test_rbac_granular_groups_multiple_roles_get_groups_by_id(
        self,
        setup_resource_definitions_in_multiple_roles,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          title: Test granular RBAC - groups in multiple roles: user can get correct groups by IDs
        """
        expected_groups = rbac_setup_resources_for_granular_rbac[1][:2]
        expected_groups_ids = {host.id for host in expected_groups}

        response = host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(
            expected_groups
        )
        response_groups_ids = {group.id for group in response.results}

        assert response.count == len(expected_groups)
        assert response.total == len(expected_groups)
        assert len(response.results) == len(expected_groups)
        assert response_groups_ids == expected_groups_ids

    def test_rbac_granular_groups_multiple_roles_get_groups_by_id_wrong(
        self,
        setup_resource_definitions_in_multiple_roles,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          negative: true
          title: Granular RBAC - groups in multiple roles: user can't get incorrect groups by IDs
        """
        all_groups = rbac_setup_resources_for_granular_rbac[1]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(all_groups)

    def test_rbac_granular_groups_multiple_roles_patch_group(
        self,
        setup_resource_definitions_in_multiple_roles,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-patch
          assignee: fstavela
          importance: high
          title: Test granular RBAC - groups in multiple roles: user can patch correct groups
        """
        correct_groups = rbac_setup_resources_for_granular_rbac[1][:2]

        for group in correct_groups:
            new_group_name = generate_display_name()
            host_inventory_non_org_admin.apis.groups.patch_group(
                group, name=new_group_name, wait_for_updated=False
            )
            host_inventory.apis.groups.verify_updated(group, name=new_group_name)

        # Teardown
        for group in correct_groups:
            host_inventory.apis.groups.patch_group(group, name=group.name)

    def test_rbac_granular_groups_multiple_roles_patch_group_wrong(
        self,
        setup_resource_definitions_in_multiple_roles,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-patch
          assignee: fstavela
          importance: high
          negative: true
          title: Test granular RBAC - groups in multiple roles: user can't patch incorrect groups
        """
        group = rbac_setup_resources_for_granular_rbac[1][2]
        original_group_name = host_inventory.apis.groups.get_group_by_id(group).name
        new_group_name = generate_display_name()

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.patch_group(
                group, name=new_group_name, wait_for_updated=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=original_group_name, retries=1)

    def test_rbac_granular_hosts_multiple_roles_get_host(
        self,
        setup_resource_definitions_in_multiple_roles,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            title: Test granular RBAC - groups in multiple roles: user can get correct hosts by ids
        """
        all_hosts = flatten(rbac_setup_resources_for_granular_rbac.host_groups)
        all_hosts_ids = [host.id for host in all_hosts]
        expected_hosts = (
            rbac_setup_resources_for_granular_rbac.host_groups[0]
            + rbac_setup_resources_for_granular_rbac.host_groups[1]
        )
        expected_hosts_ids = {host.id for host in expected_hosts}

        with raises_apierror(404, "One or more hosts not found."):
            host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(all_hosts_ids)

        response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(
            expected_hosts_ids
        )
        response_hosts_ids = {host.id for host in response.results}

        assert response.count == len(expected_hosts)
        assert response_hosts_ids == expected_hosts_ids

    def test_rbac_granular_hosts_multiple_roles_patch_host_display_name(
        self,
        setup_resource_definitions_in_multiple_roles,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-patch
            assignee: fstavela
            importance: high
            title: Test granular RBAC - groups in multiple roles: user can patch correct hosts
        """
        host1 = rbac_setup_resources_for_granular_rbac[0][0][0]
        host2 = rbac_setup_resources_for_granular_rbac[0][1][0]

        new_display_name = generate_display_name()
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            host1.id, display_name=new_display_name, wait_for_updated=False
        )
        host_inventory.apis.hosts.wait_for_updated(host1.id, display_name=new_display_name)

        new_display_name = generate_display_name()
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            host2.id, display_name=new_display_name, wait_for_updated=False
        )
        host_inventory.apis.hosts.wait_for_updated(host2.id, display_name=new_display_name)

        # Teardown
        host_inventory.apis.hosts.patch_hosts(host1.id, display_name=host1.display_name)
        host_inventory.apis.hosts.patch_hosts(host2.id, display_name=host2.display_name)

    def test_rbac_granular_hosts_multiple_roles_patch_host_display_name_wrong(
        self,
        setup_resource_definitions_in_multiple_roles,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-patch
            assignee: fstavela
            importance: high
            negative: true
            title: Test granular RBAC - groups in multiple roles: user can't patch incorrect hosts
        """
        host1 = rbac_setup_resources_for_granular_rbac[0][2][0]
        host2 = rbac_setup_resources_for_granular_rbac[0][3][0]

        new_display_name = generate_display_name()
        with raises_apierror(404, "One or more hosts not found."):
            host_inventory_non_org_admin.apis.hosts.patch_hosts(
                host1.id, display_name=new_display_name, wait_for_updated=False
            )

        with raises_apierror(404, "One or more hosts not found."):
            host_inventory_non_org_admin.apis.hosts.patch_hosts(
                host2.id, display_name=new_display_name, wait_for_updated=False
            )

        host_inventory.apis.hosts.verify_not_updated(
            host1.id, display_name=host1.display_name, retries=1
        )
        host_inventory.apis.hosts.verify_not_updated(
            host2.id, display_name=host2.display_name, retries=1
        )


@pytest.fixture(
    scope="class", params=["group.name", "host.id_with_host.id", "host.id_with_group.id"]
)
def setup_rbac_bad_key(
    request: pytest.FixtureRequest,
    rbac_setup_resources_for_granular_rbac: RBacResources,
    host_inventory: ApplicationHostInventory,
    hbi_non_org_admin_user_username: str,
):
    """Use wrong attributeFilter.key"""
    hbi_groups = [rbac_setup_resources_for_granular_rbac[1][0]]
    hosts = rbac_setup_resources_for_granular_rbac[0][0]
    host_inventory.apis.rbac.reset_user_groups(hbi_non_org_admin_user_username)

    group = host_inventory.apis.rbac.create_group(
        RBACInventoryPermission.ADMIN, hbi_groups=hbi_groups
    )
    host_inventory.apis.rbac.add_user_to_a_group(hbi_non_org_admin_user_username, group.uuid)

    key = request.param.split("-")[0]
    value = [host.id for host in hosts] if request.param == "host.id-with-host-id" else hbi_groups
    role = host_inventory.apis.rbac.create_role(
        RBACInventoryPermission.ADMIN, hbi_groups=value, key=key
    )
    host_inventory.apis.rbac.add_roles_to_a_group([role], group.uuid)

    yield

    host_inventory.apis.rbac.delete_role(role.uuid)
    host_inventory.apis.rbac.delete_group(group.uuid)


class TestRBACGranularBadAttributeFilter:
    def test_rbac_granular_groups_bad_attribute_filter_read_endpoint(
        self,
        setup_rbac_bad_key,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: medium
          negative: true
          title: Test that users with granular RBAC bad attributeFilter can't access groups
        """
        group = rbac_setup_resources_for_granular_rbac[1][0]

        with raises_apierror(503, "Invalid value for attributeFilter.key in RBAC response."):
            host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(group)

    def test_rbac_granular_groups_bad_attribute_filter_write_endpoint(
        self,
        setup_rbac_bad_key,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
          requirements: inv-groups-patch
          assignee: fstavela
          importance: medium
          negative: true
          title: Test that users with granular RBAC bad attributeFilter can't edit groups
        """
        group = rbac_setup_resources_for_granular_rbac[1][0]
        original_group_name = host_inventory.apis.groups.get_group_by_id(group).name
        new_group_name = generate_display_name()

        with raises_apierror(503, "Invalid value for attributeFilter.key in RBAC response."):
            host_inventory_non_org_admin.apis.groups.patch_group(
                group, name=new_group_name, wait_for_updated=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=original_group_name, retries=1)

    def test_rbac_granular_hosts_bad_attribute_filter_read_endpoint(
        self,
        setup_rbac_bad_key,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: medium
            negative: true
            title: Test that users with granular RBAC bad attributeFilter can't access hosts
        """
        hosts = rbac_setup_resources_for_granular_rbac[0][0]
        hosts_ids = [host.id for host in hosts]

        with raises_apierror(503, "Invalid value for attributeFilter.key in RBAC response."):
            host_inventory_non_org_admin.apis.hosts.get_hosts_by_id(hosts_ids)

    def test_rbac_granular_hosts_bad_attribute_filter_write_endpoint(
        self,
        setup_rbac_bad_key,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-patch
            assignee: fstavela
            importance: medium
            negative: true
            title: Test that users with granular RBAC bad attributeFilter can't edit hosts
        """
        host = rbac_setup_resources_for_granular_rbac[0][0][0]
        new_display_name = generate_display_name()
        with raises_apierror(503, "Invalid value for attributeFilter.key in RBAC response."):
            host_inventory_non_org_admin.apis.hosts.patch_hosts(
                host.id, display_name=new_display_name, wait_for_updated=False
            )

        host_inventory.apis.hosts.verify_not_updated(
            host.id, display_name=host.display_name, retries=1
        )
