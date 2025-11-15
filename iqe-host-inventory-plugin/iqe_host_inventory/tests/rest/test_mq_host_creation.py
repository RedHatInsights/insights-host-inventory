import datetime as dt
import logging
import uuid
from copy import deepcopy
from datetime import timedelta
from time import sleep

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils import assert_datetimes_equal
from iqe_host_inventory.utils.datagen_utils import fake
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_user_identity
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.kafka_utils import prepare_identity_metadata

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


def get_accuracy(datetime1, datetime2) -> dt.timedelta:
    if isinstance(datetime1, str):
        datetime1 = dt.datetime.fromisoformat(datetime1)
    if isinstance(datetime2, str):
        datetime2 = dt.datetime.fromisoformat(datetime2)
    return abs(datetime1 - datetime2)


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_create_single_host(host_inventory: ApplicationHostInventory):
    """
    Create a single host by putting a valid message on the ingress topic.

    metadata:
        requirements: inv-host-create
        assignee: fstavela
        importance: critical
        title: Inventory: Test create a single host by putting a valid message on
            the ingress topic
    """
    host_data = host_inventory.datagen.create_host_data()
    consumed_host_messages = host_inventory.kafka.create_host_events([host_data])
    assert len(consumed_host_messages) == 1

    consumed_host_message = consumed_host_messages[0]
    assert consumed_host_message is not None
    assert consumed_host_message.value.get("type") == "created"

    host = consumed_host_message.host

    # Issue a GET to confirm the host was created
    retrieved_hosts = host_inventory.apis.hosts.wait_for_created_by_filters(
        insights_id=host.insights_id
    )

    assert len(retrieved_hosts) == 1
    assert retrieved_hosts[0].id == host.id


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_create_multiple_hosts(host_inventory: ApplicationHostInventory):
    """
    Confirm that multiple hosts are created when multiple messages are put on
    the topic.

    metadata:
        requirements: inv-host-create
        assignee: fstavela
        importance: critical
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    assert len(hosts) == 3

    # GET the hosts to confirm creation
    for host in hosts:
        retrieved_hosts = host_inventory.apis.hosts.get_hosts(insights_id=host.insights_id)
        assert len(retrieved_hosts) == 1
        assert host.insights_id == retrieved_hosts[0].insights_id
        assert host.id == retrieved_hosts[0].id


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "update_field,update_value,reporter",
    [
        pytest.param("display_name", "Updated display_name", "iqe-host-inventory"),
        pytest.param("ansible_host", "Updated ansible_host", "iqe-host-inventory"),
        pytest.param("fqdn", "updated fqdn", "iqe-host-inventory"),
        pytest.param("bios_uuid", str(uuid.uuid4()), "iqe-host-inventory", id="bios uuid for iqe"),
        pytest.param(
            "satellite_id", str(uuid.uuid4()), "iqe-host-inventory", id="satellite uuid for iqe"
        ),
        pytest.param(
            "subscription_manager_id",
            str(uuid.uuid4()),
            "iqe-host-inventory",
            id="subscription uuid for iqe",
        ),
        pytest.param("display_name", "Updated display_name", "yupana"),
        pytest.param("ansible_host", "Updated ansible_host", "yupana"),
        pytest.param("fqdn", "updated fqdn", "yupana"),
        pytest.param("bios_uuid", str(uuid.uuid4()), "yupana", id="bios uuid for yupana"),
        pytest.param("satellite_id", str(uuid.uuid4()), "yupana", id="satellite uuid for yupana"),
        pytest.param(
            "subscription_manager_id",
            str(uuid.uuid4()),
            "yupana",
            id="subscription uuid for yupana",
        ),
        pytest.param("display_name", "Updated display_name", "rhsm-conduit"),
    ],
)
def test_update_single_host(
    host_inventory: ApplicationHostInventory,
    update_field: str,
    update_value: str,
    reporter: str,
):
    """
    Confirm that a host can be updated by dropping a follow-up message.

    metadata:
        requirements: inv-host-update
        assignee: fstavela
        importance: critical
    """
    host_data = host_inventory.datagen.create_host_data()
    consumed_host_messages = host_inventory.kafka.create_host_events([host_data])
    assert len(consumed_host_messages) == 1

    consumed_host_message = consumed_host_messages[0]
    assert consumed_host_message.value.get("type") == "created"

    host = consumed_host_message.host
    host_inventory.apis.hosts.wait_for_created(host)

    host_update_data = host_data.copy()
    host_update_data[update_field] = update_value
    host_update_data["reporter"] = reporter

    consumed_updated_host_messages = host_inventory.kafka.create_host_events([host_update_data])
    assert len(consumed_updated_host_messages) == 1

    consumed_updated_host_message = consumed_updated_host_messages[0]
    assert consumed_updated_host_message.value.get("type") == "updated"

    updated_host = consumed_updated_host_message.host

    assert host.id == updated_host.id

    host_inventory.apis.hosts.wait_for_updated(host, **{update_field: update_value})  # type: ignore[arg-type]


@pytest.mark.ephemeral
@pytest.mark.parametrize("disallowed_field", ["created", "updated", "id"])
def test_disallowed_update_to_single_host(
    host_inventory: ApplicationHostInventory,
    disallowed_field: str,
):
    """Confirm that certain types of updates are ignored.
    1. Updates to created date are ignored.
    2. Updates to updated date are ignored.
    3. Updates to id are ignored.

    metadata:
        requirements: inv-mq-fields-protection
        assignee: fstavela
        importance: medium
    """
    host_data = host_inventory.datagen.create_host_data()
    consumed_host_messages = host_inventory.kafka.create_host_events([host_data])
    assert len(consumed_host_messages) == 1

    consumed_host_message = consumed_host_messages[0]
    assert consumed_host_message.value.get("type") == "created"
    host = consumed_host_message.host
    host_inventory.apis.hosts.wait_for_created(host)
    value_not_ignore = getattr(host, disallowed_field)
    if disallowed_field in ("created", "updated"):
        new_value_to_ignore = fake.iso8601(tzinfo=dt.UTC)
    else:
        new_value_to_ignore = generate_uuid()
    host_update_data = {**host_data, "id": host.id, disallowed_field: new_value_to_ignore}

    host_updated = host_inventory.kafka.create_host(host_data=host_update_data)

    if disallowed_field in ("created", "updated"):
        value_not_ignore_updated = getattr(host_updated, disallowed_field)
        if disallowed_field == "created":
            assert value_not_ignore_updated == value_not_ignore
        accuracy = get_accuracy(value_not_ignore_updated, value_not_ignore)
        host_inventory.apis.hosts.verify_not_updated(
            host, **{disallowed_field: value_not_ignore}, accuracy=accuracy
        )
    else:
        host_inventory.apis.hosts.verify_not_updated(host, **{disallowed_field: value_not_ignore})


@pytest.mark.ephemeral
def test_platform_metadata_passthrough(host_inventory: ApplicationHostInventory) -> None:
    """
    Confirm that values passed for platform_metadata are propagated to the
    events topic.

    metadata:
        requirements: inv-preserve-metadata
        assignee: fstavela
        importance: medium
    """
    host_data = host_inventory.datagen.create_host_data()
    metadata = prepare_identity_metadata(generate_user_identity(host_data["org_id"]))
    metadata["test"] = "some_value"

    event_messages = host_inventory.kafka.create_host_events([host_data], metadata=metadata)
    assert len(event_messages) == 1

    event_message = event_messages[0]
    assert event_message.value["platform_metadata"]["test"] == "some_value"


def create_host_data_for_display_name_fallback_test(
    host_data, has_fqdn, has_display_name, fqdn, display_name
):
    updated_host_data = deepcopy(host_data)
    updated_host_data["ansible_host"] = generate_display_name()
    if has_fqdn:
        updated_host_data["fqdn"] = fqdn
    else:
        updated_host_data.pop("fqdn", None)
    if has_display_name:
        updated_host_data["display_name"] = display_name
    else:
        updated_host_data.pop("display_name", None)
    return updated_host_data


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "has_display_name", [True, False], ids=["with-display_name", "without-display_name"]
)
@pytest.mark.parametrize("has_fqdn", [True, False], ids=["with-fqdn", "without-fqdn"])
def test_create_host_display_name_fallback(
    host_inventory: ApplicationHostInventory,
    has_display_name: bool,
    has_fqdn: bool,
):
    """
    Test display_name fallback on host creation when it is not provided

    JIRA: https://issues.redhat.com/browse/ESSNTL-830

    metadata:
        assignee: fstavela
        requirements: inv-display_name-fallback, inv-host-create
        importance: medium
        title: Test display_name fallback on host creation when it is not provided
    """
    fqdn = generate_display_name()
    display_name = generate_display_name()
    host_data = create_host_data_for_display_name_fallback_test(
        host_inventory.datagen.create_host_data(), has_fqdn, has_display_name, fqdn, display_name
    )

    host = host_inventory.kafka.create_host(host_data=host_data)
    response = host_inventory.apis.hosts.get_hosts_by_id_response(host.id)
    assert response.count == 1

    if has_display_name:
        assert host.display_name == display_name
        assert response.results[0].display_name == display_name
    elif has_fqdn:
        assert host.display_name == fqdn
        assert response.results[0].display_name == fqdn
    else:
        assert host.display_name == host.id
        assert response.results[0].display_name == host.id


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "has_display_name", [True, False], ids=["with-display_name", "without-display_name"]
)
@pytest.mark.parametrize("has_fqdn", [True, False], ids=["with-fqdn", "without-fqdn"])
def test_update_host_custom_display_name(
    host_inventory: ApplicationHostInventory,
    has_display_name: bool,
    has_fqdn: bool,
):
    """
    Test display_name fallback when updating host with custom display_name and
    new display_name is not provided

    JIRA: https://issues.redhat.com/browse/ESSNTL-830

    metadata:
        assignee: fstavela
        requirements: inv-display_name-fallback, inv-host-update
        importance: medium
        title: Test display_name fallback when updating host with custom display_name and
            new display_name is not provided
    """
    original_display_name = generate_display_name()
    host_data = host_inventory.datagen.create_host_data()
    host_data["fqdn"] = generate_display_name()
    host_data["display_name"] = original_display_name
    original_host = host_inventory.kafka.create_host(host_data=host_data)

    fqdn = generate_display_name()
    display_name = generate_display_name()
    updated_host_data = create_host_data_for_display_name_fallback_test(
        host_data, has_fqdn, has_display_name, fqdn, display_name
    )

    updated_host = host_inventory.kafka.create_host(host_data=updated_host_data)
    assert original_host.id == updated_host.id
    host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=updated_host.ansible_host
    )
    response = host_inventory.apis.hosts.get_hosts_by_id_response(updated_host.id)
    assert response.count == 1

    if has_display_name:
        assert updated_host.display_name == display_name
        assert response.results[0].display_name == display_name
    else:
        assert updated_host.display_name == original_display_name
        assert response.results[0].display_name == original_display_name


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "has_display_name", [True, False], ids=["with-display_name", "without-display_name"]
)
@pytest.mark.parametrize("has_fqdn", [True, False], ids=["with-fqdn", "without-fqdn"])
def test_update_host_fqdn_as_display_name(
    host_inventory: ApplicationHostInventory,
    has_display_name: bool,
    has_fqdn: bool,
):
    """
    Test display_name fallback when updating host with display_name == fqdn and
    new display_name is not provided

    JIRA: https://issues.redhat.com/browse/ESSNTL-830

    metadata:
        assignee: fstavela
        requirements: inv-display_name-fallback, inv-host-update
        importance: medium
        title: Test display_name fallback when updating host with display_name == fqdn and
            new display_name is not provided
    """
    original_fqdn = generate_display_name()
    host_data = host_inventory.datagen.create_host_data()
    host_data["fqdn"] = original_fqdn
    host_data.pop("display_name", None)
    original_host = host_inventory.kafka.create_host(host_data=host_data)

    fqdn = generate_display_name()
    display_name = generate_display_name()
    updated_host_data = create_host_data_for_display_name_fallback_test(
        host_data, has_fqdn, has_display_name, fqdn, display_name
    )

    updated_host = host_inventory.kafka.create_host(host_data=updated_host_data)
    assert original_host.id == updated_host.id
    host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=updated_host.ansible_host
    )
    response = host_inventory.apis.hosts.get_hosts_by_id_response(updated_host.id)
    assert response.count == 1

    if has_display_name:
        assert updated_host.display_name == display_name
        assert response.results[0].display_name == display_name
    elif has_fqdn:
        assert updated_host.display_name == fqdn
        assert response.results[0].display_name == fqdn
    else:
        assert updated_host.display_name == original_fqdn
        assert response.results[0].display_name == original_fqdn


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "has_display_name", [True, False], ids=["with-display_name", "without-display_name"]
)
@pytest.mark.parametrize("has_fqdn", [True, False], ids=["with-fqdn", "without-fqdn"])
def test_update_host_host_id_as_display_name(
    host_inventory: ApplicationHostInventory,
    has_display_name: bool,
    has_fqdn: bool,
):
    """
    Test display_name fallback when updating host with display_name == host ID and
    new display_name is not provided

    JIRA: https://issues.redhat.com/browse/ESSNTL-830

    metadata:
        assignee: fstavela
        requirements: inv-display_name-fallback, inv-host-update
        importance: medium
        title: Test display_name fallback when updating host with display_name == host ID and
            new display_name is not provided
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data.pop("fqdn", None)
    host_data.pop("display_name", None)
    original_host = host_inventory.kafka.create_host(host_data=host_data)

    fqdn = generate_display_name()
    display_name = generate_display_name()
    updated_host_data = create_host_data_for_display_name_fallback_test(
        host_data, has_fqdn, has_display_name, fqdn, display_name
    )

    updated_host = host_inventory.kafka.create_host(host_data=updated_host_data)
    assert original_host.id == updated_host.id
    host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=updated_host.ansible_host
    )
    response = host_inventory.apis.hosts.get_hosts_by_id_response(updated_host.id)
    assert response.count == 1

    if has_display_name:
        assert updated_host.display_name == display_name
        assert response.results[0].display_name == display_name
    elif has_fqdn:
        assert updated_host.display_name == fqdn
        assert response.results[0].display_name == fqdn
    else:
        assert updated_host.display_name == updated_host.id
        assert response.results[0].display_name == updated_host.id


