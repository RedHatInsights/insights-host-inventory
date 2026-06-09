# mypy: disallow-untyped-defs

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from pytest_mock import MockFixture

from app.exceptions import ValidationException
from app.models import Host
from app.queue.host_mq import IngressMessageConsumer
from app.queue.host_mq import write_add_update_event_message
from lib.host_repository import host_query
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_encoded_idstr
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import valid_system_profile

OWNER_ID: str = SYSTEM_IDENTITY["system"]["cn"]


def _assert_host_not_in_db(org_id: str, subscription_manager_id: str) -> None:
    result = host_query(org_id).filter(Host.subscription_manager_id == subscription_manager_id).one_or_none()
    assert result is None


# --- Positive: system identity with correct owner_id ---


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_owner_id(mq_create_or_update_host: Callable, db_get_host: Callable) -> None:
    host = minimal_host(system_profile={"owner_id": OWNER_ID})
    created_host_from_event = mq_create_or_update_host(host)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert str(created_host_from_db.static_system_profile.owner_id) == OWNER_ID


# --- Positive: RHSM reporter ---


@pytest.mark.usefixtures("event_datetime_mock")
@pytest.mark.parametrize(
    "with_account, rhsm_reporter",
    [
        (True, "rhsm-conduit"),
        (False, "rhsm-conduit"),
        (True, "rhsm-system-profile-bridge"),
        (False, "rhsm-system-profile-bridge"),
    ],
)
def test_add_host_rhsm_conduit_without_cn(
    mq_create_or_update_host: Callable, with_account: bool, rhsm_reporter: str
) -> None:
    sub_mangager_id = "09152341-475c-4671-a376-df609374c349"

    metadata_without_b64 = get_platform_metadata(identity=SYSTEM_IDENTITY)
    del metadata_without_b64["b64_identity"]

    if with_account:
        host = minimal_host(
            account=SYSTEM_IDENTITY.get("account_number"),
            reporter=rhsm_reporter,
            subscription_manager_id=sub_mangager_id,
        )
    else:
        host = minimal_host(reporter=rhsm_reporter, subscription_manager_id=sub_mangager_id)

    key, event, headers = mq_create_or_update_host(host, platform_metadata=metadata_without_b64, return_all_data=True)

    assert event["host"]["system_profile"]["owner_id"] == "09152341-475c-4671-a376-df609374c349"


@pytest.mark.usefixtures("event_datetime_mock")
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_add_host_rhsm_conduit_owner_id(mq_create_or_update_host: Callable, rhsm_reporter: str) -> None:
    sub_mangager_id = "09152341-475c-4671-a376-df609374c349"

    host = minimal_host(
        reporter=rhsm_reporter,
        subscription_manager_id=sub_mangager_id,
        system_profile={"owner_id": OWNER_ID},
    )

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert event["host"]["system_profile"]["owner_id"] == "09152341-475c-4671-a376-df609374c349"


@pytest.mark.usefixtures("flask_app")
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_reporter_and_no_platform_metadata(
    rhsm_reporter: str, ingress_message_consumer_mock: IngressMessageConsumer
) -> None:
    host = minimal_host(
        insights_id=generate_uuid(),
        reporter=rhsm_reporter,
        subscription_manager_id=OWNER_ID,
    )

    message = wrap_message(host.data(), "add_host")

    ingress_message_consumer_mock.handle_message(json.dumps(message))


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_reporter_and_no_identity(mocker: MockFixture, rhsm_reporter: str) -> None:
    expected_insights_id = generate_uuid()
    mock_event_producer = mocker.Mock()
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(
        insights_id=expected_insights_id,
        reporter=rhsm_reporter,
        subscription_manager_id=OWNER_ID,
    )

    platform_metadata = get_platform_metadata()
    platform_metadata.pop("b64_identity")
    message = wrap_message(host.data(), "add_host", platform_metadata)

    consumer = IngressMessageConsumer(
        mocker.Mock(), mocker.Mock(), mock_event_producer, mock_notification_event_producer
    )

    result = consumer.handle_message(json.dumps(message))
    write_add_update_event_message(mock_event_producer, mock_notification_event_producer, result)

    mock_event_producer.write_event.assert_called_once()
    mock_notification_event_producer.assert_not_called()


