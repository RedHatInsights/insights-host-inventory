"""
metadata:
    requirements: inv-rbac
"""

import logging
import random

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_facts
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api import ApiException
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent]


@pytest.fixture(
    params=[
        lf("rbac_inventory_hosts_write_user_setup_class"),
        lf("rbac_inventory_hosts_all_user_setup_class"),
        lf("rbac_inventory_admin_user_setup_class"),
    ],
    scope="class",
)
def write_permission_user_setup(request):
    return request.param


@pytest.fixture(
    params=[
        lf("rbac_inventory_groups_read_user_setup_class"),
        lf("rbac_inventory_groups_write_user_setup_class"),
        lf("rbac_inventory_groups_all_user_setup_class"),
        lf("rbac_inventory_hosts_read_user_setup_class"),
        lf("rbac_inventory_all_read_user_setup_class"),
        lf("rbac_inventory_user_without_permissions_setup_class"),
    ],
    scope="class",
)
def no_write_permission_user_setup(request):
    return request.param


@pytest.fixture
def prepare_hosts(host_inventory: ApplicationHostInventory) -> list[HostOut]:
    return host_inventory.upload.create_hosts(2)


@pytest.mark.usefixtures("write_permission_user_setup")
class TestRBACHostsWritePermission:
    def test_rbac_hosts_write_permission_delete_host_by_id(
        self,
        rbac_setup_resources,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
        prepare_hosts: list[HostOut],
    ):
        """
        Test response when a user who has "write" permission tries to delete a host via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8536
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host
        2. Ensure the host is successfully created
        3. Issue a DELETE request on /hosts/{uuid} to delete the host using a user
           who has "write" permission
        4. Ensure DELETE request returns a 200 response
        5. Issue a GET request to check if the host was successfully deleted
        6. Ensure GET request returns an empty result

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            title: Inventory: Confirm users who have only "write" permission can delete hosts
        """
        group = rbac_setup_resources[1][0]
        host1 = prepare_hosts[0]
        host2 = prepare_hosts[1]
        host_inventory.apis.groups.add_hosts_to_group(group, host1)

        host_inventory_non_org_admin.apis.hosts.delete_by_id_raw([host1.id, host2.id])
        host_inventory.apis.hosts.wait_for_deleted([host1, host2])

    def test_rbac_hosts_write_permission_delete_hosts_filtered(
        self,
        rbac_setup_resources,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-2218

        metadata:
            requirements: inv-hosts-delete-filtered-hosts
            assignee: fstavela
            importance: high
            title: Test that users with "hosts:write" permission can delete filtered hosts
        """
        group = rbac_setup_resources[1][0]
        prefix = f"iqe-hbi-delete-filtered_{generate_uuid()}"
        hosts_data = [HostData(display_name_prefix=prefix) for _ in range(2)]
        host1, host2 = host_inventory.upload.create_hosts(hosts_data=hosts_data)
        host_inventory.apis.groups.add_hosts_to_group(group, host1)

        host_inventory_non_org_admin.apis.hosts.delete_filtered(
            display_name=prefix, wait_for_deleted=False
        )
        host_inventory.apis.hosts.wait_for_deleted([host1, host2])

    def test_rbac_hosts_write_permission_patch_host_display_name(
        self,
        rbac_setup_resources,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
        prepare_hosts: list[HostOut],
    ):
        """
        Test response when a user who has "write" permission tries to update host's display_name
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8536
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host
        2. Ensure the host is successfully created
        3. Issue a PATCH request on /hosts/{uuid} to update host's display_name using a user
           who has "write" permission
        4. Ensure PATCH request returns a 200 response
        5. Issue a GET request to check if the host was updated
        6. Ensure GET request returns a 200 and the display name was updated

        metadata:
            requirements: inv-hosts-patch
            assignee: fstavela
            importance: high
            title: Inventory: Confirm users with "write" permission can update host's display_name
        """
        group = rbac_setup_resources[1][0]
        host1 = prepare_hosts[0]
        host2 = prepare_hosts[1]
        host_inventory.apis.groups.add_hosts_to_group(group, host1)

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

    @pytest.mark.ephemeral
    def test_rbac_hosts_write_permission_patch_merge_host_facts(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        Test response when a user who has "write" permission tries to merge host facts
        under a namespace via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8536
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host with some facts
        2. Ensure the host is successfully created
        3. Issue a PATCH request on /hosts/{uuid}/facts/{namespace} to merge new facts
           with the existing ones using a user who has "write" permission
        4. Ensure PATCH request returns a 200 response
        5. Issue a GET request to check the host's facts were updated
        6. Ensure GET request returns a 200 with the new facts merged with the existing ones

        metadata:
            requirements: inv-hosts-patch-facts
            assignee: fstavela
            importance: high
            title: Inventory: Confirm users who have "write" permission can merge host facts
                under a namespace
        """
        fact_namespace = "some-fancy-facts"
        original_facts = {
            "fact1": "duck rubber debugging is amazing",
            "fact2": "for the power of the super cow",
        }
        fancy_facts = [{"namespace": fact_namespace, "facts": original_facts}]
        host_data = host_inventory.datagen.create_host_data(facts=fancy_facts)
        host = host_inventory.kafka.create_host(host_data=host_data)

        new_facts = {"fact2": f"loves in the air - {random.randint(0, 999_999)}"}

        host_inventory_non_org_admin.apis.hosts.merge_facts(
            host.id, fact_namespace, new_facts, wait_for_updated=False
        )

        response_host = host_inventory.apis.hosts.get_hosts_by_id_response(host.id).results[0]

        new_facts = {**original_facts, **new_facts}  # fact2 will be overridden

        assert len(response_host.facts) == 1
        facts = response_host.facts[0]
        assert len(facts.facts) == 2
        assert facts.namespace == fact_namespace
        assert facts.facts == new_facts

    @pytest.mark.ephemeral
    def test_rbac_hosts_write_permission_put_replace_host_facts(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        Test response when a user who has "write" permission tries to replace host facts
        under a namespace via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8536
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host with some facts
        2. Ensure the host is successfully created
        3. Issue a PUT request on /hosts/{uuid}/facts/{namespace} to replace existing facts
           using a user who has "write" permission
        4. Ensure PUT request returns a 200 response
        5. Issue a GET request to check the host's facts were updated
        6. Ensure GET request returns a 200 with the new facts

        metadata:
            requirements: inv-hosts-put-facts
            assignee: fstavela
            importance: high
            title: Inventory: Confirm users who have "write" permission can replace existing facts
                under a namespace
        """
        fancy_facts = generate_facts()
        host_data = host_inventory.datagen.create_host_data(facts=fancy_facts)
        host = host_inventory.kafka.create_host(host_data=host_data)

        fact_namespace = fancy_facts[0]["namespace"]
        host_id = host.id

        new_facts = {"fact2": f"loves in the air - {random.randint(0, 999_999)}"}

        host_inventory_non_org_admin.apis.hosts.replace_facts(
            host.id, namespace=fact_namespace, facts=new_facts, wait_for_updated=False
        )

        response_host = host_inventory.apis.hosts.get_hosts_by_id_response(host_id).results[0]

        assert len(response_host.facts) == 1
        facts = response_host.facts[0]
        assert len(facts.facts) == 1
        assert facts.namespace == fact_namespace
        assert facts.facts == new_facts


@pytest.mark.usefixtures("no_write_permission_user_setup")
class TestRBACHostsNoWritePermission:
    def test_rbac_hosts_no_write_permission_delete_host_by_id(
        self,
        rbac_setup_resources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        Test response when a user who doesn't have "write" permission tries to delete a host
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8536
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host
        2. Ensure the host is successfully created
        3. Issue a DELETE request on /hosts/{uuid} to delete the host using a user
           who doesn't have "write" permission
        4. Ensure DELETE request returns a 403 response
        5. Issue a GET request to check if the host was deleted
        6. Ensure GET request returns a 200 response meaning that the host still exists

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users who have only "read" permission can't delete hosts
        """
        hosts_ids = [host.id for host in rbac_setup_resources[0]]

        with pytest.raises(ApiException) as err:
            host_inventory_non_org_admin.apis.hosts.delete_by_id_raw(hosts_ids[0])
        assert err.value.status == 403

        with pytest.raises(ApiException) as err:
            host_inventory_non_org_admin.apis.hosts.delete_by_id_raw(hosts_ids[1])
        assert err.value.status == 403

        host_inventory.apis.hosts.verify_not_deleted(hosts_ids)

    def test_rbac_hosts_no_write_permission_delete_hosts_filtered(
        self,
        rbac_setup_resources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-2218

        metadata:
            requirements: inv-hosts-delete-filtered-hosts
            assignee: fstavela
            importance: high
            negative: true
            title: Test that users without "hosts:write" permission can't delete filtered hosts
        """
        hosts = rbac_setup_resources[0]
        hosts_ids = [host.id for host in hosts]

        with pytest.raises(ApiException) as err:
            host_inventory_non_org_admin.apis.hosts.delete_filtered(
                display_name=hosts[0].display_name
            )
        assert err.value.status == 403

        with pytest.raises(ApiException) as err:
            host_inventory_non_org_admin.apis.hosts.delete_filtered(
                display_name=hosts[1].display_name
            )
        assert err.value.status == 403

        host_inventory.apis.hosts.verify_not_deleted(hosts_ids)

    def test_rbac_hosts_no_write_permission_patch_host_display_name(
        self,
        rbac_setup_resources,
        host_inventory_non_org_admin,
        host_inventory,
    ):
        """
        Test response when a user who has "read" permission tries to update host's display_name
        via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8536
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host
        2. Ensure the host is successfully created
        3. Issue a PATCH request on /hosts/{uuid} to update host's display_name using a user
           who doesn't have "write" permission
        4. Ensure PATCH request returns a 403 response
        5. Issue a GET request to check if the host was updated
        6. Ensure GET request returns a 200 but the display name was not updated

        metadata:
            requirements: inv-hosts-patch
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users who have only "read" permission can't update
                host's display_name
        """
        hosts = rbac_setup_resources[0]
        hosts_ids = [host.id for host in hosts]
        new_display_name = generate_display_name()

        with pytest.raises(ApiException) as err:
            host_inventory_non_org_admin.apis.hosts.patch_hosts(
                hosts_ids[0], display_name=new_display_name
            )
        assert err.value.status == 403

        with pytest.raises(ApiException) as err:
            host_inventory_non_org_admin.apis.hosts.patch_hosts(
                hosts_ids[1], display_name=new_display_name
            )
        assert err.value.status == 403

        host_inventory.apis.hosts.verify_not_updated(
            hosts_ids[0], display_name=hosts[0].display_name
        )
        host_inventory.apis.hosts.verify_not_updated(
            hosts_ids[1], display_name=hosts[1].display_name
        )

    @pytest.mark.ephemeral
    def test_rbac_hosts_no_write_permission_patch_merge_host_facts(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        Test response when a user who doesn't have "write" permission tries to merge host facts
        under a namespace via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8536
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host with some facts
        2. Ensure the host is successfully created
        3. Issue a PATCH request on /hosts/{uuid}/facts/{namespace} to merge new facts
           with the existing ones using a user who doesn't have "write" permission
        4. Ensure PATCH request returns a 403 response
        5. Issue a GET request to check the host's facts were updated
        6. Ensure GET request returns a 200 and the facts were not updated

        metadata:
            requirements: inv-hosts-patch-facts
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users who doesn't have "write" permission can't merge
                   host facts under a namespace
        """
        fact_namespace = "some-fancy-facts"
        original_facts = {
            "fact1": "duck rubber debugging is amazing",
            "fact2": "for the power of the super cow",
        }
        fancy_facts = [{"namespace": fact_namespace, "facts": original_facts}]

        host_data = host_inventory.datagen.create_host_data(facts=fancy_facts)
        host = host_inventory.kafka.create_host(host_data=host_data)

        new_facts = {"fact2": f"loves in the air - {random.randint(0, 999_999)}"}

        with pytest.raises(ApiException) as err:
            host_inventory_non_org_admin.apis.hosts.merge_facts(host.id, fact_namespace, new_facts)

        assert err.value.status == 403

        response = host_inventory.apis.hosts.get_hosts_by_id_response(host.id)

        assert response.count == 1
        facts = response.results[0].facts[0]
        assert facts.namespace == fact_namespace
        assert len(facts.facts) == 2
        assert facts.facts == original_facts

    @pytest.mark.ephemeral
    def test_rbac_hosts_no_write_permission_put_replace_host_facts(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        Test response when a user who doesn't have "write" permission tries to replace host facts
        under a namespace via REST API

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8536
        JIRA: https://issues.redhat.com/browse/RHCLOUD-9570

        1. Create a new host with some facts
        2. Ensure the host is successfully created
        3. Issue a PUT request on /hosts/{uuid}/facts/{namespace} to replace existing facts
           using a user who doesn't have "write" permission
        4. Ensure PUT request returns a 403 response
        5. Issue a GET request to check the host's facts were updated
        6. Ensure GET request returns a 200 and facts were not updated

        metadata:
            requirements: inv-hosts-put-facts
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users who doesn't have "write" permission can't replace
                existing facts under a namespace
        """
        fancy_facts = generate_facts()
        host_data = host_inventory.datagen.create_host_data(facts=fancy_facts)
        host = host_inventory.kafka.create_host(host_data=host_data)

        fact_namespace = fancy_facts[0]["namespace"]
        original_facts = fancy_facts[0]["facts"]
        host_id = host.id

        new_facts = {"fact2": f"loves in the air - {random.randint(0, 999_999)}"}

        with pytest.raises(ApiException) as err:
            host_inventory_non_org_admin.apis.hosts.replace_facts(
                host_id, namespace=fact_namespace, facts=new_facts
            )

        assert err.value.status == 403

        response = host_inventory.apis.hosts.get_hosts_by_id_response(host.id)

        assert response.count == 1
        facts = response.results[0].facts[0]
        assert facts.namespace == fact_namespace
        assert len(facts.facts) == 2
        assert facts.facts == original_facts