@pytest.mark.ephemeral
def test_mq_create_host_with_org_id_key(
    host_inventory: ApplicationHostInventory, hbi_default_org_id: str
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-13496

    metadata:
        assignee: fstavela
        requirements: inv-host-create, inv-accept-mq-key
        importance: high
        title: Test creating a host with populating kafka key with org_id
    """
    host_inventory.kafka.create_host(key=hbi_default_org_id)


@pytest.mark.ephemeral
def test_mq_update_host_with_org_id_key(
    host_inventory: ApplicationHostInventory, hbi_default_org_id: str
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-13496

    metadata:
        assignee: fstavela
        requirements: inv-host-update, inv-accept-mq-key
        importance: high
        title: Test updating a host with populating kafka key with org_id
    """
    host_data = host_inventory.datagen.create_host_data()
    host = host_inventory.kafka.create_host(host_data=host_data)

    host_data["display_name"] = generate_display_name()
    updated_host = host_inventory.kafka.create_host(host_data=host_data, key=hbi_default_org_id)
    assert updated_host.display_name == host_data["display_name"]
    host_inventory.apis.hosts.wait_for_updated(host, display_name=host_data["display_name"])


@pytest.mark.ephemeral
def test_create_host_to_compare_last_check_in_with_updated(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-15759

    metadata:
      requirements: inv-hosts-last_check_in-field, inv-host-update, inv-host-create
      assignee: zabikeno
      importance: high
      title: Test 'last_check_in' and 'updated' is equals for new uploaded host
            (same equals for updated new host via kafka)
    """
    host_data = host_inventory.datagen.create_host_data()
    host = host_inventory.kafka.create_host(host_data)

    assert_datetimes_equal(host.last_check_in, host.updated, accuracy=timedelta(milliseconds=100))

    response = host_inventory.apis.hosts.get_hosts(id=host.id)
    host_response = response[0]
    assert_datetimes_equal(
        host_response.last_check_in, host_response.updated, accuracy=timedelta(milliseconds=100)
    )

    host_update_data = host_data.copy()
    host_update_data["reporter"] = "rhsm-conduit"
    host_updated = host_inventory.kafka.create_host(host_data=host_update_data)

    assert_datetimes_equal(
        host_updated.last_check_in, host_updated.updated, accuracy=timedelta(milliseconds=100)
    )

    assert host_updated.last_check_in != host_response.last_check_in
    assert host_updated.updated != host_response.updated


@pytest.mark.ephemeral
@pytest.mark.manual
def test_mq_batching_race_condition(host_inventory: ApplicationHostInventory):
    """
    This test reproduces the MQ race condition issue when the same host is created 2 times in
    Inventory after multiple reporters send the payload at almost the same time.

    To run this test, you have to deploy host-inventory with enabled MQ batch processing:
    `bonfire deploy ... -p host-inventory/MQ_DB_BATCH_MAX_MESSAGES=10`

    Tests marked with `@pytest.mark.manual` are skipped by default. To run them, remove the marker.

    https://issues.redhat.com/browse/RHINENG-17921

    metadata:
        assignee: fstavela
        requirements: inv-host-create
        importance: high
        title: Reproduce MQ race condition issue when batched MQ processing is enabled
        automation_status: not_automated
    """
    # Generate random payload message, populate rhc_client_id, don't populate rhc_config_state
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["rhc_client_id"] = generate_uuid()
    host_data["system_profile"].pop("rhc_config_state", None)
    host_data["reporter"] = "puptoo"

    # Let 2nd payload message be the same, populate rhc_config_state, don't populate rhc_client_id
    host_data2 = deepcopy(host_data)
    host_data2["system_profile"]["rhc_config_state"] = generate_uuid()
    host_data2["system_profile"].pop("rhc_client_id", None)
    host_data2["reporter"] = "cloud-connector"

    # Send both messages at the same time, so they are in the same batch of processed messages
    host_inventory.kafka.produce_host_update_messages([host_data, host_data2], flush=True)
    sleep(2)

    # Check that only one host was created (and then updated with the second message)
    response_hosts = host_inventory.apis.hosts.get_hosts(insights_id=host_data["insights_id"])
    assert len(response_hosts) == 1
    response_host = response_hosts[0]
    assert "puptoo" in response_host.per_reporter_staleness
    assert "cloud-connector" in response_host.per_reporter_staleness

    # Check that both rhc_config_state and rhc_client_id are populated in Inventory
    response_sp_res = host_inventory.apis.hosts.get_hosts_system_profile(response_host)
    assert len(response_sp_res) == 1
    response_sp = response_sp_res[0]
    assert response_sp.system_profile.rhc_client_id == host_data["system_profile"]["rhc_client_id"]
    assert (
        response_sp.system_profile.rhc_config_state
        == host_data2["system_profile"]["rhc_config_state"]
    )


@pytest.mark.ephemeral
@pytest.mark.manual
def test_mq_batching_different_hosts(host_inventory: ApplicationHostInventory):
    """
    To run this test, you have to deploy host-inventory with enabled MQ batch processing:
    `bonfire deploy ... -p host-inventory/MQ_DB_BATCH_MAX_MESSAGES=10`

    Tests marked with `@pytest.mark.manual` are skipped by default. To run them, remove the marker.

    https://issues.redhat.com/browse/RHINENG-17921

    metadata:
        assignee: fstavela
        requirements: inv-host-create
        importance: high
        title: Test that HBI creates 2 hosts when it receives 2 different payloads with MQ batching
        automation_status: not_automated
    """
    # Generate 2 random payload messages
    hosts_data = host_inventory.datagen.create_n_hosts_data(
        2, display_name=generate_display_name()
    )

    # Send both messages at the same time, so they are in the same batch of processed messages
    host_inventory.kafka.produce_host_update_messages(hosts_data, flush=True)
    sleep(2)

    response_hosts = host_inventory.apis.hosts.get_hosts(
        display_name=hosts_data[0]["display_name"]
    )
    logger.info(f"Number of hosts: {len(response_hosts)}")
    for response_host in response_hosts:
        logger.info(response_host.to_dict())

    # Check that two hosts were created
    assert len(response_hosts) == 2
    assert len({response_host.id for response_host in response_hosts}) == 2
    assert {response_host.insights_id for response_host in response_hosts} == {
        host["insights_id"] for host in hosts_data
    }


@pytest.mark.ephemeral
@pytest.mark.manual
def test_mq_batching_dedup_from_db(host_inventory: ApplicationHostInventory):
    """
    To run this test, you have to deploy host-inventory with enabled MQ batch processing:
    `bonfire deploy ... -p host-inventory/MQ_DB_BATCH_MAX_MESSAGES=10`

    Tests marked with `@pytest.mark.manual` are skipped by default. To run them, remove the marker.

    https://issues.redhat.com/browse/RHINENG-17921

    metadata:
        assignee: fstavela
        requirements: inv-host-create
        importance: high
        title: Test that HBI updates host from DB if not found in the current MQ batch
        automation_status: not_automated
    """
    # Create a host and wait until the MQ batch is processed and the host is created in DB
    host_data = host_inventory.datagen.create_host_data(display_name=generate_display_name())
    host_data["system_profile"]["rhc_client_id"] = generate_uuid()
    host_data["system_profile"].pop("rhc_config_state", None)
    host_data["reporter"] = "puptoo"
    host = host_inventory.kafka.create_host(host_data, wait_for_created=True)

    # In the next batch, send one message for a new host and one to update the existing host
    host_data2 = deepcopy(host_data)
    host_data2["system_profile"]["rhc_config_state"] = generate_uuid()
    host_data2["system_profile"].pop("rhc_client_id", None)
    host_data2["reporter"] = "cloud-connector"
    hosts_data = [
        host_inventory.datagen.create_host_data(display_name=host_data["display_name"]),
        host_data2,
    ]

    # Send both messages at the same time, so they are in the same batch of processed messages
    host_inventory.kafka.produce_host_update_messages(hosts_data, flush=True)
    sleep(2)

    response_hosts = host_inventory.apis.hosts.get_hosts(display_name=host_data["display_name"])
    logger.info(f"Number of hosts: {len(response_hosts)}")
    for response_host in response_hosts:
        logger.info(response_host.to_dict())
        response_sp = host_inventory.apis.hosts.get_hosts_system_profile(response_host)[0]
        logger.info(f"rhc_client_id: {response_sp.system_profile.rhc_client_id}")
        logger.info(f"rhc_config_state: {response_sp.system_profile.rhc_config_state}")

    # Check that two hosts were created
    assert len(response_hosts) == 2
    assert len({response_host.id for response_host in response_hosts}) == 2
    assert {response_host.insights_id for response_host in response_hosts} == {
        host["insights_id"] for host in hosts_data
    }

    # Check that the original host was correctly updated
    response_host = host_inventory.apis.hosts.get_host_by_id(host)
    assert "puptoo" in response_host.per_reporter_staleness
    assert "cloud-connector" in response_host.per_reporter_staleness

    # Check that both rhc_config_state and rhc_client_id are populated in Inventory
    response_sp_res = host_inventory.apis.hosts.get_hosts_system_profile(host)
    assert len(response_sp_res) == 1
    response_sp = response_sp_res[0]
    assert response_sp.system_profile.rhc_client_id == host_data["system_profile"]["rhc_client_id"]
    assert (
        response_sp.system_profile.rhc_config_state
        == host_data2["system_profile"]["rhc_config_state"]
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize("reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_update_display_name_ignored_after_created_by_puptoo(
    host_inventory: ApplicationHostInventory,
    reporter: str,
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19514

    metadata:
        assignee: fstavela
        requirements: inv-rhsm-display_name
        importance: high
        title: Test that HBI ignores display_name updates from RHSM if it has been set by puptoo
    """
    # Create a host with display_name as puptoo
    original_display_name = generate_display_name()
    host_data = host_inventory.datagen.create_host_data(
        display_name=original_display_name, reporter="puptoo"
    )
    host = host_inventory.kafka.create_host(host_data)
    assert host.display_name == original_display_name
    assert host.reporter == "puptoo"

    # Try to update the display_name as RHSM
    host_data["display_name"] = generate_display_name()
    host_data["reporter"] = reporter
    updated_host = host_inventory.kafka.create_host(host_data)
    assert updated_host.display_name == original_display_name
    assert updated_host.reporter == reporter

    response_host = host_inventory.apis.hosts.get_host_by_id(host)
    assert response_host.display_name == original_display_name
    assert response_host.reporter == reporter


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "orig_reporter",
    (
        "puptoo",
        "yupana",
        "yuptoo",
        "satellite",
        "discovery",
        "rhsm-conduit",
        "rhsm-system-profile-bridge",
        "cloud-connector",
        "test-reporter",
    ),
)
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_update_display_name_ignored_after_updated_by_api(
    host_inventory: ApplicationHostInventory,
    orig_reporter: str,
    rhsm_reporter: str,
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-19514

    metadata:
        assignee: fstavela
        requirements: inv-rhsm-display_name
        importance: high
        title: Test that HBI ignores display_name updates from RHSM if it has been set via API (UI)
    """
    # Create a host without setting the display_name
    host_data = host_inventory.datagen.create_host_data(reporter=orig_reporter)
    host_data.pop("display_name", None)
    host = host_inventory.kafka.create_host(host_data)
    assert host.display_name == host.fqdn
    assert host.reporter == orig_reporter

    # Update the display_name via API
    api_display_name = generate_display_name()
    host_inventory.apis.hosts.patch_hosts(host, display_name=api_display_name)

    response_host = host_inventory.apis.hosts.get_host_by_id(host)
    assert response_host.display_name == api_display_name
    assert response_host.reporter == orig_reporter

    # Try to update the display_name as RHSM
    host_data["display_name"] = generate_display_name()
    host_data["reporter"] = rhsm_reporter
    updated_host = host_inventory.kafka.create_host(host_data)
    assert updated_host.display_name == api_display_name
    assert updated_host.reporter == rhsm_reporter

    response_host = host_inventory.apis.hosts.get_host_by_id(host)
    assert response_host.display_name == api_display_name
    assert response_host.reporter == rhsm_reporter
