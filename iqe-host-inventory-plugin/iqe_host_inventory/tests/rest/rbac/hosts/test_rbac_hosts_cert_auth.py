"""
metadata:
  requirements: inv-rbac-cert-auth-bypass
"""

import logging
import operator

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_default_operating_system
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent, pytest.mark.cert_auth]


@pytest.mark.usefixtures("rbac_inventory_user_without_permissions_setup_class")
class TestRBACHostsCertAuth:
    def test_rbac_hosts_cert_auth_bypass_checks_list_hosts(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
        hbi_non_org_admin_user_org_id,
    ):
        """
        Test response when a cert-auth client tries to list hosts via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8950

        1. Create a new host
        2. Issue a GET request on /hosts resource using the cert-auth client associated
           to a user who doesn't have any permission
        3. Ensure GET request returns a 200 response with a list of hosts associated
           with the user's org_id

        metadata:
            requirements: inv-hosts-get-list
            assignee: fstavela
            importance: high
            title: Inventory: Confirm cert-auth clients bypass RBAC checks when listing hosts
        """
        expected_hosts_ids = {host.id for host in rbac_cert_auth_setup_resources[0]}

        response = host_inventory_non_org_admin_cert_auth.apis.hosts.get_hosts_response()
        response_hosts_ids = {host.id for host in response.results}

        assert len(response.results) >= 2
        for result in response.results:
            assert result.org_id == hbi_non_org_admin_user_org_id
        assert expected_hosts_ids.issubset(response_hosts_ids)

    def test_rbac_hosts_cert_auth_bypass_checks_get_host(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
    ):
        """
        Test response when a cert-auth client tries to access host details via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8950

        1. Create a new host
        2. Issue a GET request on /hosts/{uuid} resource using the cert-auth client associated
           to a user who doesn't have any permission
        3. Ensure GET request returns a 200 response with the host details

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            title: Inventory: Confirm cert-auth clients bypass RBAC checks when getting host details
        """  # NOQA: E501
        expected_hosts_ids = {host.id for host in rbac_cert_auth_setup_resources[0]}

        response = host_inventory_non_org_admin_cert_auth.apis.hosts.get_hosts_by_id_response(
            list(expected_hosts_ids)
        )
        response_hosts_ids = {host.id for host in response.results}

        assert response.count == 2
        assert response_hosts_ids == expected_hosts_ids

    def test_rbac_hosts_cert_auth_bypass_checks_get_host_system_profile(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
    ):
        """
        Test response when a cert-auth client tries to access host system profile facts
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8950

        1. Create a new host with system profile facts
        2. Issue a GET request on /hosts/{uuid}/system_profile resource using
           the cert-auth client associated to a user who doesn't have any permission
        3. Ensure GET request returns a 200 response with the host system profile facts

        metadata:
            requirements: inv-hosts-get-system_profile
            assignee: fstavela
            importance: high
            title: Inventory: Confirm cert-auth clients bypass RBAC checks when getting
                host system profile facts
        """
        expected_hosts_ids = {host.id for host in rbac_cert_auth_setup_resources[0]}

        response = (
            host_inventory_non_org_admin_cert_auth.apis.hosts.get_hosts_system_profile_response(
                list(expected_hosts_ids)
            )
        )
        response_hosts_ids = {host.id for host in response.results}

        assert response.count == 2
        assert response_hosts_ids == expected_hosts_ids
        for host in response.results:
            assert host.system_profile.operating_system.to_dict() == get_default_operating_system()

    def test_rbac_hosts_cert_auth_bypass_checks_get_host_tags(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
    ):
        """
        Test response when a cert-auth client tries to access host tags via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8950

        1. Create a new host with tags
        2. Issue a GET request on /hosts/{uuid}/tags resource using the cert-auth client associated
           to a user who doesn't have any permission
        3. Ensure GET request returns a 200 response with the host tags

        metadata:
            requirements: inv-hosts-get-tags
            assignee: fstavela
            importance: high
            title: Inventory: Confirm cert-auth clients bypass RBAC checks when getting host tags
        """
        hosts_ids = [host.id for host in rbac_cert_auth_setup_resources[0]]

        response = host_inventory_non_org_admin_cert_auth.apis.hosts.get_host_tags_response(
            hosts_ids
        )

        assert response.count == 2
        dict_tags = [tag.to_dict() for tag in response.results[hosts_ids[0]]]
        assert sorted(dict_tags, key=operator.itemgetter("key")) == sorted(
            rbac_cert_auth_setup_resources[2][0], key=operator.itemgetter("key")
        )
        dict_tags = [tag.to_dict() for tag in response.results[hosts_ids[1]]]
        assert sorted(dict_tags, key=operator.itemgetter("key")) == sorted(
            rbac_cert_auth_setup_resources[2][1], key=operator.itemgetter("key")
        )

    def test_rbac_hosts_cert_auth_bypass_checks_get_host_tags_count(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
    ):
        """
        Test response when a cert-auth client tries to access host tags count via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8950

        1. Create a new host with tags
        2. Issue a GET request on /hosts/{uuid}/tags/count resource using the
           cert-auth client associated to a user who doesn't have any permission
        3. Ensure GET request returns a 200 response with the host tags count

        metadata:
            requirements: inv-hosts-get-tags-count
            assignee: fstavela
            importance: high
            title: Test that RBAC is ignored for getting host tags count with cert auth
        """
        hosts_ids = [host.id for host in rbac_cert_auth_setup_resources[0]]

        response = host_inventory_non_org_admin_cert_auth.apis.hosts.get_host_tags_count_response(
            hosts_ids
        )

        assert response.count == 2
        assert response.results[hosts_ids[0]] == len(rbac_cert_auth_setup_resources[2][0])
        assert response.results[hosts_ids[1]] == len(rbac_cert_auth_setup_resources[2][1])

    def test_rbac_hosts_cert_auth_bypass_checks_get_tags(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
    ):
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-tags-get-list
            assignee: fstavela
            importance: high
            title: Test that RBAC is ignored for getting tags with cert auth
        """
        tags = sorted(flatten(rbac_cert_auth_setup_resources[2]), key=operator.itemgetter("key"))

        response = host_inventory_non_org_admin_cert_auth.apis.tags.get_tags_response()

        assert response.count == len(tags)
        for tag in response.results:
            assert tag.count == 1
        dict_tags = [tag.tag.to_dict() for tag in response.results]
        assert sorted(dict_tags, key=operator.itemgetter("key")) == tags

    def test_rbac_hosts_cert_auth_bypass_checks_get_operating_systems(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
    ):
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            title: Test that RBAC is ignored for getting operating systems with cert auth
        """
        hosts = rbac_cert_auth_setup_resources[0]

        response = host_inventory_non_org_admin_cert_auth.apis.system_profile.get_operating_systems_response()  # noqa

        assert response.count == 1
        assert len(response.results) == 1
        assert response.results[0].count == len(hosts)
        assert response.results[0].value.to_dict() == get_default_operating_system()

    def test_rbac_hosts_cert_auth_bypass_checks_get_sap_system(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
    ):
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            title: Test that RBAC is ignored for getting sap system values with cert auth
        """
        response = (
            host_inventory_non_org_admin_cert_auth.apis.system_profile.get_sap_systems_response()
        )
        assert response.count == 0
        assert len(response.results) == 0

    def test_rbac_hosts_cert_auth_bypass_checks_get_sap_sids(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
    ):
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            title: Test that RBAC is ignored for getting sap sids with cert auth
        """
        response = (
            host_inventory_non_org_admin_cert_auth.apis.system_profile.get_sap_sids_response()
        )
        assert response.count == 0
        assert len(response.results) == 0

    def test_rbac_hosts_cert_auth_bypass_checks_export_hosts(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
    ):
        """
        Test response when a cert-auth client tries to export hosts

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8950
              https://projects.engineering.redhat.com/browse/RHCLOUD-34803

        1. Create a couple hosts
        2. Perform an export using the cert-auth client associated to a user
           who doesn't have any permission
        3. Ensure the export completes successfully

        metadata:
            requirements: inv-export-hosts
            assignee: msager
            importance: high
            title: Inventory: Confirm cert-auth clients bypass RBAC checks when exporting hosts
        """
        expected_hosts_ids = {host.id for host in rbac_cert_auth_setup_resources[0]}

        report = host_inventory_non_org_admin_cert_auth.apis.exports.export_hosts()
        exported_hosts_ids = {host["host_id"] for host in report}

        assert len(report) >= len(expected_hosts_ids)
        assert expected_hosts_ids.issubset(exported_hosts_ids)

    def test_rbac_hosts_cert_auth_bypass_checks_get_host_exists(
        self,
        rbac_cert_auth_setup_resources,
        host_inventory_non_org_admin_cert_auth,
    ):
        """
        Test response when a cert-auth client tries to check a host's existence via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8950

        1. Create a new host
        2. Issue a GET request on /host_exists using the cert-auth client associated
           to a user who doesn't have any permission
        3. Ensure GET request returns a 200 response with the host id

        metadata:
            requirements: inv-host_exists-get-by-insights-id
            assignee: msager
            importance: high
            title: Inventory: Confirm cert-auth clients bypass RBAC checks when checking
                host's existence
        """
        insights_id = rbac_cert_auth_setup_resources[0][0].insights_id
        expected_host_id = rbac_cert_auth_setup_resources[0][0].id

        response_host_id = host_inventory_non_org_admin_cert_auth.apis.hosts.get_host_exists(
            insights_id
        ).id

        assert response_host_id == expected_host_id

    def test_rbac_hosts_cert_auth_bypass_checks_delete_host(
        self,
        rbac_cert_auth_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
    ):
        """
        Test response when a cert-auth client tries to delete a host via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8950

        1. Create a new host
        2. Issue a DELETE request on /hosts/{uuid} to delete the host using the
           cert-auth client associated to a user who doesn't have any permission
        3. Ensure DELETE request returns a 200 response
        4. Issue a GET request to check if the host was successfully deleted
        5. Ensure GET request returns a 404 response

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            title: Inventory: Confirm cert-auth clients bypass RBAC checks when deleting hosts
        """
        group = rbac_cert_auth_setup_resources[1][0]
        host1, host2 = host_inventory_non_org_admin_cert_auth.upload.create_hosts(2)
        host_inventory.apis.groups.add_hosts_to_group(group, host1)

        host_inventory_non_org_admin_cert_auth.apis.hosts.delete_by_id_raw([
            host1.id,
            host2.id,
        ])
        host_inventory.apis.hosts.wait_for_deleted([host1, host2])

    def test_rbac_hosts_cert_auth_bypass_checks_delete_hosts_filtered(
        self,
        rbac_cert_auth_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-2218

        metadata:
            requirements: inv-hosts-delete-filtered-hosts
            assignee: fstavela
            importance: high
            title: Test that RBAC is ignored for deleting filtered hosts with cert auth
        """
        group = rbac_cert_auth_setup_resources[1][0]
        prefix = f"iqe-hbi-delete-filtered_{generate_uuid()}"
        hosts_data = [HostData(display_name_prefix=prefix) for _ in range(2)]
        host1, host2 = host_inventory_non_org_admin_cert_auth.upload.create_hosts(
            hosts_data=hosts_data
        )
        host_inventory.apis.groups.add_hosts_to_group(group, host1)

        host_inventory_non_org_admin_cert_auth.apis.hosts.delete_filtered(display_name=prefix)
        host_inventory.apis.hosts.wait_for_deleted([host1, host2])

    def test_rbac_hosts_cert_auth_bypass_checks_patch_host_display_name(
        self,
        rbac_cert_auth_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
    ):
        """
        Test response when a cert-auth client tries to update host's display_name
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8950

        1. Create a new host
        2. Issue a PATCH request on /hosts/{uuid} to update host's display_name using the
           cert-auth client associated to a user who doesn't have any permission
        3. Ensure PATCH request returns a 200 response
        4. Issue a GET request to check if the host was updated
        5. Ensure GET request returns a 200 and the display name is updated

        metadata:
            requirements: inv-hosts-patch
            assignee: fstavela
            importance: high
            title: Inventory: Confirm cert-auth clients bypass RBAC checks when updating
                host's display_name
        """
        group = rbac_cert_auth_setup_resources[1][0]
        host1, host2 = host_inventory_non_org_admin_cert_auth.upload.create_hosts(2)
        host_inventory.apis.groups.add_hosts_to_group(group, host1)

        new_display_name = generate_display_name()
        host_inventory_non_org_admin_cert_auth.apis.hosts.patch_hosts(
            host1.id, display_name=new_display_name, wait_for_updated=False
        )
        host_inventory.apis.hosts.wait_for_updated(host1.id, display_name=new_display_name)
        host_inventory_non_org_admin_cert_auth.apis.hosts.wait_for_updated(
            host1.id, display_name=new_display_name
        )

        new_display_name = generate_display_name()
        host_inventory_non_org_admin_cert_auth.apis.hosts.patch_hosts(
            host2.id, display_name=new_display_name, wait_for_updated=False
        )
        host_inventory.apis.hosts.wait_for_updated(host2.id, display_name=new_display_name)
        host_inventory_non_org_admin_cert_auth.apis.hosts.wait_for_updated(
            host2.id, display_name=new_display_name
        )


def test_rbac_hosts_cert_auth_different_certificate(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
):
    """
    Test response when a cert-auth client tries to get host created with different certificate

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8950

    metadata:
        requirements: inv-api-cert-auth
        assignee: fstavela
        importance: high
        title: Inventory: Test cert-auth different certificates
    """
    host = host_inventory_non_org_admin_cert_auth.upload.create_host()

    response = host_inventory_cert_auth.apis.hosts.get_hosts_response()
    assert response.count == 0

    with raises_apierror((403, 404)):
        host_inventory_cert_auth.apis.hosts.get_hosts_by_id_response(host.id)


def test_rbac_granular_hosts_cert_auth_bypass_checks_get_host(
    hbi_non_org_admin_user_rbac_setup,
    rbac_cert_auth_setup_resources,
    host_inventory_non_org_admin_cert_auth,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:
        requirements: inv-hosts-get-by-id, inv-rbac-cert-auth-bypass
        assignee: fstavela
        importance: high
        title: Test that granular RBAC is ignored on Hosts endpoints with cert auth
    """
    # Setup
    groups = rbac_cert_auth_setup_resources[1]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_READ], hbi_groups=[groups[0]]
    )
    expected_hosts_ids = {host.id for host in rbac_cert_auth_setup_resources[0]}

    # Test
    response = host_inventory_non_org_admin_cert_auth.apis.hosts.get_hosts_by_id_response(
        list(expected_hosts_ids)
    )
    response_hosts_ids = {host.id for host in response.results}

    assert response.count == len(expected_hosts_ids)
    assert response_hosts_ids == expected_hosts_ids