# --- Negative: wrong owner_id / wrong CN ---


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_wrong_owner(mocker: MockFixture, mq_create_or_update_host: Callable) -> None:
    mock_notification_event_producer = mocker.Mock()
    expected_insights_id = generate_uuid()
    expected_system_profile = valid_system_profile()

    host = minimal_host(
        insights_id=expected_insights_id,
        system_profile=expected_system_profile,
    )

    with pytest.raises(ValidationException) as ve:
        mq_create_or_update_host(
            host, return_all_data=True, notification_event_producer=mock_notification_event_producer
        )
    assert ve.value.detail == "The owner in host does not match the owner in identity"
    mock_notification_event_producer.write_event.assert_called_once()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)


@pytest.mark.usefixtures("flask_app")
def test_owner_id_different_from_cn(mocker: MockFixture) -> None:
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(
        insights_id=generate_uuid(),
        system_profile={"owner_id": "137c9d58-941c-4bb9-9426-7879a367c23b"},
    )

    message = wrap_message(host.data(), "add_host", get_platform_metadata())
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    with pytest.raises(ValidationException) as ve:
        consumer.handle_message(json.dumps(message))

    assert ve.value.detail == "The owner in host does not match the owner in identity"
    mock_notification_event_producer.write_event.assert_called_once()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)


# --- Negative: owner_id format ---


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_owner_incorrect_format(mocker: MockFixture, mq_create_or_update_host: Callable) -> None:
    mock_notification_event_producer = mocker.Mock()
    owner_id = "Mike Wazowski"
    host = minimal_host(system_profile={"owner_id": owner_id})
    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)


# --- Negative: no identity / no metadata ---


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
def test_no_identity_and_no_rhsm_reporter(mocker: MockFixture) -> None:
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(insights_id=generate_uuid())

    platform_metadata = get_platform_metadata()
    platform_metadata.pop("b64_identity")

    message = wrap_message(host.data(), "add_host", platform_metadata)
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    with pytest.raises(ValidationException):
        consumer.handle_message(json.dumps(message))
    mock_notification_event_producer.write_event.assert_called_once()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
def test_non_rhsm_reporter_and_no_identity(mocker: MockFixture) -> None:
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(
        insights_id=generate_uuid(),
        reporter="yee-haw",
        subscription_manager_id=OWNER_ID,
    )

    platform_metadata = get_platform_metadata()
    platform_metadata.pop("b64_identity")
    message = wrap_message(host.data(), "add_host", platform_metadata)
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)
    with pytest.raises(ValidationException):
        consumer.handle_message(json.dumps(message))
    mock_notification_event_producer.write_event.assert_called_once()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)


# --- Negative: invalid identity ---


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_invalid_identity(mocker: MockFixture, mq_create_or_update_host: Callable) -> None:
    identity = deepcopy(USER_IDENTITY)
    identity["account_number"] = -5
    metadata = {
        "request_id": "b9757340-f839-4541-9af6-f7535edf08db",
        "archive_url": "http://s3.aws.com/redhat/insights/1234567",
        "b64_identity": get_encoded_idstr(identity),
    }
    mock_notification_event_producer = mocker.Mock()
    host = minimal_host()
    with pytest.raises(ValidationException):
        mq_create_or_update_host(
            host, notification_event_producer=mock_notification_event_producer, platform_metadata=metadata
        )

    mock_notification_event_producer.write_event.assert_called_once()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)


# --- Positive: non-system identity (user / service account) ---


