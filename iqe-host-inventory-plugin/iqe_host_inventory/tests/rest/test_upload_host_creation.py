# mypy: disallow-untyped-defs

import logging

import pytest
from fauxfactory import gen_mac

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import gen_tag
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import rand_str
from iqe_host_inventory.utils.staleness_utils import validate_host_timestamps
from iqe_host_inventory.utils.tag_utils import sort_tags
from iqe_host_inventory.utils.upload_utils import IMAGE_MODE_ARCHIVE
from iqe_host_inventory.utils.upload_utils import get_archive_and_collect_method
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
@pytest.mark.usefixtures("hbi_staleness_cleanup")
@pytest.mark.parametrize("operating_system", ["RHEL", "CentOS Linux"])
def test_create_new_host(
    host_inventory: ApplicationHostInventory, hbi_default_org_id: str, operating_system: str
) -> None:
    """
    Test creation of new host via archive upload (Ingress/Puptoo)

    JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-584

    1. Issue POST to create a single host via archive upload
    2. Confirm host is created with the expected display_name

    metadata:
        requirements: inv-host-create
        assignee: fstavela
        importance: critical
        title: Inventory: POST creation of new host via archive upload (Ingress/Puptoo)
    """
    display_name = generate_display_name()

    base_archive, core_collect = get_archive_and_collect_method(operating_system)
    host = host_inventory.upload.create_host(
        display_name=display_name, base_archive=base_archive, core_collect=core_collect
    )

    assert host.display_name == display_name
    assert host.org_id == hbi_default_org_id

    system_profile_response = host_inventory.apis.hosts.get_host_system_profile(host)
    assert system_profile_response.system_profile.operating_system.name == operating_system

    # Ensure hosts created via ingress/puptoo have their culling dates calculated correctly
    assert host.reporter == "puptoo"
    validate_host_timestamps(host_inventory, host)


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_create_same_host_twice(host_inventory: ApplicationHostInventory) -> None:
    """
    Test creation of duplicate host via archive upload (Ingress/Puptoo)

    JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-584

    1. Issue POST to create a single host via archive upload
    2. Issue POST again with the exact same archive
    3. Confirm only a single host is created

    metadata:
        requirements: inv-host-create, inv-host-update, inv-host-deduplication
        assignee: fstavela
        importance: critical
        title: Inventory: POST creation of duplicate host via archive upload (Ingress/Puptoo)
    """
    display_name = generate_display_name()
    insights_id = generate_uuid()
    subscription_manager_id = generate_uuid()
    tags = [gen_tag()]

    logger.info("Creating the host 1st time")
    host_1 = host_inventory.upload.create_host(
        display_name=display_name,
        insights_id=insights_id,
        subscription_manager_id=subscription_manager_id,
        tags=tags,
    )

    logger.info("Creating the host 2nd time")
    host_2 = host_inventory.upload.create_host(
        display_name=display_name,
        insights_id=insights_id,
        subscription_manager_id=subscription_manager_id,
        tags=tags,
    )

    assert host_1.id == host_2.id


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_create_two_hosts_almost_equal(host_inventory: ApplicationHostInventory) -> None:
    """
    Test Creation of Two Similar Hosts via archive upload (Ingress/Puptoo)

    JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-584

    Tests if it is possible to create two hosts with almost
    the same data (couple of values different) but with the same insights_id

    1. Create a host via archive upload
    2. Modify the payload and attempt to re-create the primary host
    3. Confirm the original host was updated (only one host in total should have been created).

    metadata:
        requirements: inv-host-create, inv-host-deduplication
        assignee: fstavela
        importance: critical
        title: Inventory: Confirm duplicate hosts with the same insights_id cannot be
            created via archive upload (Ingress/Puptoo)
    """
    display_name = generate_display_name()
    insights_id = generate_uuid()
    subscription_manager_id = generate_uuid()
    mac_address = gen_mac()

    logger.info("Creating the host 1st time")
    host = host_inventory.upload.create_host(
        display_name=display_name,
        insights_id=insights_id,
        subscription_manager_id=subscription_manager_id,
        mac_address=mac_address,
    )

    assert host.display_name == display_name
    assert host.insights_id == insights_id
    assert host.subscription_manager_id == subscription_manager_id
    assert host.mac_addresses == [mac_address]

    logger.info("Creating the host 2nd time")
    updated_subscription_manager_id = generate_uuid()
    host = host_inventory.upload.create_host(
        display_name=display_name,
        insights_id=insights_id,
        subscription_manager_id=updated_subscription_manager_id,
        mac_address=mac_address,
    )

    host_inventory.apis.hosts.wait_for_updated(
        host, subscription_manager_id=updated_subscription_manager_id
    )

    logger.info(f"Retrieving hosts by filtering the display_name: {display_name}")
    retrieved_hosts = host_inventory.apis.hosts.get_hosts(display_name=display_name)
    assert len(retrieved_hosts) == 1

    assert retrieved_hosts[0].id == host.id
    assert retrieved_hosts[0].display_name == display_name
    assert retrieved_hosts[0].insights_id == insights_id
    assert retrieved_hosts[0].subscription_manager_id == updated_subscription_manager_id
    assert retrieved_hosts[0].mac_addresses == [mac_address]


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
@pytest.mark.parametrize(
    "tags",
    [
        [TagDict(namespace="insights-client", key=rand_str(), value=rand_str())],
        [TagDict(namespace="insights-client", key=rand_str(), value=None)],
        [
            TagDict(namespace="insights-client", key=rand_str(), value=rand_str()),
            TagDict(namespace="insights-client", key=rand_str(), value=None),
        ],
    ],
    ids=["complete", "no-value", "complete-and-no-value"],
)
def test_create_new_host_with_tags(
    host_inventory: ApplicationHostInventory, tags: list[TagDict]
) -> None:
    """
    Test creation of new host via archive upload (Ingress/Puptoo)

    JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-584

    1. Issue POST to create a single host with tags via archive upload
    2. Confirm host is created
    3. Issue a GET request to retrieve the host tags
    4. Ensure the expected tags are returned

    metadata:
        requirements: inv-tags, inv-host-create
        assignee: fstavela
        importance: high
        title: Inventory: POST creation of new host with tags via archive upload (Ingress/Puptoo)
    """
    host = host_inventory.upload.create_host(tags=tags)

    response = host_inventory.apis.hosts.get_host_tags_response(host.id)

    expected_tags = sort_tags(tags)
    logger.info(f"Expected tags: {expected_tags}")

    actual_tags = sort_tags(response.results[host.id])
    logger.info(f"Actual tags: {actual_tags}")

    assert expected_tags == actual_tags


