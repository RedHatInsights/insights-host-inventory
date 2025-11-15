from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any
from typing import cast
from uuid import UUID

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import ErrorNotificationWrapper
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.kafka_utils import prepare_identity_metadata

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


@pytest.fixture(
    params=[
        pytest.param(lf("system_identity_correct"), id="system"),
        pytest.param(lf("user_identity_correct"), id="user"),
        pytest.param(lf("service_account_identity_correct"), id="service_account"),
    ]
)
def kafka_correct_identity(request) -> dict[str, Any]:
    return request.param


@pytest.fixture()
def empty_identity():
    return {"identity": {}}


@pytest.fixture()
def empty_dict():
    return {}


@pytest.fixture()
def identity_blank_org_id(kafka_correct_identity: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(kafka_correct_identity)
    identity["identity"]["org_id"] = ""
    return identity


@pytest.fixture()
def identity_without_org_id(kafka_correct_identity: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(kafka_correct_identity)
    del identity["identity"]["org_id"]
    return identity


@pytest.fixture()
def identity_invalid_type(kafka_correct_identity: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(kafka_correct_identity)
    identity["identity"]["type"] = "Invalid"
    return identity


@pytest.fixture()
def identity_blank_type(kafka_correct_identity: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(kafka_correct_identity)
    identity["identity"]["type"] = ""
    return identity


@pytest.fixture()
def identity_without_type(kafka_correct_identity: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(kafka_correct_identity)
    del identity["identity"]["type"]
    return identity


@pytest.fixture(params=["invalid-auth", "classic-proxy"])
def identity_invalid_auth_type(request, kafka_correct_identity: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(kafka_correct_identity)
    identity["identity"]["auth_type"] = request.param
    return identity


@pytest.fixture()
def identity_blank_auth_type(kafka_correct_identity: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(kafka_correct_identity)
    identity["identity"]["auth_type"] = ""
    return identity


@pytest.fixture()
def identity_without_auth_type(kafka_correct_identity: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(kafka_correct_identity)
    del identity["identity"]["auth_type"]
    return identity


@pytest.fixture()
def system_identity_blank_cn(system_identity_correct: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(system_identity_correct)
    identity["identity"]["system"]["cn"] = ""
    return identity


@pytest.fixture()
def system_identity_without_cn(system_identity_correct: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(system_identity_correct)
    del identity["identity"]["system"]["cn"]
    return identity


@pytest.fixture()
def system_identity_invalid_cert_type(system_identity_correct: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(system_identity_correct)
    identity["identity"]["system"]["cert_type"] = "invalid"
    return identity


@pytest.fixture()
def system_identity_blank_cert_type(system_identity_correct: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(system_identity_correct)
    identity["identity"]["system"]["cert_type"] = ""
    return identity


@pytest.fixture()
def system_identity_without_cert_type(system_identity_correct: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(system_identity_correct)
    del identity["identity"]["system"]["cert_type"]
    return identity


@pytest.fixture()
def system_identity_blank_system(system_identity_correct: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(system_identity_correct)
    del identity["identity"]["system"]["cn"]
    del identity["identity"]["system"]["cert_type"]
    return identity


@pytest.fixture()
def system_identity_without_system(system_identity_correct: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(system_identity_correct)
    del identity["identity"]["system"]
    return identity


@pytest.fixture()
def service_account_identity_blank_client_id(
    service_account_identity_correct: dict[str, Any],
) -> dict[str, Any]:
    identity = deepcopy(service_account_identity_correct)
    identity["identity"]["service_account"]["client_id"] = ""
    return identity


@pytest.fixture()
def service_account_identity_without_client_id(
    service_account_identity_correct: dict[str, Any],
) -> dict[str, Any]:
    identity = deepcopy(service_account_identity_correct)
    del identity["identity"]["service_account"]["client_id"]
    return identity


@pytest.fixture()
def service_account_identity_blank_username(
    service_account_identity_correct: dict[str, Any],
) -> dict[str, Any]:
    identity = deepcopy(service_account_identity_correct)
    identity["identity"]["service_account"]["username"] = ""
    return identity


@pytest.fixture()
def service_account_identity_without_username(
    service_account_identity_correct: dict[str, Any],
) -> dict[str, Any]:
    identity = deepcopy(service_account_identity_correct)
    del identity["identity"]["service_account"]["username"]
    return identity


@pytest.fixture()
def service_account_identity_blank_service_account(
    service_account_identity_correct: dict[str, Any],
) -> dict[str, Any]:
    identity = deepcopy(service_account_identity_correct)
    del identity["identity"]["service_account"]["client_id"]
    del identity["identity"]["service_account"]["username"]
    return identity


@pytest.fixture()
def service_account_identity_without_service_account(
    service_account_identity_correct: dict[str, Any],
) -> dict[str, Any]:
    identity = deepcopy(service_account_identity_correct)
    del identity["identity"]["service_account"]
    return identity


@pytest.fixture()
def prepare_host_for_updates(
    host_inventory: ApplicationHostInventory, user_identity_correct: dict
):
    def _prepare_host(owner_id: str | None = None):
        metadata = prepare_identity_metadata(user_identity_correct)
        host_data = host_inventory.datagen.create_host_data()
        if owner_id is not None:
            host_data["system_profile"]["owner_id"] = owner_id
        host = host_inventory.kafka.create_host(metadata=metadata, host_data=host_data)
        return {"host": host, "data": host_data}

    return _prepare_host


@pytest.mark.ephemeral
def test_mq_create_system_host_all_correct(
    host_inventory: ApplicationHostInventory,
    system_identity_correct: dict,
):
    """Test creating host via kafka with "system" identity and correct owner_id
    metadata:
        requirements: inv-host-create, inv-mq-identity-validation
        importance: high
        assignee: fstavela
        title: Create host via kafka with "system" identity and correct owner_id
    """
    metadata = prepare_identity_metadata(system_identity_correct)
    owner_id = system_identity_correct["identity"]["system"]["cn"]
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["owner_id"] = owner_id
    host = host_inventory.kafka.create_host(metadata=metadata, host_data=host_data)
    host_inventory.apis.hosts.wait_for_updated(host.id, id=host.id)
    host_inventory.apis.hosts.wait_for_system_profile_updated(host.id, owner_id=owner_id)


@pytest.mark.ephemeral
def test_mq_update_system_host_all_correct(
    host_inventory: ApplicationHostInventory,
    system_identity_correct: dict,
    prepare_host_for_updates,
):
    """Test updating host via kafka with "system" identity and correct owner_id
    metadata:
        requirements: inv-host-update, inv-mq-identity-validation
        importance: high
        assignee: fstavela
        title: Update host via kafka with "system" identity and correct owner_id
    """
    owner_id = system_identity_correct["identity"]["system"]["cn"]
    prepared_host = prepare_host_for_updates(owner_id)
    host_data = prepared_host["data"]
    host = prepared_host["host"]

    metadata = prepare_identity_metadata(system_identity_correct)
    new_display_name = generate_display_name()
    updated_host_data = dict(host_data, display_name=new_display_name)
    updated_host = host_inventory.kafka.create_host(metadata=metadata, host_data=updated_host_data)
    assert updated_host.id == host.id
    host_inventory.apis.hosts.wait_for_updated(host.id, display_name=new_display_name)


@pytest.mark.ephemeral
@pytest.mark.parametrize("has_owner_id", [True, False])
def test_mq_create_non_system_host_all_correct(
    host_inventory: ApplicationHostInventory,
    non_system_identity_correct: dict,
    has_owner_id: bool,
):
    """Test creating host via kafka with "user" identity
    metadata:
        requirements: inv-host-create, inv-mq-identity-validation
        importance: high
        assignee: fstavela
        title: Create host via kafka with "user" identity
    """
    metadata = prepare_identity_metadata(non_system_identity_correct)
    host_data = host_inventory.datagen.create_host_data()
    owner_id = generate_uuid()
    if has_owner_id:
        host_data["system_profile"]["owner_id"] = owner_id
    host = host_inventory.kafka.create_host(metadata=metadata, host_data=host_data)
    api_host = host_inventory.apis.hosts.get_host_by_id(host.id)
    assert api_host.id == host.id

    if has_owner_id:
        host_inventory.apis.hosts.wait_for_system_profile_updated(host.id, owner_id=owner_id)


@pytest.mark.ephemeral
@pytest.mark.parametrize("original_has_owner_id", [True, False])
@pytest.mark.parametrize("updated_has_owner_id", [True, False])
def test_mq_update_non_system_host_all_correct(
    host_inventory: ApplicationHostInventory,
    non_system_identity_correct: dict,
    prepare_host_for_updates,
    original_has_owner_id: bool,
    updated_has_owner_id: bool,
):
    """Test updating host via kafka with "user" identity
    metadata:
        requirements: inv-host-update, inv-mq-identity-validation
        importance: high
        assignee: fstavela
        title: Update host via kafka with "user" identity
    """
    original_owner_id = generate_uuid()
    if original_has_owner_id:
        prepared_host = prepare_host_for_updates(original_owner_id)
    else:
        prepared_host = prepare_host_for_updates()
    host_data = prepared_host["data"]
    host = prepared_host["host"]

    metadata = prepare_identity_metadata(non_system_identity_correct)
    new_display_name = generate_display_name()
    updated_owner_id = generate_uuid()
    updated_host_data = {**host_data, "display_name": new_display_name}
    if updated_has_owner_id:
        spf = cast(dict[str, Any], updated_host_data["system_profile"])
        updated_host_data["system_profile"] = {**spf, "owner_id": updated_owner_id}
    updated_host = host_inventory.kafka.create_host(metadata=metadata, host_data=updated_host_data)
    assert host.id == updated_host.id

    host_inventory.apis.hosts.wait_for_updated(host.id, display_name=new_display_name)

    if updated_has_owner_id:
        expected_owner_id = updated_owner_id
    elif original_has_owner_id:
        expected_owner_id = original_owner_id
    else:
        expected_owner_id = None
    host_inventory.apis.hosts.wait_for_system_profile_updated(host.id, owner_id=expected_owner_id)


@pytest.mark.ephemeral
@pytest.mark.parametrize("omit_metadata", [True, False])
@pytest.mark.parametrize("reporter", ["rhsm-conduit", "rhsm-system-profile-bridge"])
def test_mq_create_system_host_rhsm_reporter(
    host_inventory: ApplicationHostInventory,
    omit_metadata: bool,
    reporter: str,
):
    """Test creating host via kafka as rhsm reporter
    If provided subscription_manager_id is in hex uuid format (without dashes),
    inventory should transform it to the canonical form (with dashes) when setting owner_id

    metadata:
        requirements: inv-host-create, inv-mq-identity-exception-rhsm
        importance: high
        assignee: fstavela
        title: Create host via kafka as rhsm reporter
    """
    rhsm_id = generate_uuid()
    host_data = host_inventory.datagen.create_host_data()
    host_data["reporter"] = reporter
    host_data["subscription_manager_id"] = rhsm_id
    host = host_inventory.kafka.create_host(
        host_data=host_data, omit_identity=True, omit_metadata=omit_metadata
    )
    host_inventory.apis.hosts.wait_for_updated(host.id, subscription_manager_id=rhsm_id)
    host_inventory.apis.hosts.wait_for_system_profile_updated(host.id, owner_id=str(UUID(rhsm_id)))


@pytest.mark.ephemeral
@pytest.mark.parametrize("update_rhsm_id", [True, False])
@pytest.mark.parametrize("omit_metadata", [True, False])
@pytest.mark.parametrize("reporter", ["rhsm-conduit", "rhsm-system-profile-bridge"])
def test_mq_update_system_host_rhsm_reporter(
    host_inventory: ApplicationHostInventory,
    update_rhsm_id: bool,
    omit_metadata: bool,
    reporter: str,
):
    """Test updating host via kafka as rhsm reporter
    If provided subscription_manager_id is in hex uuid format (without dashes),
    inventory should transform it to the canonical form (with dashes) when setting owner_id

    metadata:
        requirements: inv-host-update, inv-mq-identity-exception-rhsm
        importance: high
        assignee: fstavela
        title: Update host via kafka as rhsm reporter
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["reporter"] = reporter
    rhsm_id = host_data["subscription_manager_id"]
    host = host_inventory.kafka.create_host(
        host_data=host_data,
        omit_identity=True,
        omit_metadata=omit_metadata,
    )

    new_ansible_host = generate_display_name()
    updated_host_data = dict(host_data, ansible_host=new_ansible_host)
    if update_rhsm_id:
        rhsm_id = generate_uuid()
        updated_host_data["subscription_manager_id"] = rhsm_id
    updated_host = host_inventory.kafka.create_host(
        host_data=updated_host_data, omit_identity=True, omit_metadata=omit_metadata
    )
    assert host.id == updated_host.id

    host_inventory.apis.hosts.wait_for_updated(
        host.id, ansible_host=new_ansible_host, subscription_manager_id=rhsm_id
    )
    host_inventory.apis.hosts.wait_for_system_profile_updated(host.id, owner_id=str(UUID(rhsm_id)))


@pytest.mark.ephemeral
@pytest.mark.parametrize("omit_metadata", [True, False])
@pytest.mark.parametrize("reporter", ["rhsm-conduit", "rhsm-system-profile-bridge"])
def test_mq_create_system_host_rhsm_reporter_without_subscription_manager_id(
    host_inventory: ApplicationHostInventory,
    omit_metadata: bool,
    reporter: str,
):
    """Test creating host via kafka as rhsm reporter without subscription_manager_id

    metadata:
        requirements: inv-host-create, inv-mq-identity-exception-rhsm, inv-mq-identity-validation
        importance: medium
        assignee: fstavela
        negative: true
        title: Try to create host via kafka as rhsm-conduit reporter without sub_man_id
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["reporter"] = reporter
    host_data.pop("subscription_manager_id", None)

    host_inventory.kafka.produce_host_create_messages(
        [host_data], omit_identity=True, omit_metadata=omit_metadata
    )
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(retries=1, display_name=host_data["display_name"])


@pytest.mark.ephemeral
def test_mq_create_system_host_without_owner_id(
    host_inventory: ApplicationHostInventory, system_identity_correct: dict
):
    """Test creating host via kafka with "system" identity without owner_id in host data
    The host should be successfully created with owner_id == identity.system.cn
    metadata:
        requirements: inv-host-create, inv-mq-identity-validation
        importance: high
        assignee: fstavela
        title: Create host via kafka without owner_id in host data
    """
    metadata = prepare_identity_metadata(system_identity_correct)
    owner_id = system_identity_correct["identity"]["system"]["cn"]
    host = host_inventory.kafka.create_host(metadata=metadata)

    host_inventory.apis.hosts.wait_for_system_profile_updated(host.id, owner_id=owner_id)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "original_owner_id, updated_owner_id",
    [(None, "cn"), ("wrong", "cn"), (None, None), ("cn", None), ("wrong", None)],
)
def test_mq_update_system_host_different_owner_id(
    host_inventory: ApplicationHostInventory,
    system_identity_correct: dict,
    prepare_host_for_updates,
    original_owner_id: str | None,
    updated_owner_id: str | None,
):
    """Test updating host via kafka with "system" identity with wrong owner_id
    The host should be successfully created and the owner_id should be updated
    metadata:
        requirements: inv-host-update, inv-mq-identity-validation
        importance: high
        assignee: fstavela
        title: Update host via kafka with wrong owner_id
    """
    if original_owner_id == "cn":
        prepared_host = prepare_host_for_updates(
            system_identity_correct["identity"]["system"]["cn"]
        )
    elif original_owner_id == "wrong":
        prepared_host = prepare_host_for_updates(generate_uuid())
    else:
        prepared_host = prepare_host_for_updates()
    host_data = prepared_host["data"]
    host = prepared_host["host"]

    metadata = prepare_identity_metadata(system_identity_correct)
    new_display_name = generate_display_name()
    updated_host_data = dict(host_data, display_name=new_display_name)
    cn = system_identity_correct["identity"]["system"]["cn"]
    if updated_owner_id is None and original_owner_id is not None:
        del updated_host_data["system_profile"]["owner_id"]  # type: ignore
    if updated_owner_id == "cn":
        updated_host_data["system_profile"]["owner_id"] = cn  # type: ignore
    updated_host = host_inventory.kafka.create_host(metadata=metadata, host_data=updated_host_data)
    assert host.id == updated_host.id

    host_inventory.apis.hosts.wait_for_updated(host.id, display_name=new_display_name)
    host_inventory.apis.hosts.wait_for_system_profile_updated(host.id, owner_id=cn)


@pytest.mark.ephemeral
def test_mq_create_system_host_wrong_cn(
    host_inventory: ApplicationHostInventory, system_identity_correct: dict
):
    """Test creating host via kafka with "system" identity with different owner_id in
    identity and host data
    metadata:
        requirements: inv-mq-identity-validation
        importance: high
        assignee: fstavela
        negative: true
        title: Create host via kafka with different owner_id in identity and host data
    """
    metadata = prepare_identity_metadata(system_identity_correct)
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["owner_id"] = generate_uuid()
    insights_id = host_data["insights_id"]

    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata)
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(retries=1, insights_id=insights_id)


@pytest.mark.ephemeral
@pytest.mark.parametrize("host_owner_id", [None, "different", "host_data", "identity"])
def test_mq_update_system_host_wrong_cn(
    host_inventory: ApplicationHostInventory,
    system_identity_correct: dict,
    prepare_host_for_updates,
    host_owner_id: str | None,
):
    """Test updating host via kafka with "system" identity with different owner_id in
    identity and host data
    metadata:
        requirements: inv-mq-identity-validation
        importance: high
        assignee: fstavela
        negative: true
        title: Update host via kafka with different owner_id in identity and host data
    """
    owner_id = generate_uuid()
    if host_owner_id == "host_data":
        prepared_host = prepare_host_for_updates(owner_id)
    elif host_owner_id == "identity":
        prepared_host = prepare_host_for_updates(
            system_identity_correct["identity"]["system"]["cn"]
        )
    elif host_owner_id == "different":
        prepared_host = prepare_host_for_updates(generate_uuid())
    else:
        prepared_host = prepare_host_for_updates()
    host_data = prepared_host["data"]
    host = prepared_host["host"]

    metadata = prepare_identity_metadata(system_identity_correct)
    updated_host_data = dict(host_data, display_name=generate_display_name())
    updated_host_data["system_profile"]["owner_id"] = owner_id

    host_inventory.kafka.produce_host_create_messages([updated_host_data], metadata=metadata)
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, updated_host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_updated(
        host.id, retries=1, display_name=host_data["display_name"]
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
@pytest.mark.parametrize(
    "identity",
    [lf("get_system_identity"), lf("get_non_system_identity")],
)
def test_mq_create_host_wrong_org_id(
    host_inventory: ApplicationHostInventory,
    has_owner_id: bool,
    identity: dict,
):
    """Test creating host via kafka with identity with wrong org_id
    metadata:
        requirements: inv-mq-identity-validation
        importance: high
        assignee: fstavela
        negative: true
        title: Create host via kafka with wrong org_id
    """
    metadata = prepare_identity_metadata(identity)
    host_data = host_inventory.datagen.create_host_data()
    try:
        owner_id = identity["identity"]["system"]["cn"]
    except KeyError:
        owner_id = generate_uuid()
    if has_owner_id:
        host_data["system_profile"]["owner_id"] = owner_id
    insights_id = host_data["insights_id"]

    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata)
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(retries=1, insights_id=insights_id)


@pytest.mark.ephemeral
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
@pytest.mark.parametrize(
    "identity",
    [lf("get_system_identity"), lf("get_non_system_identity")],
)
def test_mq_update_host_wrong_org_id(
    host_inventory: ApplicationHostInventory,
    prepare_host_for_updates,
    has_owner_id: bool,
    identity: dict,
):
    """Test updating host via kafka with identity with wrong org_id
    metadata:
        requirements: inv-mq-identity-validation
        importance: high
        assignee: fstavela
        negative: true
        title: Update host via kafka with wrong org_id
    """
    try:
        owner_id = identity["identity"]["system"]["cn"]
    except KeyError:
        owner_id = generate_uuid()
    if has_owner_id:
        prepared_host = prepare_host_for_updates(owner_id)
    else:
        prepared_host = prepare_host_for_updates()
    host_data = prepared_host["data"]
    host = prepared_host["host"]

    metadata = prepare_identity_metadata(identity)
    updated_host_data = dict(host_data, display_name=generate_display_name())

    host_inventory.kafka.produce_host_create_messages([updated_host_data], metadata=metadata)
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, updated_host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_updated(
        host, retries=1, display_name=host_data["display_name"]
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
def test_mq_create_host_without_metadata(
    host_inventory: ApplicationHostInventory, has_owner_id: bool
):
    """Test creating host via kafka without metadata
    metadata:
        requirements: inv-mq-identity-validation
        importance: high
        assignee: fstavela
        negative: true
        title: Create host via kafka without metadata
    """
    host_data = host_inventory.datagen.create_host_data()
    insights_id = host_data["insights_id"]
    if has_owner_id:
        host_data["system_profile"]["owner_id"] = generate_uuid()

    host_inventory.kafka.produce_host_create_messages([host_data], omit_metadata=True)
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(retries=1, insights_id=insights_id)


@pytest.mark.ephemeral
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
def test_mq_update_host_without_metadata(
    host_inventory: ApplicationHostInventory,
    prepare_host_for_updates,
    has_owner_id: bool,
):
    """Test updating host via kafka without metadata
    metadata:
        requirements: inv-mq-identity-validation
        importance: high
        assignee: fstavela
        negative: true
        title: Update host via kafka without metadata
    """
    if has_owner_id:
        prepared_host = prepare_host_for_updates(generate_uuid())
    else:
        prepared_host = prepare_host_for_updates()
    host_data = prepared_host["data"]
    host = prepared_host["host"]

    updated_host_data = dict(host_data, display_name=generate_display_name())
    host_inventory.kafka.produce_host_create_messages([updated_host_data], omit_metadata=True)
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, updated_host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_updated(
        host, retries=1, display_name=host_data["display_name"]
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
def test_mq_create_host_without_identity(
    host_inventory: ApplicationHostInventory, has_owner_id: bool
):
    """Test creating host via kafka without identity
    metadata:
        requirements: inv-mq-identity-validation
        importance: high
        assignee: fstavela
        negative: true
        title: Create host via kafka without identity
    """
    host_data = host_inventory.datagen.create_host_data()
    insights_id = host_data["insights_id"]
    if has_owner_id:
        host_data["system_profile"]["owner_id"] = generate_uuid()

    host_inventory.kafka.produce_host_create_messages([host_data], omit_identity=True)
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(retries=1, insights_id=insights_id)


@pytest.mark.ephemeral
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
def test_mq_update_host_without_identity(
    host_inventory: ApplicationHostInventory,
    prepare_host_for_updates,
    has_owner_id: bool,
):
    """Test updating host via kafka without identity
    metadata:
        requirements: inv-mq-identity-validation
        importance: high
        assignee: fstavela
        negative: true
        title: Update host via kafka without identity
    """
    if has_owner_id:
        prepared_host = prepare_host_for_updates(generate_uuid())
    else:
        prepared_host = prepare_host_for_updates()
    host_data = prepared_host["data"]
    host = prepared_host["host"]

    updated_host_data = dict(host_data, display_name=generate_display_name())
    host_inventory.kafka.produce_host_create_messages([updated_host_data], omit_identity=True)
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, updated_host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_updated(
        host, retries=1, display_name=host_data["display_name"]
    )


parametrize_identity_invalid = pytest.mark.parametrize(
    "identity",
    [
        pytest.param(
            lf("identity_blank_org_id"),
            id="blank_org_id",
        ),
        pytest.param(
            lf("identity_without_org_id"),
            id="without_org_id",
        ),
        pytest.param(
            lf("identity_invalid_type"),
            id="invalid_type",
        ),
        pytest.param(
            lf("identity_blank_type"),
            id="blank_type",
        ),
        pytest.param(
            lf("identity_without_type"),
            id="without_type",
        ),
        pytest.param(
            lf("identity_invalid_auth_type"),
            id="invalid_auth_type",
        ),
        pytest.param(
            lf("identity_blank_auth_type"),
            id="blank_auth_type",
        ),
        pytest.param(
            lf("identity_without_auth_type"),
            id="without_auth_type",
        ),
        pytest.param(
            lf("system_identity_blank_cn"),
            id="system_blank_cn",
        ),
        pytest.param(
            lf("system_identity_without_cn"),
            id="system_without_cn",
        ),
        pytest.param(
            lf("system_identity_invalid_cert_type"),
            id="system_invalid_cert_type",
        ),
        pytest.param(
            lf("system_identity_blank_cert_type"),
            id="system_blank_cert_type",
        ),
        pytest.param(
            lf("system_identity_without_cert_type"),
            id="system_without_cert_type",
        ),
        pytest.param(
            lf("system_identity_blank_system"),
            id="system_blank_system",
        ),
        pytest.param(
            lf("system_identity_without_system"),
            id="system_without_system",
        ),
        pytest.param(
            lf("service_account_identity_blank_client_id"),
            id="service_account_blank_client_id",
        ),
        pytest.param(
            lf("service_account_identity_without_client_id"),
            id="service_account_without_client_id",
        ),
        pytest.param(
            lf("service_account_identity_blank_username"),
            id="service_account_blank_username",
        ),
        pytest.param(
            lf("service_account_identity_without_username"),
            id="service_account_without_username",
        ),
        pytest.param(
            lf("service_account_identity_blank_service_account"),
            id="service_account_blank_service_account",
        ),
        pytest.param(
            lf("service_account_identity_without_service_account"),
            id="service_account_without_service_account",
        ),
        pytest.param(
            lf("empty_identity"),
            id="empty_identity",
        ),
        pytest.param(
            lf("empty_dict"),
            id="empty_dict",
        ),
    ],
)


@pytest.mark.ephemeral
@parametrize_identity_invalid
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
def test_mq_create_host_wrong_identity(
    host_inventory: ApplicationHostInventory,
    identity: dict,
    has_owner_id: bool,
):
    """Test creating host via kafka with wrong identity
    metadata:
        requirements: inv-mq-identity-validation
        importance: medium
        assignee: fstavela
        negative: true
        title: Create host via kafka with wrong identity
    """
    metadata = prepare_identity_metadata(identity)
    host_data = host_inventory.datagen.create_host_data()
    insights_id = host_data["insights_id"]
    if has_owner_id:
        try:
            # Check that CN != ""
            if identity["identity"]["system"]["cn"]:
                host_data["system_profile"]["owner_id"] = identity["identity"]["system"]["cn"]
            else:
                host_data["system_profile"]["owner_id"] = generate_uuid()
        except KeyError:
            host_data["system_profile"]["owner_id"] = generate_uuid()

    host_inventory.kafka.produce_host_create_messages([host_data], metadata=metadata)
    if identity.get("identity", {}).get("org_id", None) is not None:
        host_inventory.kafka.wait_for_filtered_error_message(
            ErrorNotificationWrapper.display_name, host_data["display_name"]
        )

    host_inventory.apis.hosts.verify_not_created(retries=1, insights_id=insights_id)


@pytest.mark.ephemeral
@parametrize_identity_invalid
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
def test_mq_update_host_wrong_identity(
    host_inventory: ApplicationHostInventory,
    prepare_host_for_updates,
    identity: dict,
    has_owner_id: bool,
):
    """Test updating host via kafka with wrong identity
    metadata:
        requirements: inv-mq-identity-validation
        importance: medium
        assignee: fstavela
        negative: true
        title: Update host via kafka with wrong identity
    """
    if has_owner_id:
        try:
            # Check that CN != ""
            if identity["identity"]["system"]["cn"]:
                prepared_host = prepare_host_for_updates(identity["identity"]["system"]["cn"])
            else:
                prepared_host = prepare_host_for_updates(generate_uuid())
        except KeyError:
            prepared_host = prepare_host_for_updates(generate_uuid())
    else:
        prepared_host = prepare_host_for_updates()
    host_data = prepared_host["data"]
    host = prepared_host["host"]

    updated_host_data = dict(host_data, display_name=generate_display_name())
    metadata = prepare_identity_metadata(identity)

    host_inventory.kafka.produce_host_create_messages([updated_host_data], metadata=metadata)
    if identity.get("identity", {}).get("org_id", None) is not None:
        host_inventory.kafka.wait_for_filtered_error_message(
            ErrorNotificationWrapper.display_name, updated_host_data["display_name"]
        )

    host_inventory.apis.hosts.verify_not_updated(
        host, retries=1, display_name=host_data["display_name"]
    )
