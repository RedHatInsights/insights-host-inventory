import logging
from copy import deepcopy
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import ErrorNotificationWrapper
from iqe_host_inventory.modeling.wrappers import KafkaMessageNotFoundError
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_provider_type
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.kafka_utils import prepare_identity_metadata
from iqe_host_inventory.utils.notifications_utils import check_notifications_data
from iqe_host_inventory.utils.notifications_utils import check_notifications_headers

pytestmark = [pytest.mark.backend, pytest.mark.kafka]

logger = logging.getLogger(__name__)


@pytest.fixture()
def system_identity_blank_org_id(get_system_identity):
    identity = deepcopy(get_system_identity)
    identity["identity"]["org_id"] = ""
    return identity


def check_error_notifications_headers(headers: dict[str, str], request_id: str) -> None:
    check_notifications_headers(headers, "validation-error", request_id)


def check_error_notifications_data(msg: ErrorNotificationWrapper, org_id: str) -> None:
    check_notifications_data(msg, event_type="validation-error", org_id=org_id)

    # context
    assert set(msg.context.keys()) == {"event_name", "display_name"}, set(msg.context.keys())
    assert msg.event_name == "Host Validation Error", f"{msg.event_name} != Host Validation Error"
    assert msg.context["display_name"] == msg.display_name, (
        f"{msg.context['display_name']} != {msg.display_name}"
    )

    # events[0].payload
    assert set(msg.payload.keys()) == {
        "request_id",
        "display_name",
        "canonical_facts",
        "error",
    }, set(msg.payload.keys())

    # events[0].payload.error
    assert type(msg.error) is dict
    assert set(msg.error.keys()) == {"code", "message", "stack_trace", "severity"}, set(
        msg.error.keys()
    )
    assert msg.code == "VE001", f"{msg.code} != VE001"
    assert msg.stack_trace is None
    assert msg.severity == "error", f"{msg.severity} != error"


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_account_number", [True, False])
def test_notifications_kafka_error_create_wrong_provider_fields(
    host_inventory: ApplicationHostInventory,
    hbi_default_account_number: str,
    with_account_number: bool,
) -> None:
    """
    Test that when I try to create a host with only one of the provider fields,
    Inventory will produce kafka notification message about the failure.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2965

    metadata:
        requirements: inv-notifications-validation-error
        assignee: fstavela
        importance: high
        title: Test notifications after creating host with only one provider field
    """
    host_data = host_inventory.datagen.create_host_data()
    if with_account_number:
        host_data["account"] = hbi_default_account_number
    host_data["provider_id"] = generate_uuid()
    host_data.pop("provider_type", None)

    metadata = {"request_id": generate_uuid()}
    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata, flush=True)
    msg = host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )

    assert msg.display_name == host_data["display_name"]
    assert msg.request_id == metadata["request_id"]
    assert msg.canonical_facts.get("insights_id") == host_data["insights_id"]
    assert (
        msg.message == "{'_schema': ['provider_type and provider_id are both required.']}; "
        "Invalid data: {'_schema': '<missing>'}"
    )

    check_error_notifications_data(msg, host_data["org_id"])
    check_error_notifications_headers(msg.headers, metadata["request_id"])


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("with_account_number", [True, False])
def test_notifications_kafka_error_create_wrong_host_format(
    host_inventory: ApplicationHostInventory,
    hbi_default_account_number: str,
    with_account_number: bool,
) -> None:
    """
    Test that when I try to create a host with wrong host field format,
    Inventory will produce kafka notification message about the failure.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2965

    metadata:
        requirements: inv-notifications-validation-error
        assignee: fstavela
        importance: high
        title: Test notifications after creating host with wrong host field format
    """
    host_data = host_inventory.datagen.create_host_data()
    if with_account_number:
        host_data["account"] = hbi_default_account_number
    host_data["subscription_manager_id"] = generate_display_name()
    metadata = {"request_id": generate_uuid()}

    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata, flush=True)
    msg = host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    logger.info(f"Received error message: {msg.value}")

    assert msg.display_name == host_data["display_name"]
    assert msg.request_id == metadata["request_id"]
    assert msg.canonical_facts.get("insights_id") == host_data["insights_id"]
    assert (
        msg.canonical_facts.get("subscription_manager_id") == host_data["subscription_manager_id"]
    )
    assert (
        msg.message == "{'subscription_manager_id': ['Invalid value.']}; "
        f"Invalid data: {{'subscription_manager_id': '{host_data['subscription_manager_id']}'}}"
    )

    check_error_notifications_data(msg, host_data["org_id"])
    check_error_notifications_headers(msg.headers, metadata["request_id"])


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("with_account_number", [True, False])
def test_notifications_kafka_error_create_wrong_sp_format(
    host_inventory: ApplicationHostInventory,
    hbi_default_account_number: str,
    with_account_number: bool,
) -> None:
    """
    Test that when I try to create a host with wrong system profile field format,
    Inventory will produce kafka notification message about the failure.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2965

    metadata:
        requirements: inv-notifications-validation-error
        assignee: fstavela
        importance: high
        title: Test notifications after creating host with wrong system profile field format
    """
    host_data = host_inventory.datagen.create_host_data()
    if with_account_number:
        host_data["account"] = hbi_default_account_number
    host_data["system_profile"]["rhc_client_id"] = generate_uuid()[:30]
    metadata = {"request_id": generate_uuid()}

    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata, flush=True)
    msg = host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    logger.info(f"Received error message: {msg.value}")

    assert msg.display_name == host_data["display_name"]
    assert msg.request_id == metadata["request_id"]
    assert msg.canonical_facts.get("insights_id") == host_data["insights_id"]
    assert msg.message.startswith(
        "{'system_profile': [\"System profile does not conform to schema.\\n"
        f"'{host_data['system_profile']['rhc_client_id']}' does not match "
        "'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'"
    )

    check_error_notifications_data(msg, host_data["org_id"])
    check_error_notifications_headers(msg.headers, metadata["request_id"])


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_account_number", [True, False])
def test_notifications_kafka_error_create_wrong_identity(
    host_inventory: ApplicationHostInventory,
    system_identity_blank_org_id: dict[str, Any],
    hbi_default_account_number: str,
    with_account_number: bool,
) -> None:
    """
    Test that when I try to create a host with invalid identity,
    Inventory will produce kafka notification message about the failure.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2965

    metadata:
        requirements: inv-notifications-validation-error
        assignee: fstavela
        importance: high
        title: Test notifications after creating host with invalid identity
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["owner_id"] = system_identity_blank_org_id["identity"]["system"][
        "cn"
    ]
    if with_account_number:
        host_data["account"] = hbi_default_account_number

    metadata = prepare_identity_metadata(system_identity_blank_org_id)
    metadata["request_id"] = generate_uuid()
    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata, flush=True)
    msg = host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    logger.info(f"Received error message: {msg.value}")

    assert msg.display_name == host_data["display_name"]
    assert msg.request_id == metadata["request_id"]
    assert msg.canonical_facts.get("insights_id") == host_data["insights_id"]
    assert msg.message == "The org_id in the identity does not match the org_id in the host."

    check_error_notifications_data(msg, host_data["org_id"])
    check_error_notifications_headers(msg.headers, metadata["request_id"])


@pytest.mark.ephemeral
def test_notifications_kafka_error_update_wrong_provider_fields(
    host_inventory: ApplicationHostInventory,
):
    """
    Test that when I try to update a host with only one of the provider fields,
    Inventory will produce kafka notification message about the failure.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2965

    metadata:
        requirements: inv-notifications-validation-error
        assignee: fstavela
        importance: medium
        title: Test notifications after updating host with only one provider field
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["provider_id"] = generate_uuid()
    host_data["provider_type"] = generate_provider_type()
    host_inventory.kafka.create_host(host_data)

    host_data.pop("provider_type", None)
    metadata = {"request_id": generate_uuid()}
    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata, flush=True)
    msg = host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    logger.info(f"Received error message: {msg.value}")

    assert msg.display_name == host_data["display_name"]
    assert msg.request_id == metadata["request_id"]
    assert msg.canonical_facts.get("insights_id") == host_data["insights_id"]
    assert (
        msg.message == "{'_schema': ['provider_type and provider_id are both required.']}; "
        "Invalid data: {'_schema': '<missing>'}"
    )

    check_error_notifications_data(msg, host_data["org_id"])
    check_error_notifications_headers(msg.headers, metadata["request_id"])


