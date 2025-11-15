# mypy: disallow-untyped-defs

"""
metadata:
    requirements: inv-rbac
"""

import logging
import operator

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import get_default_operating_system
from iqe_host_inventory_api import ApiException
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent]


@pytest.fixture(
    params=[
        lf("rbac_inventory_hosts_read_user_setup_class"),
        lf("rbac_inventory_all_read_user_setup_class"),
        lf("rbac_inventory_hosts_all_user_setup_class"),
        lf("rbac_inventory_admin_user_setup_class"),
    ],
    scope="class",
)
def read_permission_user_setup(request: pytest.FixtureRequest) -> None:
    return request.param


@pytest.fixture(
    params=[
        lf("rbac_inventory_groups_read_user_setup_class"),
        lf("rbac_inventory_groups_write_user_setup_class"),
        lf("rbac_inventory_groups_all_user_setup_class"),
        lf("rbac_inventory_hosts_write_user_setup_class"),
        lf("rbac_inventory_user_without_permissions_setup_class"),
    ],
    scope="class",
)
def no_read_permission_user_setup(request: pytest.FixtureRequest) -> None:
    return request.param


@pytest.mark.usefixtures("read_permission_user_setup")
class TestRBACHostsReadPermission:
    def test_rbac_hosts_read_permission_list_hosts(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
        hbi_non_org_admin_user_org_id: str,
    ) -> None:
        """
        Test response when a user who has "read" permission tries to list hosts via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8535
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host
        2. Ensure the host is successfully created
        3. Issue a GET request on /hosts resource using the user who has "read" permission
        4. Ensure GET request returns a 200 response with a list of hosts associated
           with the user's org_id

        metadata:
            requirements: inv-hosts-get-list
            assignee: fstavela
            importance: high
            title: Inventory: Confirm users who have "read" permission have access to list hosts
        """
        expected_hosts_ids = {host.id for host in rbac_setup_resources[0]}

        response = host_inventory_non_org_admin.apis.hosts.get_hosts_response()
        response_hosts_ids = {host.id for host in response.results}

        assert len(response.results) >= 2
        for result in response.results:
            assert result.org_id == hbi_non_org_admin_user_org_id
        assert expected_hosts_ids.issubset(response_hosts_ids)

    def test_rbac_hosts_read_permission_get_host(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who has "read" permission tries to access host details
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8535
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host
        2. Ensure the host is successfully created
        3. Issue a GET request on /hosts/{uuid} resource using the user who has "read" permission
        4. Ensure GET request returns a 200 response with the host details

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            title: Inventory: Confirm users who have "read" permission have access to host details
        """
        expected_hosts_ids = {host.id for host in rbac_setup_resources[0]}

        response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(
            list(expected_hosts_ids)
        )
        response_hosts_ids = {host.id for host in response.results}

        assert response.count == 2
        assert response_hosts_ids == expected_hosts_ids

    def test_rbac_hosts_read_permission_get_host_system_profile(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who has "read" permission tries to access host system profile
        facts via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8535
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host with system profile facts
        2. Ensure the host is successfully created
        3. Issue a GET request on /hosts/{uuid}/system_profile resource using the user
           who has "read" permission
        4. Ensure GET request returns a 200 response with the host system profile facts

        metadata:
            requirements: inv-hosts-get-system_profile
            assignee: fstavela
            importance: high
            title: Inventory: Confirm users who have "read" permission have access to
                host system profile facts
        """
        expected_hosts_ids = {host.id for host in rbac_setup_resources[0]}

        response = host_inventory_non_org_admin.apis.hosts.get_hosts_system_profile_response(
            list(expected_hosts_ids)
        )
        response_hosts_ids = {host.id for host in response.results}

        assert response.count == 2
        assert response_hosts_ids == expected_hosts_ids
        for host in response.results:
            assert host.system_profile.operating_system.to_dict() == get_default_operating_system()

    def test_rbac_hosts_read_permission_get_host_tags(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who has "read" permission tries to access host tags
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8535
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host with tags
        2. Ensure the host is successfully created
        3. Issue a GET request on /hosts/{uuid}/tags resource using the user who has
           "read" permission
        4. Ensure GET request returns a 200 response with the host tags

        metadata:
            requirements: inv-hosts-get-tags
            assignee: fstavela
            importance: high
            title: Inventory: Confirm users who have "read" permission have access to host tags
        """
        hosts_ids = [host.id for host in rbac_setup_resources[0]]

        response = host_inventory_non_org_admin.apis.hosts.get_host_tags_response(hosts_ids)

        assert response.count == 2
        dict_tags = [tag.to_dict() for tag in response.results[hosts_ids[0]]]
        assert sorted(dict_tags, key=operator.itemgetter("key")) == sorted(
            rbac_setup_resources[2][0], key=operator.itemgetter("key")
        )
        dict_tags = [tag.to_dict() for tag in response.results[hosts_ids[1]]]
        assert sorted(dict_tags, key=operator.itemgetter("key")) == sorted(
            rbac_setup_resources[2][1], key=operator.itemgetter("key")
        )

    def test_rbac_hosts_read_permission_get_host_tags_count(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who has "read" permission tries to access host tags count
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8535
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host with tags
        2. Ensure the host is successfully created
        3. Issue a GET request on /hosts/{uuid}/tags/count resource using the user
           who has "read" permission
        4. Ensure GET request returns a 200 response with the host tags count

        metadata:
            requirements: inv-hosts-get-tags-count
            assignee: fstavela
            importance: high
            title: Inventory: Confirm users with "read" permission have access to host tags count
        """
        hosts_ids = [host.id for host in rbac_setup_resources[0]]

        response = host_inventory_non_org_admin.apis.hosts.get_host_tags_count_response(hosts_ids)

        assert response.count == 2
        assert response.results[hosts_ids[0]] == len(rbac_setup_resources[2][0])
        assert response.results[hosts_ids[1]] == len(rbac_setup_resources[2][1])

    def test_rbac_hosts_read_permission_get_tags(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-tags-get-list
            assignee: fstavela
            importance: high
            title: Inventory: Confirm users who have "read" permission have access to tags
        """
        tags = sorted(flatten(rbac_setup_resources[2]), key=operator.itemgetter("key"))

        response = host_inventory_non_org_admin.apis.tags.get_tags_response()

        assert response.count == len(tags)
        for tag in response.results:
            assert tag.count == 1
        dict_tags = [tag.tag.to_dict() for tag in response.results]
        assert sorted(dict_tags, key=operator.itemgetter("key")) == tags

    def test_rbac_hosts_read_permission_get_operating_systems(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            title: Test that users with "hosts:read" permission can get a list of operating systems
        """
        hosts = rbac_setup_resources[0]

        response = (
            host_inventory_non_org_admin.apis.system_profile.get_operating_systems_response()
        )

        assert response.count == 1
        assert len(response.results) == 1
        assert response.results[0].count == len(hosts)
        assert response.results[0].value.to_dict() == get_default_operating_system()

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_hosts_read_permission_get_sap_system(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            title: Test that users with "hosts:read" permission can get a list of sap system values
        """
        response = host_inventory_non_org_admin.apis.system_profile.get_sap_systems_response()
        assert response.count == 0
        assert len(response.results) == 0

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_hosts_read_permission_get_sap_sids(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            title: Test that users with "hosts:read" permission can get a list of sap sids
        """
        response = host_inventory_non_org_admin.apis.system_profile.get_sap_sids_response()
        assert response.count == 0
        assert len(response.results) == 0

    def test_rbac_hosts_read_permission_export_hosts(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who has "read" permission tries to export hosts via REST API

        1. Create some hosts
        2. Perform a host export as the user who has "read" permission
        3. Verify that the export succeeds

        metadata:
            requirements: inv-export-hosts
            assignee: msager
            importance: high
            title: Inventory: Confirm users who have "read" permission are able to export hosts
        """
        expected_hosts_ids = {host.id for host in rbac_setup_resources[0]}

        report: list[dict] = host_inventory_non_org_admin.apis.exports.export_hosts()  # type: ignore[assignment]
        exported_hosts_ids = {host["host_id"] for host in report}

        assert len(report) >= len(expected_hosts_ids)
        assert expected_hosts_ids.issubset(exported_hosts_ids)

    def test_rbac_hosts_read_permission_get_host_exists(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who has "read" permission checks to see if a
        host exists via REST API

        1. Create a new host
        2. Ensure the host is successfully created
        3. Issue a GET request on /host_exists using the user who has "read" permission
        4. Ensure GET request returns a 200 response with the host id

        metadata:
            requirements: inv-host_exists-get-by-insights-id
            assignee: msager
            importance: high
            title: Confirm users who have "read" permission can check for host existence
        """
        insights_id = rbac_setup_resources[0][0].insights_id
        expected_host_id = rbac_setup_resources[0][0].id

        response = host_inventory_non_org_admin.apis.hosts.get_host_exists(insights_id)

        assert response.id == expected_host_id


@pytest.mark.usefixtures("no_read_permission_user_setup")
class TestRBACHostsNoReadPermission:
    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_hosts_no_read_permission_list_hosts(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who doesn't have "read" permission tries to list hosts
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8535
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host
        2. Ensure the host is successfully created
        3. Issue a GET request on /hosts resource using the user who doesn't have "read" permission
        4. Ensure GET request returns a 403 response

        metadata:
            requirements: inv-hosts-get-list
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users who don't have "read" permission don't have
                access to list hosts
        """
        with pytest.raises(ApiException) as err:
            host_inventory_non_org_admin.apis.hosts.get_hosts_response()

        assert err.value.status == 403

    def test_rbac_hosts_no_read_permission_get_host(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who doesn't have "read" permission tries to access host details
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8535
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host
        2. Ensure the host is successfully created
        3. Issue a GET request on /hosts/{uuid} resource using the user
        who doesn't have "read" permission
        4. Ensure GET request returns a 403 response

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users who don't have "read" permission don't have access
                to host details
        """
        hosts_ids = [host.id for host in rbac_setup_resources[0]]

        for host_id in hosts_ids:
            with pytest.raises(ApiException) as err:
                host_inventory_non_org_admin.apis.hosts.get_hosts_by_id(host_id)
            assert err.value.status == 403

    def test_rbac_hosts_no_read_permission_get_host_system_profile(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who doesn't have "read" permission tries to access
        host system profile facts via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8535
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host with system profile facts
        2. Ensure the host is successfully created
        3. Issue a GET request on /hosts/{uuid}/system_profile resource using the user
           who doesn't have "read" permission
        4. Ensure GET request returns a 403 response

        metadata:
            requirements: inv-hosts-get-system_profile
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users who don't have "read" permission don't have access to
                host system profile facts
        """
        hosts_ids = [host.id for host in rbac_setup_resources[0]]

        for host_id in hosts_ids:
            with pytest.raises(ApiException) as err:
                host_inventory_non_org_admin.apis.hosts.get_hosts_system_profile(host_id)

            assert err.value.status == 403

    def test_rbac_hosts_no_read_permission_get_host_tags(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who doesn't have "read" permission tries to access host tags
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8535
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host with tags
        2. Ensure the host is successfully created
        3. Issue a GET request on /hosts/{uuid}/tags resource using the user
        who doesn't have "read" permission
        4. Ensure GET request returns a 403 response

        metadata:
            requirements: inv-hosts-get-tags
            assignee: fstavela
            importance: high
            negative: true
            title: Confirm users without "read" permission don't have access to host tags
        """
        hosts_ids = [host.id for host in rbac_setup_resources[0]]

        for host_id in hosts_ids:
            with pytest.raises(ApiException) as err:
                host_inventory_non_org_admin.apis.hosts.get_host_tags_response(host_id)
            assert err.value.status == 403

    def test_rbac_hosts_no_read_permission_get_host_tags_count(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who doesn't have "read" permission tries to access
        host tags count via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8535
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host with tags
        2. Ensure the host is successfully created
        3. Issue a GET request on /hosts/{uuid}/tags/count resource using the user
           who doesn't have "read" permission
        4. Ensure GET request returns a 403 response

        metadata:
            requirements: inv-hosts-get-tags-count
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users who don't have "read" permission don't have access
                to host tags count
        """
        hosts_ids = [host.id for host in rbac_setup_resources[0]]

        for host_id in hosts_ids:
            with pytest.raises(ApiException) as err:
                host_inventory_non_org_admin.apis.hosts.get_host_tags_count_response(host_id)
            assert err.value.status == 403

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_hosts_no_read_permission_get_tags(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-tags-get-list
            assignee: fstavela
            importance: high
            negative: true
            title: Test that users without "hosts:read" permission can't get tags
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.tags.get_tags()

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_hosts_no_read_permission_get_operating_systems(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            negative: true
            title: Test that users without "hosts:read" permission can't get operating systems
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.system_profile.get_operating_systems()

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_hosts_no_read_permission_get_sap_system(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            negative: true
            title: Test that users without "hosts:read" permission can't get sap system values
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.system_profile.get_sap_systems()

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_hosts_no_read_permission_get_sap_sids(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """

        https://issues.redhat.com/browse/ESSNTL-4961

        metadata:
            requirements: inv-system_profile-operating_system
            assignee: fstavela
            importance: high
            negative: true
            title: Test that users without "hosts:read" permission can't get a list of sap sids
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.system_profile.get_sap_sids()

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_hosts_no_read_permission_export_hosts(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/RHINENG-11863

        metadata:
            requirements: inv-export-hosts
            assignee: msager
            importance: high
            negative: true
            title: Test that users without "hosts:read" permission can't export hosts
        """
        host_inventory_non_org_admin.apis.exports.verify_access_denied()

    def test_rbac_hosts_no_read_permission_get_host_exists(
        self,
        rbac_setup_resources: tuple[
            list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]
        ],
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test that users without "read" permission can't check to see if a
        host exists

        1. Create a new host
        2. Ensure the host is successfully created
        3. Issue a GET request on /host_exists as a user who does not have "read" permission
        4. Ensure GET request returns a 403 response

        metadata:
            requirements: inv-host_exists-get-by-insights-id
            assignee: msager
            importance: high
            title: Confirm users who don't have "read" permission can't check for host existence
        """
        insights_id = rbac_setup_resources[0][0].insights_id

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.hosts.get_host_exists(insights_id)
