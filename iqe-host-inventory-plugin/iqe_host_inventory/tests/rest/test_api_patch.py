import logging
import random

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils import assert_datetimes_equal
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import fake
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.staleness_utils import create_hosts_in_state
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def prepare_hosts(host_inventory: ApplicationHostInventory) -> list[HostOut]:
    return host_inventory.upload.create_hosts(2, cleanup_scope="module")


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_patch_display_name(
    host_inventory: ApplicationHostInventory, prepare_hosts: list[HostOut]
):
    """
    Test PATCH display_name field of host.

    1. Create a host
    2. PATCH the host with a different display_name value
    3. GET the host
    4. Confirm the host has the new display_name value

    metadata:
        requirements: inv-hosts-patch
        assignee: fstavela
        importance: high
        title: Inventory: PATCH display_name field of host
    """
    host = prepare_hosts[0]

    new_display_name = generate_display_name()

    host_inventory.apis.hosts.patch_hosts(host.id, display_name=new_display_name)

    host_inventory.apis.hosts.wait_for_updated(host, display_name=new_display_name)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup_culled")
def test_patch_display_name_culled_host(host_inventory: ApplicationHostInventory):
    """
    Test PATCH display_name field of a culled host

    1. Create a host in culled state
    2. Attempt to PATCH the host with a different display_name value
    3. Confirm the response from the PATCH has status code 404

    metadata:
        requirements: inv-hosts-patch, inv-staleness-hosts
        assignee: fstavela
        importance: low
        negative: true
        title: Inventory: PATCH display_name field of a culled host
    """
    host_data = host_inventory.datagen.create_host_data()
    host = create_hosts_in_state(host_inventory, [host_data], host_state="culling")[0]

    new_display_name = generate_display_name()

    with raises_apierror(404):
        host_inventory.apis.hosts.patch_hosts(host.id, display_name=new_display_name)


def test_patch_ansible_host(
    host_inventory: ApplicationHostInventory, prepare_hosts: list[HostOut]
):
    """
    Test PATCH ansible_host field of host.

    1. Create a host
    2. PATCH the host with a different ansible_host value
    3. GET the host
    4. Confirm the host has the new ansible_host value

    metadata:
        requirements: inv-hosts-patch
        assignee: fstavela
        importance: high
        title: Inventory: PATCH ansible_host field of host
    """
    host = prepare_hosts[0]

    new_ansible_host = fake.hostname()

    host_inventory.apis.hosts.patch_hosts(host.id, ansible_host=new_ansible_host)
    host_inventory.apis.hosts.wait_for_updated(host, ansible_host=new_ansible_host)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup_culled")
def test_patch_ansible_host_culled_host(host_inventory: ApplicationHostInventory):
    """
    Test PATCH ansible_host field of a culled host

    1. Create a host in culled state
    2. Attempt to PATCH the host with a different ansible_host value
    3. Confirm the response from the PATCH has status code 404

    metadata:
        requirements: inv-hosts-patch, inv-staleness-hosts
        assignee: fstavela
        importance: low
        title: Inventory: PATCH ansible_host field of a culled host
    """
    host_data = host_inventory.datagen.create_host_data()
    host = create_hosts_in_state(host_inventory, [host_data], host_state="culling")[0]
    assert isinstance(host, HostWrapper)
    new_ansible_host = fake.hostname()
    with raises_apierror(404):
        host_inventory.apis.hosts.patch_hosts(host.id, ansible_host=new_ansible_host)


def test_patch_display_name_multiple_hosts(
    host_inventory: ApplicationHostInventory, prepare_hosts: list[HostOut]
):
    """
    Test PATCH display_name field of multiple hosts

    1. Create two hosts
    2. PATCH the hosts with a different display_name value
    3. GET the hosts
    4. Confirm the hosts have the new display_name value

    metadata:
        requirements: inv-hosts-patch
        assignee: fstavela
        importance: medium
        title: Inventory: PATCH display_name field of multiple hosts
    """
    hosts = prepare_hosts
    host_ids = [host.id for host in hosts]

    new_display_name = generate_display_name()

    host_inventory.apis.hosts.patch_hosts(host_ids, display_name=new_display_name)

    host_inventory.apis.hosts.wait_for_updated(hosts[0], display_name=new_display_name)
    host_inventory.apis.hosts.wait_for_updated(hosts[1], display_name=new_display_name)


@pytest.mark.ephemeral
def test_patch_facts_over_an_existing_fact(host_inventory: ApplicationHostInventory):
    """
    Test PATCH facts in an existing namespace.

    1. Create a host with facts in a namespace
    2. PATCH the host with updates to an existing fact
    3. GET the host
    4. Confirm the host has the new fact value

    metadata:
        requirements: inv-hosts-patch-facts
        assignee: fstavela
        importance: medium
        title: Inventory: PATCH facts in an existing namespace
    """
    fact_namespace = "some-fancy-facts"
    original_facts = {
        "fact1": "duck rubber debugging is amazing",
        "fact2": "for the power of the super cow",
    }
    fancy_facts = [{"namespace": fact_namespace, "facts": original_facts}]
    host_data = host_inventory.datagen.create_host_data(facts=fancy_facts)
    host = host_inventory.kafka.create_host(host_data=host_data)

    fact_patch = {"fact2": f"loves in the air - {random.randint(0, 999_999)}"}

    host_inventory.apis.hosts.merge_facts(host.id, fact_namespace, fact_patch)

    new_facts = {**original_facts, **fact_patch}  # fact2 will be overriden

    host_inventory.apis.hosts.wait_for_facts_replaced(host, fact_namespace, new_facts)


