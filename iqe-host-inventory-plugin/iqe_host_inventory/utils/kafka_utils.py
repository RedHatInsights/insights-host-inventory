from __future__ import annotations

import json
import logging
import warnings
from base64 import b64decode
from base64 import b64encode
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from time import sleep
from typing import Any
from typing import TypeVar
from typing import cast
from uuid import UUID

import pytest
from confluent_kafka.error import ConsumeError
from iqe_mq._transforms import MessageWrapper as MqMessageWrapper

from iqe_host_inventory.deprecations import DEPRECATE_FIND_MQ_HOST_MSGS
from iqe_host_inventory.deprecations import DEPRECATE_MQ_CREATE_OR_UPDATE_HOST
from iqe_host_inventory.modeling.wrappers import HostMessageWrapper
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.modeling.wrappers import KafkaMessageNotFoundError
from iqe_host_inventory.utils import assert_datetimes_equal
from iqe_host_inventory.utils.datagen_utils import DEFAULT_INSIGHTS_ID
from iqe_host_inventory.utils.datagen_utils import HOST_FIELDS
from iqe_host_inventory.utils.datagen_utils import generate_user_identity
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.staleness_utils import validate_staleness_timestamps

logger = logging.getLogger(__name__)


def wrap_payload(
    single_payload: dict[str, Any],
    identity: dict[str, Any],
    operation: str = "add_host",
    operation_args: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
    omit_identity: bool = False,
    omit_metadata: bool = False,
    omit_request_id: bool = False,
):
    used_identity = deepcopy(identity)  # Modifications to identity will affect application config

    result = {"data": single_payload, "operation": operation}

    if operation_args is not None:
        result["operation_args"] = operation_args

    if "org_id" in single_payload:
        used_identity["org_id"] = single_payload["org_id"]

    identity_metadata = (
        {} if omit_identity else prepare_identity_metadata({"identity": used_identity})
    )
    metadata = {**identity_metadata, **metadata} if metadata else identity_metadata
    if not omit_metadata:
        if "request_id" not in metadata and not omit_request_id:
            metadata["request_id"] = generate_uuid()

        result["platform_metadata"] = metadata

    return result


def match_hosts(message: dict, data_to_match: dict):
    warnings.warn(DEPRECATE_FIND_MQ_HOST_MSGS, stacklevel=2)
    if not isinstance(message, dict) or not isinstance(data_to_match, dict):
        return None

    field_to_match = data_to_match.get("field")

    for field_value in data_to_match.get("values", ()):
        if message.get("host"):
            message_field_value = message["host"].get(field_to_match)
        else:
            message_field_value = message.get(field_to_match)

        if field_value == message_field_value:
            return message


def events_message_expected_headers() -> set[str]:
    return {
        "event_type",
        "request_id",
        "producer",
        "insights_id",
        "os_name",
        "reporter",
        "host_type",
        "is_bootc",
    }


def delete_message_expected_fields() -> set[str]:
    return {
        "timestamp",
        "type",
        "id",
        "account",
        "org_id",
        "insights_id",
        "subscription_manager_id",
        "initiated_by_frontend",
        "request_id",
        "metadata",
        "platform_metadata",
    }


def create_or_update_message_expected_fields() -> set[str]:
    return {"timestamp", "type", "host", "metadata", "platform_metadata"}


