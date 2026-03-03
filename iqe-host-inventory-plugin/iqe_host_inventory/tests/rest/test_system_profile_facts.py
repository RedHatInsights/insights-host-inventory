# mypy: disallow-untyped-defs

import logging
from datetime import datetime

import pytest
from iqe.utils.blockers import iqe_blocker

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_default_cloud_provider
from iqe_host_inventory_api.models.system_profile_operating_system import (
    SystemProfileOperatingSystem,
)

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_system_profile_facts_creation_on_initial_message(
    host_inventory: ApplicationHostInventory,
    example_system_profile_facts: dict,
) -> None:
    """
    Test System Profile Fact Creation via MQ.

    Confirm that on the initial message of host data the system profile facts can be included
    and that the host is created with the specified system profile fact values.

    metadata:
        requirements: inv-hosts-get-system_profile
        assignee: fstavela
        importance: critical
        title: Inventory: System Profile Fact Creation on Initial message
    """
    host = host_inventory.kafka.create_host()
    fetched_host = host_inventory.apis.hosts.wait_for_system_profile_updated(
        host, cloud_provider=get_default_cloud_provider()
    )

    for fact_key, fact_val in example_system_profile_facts.items():
        actual_value = getattr(fetched_host.system_profile, fact_key)
        assert actual_value is not None
        if isinstance(actual_value, datetime):
            # convert datetime object to string for fact value comparison
            actual_value = actual_value.isoformat()
        if isinstance(actual_value, SystemProfileOperatingSystem):
            actual_value = actual_value.to_dict()
        assert actual_value == fact_val, f"Mismatch in profile facts on key {fact_key}"


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("sap_system", [True, False])
def test_system_profile_facts_sap_system(
    host_inventory: ApplicationHostInventory, sap_system: bool
) -> None:
    """
    Test System Profile Facts - Create a new host with a SAP system fact via MQ

    Confirm that is possible to create a host with a SAP system profile fact
    After RHINENG-21482, SAP data is storred in workloads.sap structure.

    metadata:
        requirements: inv-host-create, inv-hosts-get-system_profile
        assignee: fstavela
        importance: critical
        title: Inventory: System Profile Fact - SAP System
    """
    host_data = host_inventory.datagen.create_host_data()

    if "workloads" not in host_data["system_profile"]:
        host_data["system_profile"]["workloads"] = {}

    host_data["system_profile"]["workloads"] = {
        "sap": {
            "sap_system": sap_system,
        },
    }

    host = host_inventory.kafka.create_host(host_data=host_data)

    fetched_host = host_inventory.apis.hosts.get_hosts_system_profile_response(host.id)

    # Verify workloads.sap.sap_system is returned correctly
    system_profile_dict = fetched_host.results[0].system_profile.to_dict()
    assert "workloads" in system_profile_dict
    assert "sap" in system_profile_dict["workloads"]
    assert system_profile_dict["workloads"]["sap"]["sap_system"] == sap_system


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "sap_sid",
    [
        ["ABC"],
        ["ABC", "CDE"],
        ["ABC", "CDE", "EFG"],
        ["A01", "BCD", "C1E"],
        ["A00", "AB0", "ABC"],
    ],
)
def test_system_profile_facts_sap_sid(
    host_inventory: ApplicationHostInventory, sap_sid: list[str]
) -> None:
    """
    Test System Profile Facts - Create a new host with a SAP sids fact via MQ
    After RHINENG-21482, SAP data is storred in workloads.sap structure.

    metadata:
        requirements: inv-host-create, inv-hosts-get-system_profile
        assignee: fstavela
        importance: critical
        title: Inventory: System Profile Fact - SAP sids
    """
    host_data = host_inventory.datagen.create_host_data()

    if "workloads" not in host_data["system_profile"]:
        host_data["system_profile"]["workloads"] = {}

    host_data["system_profile"]["workloads"] = {
        "sap": {
            "sap_system": True,
            "sids": sap_sid,
        },
    }

    host = host_inventory.kafka.create_host(host_data=host_data)

    fetched_host = host_inventory.apis.hosts.get_hosts_system_profile_response(host.id)

    # Verify workloads.sap.sids is returned correctly
    system_profile_dict = fetched_host.results[0].system_profile.to_dict()
    assert "workloads" in system_profile_dict
    assert "sap" in system_profile_dict["workloads"]
    assert system_profile_dict["workloads"]["sap"]["sids"] == sap_sid


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_system_profile_facts_owner_id(host_inventory: ApplicationHostInventory) -> None:
    """
    Test System Profile Facts - Create a new host with an owner_id fact via MQ

    metadata:
        requirements: inv-host-create, inv-hosts-get-system_profile
        assignee: fstavela
        importance: critical
        title: Inventory: System Profile Fact - owner_id
    """
    owner_id = generate_uuid()
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["owner_id"] = owner_id

    host = host_inventory.kafka.create_host(host_data=host_data)

    fetched_host = host_inventory.apis.hosts.get_hosts_system_profile_response(host.id)

    assert fetched_host.results[0].system_profile.owner_id == owner_id


@iqe_blocker(iqe_blocker.jira("RHINENG-17920", category=iqe_blocker.PRODUCT_ISSUE))
@pytest.mark.ephemeral
def test_system_profile_facts_update_single_field(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    metadata:
        requirements: inv-host-update
        assignee: fstavela
        importance: critical
        title: Test updating single system_profile field won't overwrite other fields
    """
    host_data = host_inventory.datagen.create_complete_host_data()
    host = host_inventory.kafka.create_host(host_data)

    new_rhsm_field = {"environment_ids": [generate_uuid()]}
    expected_system_profile = dict(host_data["system_profile"])
    expected_system_profile["rhsm"].update(new_rhsm_field)
    new_display_name = generate_display_name()
    # Send only one system profile field in the update message
    host_data["system_profile"] = {"rhsm": new_rhsm_field}
    host_data["display_name"] = new_display_name
    updated_host = host_inventory.kafka.create_host(host_data)

    # The new field value should be merged with the original system profile
    assert updated_host.id == host.id
    assert updated_host.system_profile == expected_system_profile

    host_inventory.apis.hosts.wait_for_updated(updated_host, display_name=new_display_name)
    response_host = host_inventory.apis.hosts.get_host_system_profile(updated_host)
    assert response_host.system_profile.rhsm.environment_ids == new_rhsm_field["environment_ids"]
    # Check that random other field wasn't overwritten
    assert (
        response_host.system_profile.insights_client_version
        == expected_system_profile["insights_client_version"]
    )