def test_create_new_sap_host(host_inventory: ApplicationHostInventory) -> None:
    """
    Test creation of new host with a SAP system fact via archive upload (Ingress/Puptoo)

    Confirm that is possible to create a host with a SAP system profile fact

    1. Issue POST to create a single host via archive upload by sending a SAP tarball
    2. Confirm host is created with the expected display_name
    3. Issue a GET request to retrieve the host system profile facts
    4. Confirm the system profile fact (SAP system) equals to TRUE

     metadata:
        requirements: inv-host-create, inv-hosts-get-system_profile
        assignee: fstavela
        importance: high
        title: Inventory: POST creation of new SAP host via archive upload (Ingress/Puptoo)
    """
    display_name = generate_display_name()

    host = host_inventory.upload.create_host(
        display_name=display_name, base_archive="sap_core_collect.tar.gz"
    )

    assert host.display_name == display_name

    fetched_host = host_inventory.apis.hosts.get_hosts_system_profile_response(host.id)

    assert fetched_host.results[0].system_profile.sap_system


def test_create_image_mode_host(
    host_inventory: ApplicationHostInventory, hbi_upload_prepare_host_module: HostOut
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-8988

     metadata:
        requirements: inv-host-create, inv-hosts-filter-by-system_profile-bootc_status
        assignee: fstavela
        importance: high
        title: Test creating and filtering image-mode hosts
    """
    conventional_host = hbi_upload_prepare_host_module
    image_host = host_inventory.upload.create_host(base_archive=IMAGE_MODE_ARCHIVE)

    # Check correct data in system_profile
    response_host = host_inventory.apis.hosts.get_host_system_profile(image_host.id)
    assert response_host.system_profile.bootc_status
    assert response_host.system_profile.bootc_status.booted
    assert response_host.system_profile.bootc_status.booted.image
    assert response_host.system_profile.bootc_status.booted.image_digest

    # Check filtering for image-mode hosts
    response = host_inventory.apis.hosts.get_hosts_response(
        filter=["[bootc_status][booted][image_digest][is]=not_nil"]
    )
    assert response.count >= 1
    response_ids = {host.id for host in response.results}
    assert image_host.id in response_ids
    assert conventional_host.id not in response_ids

    # Check filtering for conventional hosts
    response = host_inventory.apis.hosts.get_hosts_response(
        filter=["[bootc_status][booted][image_digest][is]=nil"]
    )
    assert response.count >= 1
    response_ids = {host.id for host in response.results}
    assert conventional_host.id in response_ids
    assert image_host.id not in response_ids