def check_host_timestamps(
    updated_host: HostWrapper | dict,
    original_host: HostWrapper | dict,
    staleness_settings: dict[str, int] | None = None,
) -> None:
    """Check that the new 'updated' timestamp is bigger than the original 'updated' timestamp and
    all host-level staleness timestamps are correct. Also remove these timestamps from host data.
    This function is used to check the host timestamps after an API update of a host."""

    def _extract_timestamps(data: dict) -> dict[str, datetime]:
        timestamps = {
            "updated": data.pop("updated"),
            "stale_timestamp": data.pop("stale_timestamp"),
            "stale_warning_timestamp": data.pop("stale_warning_timestamp"),
            "culled_timestamp": data.pop("culled_timestamp"),
        }
        for key, value in timestamps.items():
            timestamps[key] = datetime.fromisoformat(value) if isinstance(value, str) else value
        return timestamps

    updated_data = updated_host.data() if isinstance(updated_host, HostWrapper) else updated_host
    orig_data = original_host.data() if isinstance(original_host, HostWrapper) else original_host

    updated_timestamps = _extract_timestamps(updated_data)
    original_timestamps = _extract_timestamps(orig_data)

    # Host's "updated" timestamp was changed by host or groups manipulation
    assert updated_timestamps["updated"] > original_timestamps["updated"]

    # Host's "last_check_in" timestamp shouldn't be changed by API updates
    assert updated_data["last_check_in"] == orig_data["last_check_in"]

    validate_staleness_timestamps(
        updated_data["last_check_in"],
        stale_timestamp=updated_timestamps["stale_timestamp"],
        stale_warning_timestamp=updated_timestamps["stale_warning_timestamp"],
        culled_timestamp=updated_timestamps["culled_timestamp"],
        staleness_settings=staleness_settings,
    )


def check_prs_timestamps(
    per_reporter_staleness: dict,
    latest_reporter: str,
    host_last_check_in: str | datetime,
    *,
    staleness_settings: dict[str, int] | None = None,
) -> None:
    assert latest_reporter in per_reporter_staleness
    for prs_reporter, prs_timestamps in per_reporter_staleness.items():
        if prs_reporter == latest_reporter:
            assert_datetimes_equal(
                prs_timestamps["last_check_in"],
                host_last_check_in,
            )
        else:
            assert prs_timestamps["last_check_in"] < host_last_check_in

        validate_staleness_timestamps(
            prs_timestamps["last_check_in"],
            stale_timestamp=prs_timestamps["stale_timestamp"],
            stale_warning_timestamp=prs_timestamps["stale_warning_timestamp"],
            culled_timestamp=prs_timestamps["culled_timestamp"],
            staleness_settings=staleness_settings,
        )


def _check_event_headers(
    message: HostMessageWrapper,
    event_type: str,
    host: HostWrapper,
    request_id: str | None,
) -> None:
    assert message.headers.keys() == events_message_expected_headers()
    assert message.headers["event_type"] == event_type
    assert message.headers["request_id"] == (request_id or "")
    assert message.headers["producer"].startswith("host-inventory"), (
        f"'{message.headers['producer']}' doesn't start with 'host-inventory'"
    )
    assert message.headers["insights_id"] == (host.insights_id or "")
    assert message.headers["os_name"] == host.system_profile.get("operating_system", {}).get(
        "name", ""
    )
    assert message.headers["reporter"] == host.reporter
    assert message.headers["host_type"] == host.system_profile.get("host_type", "")
    is_bootc = str(host.system_profile.get("bootc_status", {}).get("booted") is not None)
    assert message.headers["is_bootc"] == is_bootc


def _check_create_or_update_event_fields(
    message: HostMessageWrapper,
    event_type: str,
    time1: datetime,
    time2: datetime,
    request_id: str | None,
    identity: dict,
) -> None:
    assert message.value.keys() == create_or_update_message_expected_fields()
    assert message.value["type"] == event_type
    assert time1 < datetime.fromisoformat(message.value["timestamp"]) < time2
    assert message.value["metadata"] == {"request_id": request_id}
    msg_identity = stripped_identity(message.value["platform_metadata"]["b64_identity"])
    expected_identity = stripped_identity(identity)
    assert msg_identity == expected_identity, f"{msg_identity} != {expected_identity}"


def _check_delete_event_fields(
    message: HostMessageWrapper,
    time1: datetime,
    time2: datetime,
    host: HostWrapper,
    request_id: str | None,
    identity: dict,
    initiated_by_frontend: bool = False,
) -> None:
    assert message.value.keys() == delete_message_expected_fields()
    assert message.value["type"] == "delete"
    assert time1 < datetime.fromisoformat(message.value["timestamp"]) < time2
    assert message.value["id"] == host.id
    assert message.value["account"] == host.account
    assert message.value["org_id"] == host.org_id
    assert message.value["insights_id"] == str(host.insights_id)
    assert message.value["subscription_manager_id"] == host.subscription_manager_id
    assert message.value["initiated_by_frontend"] is initiated_by_frontend
    assert message.value["request_id"] == request_id
    assert message.value["metadata"] == {"request_id": request_id}
    assert normalize_identity(
        message.value["platform_metadata"]["b64_identity"]
    ) == normalize_identity(identity)