@pytest.mark.ephemeral
def test_notifications_kafka_error_update_wrong_host_format(
    host_inventory: ApplicationHostInventory,
):
    """
    Test that when I try to update a host with wrong host field format,
    Inventory will produce kafka notification message about the failure.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2965

    metadata:
        requirements: inv-notifications-validation-error
        assignee: fstavela
        importance: medium
        title: Test notifications after updating host with wrong host field format
    """
    host_data = host_inventory.datagen.create_host_data()
    host_inventory.kafka.create_host(host_data)

    host_data["subscription_manager_id"] = generate_display_name()
    metadata = {"request_id": generate_uuid()}
    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata, flush=True)
    msg = host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    logger.info(f"Received error message: {msg.value}")

    assert msg.display_name == host_data["display_name"]
    assert msg.request_id == metadata["request_id"]
    assert msg.canonical_facts.get("insights_id") == host_data["insights_id"]
    assert (
        msg.canonical_facts.get("subscription_manager_id") == host_data["subscription_manager_id"]
    )
    assert (
        msg.message == "{'subscription_manager_id': ['Invalid value.']}; "
        f"Invalid data: {{'subscription_manager_id': '{host_data['subscription_manager_id']}'}}"
    )

    check_error_notifications_data(msg, host_data["org_id"])
    check_error_notifications_headers(msg.headers, metadata["request_id"])


