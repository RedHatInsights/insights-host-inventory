"""
metadata:
    requirements: inv-rbac-granular-groups
"""

import logging
import operator
from os import getenv

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBacResources
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.api_utils import ungrouped_host_groups
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_default_operating_system
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
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
        lf("rbac_inventory_hosts_read_granular_user_setup_class"),
        lf("rbac_inventory_all_read_granular_user_setup_class"),
        lf("rbac_inventory_hosts_all_granular_user_setup_class"),
        lf("rbac_inventory_admin_granular_user_setup_class"),
    ],
    scope="class",
)
def read_permission_user_setup(request):
    return request.param


@pytest.fixture(
    params=[
        lf("rbac_inventory_hosts_write_granular_user_setup_class"),
        lf("rbac_inventory_hosts_all_granular_user_setup_class"),
        lf("rbac_inventory_admin_granular_user_setup_class"),
    ],
    scope="class",
)
def write_permission_user_setup(request):
    return request.param


@pytest.mark.usefixtures("read_permission_user_setup")
class TestRBACGranularHostsReadPermission:
    def test_rbac_granular_hosts_read_permission_list_hosts(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        hbi_non_org_admin_user_org_id,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-list
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can get a correct list of hosts
        """
        expected_hosts = (
            rbac_setup_resources_for_granular_rbac[0][0]
            + rbac_setup_resources_for_granular_rbac[0][1]
        )
        expected_hosts_ids = {host.id for host in expected_hosts}

        response = host_inventory_non_org_admin.apis.hosts.get_hosts_response()
        response_hosts_ids = {host.id for host in response.results}

        assert len(response.results) == len(expected_hosts)
        for result in response.results:
            assert result.org_id == hbi_non_org_admin_user_org_id
        assert response_hosts_ids == expected_hosts_ids

    def test_rbac_granular_hosts_read_permission_get_host(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can get correct hosts by ids
        """
        all_hosts = flatten(rbac_setup_resources_for_granular_rbac[0])
        all_hosts_ids = [host.id for host in all_hosts]
        expected_hosts = (
            rbac_setup_resources_for_granular_rbac[0][0]
            + rbac_setup_resources_for_granular_rbac[0][1]
        )
        expected_hosts_ids = {host.id for host in expected_hosts}

        with raises_apierror(404):
            host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(all_hosts_ids)

        response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(
            expected_hosts_ids
        )
        response_hosts_ids = {host.id for host in response.results}

        assert response.count == len(expected_hosts)
        assert response_hosts_ids == expected_hosts_ids

    def test_rbac_granular_hosts_read_permission_get_host_system_profile(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-system_profile
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can get correct system profiles
        """
        all_hosts = flatten(rbac_setup_resources_for_granular_rbac[0])
        all_hosts_ids = [host.id for host in all_hosts]
        expected_hosts = (
            rbac_setup_resources_for_granular_rbac[0][0]
            + rbac_setup_resources_for_granular_rbac[0][1]
        )
        expected_hosts_ids = {host.id for host in expected_hosts}

        with raises_apierror(404):
            host_inventory_non_org_admin.apis.hosts.get_hosts_system_profile_response(
                all_hosts_ids
            )
        response = host_inventory_non_org_admin.apis.hosts.get_hosts_system_profile_response(
            expected_hosts_ids
        )
        response_hosts_ids = {host.id for host in response.results}

        assert response.count == len(expected_hosts)
        assert response_hosts_ids == expected_hosts_ids
        for host in response.results:
            assert host.system_profile.operating_system.to_dict() == get_default_operating_system()

    def test_rbac_granular_hosts_read_permission_get_host_tags(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-tags
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can get correct host tags
        """
        all_hosts = flatten(rbac_setup_resources_for_granular_rbac[0])
        all_hosts_ids = [host.id for host in all_hosts]
        expected_hosts = (
            rbac_setup_resources_for_granular_rbac[0][0]
            + rbac_setup_resources_for_granular_rbac[0][1]
        )
        expected_hosts_ids = {host.id for host in expected_hosts}

        with raises_apierror(404):
            host_inventory_non_org_admin.apis.hosts.get_host_tags_response(all_hosts_ids)

        response = host_inventory_non_org_admin.apis.hosts.get_host_tags_response(
            expected_hosts_ids
        )

        assert response.count == len(expected_hosts)
        assert all(host_id in response.results for host_id in expected_hosts_ids)
        assert not any(
            host_id in response.results for host_id in (set(all_hosts_ids) - expected_hosts_ids)
        )

    def test_rbac_granular_hosts_read_permission_get_host_tags_count(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-tags-count
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can get correct host tags counts
        """
        all_hosts = flatten(rbac_setup_resources_for_granular_rbac[0])
        all_hosts_ids = [host.id for host in all_hosts]
        expected_hosts = (
            rbac_setup_resources_for_granular_rbac[0][0]
            + rbac_setup_resources_for_granular_rbac[0][1]
        )
        expected_hosts_ids = {host.id for host in expected_hosts}

        with raises_apierror(404):
            host_inventory_non_org_admin.apis.hosts.get_host_tags_count_response(all_hosts_ids)

        response = host_inventory_non_org_admin.apis.hosts.get_host_tags_count_response(
            all_hosts_ids
        )

        assert response.count == len(expected_hosts)
        assert all(host_id in response.results for host_id in expected_hosts_ids)
        assert not any(
            host_id in response.results for host_id in (set(all_hosts_ids) - expected_hosts_ids)
        )

    def test_rbac_granular_hosts_read_permission_get_tags(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory,
        host_inventory_non_org_admin,
    ):
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-tags-get-list
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can get correct tags
        """
        expected_hosts = (
            rbac_setup_resources_for_granular_rbac[0][0]
            + rbac_setup_resources_for_granular_rbac[0][1]
        )
        hosts_ids = [host.id for host in expected_hosts]

        tags_response = host_inventory.apis.hosts.get_host_tags_response(hosts_ids)
        expected_tags = flatten(tags_response.results[host_id] for host_id in hosts_ids)
        expected_dict_tags = sorted(
            [tag.to_dict() for tag in expected_tags], key=operator.itemgetter("key")
        )

        response = host_inventory_non_org_admin.apis.tags.get_tags_response()

        assert response.count == len(expected_dict_tags)
        for tag in response.results:
            assert tag.count == 1
        dict_tags = [tag.tag.to_dict() for tag in response.results]
        assert sorted(dict_tags, key=operator.itemgetter("key")) == expected_dict_tags

    def test_rbac_granular_hosts_read_permission_get_operating_systems(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can get correct operating systems
        """
        expected_hosts = (
            rbac_setup_resources_for_granular_rbac[0][0]
            + rbac_setup_resources_for_granular_rbac[0][1]
        )

        response = (
            host_inventory_non_org_admin.apis.system_profile.get_operating_systems_response()
        )

        assert response.count == 1
        assert len(response.results) == 1
        assert response.results[0].count == len(expected_hosts)
        assert response.results[0].value.to_dict() == get_default_operating_system()

    def test_rbac_granular_hosts_read_permission_get_sap_system(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can get correct sap system values
        """
        response = host_inventory_non_org_admin.apis.system_profile.get_sap_systems_response()
        assert response.count == 0
        assert len(response.results) == 0

    def test_rbac_granular_hosts_read_permission_get_sap_sids(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can get correct sap sids
        """
        response = host_inventory_non_org_admin.apis.system_profile.get_sap_sids_response()
        assert response.count == 0
        assert len(response.results) == 0

    def test_rbac_granular_hosts_read_permission_export_hosts(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        hbi_non_org_admin_user_org_id,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-11863

        metadata:
            requirements: inv-export-hosts
            assignee: msager
            importance: high
            title: Test that users with granular RBAC access can export only
                   hosts they have access to
        """
        expected_hosts = (
            rbac_setup_resources_for_granular_rbac[0][0]
            + rbac_setup_resources_for_granular_rbac[0][1]
        )
        expected_hosts_ids = {host.id for host in expected_hosts}

        report = host_inventory_non_org_admin.apis.exports.export_hosts()
        exported_hosts_ids = {host["host_id"] for host in report}

        assert len(exported_hosts_ids) == len(expected_hosts_ids)
        assert exported_hosts_ids == expected_hosts_ids

    def test_rbac_granular_hosts_read_permission_get_host_exists(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-host_exists-get-by-insights-id
            assignee: msager
            importance: high
            title: Test that users with granular RBAC access can check host existence
        """
        insights_id = rbac_setup_resources_for_granular_rbac[0][0][0].insights_id
        expected_host_id = rbac_setup_resources_for_granular_rbac[0][0][0].id

        response = host_inventory_non_org_admin.apis.hosts.get_host_exists(insights_id)

        assert response.id == expected_host_id

    def test_rbac_granular_hosts_read_permission_get_host_exists_without_access(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-host_exists-get-by-insights-id
            assignee: msager
            importance: high
            title: Test that users with granular RBAC access can't check host
                existence for a host they don't have access to.
        """
        insights_id = rbac_setup_resources_for_granular_rbac[0][2][0].insights_id

        with raises_apierror(404, match_message=f"No host found for Insights ID '{insights_id}'"):
            host_inventory_non_org_admin.apis.hosts.get_host_exists(insights_id)


@pytest.mark.usefixtures("write_permission_user_setup")
class TestRBACGranularHostsWritePermission:
    def test_rbac_granular_hosts_write_permission_delete_host_by_id(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can delete correct hosts by IDs
        """
        correct_groups = rbac_setup_resources_for_granular_rbac[1][:2]
        host1, host2 = host_inventory.upload.create_hosts(2)
        host_inventory.apis.groups.add_hosts_to_group(correct_groups[0], host1)
        host_inventory.apis.groups.add_hosts_to_group(correct_groups[1], host2)

        host_inventory_non_org_admin.apis.hosts.delete_by_id_raw(host1.id)
        host_inventory.apis.hosts.wait_for_deleted([host1])

        host_inventory_non_org_admin.apis.hosts.delete_by_id_raw(host2.id)
        host_inventory.apis.hosts.wait_for_deleted([host2])

    def test_rbac_granular_hosts_write_permission_delete_hosts_filtered(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-2218
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-delete-filtered-hosts
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC access can delete correct filtered hosts
        """
        correct_groups = rbac_setup_resources_for_granular_rbac[1][:2]
        incorrect_group = rbac_setup_resources_for_granular_rbac[1][2]
        prefix = f"iqe-hbi-delete-filtered_{generate_uuid()}"
        hosts_data = [HostData(display_name_prefix=prefix) for _ in range(4)]
        hosts = host_inventory.upload.create_hosts(hosts_data=hosts_data)
        host_inventory.apis.groups.add_hosts_to_group(correct_groups[0], hosts[0])
        host_inventory.apis.groups.add_hosts_to_group(correct_groups[1], hosts[1])
        host_inventory.apis.groups.add_hosts_to_group(incorrect_group, hosts[2])

        host_inventory_non_org_admin.apis.hosts.delete_filtered(
            display_name=prefix, wait_for_deleted=False
        )
        host_inventory.apis.hosts.verify_not_deleted(hosts[2:])
        host_inventory.apis.hosts.wait_for_deleted(hosts[:2])

    def test_rbac_granular_hosts_write_permission_patch_host_display_name(
        self,
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
            title: Test that users with granular RBAC access can patch correct hosts
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

    def test_rbac_granular_hosts_write_permission_delete_host_by_id_wrong(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            negative: true
            title: Test that users with granular RBAC access can't delete incorrect hosts by IDs
        """
        host1 = rbac_setup_resources_for_granular_rbac[0][2][0]
        host2 = rbac_setup_resources_for_granular_rbac[0][3][0]

        with raises_apierror(404, "One or more hosts not found."):
            host_inventory_non_org_admin.apis.hosts.delete_by_id_raw(host1.id)

        with raises_apierror(404, "One or more hosts not found."):
            host_inventory_non_org_admin.apis.hosts.delete_by_id_raw(host2.id)

        host_inventory.apis.hosts.verify_not_deleted([host1.id, host2.id])

    def test_rbac_granular_hosts_write_permission_patch_host_display_name_wrong(
        self,
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
            title: Test that users with granular RBAC access can't patch incorrect hosts
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

        host_inventory.apis.hosts.verify_not_updated(host1.id, display_name=host1.display_name)
        host_inventory.apis.hosts.verify_not_updated(host2.id, display_name=host2.display_name)


@pytest.fixture(
    params=[
        lf("rbac_inventory_hosts_read_granular_user_setup_class"),
        lf("rbac_inventory_groups_write_granular_user_setup_class"),
    ],
    scope="class",
)
def wrong_permission_setup_write_endpoints(request):
    return request.param


@pytest.fixture(
    params=[
        lf("rbac_inventory_hosts_write_granular_user_setup_class"),
        lf("rbac_inventory_groups_read_granular_user_setup_class"),
    ],
    scope="class",
)
def wrong_permission_setup_read_endpoints(request):
    return request.param


class TestRBACGranularHostsWrongPermissionWriteEndpoints:
    def test_rbac_granular_hosts_wrong_permission_delete_host(
        self,
        rbac_inventory_hosts_read_granular_user_setup_class,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            negative: true
            title: Test that users with granular RBAC on wrong permission can't delete hosts
        """
        host = rbac_setup_resources_for_granular_rbac[0][0][0]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.hosts.delete_by_id_raw(host.id)

        host_inventory.apis.hosts.verify_not_deleted(host.id, retries=1)

    def test_rbac_granular_hosts_wrong_permission_patch_host_display_name(
        self,
        rbac_inventory_hosts_read_granular_user_setup_class,
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
            title: Test that users with granular RBAC on wrong permission can't patch hosts
        """
        host = rbac_setup_resources_for_granular_rbac[0][0][0]

        new_display_name = generate_display_name()
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.hosts.patch_hosts(
                host.id, display_name=new_display_name, wait_for_updated=False
            )

        host_inventory.apis.hosts.verify_not_updated(
            host.id, display_name=host.display_name, retries=1
        )


class TestRBACGranularHostsWrongPermissionReadEndpoints:
    def test_rbac_granular_hosts_wrong_permission_list_hosts(
        self,
        rbac_inventory_hosts_write_granular_user_setup_class,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-list
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC on wrong permission can't get list of hosts
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.hosts.get_hosts()

    def test_rbac_granular_hosts_wrong_permission_get_host(
        self,
        rbac_inventory_hosts_write_granular_user_setup_class,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC on wrong permission can't get hosts by ids
        """
        host = rbac_setup_resources_for_granular_rbac[0][0][0]
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.hosts.get_host_by_id(host.id)

    def test_rbac_granular_hosts_wrong_permission_get_host_system_profile(
        self,
        rbac_inventory_hosts_write_granular_user_setup_class,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-system_profile
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC on wrong permission can't get system profiles
        """
        host = rbac_setup_resources_for_granular_rbac[0][0][0]
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.hosts.get_hosts_system_profile(host.id)

    def test_rbac_granular_hosts_wrong_permission_get_host_tags(
        self,
        rbac_inventory_hosts_write_granular_user_setup_class,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-tags
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC on wrong permission can't get tags
        """
        host = rbac_setup_resources_for_granular_rbac[0][0][0]
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.hosts.get_host_tags_response(host.id)

    def test_rbac_granular_hosts_wrong_permission_get_host_tags_count(
        self,
        rbac_inventory_hosts_write_granular_user_setup_class,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-hosts-get-tags-count
            assignee: fstavela
            importance: high
            title: Test that users with granular RBAC on wrong permission can't get tags counts
        """
        host = rbac_setup_resources_for_granular_rbac[0][0][0]
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.hosts.get_host_tags_count_response(host.id)

    def test_rbac_granular_hosts_wrong_permission_export_hosts(
        self,
        rbac_inventory_hosts_write_granular_user_setup_class,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-11863

        metadata:
            requirements: inv-export-hosts
            assignee: msager
            importance: high
            title: Test that users with granular RBAC on wrong permission can't export hosts
        """
        host_inventory_non_org_admin.apis.exports.verify_access_denied()

    def test_rbac_granular_hosts_wrong_permission_get_host_exists(
        self,
        rbac_inventory_hosts_write_granular_user_setup_class,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_non_org_admin,
    ):
        """
        metadata:
            requirements: inv-host_exists-get-by-insights-id
            assignee: msager
            importance: high
            title: Test that users with granular RBAC access on wrong permission can't
                check host existence
        """
        insights_id = rbac_setup_resources_for_granular_rbac[0][0][0].insights_id

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.hosts.get_host_exists(insights_id)


def test_rbac_granular_hosts_read_permission_single_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
        requirements: inv-hosts-get-by-id
        assignee: fstavela
        importance: high
        title: Test that users with granular RBAC single group can access correct hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_READ], hbi_groups=[groups[0]]
    )

    # Test
    hosts = flatten(rbac_setup_resources_for_granular_rbac[0])
    correct_hosts_ids = {host.id for host in rbac_setup_resources_for_granular_rbac[0][0]}

    with raises_apierror(404):
        host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(hosts)

    response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(correct_hosts_ids)
    response_hosts_ids = {host.id for host in response.results}
    assert response.count == len(correct_hosts_ids)
    assert response.total == len(correct_hosts_ids)
    assert response_hosts_ids == correct_hosts_ids


def test_rbac_granular_hosts_write_permission_single_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
        requirements: inv-hosts-patch
        assignee: fstavela
        importance: high
        title: Test that users with granular RBAC single group can edit correct hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=[groups[0]]
    )

    # Test
    host = rbac_setup_resources_for_granular_rbac[0][0][0]
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.hosts.patch_hosts(
        host.id, display_name=new_name, wait_for_updated=False
    )
    host_inventory.apis.hosts.wait_for_updated(host.id, display_name=new_name)

    # Teardown
    host_inventory.apis.hosts.patch_hosts(host.id, display_name=host.display_name)


def test_rbac_granular_hosts_read_permission_null_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
        requirements: inv-hosts-get-by-id
        assignee: fstavela
        importance: high
        title: Test that users with granular RBAC null group can access only not assigned hosts
    """
    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [ungrouped_groups[0]["id"]] if len(ungrouped_groups) > 0 else [None]

    # Setup
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_READ], hbi_groups=hbi_groups
    )

    # Test
    hosts = flatten(rbac_setup_resources_for_granular_rbac[0])
    correct_hosts_ids = {host.id for host in rbac_setup_resources_for_granular_rbac[0][3]}

    with raises_apierror(404):
        host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(hosts)

    response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(correct_hosts_ids)
    response_hosts_ids = {host.id for host in response.results}
    assert response.count == len(correct_hosts_ids)
    assert response.total == len(correct_hosts_ids)
    assert response_hosts_ids == correct_hosts_ids


def test_rbac_granular_hosts_write_permission_null_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
        requirements: inv-hosts-patch
        assignee: fstavela
        importance: high
        title: Test that users with granular RBAC null group can edit not assigned hosts
    """
    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [ungrouped_groups[0]["id"]] if len(ungrouped_groups) > 0 else [None]

    # Setup
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=hbi_groups
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


def test_rbac_granular_hosts_write_permission_null_group_wrong(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
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
        title: Test that users with granular RBAC null group can't edit assigned hosts
    """
    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [ungrouped_groups[0]["id"]] if len(ungrouped_groups) > 0 else [None]

    # Setup
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=hbi_groups
    )

    # Test
    host = rbac_setup_resources_for_granular_rbac[0][2][0]
    new_name = generate_display_name()
    with raises_apierror(404, "One or more hosts not found."):
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            host.id, display_name=new_name, wait_for_updated=False
        )
    host_inventory.apis.hosts.verify_not_updated(host.id, display_name=host.display_name)


def test_rbac_granular_hosts_read_permission_null_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
        requirements: inv-hosts-get-by-id
        assignee: fstavela
        importance: high
        title: Test that users with granular RBAC null and normal group can access correct hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac.groups

    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [groups[0], ungrouped_groups[0]["id"] if len(ungrouped_groups) > 0 else None]

    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_READ], hbi_groups=hbi_groups
    )

    # Test
    hosts = flatten(rbac_setup_resources_for_granular_rbac.host_groups)
    correct_hosts_ids = {
        host.id
        for host in rbac_setup_resources_for_granular_rbac[0][0]
        + rbac_setup_resources_for_granular_rbac[0][3]
    }

    with raises_apierror(404):
        host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(hosts)

    response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(correct_hosts_ids)
    response_hosts_ids = {host.id for host in response.results}
    assert response.count == len(correct_hosts_ids)
    assert response.total == len(correct_hosts_ids)
    assert response_hosts_ids == correct_hosts_ids


def test_rbac_granular_hosts_write_permission_null_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
        requirements: inv-hosts-patch
        assignee: fstavela
        importance: high
        title: Test that users with granular RBAC null and normal group can edit correct hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]

    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [groups[0], ungrouped_groups[0]["id"] if len(ungrouped_groups) > 0 else None]

    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=hbi_groups
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


def test_rbac_granular_hosts_write_permission_null_and_normal_group_wrong(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
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
        title: Test that users with granular RBAC null and normal group can't edit incorrect hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]

    ungrouped_groups = ungrouped_host_groups(host_inventory)
    hbi_groups = [groups[0], ungrouped_groups[0]["id"] if len(ungrouped_groups) > 0 else None]

    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=hbi_groups
    )

    # Test
    host = rbac_setup_resources_for_granular_rbac[0][2][0]
    new_name = generate_display_name()
    with raises_apierror(404, "One or more hosts not found."):
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            host.id, display_name=new_name, wait_for_updated=False
        )
    host_inventory.apis.hosts.verify_not_updated(host.id, display_name=host.display_name)