def _check_create_or_update_events(
    messages: list[HostMessageWrapper],
    time1: datetime,
    time2: datetime,
    event_type: str,
    *,
    identity: dict | None = None,
    request_id: str | None = None,
) -> None:
    for message in messages:
        assert message.key == message.host.id
        _check_event_headers(message, event_type, message.host, request_id)

        if identity is None:
            org_id = message.host.org_id
            account = message.host.account
            identity = generate_user_identity(org_id, account)
        _check_create_or_update_event_fields(
            message, event_type, time1, time2, request_id, identity
        )


def check_api_update_events(
    messages: list[HostMessageWrapper],
    time1: datetime,
    time2: datetime,
    identity: dict,
    *,
    request_id: str | None = None,
) -> None:
    _check_create_or_update_events(
        messages,
        time1,
        time2,
        "updated",
        identity=identity,
        request_id=request_id,
    )


def check_mq_create_events(
    messages: list[HostMessageWrapper],
    time1: datetime,
    time2: datetime,
    identity: dict,
    *,
    request_id: str | None = None,
) -> None:
    _check_create_or_update_events(
        messages,
        time1,
        time2,
        "created",
        identity=identity,
        request_id=request_id,
    )


def check_mq_update_events(
    messages: list[HostMessageWrapper],
    time1: datetime,
    time2: datetime,
    identity: dict,
    *,
    request_id: str | None = None,
):
    _check_create_or_update_events(
        messages,
        time1,
        time2,
        "updated",
        identity=identity,
        request_id=request_id,
    )


def check_delete_events(
    messages: list[HostMessageWrapper],
    time1: datetime,
    time2: datetime,
    hosts: list[HostWrapper],
    identity: dict,
    *,
    request_id: str | None = None,
    initiated_by_frontend: bool = False,
) -> None:
    assert len(messages) == len(hosts)
    host_msgs_pairs = [(host, [msg for msg in messages if msg.key == host.id]) for host in hosts]
    for host, msgs in host_msgs_pairs:
        assert len(msgs) == 1
        message = msgs[0]
        assert message.key == host.id
        _check_event_headers(message, "delete", host, request_id)
        _check_delete_event_fields(
            message,
            time1,
            time2,
            host,
            identity=identity,
            request_id=request_id,
            initiated_by_frontend=initiated_by_frontend,
        )