@pytest.mark.ephemeral
def test_notifications_kafka_error_update_wrong_sp_format(
    host_inventory: ApplicationHostInventory,
):
    """
    Test that when I try to update a host with wrong system profile field format,
    Inventory will produce kafka notification message about the failure.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2965

    metadata:
        requirements: inv-notifications-validation-error
        assignee: fstavela
        importance: medium
        title: Test notifications after updating host with wrong system profile field format
    """
    host_data = host_inventory.datagen.create_host_data()
    host_inventory.kafka.create_host(host_data)

    host_data["system_profile"]["rhc_client_id"] = generate_uuid()[:30]
    metadata = {"request_id": generate_uuid()}
    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata, flush=True)
    msg = host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    logger.info(f"Received error message: {msg.value}")

    assert msg.display_name == host_data["display_name"]
    assert msg.request_id == metadata["request_id"]
    assert msg.canonical_facts.get("insights_id") == host_data["insights_id"]
    assert msg.message.startswith(
        "{'system_profile': [\"System profile does not conform to schema.\\n"
        f"'{host_data['system_profile']['rhc_client_id']}' does not match "
        "'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'"
    )

    check_error_notifications_data(msg, host_data["org_id"])
    check_error_notifications_headers(msg.headers, metadata["request_id"])


@pytest.mark.ephemeral
def test_notifications_kafka_error_update_wrong_identity(
    host_inventory: ApplicationHostInventory,
    system_identity_blank_org_id: dict,
):
    """
    Test that when I try to update a host with invalid identity,
    Inventory will produce kafka notification message about the failure.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2965

    metadata:
        requirements: inv-notifications-validation-error
        assignee: fstavela
        importance: medium
        title: Test notifications after updating host with invalid identity
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["owner_id"] = system_identity_blank_org_id["identity"]["system"][
        "cn"
    ]
    host_inventory.kafka.create_host(host_data)

    metadata = prepare_identity_metadata(system_identity_blank_org_id)
    metadata["request_id"] = generate_uuid()
    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata, flush=True)
    msg = host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    logger.info(f"Received error message: {msg.value}")

    assert msg.display_name == host_data["display_name"]
    assert msg.request_id == metadata["request_id"]
    assert msg.canonical_facts.get("insights_id") == host_data["insights_id"]
    assert msg.message == "The org_id in the identity does not match the org_id in the host."

    check_error_notifications_data(msg, host_data["org_id"])
    check_error_notifications_headers(msg.headers, metadata["request_id"])


@pytest.mark.ephemeral
def test_notifications_kafka_error_should_not_trigger(host_inventory: ApplicationHostInventory):
    """
    Test that notification is not produced when host was created successfully

    JIRA: https://issues.redhat.com/browse/ESSNTL-2965

    metadata:
        requirements: inv-notifications-validation-error
        assignee: fstavela
        importance: high
        negative: true
        title: Test that notification is not produced when host was created successfully
    """
    host_data = host_inventory.datagen.create_host_data()
    host = host_inventory.kafka.create_host(host_data)
    assert host.display_name == host_data["display_name"]

    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.wait_for_filtered_error_message(
            ErrorNotificationWrapper.display_name, host.display_name, timeout=3
        )
