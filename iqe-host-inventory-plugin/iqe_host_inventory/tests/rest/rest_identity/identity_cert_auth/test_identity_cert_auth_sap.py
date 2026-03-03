import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_uuid

pytestmark = [pytest.mark.backend]


@pytest.fixture
def setup_sap_hosts(
    host_inventory: ApplicationHostInventory,
    inventory_cert_system_owner_id: str,
) -> dict:
    data = {"sap_system": True, "sap_sids": "HBI", "sids": "HBI"}
    # Host without owner_id
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["sap_system"] = not data["sap_system"]
    host_data["system_profile"]["workloads"] = {"sap": {}}
    host_data["system_profile"]["workloads"]["sap"]["sap_system"] = not data["sap_system"]
    # Host without owner_id with sids
    host_data_sids = host_inventory.datagen.create_host_data()
    host_data_sids["system_profile"]["sap_system"] = True
    host_data_sids["system_profile"]["sap_sids"] = ["HB1"]
    host_data_sids["system_profile"]["workloads"] = {"sap": {}}
    host_data_sids["system_profile"]["workloads"]["sap"]["sap_system"] = True
    host_data_sids["system_profile"]["workloads"]["sap"]["sids"] = ["HB1"]
    # Host with correct owner_id
    host_data_correct = host_inventory.datagen.create_host_data()
    host_data_correct["system_profile"]["sap_system"] = data["sap_system"]
    host_data_correct["system_profile"]["sap_sids"] = [data["sap_sids"]]
    host_data_correct["system_profile"]["workloads"] = {"sap": {}}
    host_data_correct["system_profile"]["workloads"]["sap"]["sap_system"] = data["sap_system"]
    host_data_correct["system_profile"]["workloads"]["sap"]["sids"] = [data["sids"]]
    host_data_correct["system_profile"]["owner_id"] = inventory_cert_system_owner_id
    # Host with wrong owner_id
    host_data_wrong = host_inventory.datagen.create_host_data()
    host_data_wrong["system_profile"]["sap_system"] = not data["sap_system"]
    host_data_wrong["system_profile"]["workloads"] = {"sap": {}}
    host_data_wrong["system_profile"]["workloads"]["sap"]["sap_system"] = not data["sap_system"]
    host_data_wrong["system_profile"]["owner_id"] = generate_uuid()
    # Host with wrong owner_id with sids
    host_data_wrong_sids = host_inventory.datagen.create_host_data()
    host_data_wrong_sids["system_profile"]["sap_system"] = True
    host_data_wrong_sids["system_profile"]["sap_sids"] = ["HB1"]
    host_data_wrong_sids["system_profile"]["workloads"] = {"sap": {}}
    host_data_wrong_sids["system_profile"]["workloads"]["sap"]["sap_system"] = True
    host_data_wrong_sids["system_profile"]["workloads"]["sap"]["sids"] = ["HB1"]
    host_data_wrong_sids["system_profile"]["owner_id"] = generate_uuid()

    host_inventory.kafka.create_hosts(
        hosts_data=[
            host_data,
            host_data_sids,
            host_data_correct,
            host_data_wrong,
            host_data_wrong_sids,
        ]
    )

    return data


@pytest.mark.ephemeral
def test_cert_auth_enumerate_sap_system(
    setup_sap_hosts,
    host_inventory_system_correct,
):
    """
    Test that I can only enumerate SAP values of the hosts with the same owner ID as my host has
    when using cert auth.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-12040

    metadata:
        requirements: inv-api-cert-auth, inv-system_profile-get-sap_system
        assignee: fstavela
        importance: high
        title: Inventory: enumerate sap_system values using cert auth
    """
    response = host_inventory_system_correct.apis.system_profile.get_sap_systems_response()
    assert len(response.results) == 1
    assert response.results[0].value == setup_sap_hosts["sap_system"]
    assert response.results[0].count == 1


@pytest.mark.ephemeral
def test_cert_auth_enumerate_sap_sids(
    setup_sap_hosts,
    host_inventory_system_correct,
):
    """
    Test that I can only enumerate SAP SIDs of the hosts with the same owner ID as my host has
    when using cert auth.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-12040

    metadata:
        requirements: inv-api-cert-auth, inv-system_profile-get-sap_sids
        assignee: fstavela
        importance: high
        title: Inventory: enumerate sap_sids values using cert auth
    """
    response = host_inventory_system_correct.apis.system_profile.get_sap_sids_response()
    assert len(response.results) == 1
    assert response.results[0].value == setup_sap_hosts["sap_sids"]
    assert response.results[0].count == 1
