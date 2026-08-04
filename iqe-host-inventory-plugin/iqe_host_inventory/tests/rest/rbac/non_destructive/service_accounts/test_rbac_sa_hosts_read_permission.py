# mypy: disallow-untyped-defs

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBACResources
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import assert_forbidden_response
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import get_default_operating_system
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
    pytest.mark.service_account,
    pytest.mark.usefixtures("hbi_secondary_upload_prepare_host_module"),
]


class TestRBACSAHostsReadPermission:
    def test_rbac_sa_hosts_read_permission_list_hosts(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_1: ApplicationHostInventory,
        hbi_secondary_upload_prepare_host_module: HostOut,
        hbi_default_org_id: str,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:read" permission can get a list of hosts
        """
        secondary_host = hbi_secondary_upload_prepare_host_module
        expected_hosts_ids = {host.id for host in flatten(rbac_setup_resources.hosts)}

        response = host_inventory_sa_1.apis.hosts.get_hosts()
        response_hosts_ids = {host.id for host in response}

        assert len(response) >= len(expected_hosts_ids)
        for host in response:
            assert host.org_id == hbi_default_org_id
        assert secondary_host.id not in response_hosts_ids
        assert expected_hosts_ids.issubset(response_hosts_ids)

    def test_rbac_sa_hosts_read_permission_get_host_by_id(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:read" permission can get hosts by IDs
        """
        expected_hosts_ids = {host.id for host in flatten(rbac_setup_resources.hosts)}

        response = host_inventory_sa_1.apis.hosts.get_hosts_by_id_response(
            list(expected_hosts_ids)
        )
        response_hosts_ids = {host.id for host in response.results}

        assert response.count == len(expected_hosts_ids)
        assert response_hosts_ids == expected_hosts_ids

    def test_rbac_sa_hosts_read_permission_get_host_system_profile(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:read" permission
                   can get a host's system profile by ID
        """
        expected_hosts_ids = {host.id for host in flatten(rbac_setup_resources.hosts)}

        response = host_inventory_sa_1.apis.hosts.get_hosts_system_profile_response(
            list(expected_hosts_ids)
        )
        response_hosts_ids = {host.id for host in response.results}

        assert response.count == len(expected_hosts_ids)
        assert response_hosts_ids == expected_hosts_ids
        for host in response.results:
            assert host.system_profile.operating_system.to_dict() == get_default_operating_system()

    def test_rbac_sa_hosts_read_permission_get_host_tags(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:read" permission can get host's tags
        """
        hosts_ids = [host.id for host in flatten(rbac_setup_resources.hosts)]
        tags = flatten(rbac_setup_resources.tags)

        response = host_inventory_sa_1.apis.hosts.get_host_tags_response(hosts_ids)

        assert response.count == len(hosts_ids)
        for i in range(len(hosts_ids)):
            assert len(response.results[hosts_ids[i]]) == len(tags[i])
            assert_tags_found(
                tags[i], response.results[hosts_ids[i]], check_api_response_count=False
            )

    def test_rbac_sa_hosts_read_permission_get_host_tags_count(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:read" permission
                   can get host's tags count
        """
        hosts_ids = [host.id for host in flatten(rbac_setup_resources.hosts)]
        tags = flatten(rbac_setup_resources.tags)

        response = host_inventory_sa_1.apis.hosts.get_host_tags_count_response(hosts_ids)

        assert response.count == len(hosts_ids)
        for i in range(len(hosts_ids)):
            assert response.results[hosts_ids[i]] == len(tags[i])

    def test_rbac_sa_hosts_read_permission_get_tags(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:read" permission can get a list of tags
        """
        tags = flatten(flatten(rbac_setup_resources.tags))

        response = host_inventory_sa_1.apis.tags.get_tags_json()

        assert response["count"] >= len(tags)
        assert_tags_found(tags, response["results"])

    def test_rbac_sa_hosts_read_permission_get_operating_systems(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:read" permission can get a list of OSs
        """
        hosts = flatten(rbac_setup_resources.hosts)

        response = host_inventory_sa_1.apis.system_profile.get_operating_systems_response()

        assert response.count >= 1
        assert len(response.results) >= 1

        my_os = next(
            res
            for res in response.results
            if res.value.to_dict() == get_default_operating_system()
        )
        assert my_os.value.to_dict() == get_default_operating_system()
        assert my_os.count >= len(hosts)

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_hosts_read_permission_get_sap_system(
        self,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:read" permission
                   can get a list of sap system values
        """
        response = host_inventory_sa_1.apis.system_profile.get_sap_systems_response()
        assert response.count == 0
        assert len(response.results) == 0

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_hosts_read_permission_get_sap_sids(
        self,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:read" permission
                   can get a list of SAP SIDs
        """
        response = host_inventory_sa_1.apis.system_profile.get_sap_sids_response()
        assert response.count == 0
        assert len(response.results) == 0

    def test_rbac_sa_hosts_read_permission_export_hosts(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_1: ApplicationHostInventory,
        hbi_secondary_upload_prepare_host_module: HostOut,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: msager
            importance: high
            title: Test that service accounts with "hosts:read" permission can export hosts
        """
        secondary_host = hbi_secondary_upload_prepare_host_module
        expected_hosts_ids = {host.id for host in flatten(rbac_setup_resources.hosts)}

        report = host_inventory_sa_1.apis.exports.export_hosts()
        exported_hosts_ids = {dict(host)["host_id"] for host in report}

        assert len(report) >= len(expected_hosts_ids)
        assert secondary_host.id not in exported_hosts_ids
        assert expected_hosts_ids.issubset(exported_hosts_ids)

    def test_rbac_sa_hosts_read_permission_get_host_exists(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: msager
            importance: high
            title: Test that service accounts with "hosts:read" permission can check
                a host's existence
        """
        all_hosts = flatten(rbac_setup_resources.hosts)
        insights_id = all_hosts[0].insights_id
        expected_host_id = all_hosts[0].id

        response = host_inventory_sa_1.apis.hosts.get_host_exists(insights_id)

        assert response.id == expected_host_id


class TestRBACSAHostsNoReadPermission:
    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_hosts_no_read_permission_list_hosts(
        self,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission
                   can't get a list of hosts
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.hosts.get_hosts()

    def test_rbac_sa_hosts_no_read_permission_get_host(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission
                   can't get hosts by IDs
        """
        hosts_ids = [host.id for host in flatten(rbac_setup_resources.hosts)]

        for host_id in hosts_ids:
            with raises_apierror(
                403,
                "You don't have the permission to access the requested resource. "
                "It is either read-protected or not readable by the server.",
            ):
                host_inventory_sa_2.apis.hosts.get_hosts_by_id(host_id)

    def test_rbac_sa_hosts_no_read_permission_get_host_system_profile(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission
                   can't get host's system profile by ID
        """
        hosts_ids = [host.id for host in flatten(rbac_setup_resources.hosts)]

        for host_id in hosts_ids:
            with raises_apierror(
                403,
                "You don't have the permission to access the requested resource. "
                "It is either read-protected or not readable by the server.",
            ):
                host_inventory_sa_2.apis.hosts.get_hosts_system_profile(host_id)

    def test_rbac_sa_hosts_no_read_permission_get_host_tags(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission can't get host's tags
        """
        hosts_ids = [host.id for host in flatten(rbac_setup_resources.hosts)]

        for host_id in hosts_ids:
            with raises_apierror(
                403,
                "You don't have the permission to access the requested resource. "
                "It is either read-protected or not readable by the server.",
            ):
                host_inventory_sa_2.apis.hosts.get_host_tags_response(host_id)

    def test_rbac_sa_hosts_no_read_permission_get_host_tags_count(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission
                   can't get host's tags count
        """
        hosts_ids = [host.id for host in flatten(rbac_setup_resources.hosts)]

        for host_id in hosts_ids:
            with raises_apierror(
                403,
                "You don't have the permission to access the requested resource. "
                "It is either read-protected or not readable by the server.",
            ):
                host_inventory_sa_2.apis.hosts.get_host_tags_count_response(host_id)

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_hosts_no_read_permission_get_tags(
        self,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission
                   can't get a list of tags
        """
        resp = host_inventory_sa_2.apis.tags.get_tags_response()
        assert_forbidden_response(resp)

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_hosts_no_read_permission_get_operating_systems(
        self,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission
                   can't get a list of operating systems
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.system_profile.get_operating_systems()

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_hosts_no_read_permission_get_sap_system(
        self,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission
                   can't get a list of SAP system values
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.system_profile.get_sap_systems()

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_hosts_no_read_permission_get_sap_sids(
        self,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission
                   can't get a list of SAP SIDs
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.system_profile.get_sap_sids()

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_hosts_no_read_permission_export_hosts(
        self,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891
        JIRA: https://issues.redhat.com/browse/RHINENG-11863

        metadata:

            assignee: msager
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission can't export hosts
        """
        host_inventory_sa_2.apis.exports.verify_access_denied()

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_hosts_no_read_permission_get_host_exists(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

            assignee: msager
            importance: high
            negative: true
            title: Test that service accounts without "hosts:read" permission can't check
                a host's existence
        """
        insights_id = flatten(rbac_setup_resources.hosts)[0].insights_id

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.hosts.get_host_exists(insights_id)