@pytest.mark.usefixtures("event_datetime_mock")
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
@pytest.mark.parametrize(
    "identity",
    [
        pytest.param(USER_IDENTITY, id="user"),
        pytest.param(SERVICE_ACCOUNT_IDENTITY, id="service_account"),
    ],
)
def test_create_non_system_host_all_correct(
    mq_create_or_update_host: Callable,
    db_get_host: Callable,
    identity: dict[str, Any],
    has_owner_id: bool,
) -> None:
    owner_id = generate_uuid()
    host = minimal_host(org_id=identity["org_id"])
    if has_owner_id:
        host.system_profile = {"owner_id": owner_id}

    created_host = mq_create_or_update_host(host, identity=identity)
    created_host_from_db = db_get_host(created_host.id, org_id=identity["org_id"])

    assert created_host.id == str(created_host_from_db.id)
    if has_owner_id:
        assert str(created_host_from_db.static_system_profile.owner_id) == owner_id


# --- Positive: system identity without owner_id ---


@pytest.mark.usefixtures("event_datetime_mock")
def test_create_system_host_without_owner_id(mq_create_or_update_host: Callable, db_get_host: Callable) -> None:
    host = minimal_host()

    created_host = mq_create_or_update_host(host)
    created_host_from_db = db_get_host(created_host.id)

    assert str(created_host_from_db.static_system_profile.owner_id) == OWNER_ID


# --- Negative: RHSM reporter without subscription_manager_id ---


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
@pytest.mark.parametrize("omit_metadata", [True, False], ids=["without_metadata", "with_metadata"])
@pytest.mark.parametrize("rhsm_reporter", ["rhsm-conduit", "rhsm-system-profile-bridge"])
def test_create_rhsm_reporter_without_subscription_manager_id(
    mocker: MockFixture, omit_metadata: bool, rhsm_reporter: str
) -> None:
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(reporter=rhsm_reporter)
    sub_man_id = host.subscription_manager_id
    host_data = host.data()
    host_data.pop("subscription_manager_id", None)

    if omit_metadata:
        platform_metadata = None
    else:
        platform_metadata = get_platform_metadata()
        platform_metadata.pop("b64_identity")

    message = wrap_message(host_data, "add_host", platform_metadata)
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    with pytest.raises(ValidationException):
        consumer.handle_message(json.dumps(message))
    mock_notification_event_producer.write_event.assert_called_once()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], sub_man_id)


# --- Negative: wrong org_id in identity ---


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
@pytest.mark.parametrize(
    "identity",
    [
        pytest.param(SYSTEM_IDENTITY, id="system"),
        pytest.param(USER_IDENTITY, id="user"),
        pytest.param(SERVICE_ACCOUNT_IDENTITY, id="service_account"),
    ],
)
def test_create_host_wrong_org_id(mocker: MockFixture, identity: dict[str, Any], has_owner_id: bool) -> None:
    mock_notification_event_producer = mocker.Mock()

    wrong_identity = deepcopy(identity)
    wrong_identity["org_id"] = "wrong_org_id"

    host = minimal_host()
    if has_owner_id:
        if identity["type"] == "System":
            host.system_profile = {"owner_id": identity["system"]["cn"]}
        else:
            host.system_profile = {"owner_id": generate_uuid()}

    metadata = get_platform_metadata(wrong_identity)
    message = wrap_message(host.data(), "add_host", metadata)
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    with pytest.raises(ValidationException):
        consumer.handle_message(json.dumps(message))
    mock_notification_event_producer.write_event.assert_called_once()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)


# --- Negative: no platform_metadata ---


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
def test_create_host_without_metadata(mocker: MockFixture, has_owner_id: bool) -> None:
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host()
    if has_owner_id:
        host.system_profile = {"owner_id": generate_uuid()}

    message = wrap_message(host.data(), "add_host")
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    with pytest.raises(ValidationException):
        consumer.handle_message(json.dumps(message))
    mock_notification_event_producer.write_event.assert_called_once()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)


# --- Negative: comprehensive invalid identity variants ---