def check_mq_create_or_update_event_host_data(
    event_host_data: dict,
    expected_host_data: dict,
    time1: datetime,
    time2: datetime,
    *,
    groups: list | None = None,
    created_timestamp: datetime | None = None,
    host_id: str | None = None,
    staleness_settings: dict[str, int] | None = None,
) -> None:
    """Check host data in the kafka event produced after a host is created/updated via kafka.
    Takes the host data from the updated/created event (event_host_data),
    and the host data sent to HBI (expected_host_data)."""
    if created_timestamp is None:
        created_timestamp = datetime.fromisoformat(event_host_data.pop("created"))
        assert time1 < created_timestamp < time2
        assert_datetimes_equal(
            event_host_data.pop("updated"), created_timestamp, timedelta(milliseconds=1)
        )
        assert_datetimes_equal(
            event_host_data["last_check_in"], created_timestamp, timedelta(milliseconds=100)
        )
    else:
        assert datetime.fromisoformat(event_host_data.pop("created")) == created_timestamp
        assert time1 < datetime.fromisoformat(event_host_data["updated"]) < time2
        assert_datetimes_equal(
            event_host_data["last_check_in"],
            event_host_data.pop("updated"),
            timedelta(milliseconds=100),
        )

    validate_staleness_timestamps(
        event_host_data["last_check_in"],
        stale_timestamp=event_host_data.pop("stale_timestamp"),
        stale_warning_timestamp=event_host_data.pop("stale_warning_timestamp"),
        culled_timestamp=event_host_data.pop("culled_timestamp"),
        staleness_settings=staleness_settings,
    )
    expected_host_data.pop("stale_timestamp", None)
    expected_host_data.pop("stale_warning_timestamp", None)
    expected_host_data.pop("culled_timestamp", None)

    check_prs_timestamps(
        event_host_data.pop("per_reporter_staleness"),
        expected_host_data["reporter"],
        event_host_data.pop("last_check_in"),
        staleness_settings=staleness_settings,
    )

    if host_id is None:
        assert is_uuid(event_host_data.pop("id"))
    else:
        assert event_host_data.pop("id") == host_id

    # Compare the main group data, but not the timestamps
    event_group_list = event_host_data.pop("groups")

    # After Kessel Phase 0, hosts are always in exactly one group
    assert len(event_group_list) == 1

    if groups:
        assert event_group_list[0].get("ungrouped") == groups[0].get("ungrouped")
        assert event_group_list[0].get("name") == groups[0].get("name")
        assert event_group_list[0].get("id") == groups[0].get("id")
    else:
        # If no groups are provided, the host should be in the ungrouped group
        assert event_group_list[0].get("ungrouped") is True

    for field in HOST_FIELDS:
        if field.name == "insights_id":
            if expected_host_data.get("insights_id") is None:
                expected_host_data["insights_id"] = DEFAULT_INSIGHTS_ID
            continue
        if expected_host_data.get(field.name) is None:
            assert event_host_data.pop(field.name, None) is None

    assert event_host_data == expected_host_data, f"{event_host_data} != {expected_host_data}"


def is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    else:
        return True


def encode_identity(identity: dict) -> str:
    return b64encode(json.dumps(identity).encode("utf-8")).decode("utf-8")


def decode_identity(identity: str) -> dict:
    return json.loads(b64decode(identity))


def normalize_identity(identity: str | dict) -> dict:
    identity_dict = decode_identity(identity) if isinstance(identity, str) else deepcopy(identity)

    if "identity" in identity_dict:
        identity_dict = identity_dict["identity"]
    identity_dict.pop("internal", None)
    return identity_dict


def stripped_identity(identity: str | dict) -> dict:
    normalized_identity = normalize_identity(identity)
    minimal_fields = ("type", "auth_type", "org_id")
    return {key: normalized_identity[key] for key in minimal_fields}


def prepare_identity_metadata(identity: dict) -> dict:
    return {"b64_identity": encode_identity(identity)}


def log_consumed_host_message(
    message: HostMessageWrapper | MqMessageWrapper | list[HostMessageWrapper], field_to_match: str
):
    warnings.warn(DEPRECATE_MQ_CREATE_OR_UPDATE_HOST, stacklevel=2)
    if isinstance(message, list):
        for msg in message:
            log_consumed_host_message(msg, field_to_match)
    else:
        if isinstance(message, MqMessageWrapper):
            host = HostWrapper(cast(dict[str, Any], message.value()))
            logger.warning("old host message wrapper for %s", host.id)
        else:
            host = message.host
        logger.info(
            "Consumed host message for %s=%r: Host ID=%s",
            field_to_match,
            getattr(host, field_to_match),
            host.id,
        )


T = TypeVar("T")


def prevent_kafka_error[T](
    create_hosts_func: Callable[..., T], *func_args: Any, **func_kwargs: Any
) -> T:
    """
    Temporary fix for https://issues.redhat.com/browse/RHINENG-9763

    Takes any function which creates hosts and returns what that function returns.
    """
    hosts: T | None = None
    retries = 0

    while not hosts and retries < 5:
        try:
            logger.info(f"Attempt number {retries + 1} to create hosts")
            hosts = create_hosts_func(*func_args, **func_kwargs)
        except (ConsumeError, KafkaMessageNotFoundError) as err:
            logger.info(f"Received an error during hosts creation: {err}")
            retries += 1
            sleep(1)

    if hosts is None:
        pytest.fail("https://issues.redhat.com/browse/RHINENG-9763")

    assert hosts is not None  # for mypy
    return hosts
