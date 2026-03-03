"""
metadata:
  requirements: inv-api-validation
"""

import pytest

from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api import ApiException

pytestmark = [pytest.mark.backend]


@pytest.mark.parametrize(
    "invalid_uuid",
    [
        "abcdef",
        "123",
        "-123",
        "0.0",
        pytest.param(" " + generate_uuid(), id="prefix \\ "),
    ],
)
def test_invalid_uuid_in_requests(invalid_uuid, host_inventory):
    """
    Test validation for UUID fields in request URL.

    metadata:
        assignee: fstavela
        importance: low
        negative: true
        title: Inventory: validation for UUID fields in request URL.
    """
    not_a_uuid = "is not a 'uuid'"
    does_not_match = "does not match"
    multiple_hosts = [invalid_uuid, generate_uuid()]

    # GET a host, single invalid host UUID
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.get_host_by_id(invalid_uuid)
    assert err.value.status == 400
    assert does_not_match in err.value.body

    # GET a host, intermix an invalid UUID with valid UUIDs
    host_list = [generate_uuid(), invalid_uuid, generate_uuid()]
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.get_hosts_by_id(host_list)
    assert err.value.status in [400, 404]
    assert does_not_match in err.value.body

    # GET A host by insights_id
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.get_hosts(insights_id=invalid_uuid)
    assert err.value.status == 400
    assert not_a_uuid in err.value.body

    # GET system profile facts
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.get_hosts_system_profile(invalid_uuid)
    assert err.value.status == 400
    assert does_not_match in err.value.body

    # Get system profile facts for multiple systems
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.get_hosts_system_profile(multiple_hosts)
    assert err.value.status == 400
    assert does_not_match in err.value.body

    # DELETE single host
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.delete_by_id_raw(invalid_uuid)
    assert err.value.status == 400
    assert does_not_match in err.value.body

    # DELETE multiple hosts
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.delete_by_id_raw([invalid_uuid, invalid_uuid])
    assert err.value.status == 400
    assert does_not_match in err.value.body

    # PATCH a single host
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.patch_hosts(invalid_uuid, display_name="thx1138")
    assert err.value.status == 400
    assert does_not_match in err.value.body

    # PATCH multiple hosts
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.patch_hosts(multiple_hosts, display_name="thx1139")
    assert err.value.status == 400
    assert does_not_match in err.value.body

    # PATCH facts under a namespace
    facts_data = {"display_name": "thx1140"}
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.merge_facts(invalid_uuid, "some_namespace", facts_data)
    assert err.value.status == 400
    assert does_not_match in err.value.body

    # PATCH multiple facts under a namespace
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.merge_facts(multiple_hosts, "some_namespace", facts_data)
    assert err.value.status == 400
    assert does_not_match in err.value.body

    # PUT facts under a namespace
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.replace_facts(
            invalid_uuid, namespace="some_namespace", facts=facts_data
        )
    assert err.value.status == 400
    assert does_not_match in err.value.body