def _make_validation_error_identities() -> list[Any]:
    """Invalid identity variants that raise ValidationException."""
    variants: list[Any] = []

    # blank org_id (empty string — differs from missing org_id which raises KeyError)
    for base_id, base_name in [
        (SYSTEM_IDENTITY, "system"),
        (USER_IDENTITY, "user"),
        (SERVICE_ACCOUNT_IDENTITY, "service_account"),
    ]:
        identity = deepcopy(base_id)
        identity["org_id"] = ""
        variants.append(pytest.param(identity, id=f"{base_name}-blank_org_id"))

    # type variants
    for base_id, base_name in [
        (SYSTEM_IDENTITY, "system"),
        (USER_IDENTITY, "user"),
        (SERVICE_ACCOUNT_IDENTITY, "service_account"),
    ]:
        identity = deepcopy(base_id)
        identity["type"] = "Invalid"
        variants.append(pytest.param(identity, id=f"{base_name}-invalid_type"))

        identity = deepcopy(base_id)
        identity["type"] = ""
        variants.append(pytest.param(identity, id=f"{base_name}-blank_type"))

        identity = deepcopy(base_id)
        del identity["type"]
        variants.append(pytest.param(identity, id=f"{base_name}-without_type"))

    # auth_type variants
    for base_id, base_name in [
        (SYSTEM_IDENTITY, "system"),
        (USER_IDENTITY, "user"),
        (SERVICE_ACCOUNT_IDENTITY, "service_account"),
    ]:
        identity = deepcopy(base_id)
        identity["auth_type"] = "invalid-auth"
        variants.append(pytest.param(identity, id=f"{base_name}-invalid_auth_type"))

        identity = deepcopy(base_id)
        identity["auth_type"] = ""
        variants.append(pytest.param(identity, id=f"{base_name}-blank_auth_type"))

        identity = deepcopy(base_id)
        del identity["auth_type"]
        variants.append(pytest.param(identity, id=f"{base_name}-without_auth_type"))

    # system-specific: cn variants
    identity = deepcopy(SYSTEM_IDENTITY)
    identity["system"]["cn"] = ""
    variants.append(pytest.param(identity, id="system-blank_cn"))

    identity = deepcopy(SYSTEM_IDENTITY)
    del identity["system"]["cn"]
    variants.append(pytest.param(identity, id="system-without_cn"))

    # system-specific: cert_type variants
    identity = deepcopy(SYSTEM_IDENTITY)
    identity["system"]["cert_type"] = "invalid"
    variants.append(pytest.param(identity, id="system-invalid_cert_type"))

    identity = deepcopy(SYSTEM_IDENTITY)
    identity["system"]["cert_type"] = ""
    variants.append(pytest.param(identity, id="system-blank_cert_type"))

    identity = deepcopy(SYSTEM_IDENTITY)
    del identity["system"]["cert_type"]
    variants.append(pytest.param(identity, id="system-without_cert_type"))

    # system-specific: system object variants
    identity = deepcopy(SYSTEM_IDENTITY)
    del identity["system"]["cn"]
    del identity["system"]["cert_type"]
    variants.append(pytest.param(identity, id="system-blank_system"))

    identity = deepcopy(SYSTEM_IDENTITY)
    del identity["system"]
    variants.append(pytest.param(identity, id="system-without_system"))

    # service_account-specific: client_id variants
    identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)
    identity["service_account"]["client_id"] = ""
    variants.append(pytest.param(identity, id="service_account-blank_client_id"))

    identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)
    del identity["service_account"]["client_id"]
    variants.append(pytest.param(identity, id="service_account-without_client_id"))

    # service_account-specific: username variants
    identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)
    identity["service_account"]["username"] = ""
    variants.append(pytest.param(identity, id="service_account-blank_username"))

    identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)
    del identity["service_account"]["username"]
    variants.append(pytest.param(identity, id="service_account-without_username"))

    # service_account-specific: service_account object variants
    identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)
    del identity["service_account"]["client_id"]
    del identity["service_account"]["username"]
    variants.append(pytest.param(identity, id="service_account-blank_service_account"))

    identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)
    del identity["service_account"]
    variants.append(pytest.param(identity, id="service_account-without_service_account"))

    return variants