@pytest.mark.ephemeral
def test_patch_facts_non_existing_namespace(host_inventory: ApplicationHostInventory):
    """
    Test PATCH facts to a non-existing namespace.

    1. Create a host with facts in a namespace
    2. PATCH the host with updates to a fact in a namespace that does not exist
    3. Confirm the response from the PATCH has status code 400

    metadata:
        requirements: inv-hosts-patch-facts, inv-api-validation
        assignee: fstavela
        importance: low
        title: Inventory: PATCH facts to a non-existing namespace
    """
    fact_namespace = "some-facts"
    original_facts = {"fact1": "some fancy fact about the host"}
    fancy_facts = [{"namespace": fact_namespace, "facts": original_facts}]

    host_data = host_inventory.datagen.create_host_data(facts=fancy_facts)
    host = host_inventory.kafka.create_host(host_data)

    new_facts = {"fact1": "there is a fly on my soup"}

    with raises_apierror(
        404,
        "The number of hosts requested does not match "
        "the number of hosts found in the host database",
    ):
        host_inventory.apis.hosts.merge_facts(host.id, "new-namespace", new_facts)


@pytest.mark.ephemeral
def test_patch_facts_existing_namespace(host_inventory: ApplicationHostInventory):
    """
    Test PATCH new fact to an existing namespace.

    1. Create a host with facts in a namespace
    2. PATCH the host with a new fact for the existing namespace
    3. GET the updated host.
    4. Confirm all the old facts are present.
    5. Confirm the new fact is present.

    metadata:
        requirements: inv-hosts-patch-facts
        assignee: fstavela
        importance: medium
        title: Inventory: PATCH new fact to an existing namespace
    """
    fact_namespace = "some-fancy-facts"
    original_facts = {
        "fact1": "duck rubber debugging is amazing",
        "fact2": "for the power of the super cow",
    }
    fancy_facts = [{"namespace": fact_namespace, "facts": original_facts}]

    host_data = host_inventory.datagen.create_host_data(facts=fancy_facts)
    host = host_inventory.kafka.create_host(host_data)

    new_facts = {
        "fact3": f"always remember the first rule of the fight club - {random.randint(0, 999_999)}"
    }

    host_inventory.apis.hosts.merge_facts(host.id, fact_namespace, new_facts)

    expected_facts = {**original_facts, **new_facts}
    host_inventory.apis.hosts.wait_for_facts_replaced(host, fact_namespace, expected_facts)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup_culled")
def test_patch_facts_culled_host(host_inventory: ApplicationHostInventory):
    """
    Test PATCH new fact to an existing namespace on a culled host

    1. Create a host in a culled state with facts in a namespace
    2. Attempt to PATCH the host with a new fact for the existing namespace
    3. Confirm the response from the PATCH has status code 400

    metadata:
        requirements: inv-hosts-patch-facts, inv-staleness-hosts
        assignee: fstavela
        importance: low
        title: Inventory: PATCH new fact to an existing namespace on a culled host
    """
    fact_namespace = "some-fancy-facts"
    original_facts = {
        "fact1": "duck rubber debugging is amazing",
        "fact2": "for the power of the super cow",
    }
    fancy_facts = [{"namespace": fact_namespace, "facts": original_facts}]

    host_data = host_inventory.datagen.create_host_data(facts=fancy_facts)
    host = create_hosts_in_state(host_inventory, [host_data], host_state="culling")[0]

    new_facts = {
        "fact3": f"always remember the first rule of the fight club - {random.randint(0, 999_999)}"
    }

    with raises_apierror(404):
        host_inventory.apis.hosts.merge_facts(host.id, fact_namespace, new_facts)


def test_patch_host_doesnt_update_last_check_in(
    host_inventory: ApplicationHostInventory,
    hbi_default_org_id: str,
    prepare_hosts: list[HostOut],
):
    """
    https://issues.redhat.com/browse/RHINENG-15759

    metadata:
      requirements: inv-hosts-patch, inv-hosts-last_check_in-field
      assignee: zabikeno
      importance: high
      title: Make sure 'last_check_in' is not updated after patching host's name.
    """
    host = prepare_hosts[0]

    # Get the host's current state before patching to capture accurate timestamps
    host_before_patch = host_inventory.apis.hosts.get_host_by_id(host.id)

    new_display_name = generate_display_name()
    host_inventory.apis.hosts.patch_hosts(host.id, display_name=new_display_name)

    response = host_inventory.apis.hosts.get_hosts(display_name=new_display_name)
    host_response = response[0]

    assert host.org_id == hbi_default_org_id
    assert host_response.id == host.id
    assert_datetimes_equal(host_response.last_check_in, host_before_patch.last_check_in)
    # make sure staleness timestamps are stayed the same
    assert_datetimes_equal(host_response.stale_timestamp, host_before_patch.stale_timestamp)
    assert_datetimes_equal(
        host_response.stale_warning_timestamp, host_before_patch.stale_warning_timestamp
    )
    assert_datetimes_equal(host_response.culled_timestamp, host_before_patch.culled_timestamp)

    assert host_response.updated != host_before_patch.updated, (
        "Host's field 'updated' should be updated after patching host's name."
    )
