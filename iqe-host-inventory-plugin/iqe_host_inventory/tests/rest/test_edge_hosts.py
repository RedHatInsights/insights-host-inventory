import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_tags
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory.utils.upload_utils import get_edge_inventory_account_archive
from iqe_host_inventory_api.models.host_out import HostOut


@pytest.fixture(scope="class")
def prepare_edge_host(host_inventory: ApplicationHostInventory) -> tuple[HostOut, list[TagDict]]:
    """Returns (host, tags) - as a HostOut and list of dicts"""
    tags = generate_tags()
    return host_inventory.upload.create_host(
        base_archive=get_edge_inventory_account_archive(), tags=tags, cleanup_scope="class"
    ), tags


class TestEdgeHosts:
    def test_get_edge_hosts_list(
        self,
        host_inventory,
        prepare_edge_host,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-2276
        https://issues.redhat.com/browse/RHINENG-12577

        metadata:
            requirements: inv-hosts-get-list
            assignee: fstavela
            importance: high
            title: Test that edge hosts are visible
        """
        edge_host_id = prepare_edge_host[0].id

        response_hosts = host_inventory.apis.hosts.get_hosts()
        response_hosts_ids = {host.id for host in response_hosts}
        assert edge_host_id in response_hosts_ids

    def test_get_edge_tags(
        self,
        host_inventory,
        prepare_edge_host,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-2276
        https://issues.redhat.com/browse/RHINENG-12577

        metadata:
            requirements: inv-tags-get-list
            assignee: fstavela
            importance: high
            title: Test that tags of edge hosts are visible
        """
        edge_host_tags = prepare_edge_host[1]

        response = host_inventory.apis.tags.get_tags_response()
        assert_tags_found(edge_host_tags, response.results)

    def test_get_edge_hosts_by_id(
        self,
        host_inventory,
        prepare_edge_host,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-2276

        metadata:
            requirements: inv-hosts-get-by-id
            assignee: fstavela
            importance: high
            title: Test that I can get edge hosts by IDs
        """
        edge_host_id = prepare_edge_host[0].id

        response_host = host_inventory.apis.hosts.get_host_by_id(edge_host_id)
        assert response_host.id == edge_host_id

    def test_get_edge_hosts_system_profile(
        self,
        host_inventory,
        prepare_edge_host,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-2276

        metadata:
            requirements: inv-hosts-get-system_profile
            assignee: fstavela
            importance: high
            title: Test that I can get edge host's system_profile by IDs
        """
        edge_host_id = prepare_edge_host[0].id

        response_host = host_inventory.apis.hosts.get_host_system_profile(edge_host_id)
        assert response_host.id == edge_host_id
        assert response_host.system_profile.host_type == "edge"

    def test_get_edge_hosts_tags(
        self,
        host_inventory,
        prepare_edge_host,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-2276

        metadata:
            requirements: inv-hosts-get-tags
            assignee: fstavela
            importance: high
            title: Test that I can get edge host's tags by IDs
        """
        edge_host_id, edge_host_tags = prepare_edge_host[0].id, prepare_edge_host[1]

        response = host_inventory.apis.hosts.get_host_tags_response([edge_host_id])
        assert response.count == 1
        assert len(response.results) == 1
        assert len(response.results[edge_host_id]) == len(edge_host_tags)

    def test_get_edge_hosts_tags_count(
        self,
        host_inventory,
        prepare_edge_host,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-2276

        metadata:
            requirements: inv-hosts-get-tags-count
            assignee: fstavela
            importance: high
            title: Test that I can get edge host's tags count by IDs
        """
        edge_host_id, edge_host_tags = prepare_edge_host[0].id, prepare_edge_host[1]

        response = host_inventory.apis.hosts.get_host_tags_count_response([edge_host_id])
        assert response.count == 1
        assert len(response.results) == 1
        assert response.results[edge_host_id] == len(edge_host_tags)

    def test_patch_edge_hosts(
        self,
        host_inventory,
        prepare_edge_host,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-2276

        metadata:
            requirements: inv-hosts-patch
            assignee: fstavela
            importance: high
            title: Test that I can patch edge hosts
        """
        edge_host_id = prepare_edge_host[0].id
        new_display_name = generate_display_name()

        host_inventory.apis.hosts.patch_hosts(
            edge_host_id, display_name=new_display_name, wait_for_updated=False
        )
        host_inventory.apis.hosts.wait_for_updated(edge_host_id, display_name=new_display_name)

    def test_delete_edge_hosts_by_id(
        self,
        host_inventory,
        prepare_edge_host,
    ):
        """
        https://issues.redhat.com/browse/RHINENG-2276

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            title: Test that I can delete edge hosts by IDs
        """
        edge_host_id = prepare_edge_host[0].id

        host_inventory.apis.hosts.delete_by_id_raw(edge_host_id)
        host_inventory.apis.hosts.wait_for_deleted(edge_host_id)