def _make_missing_org_id_identities() -> list[Any]:
    """Identity variants with org_id key missing entirely, causing KeyError."""
    variants: list[Any] = []

    for base_id, base_name in [
        (SYSTEM_IDENTITY, "system"),
        (USER_IDENTITY, "user"),
        (SERVICE_ACCOUNT_IDENTITY, "service_account"),
    ]:
        identity = deepcopy(base_id)
        del identity["org_id"]
        variants.append(pytest.param(identity, id=f"{base_name}-without_org_id"))

    # {} → get_encoded_idstr wraps as {"identity": {}} → _decode_id returns {} → no "org_id" key
    variants.append(pytest.param({}, id="empty_identity"))

    return variants


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
@pytest.mark.parametrize("identity", _make_validation_error_identities())
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
def test_create_host_wrong_identity(mocker: MockFixture, identity: dict[str, Any], has_owner_id: bool) -> None:
    mock_notification_event_producer = mocker.Mock()

    org_id = identity.get("org_id", SYSTEM_IDENTITY["org_id"])
    host = minimal_host(org_id=org_id)
    if has_owner_id:
        try:
            cn = identity["system"]["cn"]
            if cn:
                host.system_profile = {"owner_id": cn}
            else:
                host.system_profile = {"owner_id": generate_uuid()}
        except (KeyError, TypeError):
            host.system_profile = {"owner_id": generate_uuid()}

    metadata = {
        "request_id": generate_uuid(),
        "archive_url": "http://s3.aws.com/redhat/insights/1234567",
        "b64_identity": get_encoded_idstr(identity),
    }
    message = wrap_message(host.data(), "add_host", metadata)
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    with pytest.raises(ValidationException):
        consumer.handle_message(json.dumps(message))
    mock_notification_event_producer.write_event.assert_called_once()
    _assert_host_not_in_db(org_id or SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
@pytest.mark.parametrize("identity", _make_missing_org_id_identities())
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
def test_create_host_identity_missing_org_id(
    mocker: MockFixture, identity: dict[str, Any], has_owner_id: bool
) -> None:
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host()
    if has_owner_id:
        try:
            cn = identity["system"]["cn"]
            if cn:
                host.system_profile = {"owner_id": cn}
            else:
                host.system_profile = {"owner_id": generate_uuid()}
        except (KeyError, TypeError):
            host.system_profile = {"owner_id": generate_uuid()}

    metadata = {
        "request_id": generate_uuid(),
        "archive_url": "http://s3.aws.com/redhat/insights/1234567",
        "b64_identity": get_encoded_idstr(identity),
    }
    message = wrap_message(host.data(), "add_host", metadata)
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    with pytest.raises(KeyError):
        consumer.handle_message(json.dumps(message))
    mock_notification_event_producer.write_event.assert_not_called()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)


@pytest.mark.usefixtures("event_datetime_mock", "flask_app")
@pytest.mark.parametrize("has_owner_id", [True, False], ids=["with_owner_id", "without_owner_id"])
def test_create_host_unwrapped_empty_identity(mocker: MockFixture, has_owner_id: bool) -> None:
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host()
    if has_owner_id:
        host.system_profile = {"owner_id": generate_uuid()}

    # Encode {} directly (no "identity" wrapper) — _decode_id returns None
    b64_identity = base64.b64encode(json.dumps({}).encode("utf-8")).decode("ascii")
    metadata = {
        "request_id": generate_uuid(),
        "archive_url": "http://s3.aws.com/redhat/insights/1234567",
        "b64_identity": b64_identity,
    }
    message = wrap_message(host.data(), "add_host", metadata)
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)

    with pytest.raises(TypeError):
        consumer.handle_message(json.dumps(message))
    mock_notification_event_producer.write_event.assert_not_called()
    _assert_host_not_in_db(SYSTEM_IDENTITY["org_id"], host.subscription_manager_id)
