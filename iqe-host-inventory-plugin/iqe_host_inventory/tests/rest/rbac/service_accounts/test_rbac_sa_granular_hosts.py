"""
metadata:
    requirements: inv-rbac-granular-groups
"""

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBacResources
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import raises_apierror

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent, pytest.mark.service_account]


@pytest.mark.usefixtures("rbac_setup_granular_hosts_permissions_for_sa")
class TestRBACSAGranularHosts:
    def test_rbac_sa_granular_hosts_permission_list_hosts(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_sa_2: ApplicationHostInventory,
        hbi_default_org_id: str,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-7891

        metadata:
            requirements: inv-hosts-get-list
            assignee: fstavela
            importance: high
            title: Test that service accounts with granular RBAC access
                   can get a correct list of hosts
        """
        expected_hosts = rbac_setup_resources_for_granular_rbac.host_groups[0]
        expected_hosts_ids = {host.id for host in expected_hosts}

        response = host_inventory_sa_2.apis.hosts.get_hosts()
        response_hosts_ids = {host.id for host in response}

        assert len(response) == len(expected_hosts)
        for host in response:
            assert host.org_id == hbi_default_org_id
        assert response_hosts_ids == expected_hosts_ids

    def test_rbac_sa_granular_hosts_permission_get_hosts_by_id(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_sa_2: ApplicationHostInventory,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-7891

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            title: Test that service accounts with granular RBAC access can get correct hosts by id
        """
        all_hosts = flatten(rbac_setup_resources_for_granular_rbac.host_groups)
        expected_hosts = rbac_setup_resources_for_granular_rbac.host_groups[0]
        expected_hosts_ids = {host.id for host in expected_hosts}

        response = host_inventory_sa_2.apis.hosts.get_hosts_by_id_response(all_hosts)
        response_hosts_ids = {host.id for host in response.results}

        assert response.count == len(expected_hosts)
        assert response_hosts_ids == expected_hosts_ids

    def test_rbac_sa_granular_hosts_permission_delete_host_by_id(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-7891

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            title: Test that service accounts with granular RBAC access
                   can delete correct hosts by IDs
        """
        correct_group = rbac_setup_resources_for_granular_rbac.groups[0]
        host = host_inventory.upload.create_host()
        host_inventory.apis.groups.add_hosts_to_group(correct_group, host)

        host_inventory_sa_2.apis.hosts.delete_by_id_raw(host)
        host_inventory.apis.hosts.wait_for_deleted(host)

    def test_rbac_sa_granular_hosts_permission_delete_host_by_id_wrong(
        self,
        rbac_setup_resources_for_granular_rbac: RBacResources,
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-7891

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts with granular RBAC access
                   can't delete incorrect hosts by IDs
        """
        host1 = rbac_setup_resources_for_granular_rbac.host_groups[2][0]
        host2 = rbac_setup_resources_for_granular_rbac.host_groups[3][0]

        with raises_apierror(404, "No hosts found for deletion."):
            host_inventory_sa_2.apis.hosts.delete_by_id_raw(host1)

        with raises_apierror(404, "No hosts found for deletion."):
            host_inventory_sa_2.apis.hosts.delete_by_id_raw(host2)

        host_inventory.apis.hosts.verify_not_deleted([host1, host2])
