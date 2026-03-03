from __future__ import annotations

from datetime import UTC

import pytest
from dateutil.parser import parse as parse_datetime
from pytest_mock import MockerFixture

from app.exceptions import ValidationException
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.system_profile_utils import INVALID_SYSTEM_PROFILES
from tests.helpers.system_profile_utils import VALID_SYSTEM_PROFILES
from tests.helpers.test_utils import minimal_host


def _sp_test_id(profile: dict) -> str:
    """Generate a readable pytest ID from the top-level field name and a short value hint."""
    key = next(iter(profile))
    val = profile[key]
    return f"{key}-{val!r}"


# Legacy fields that get remapped during ingestion/serialization.
# These are stored under workloads.* internally, so the original key
# won't appear in the event or API response.
LEGACY_SP_FIELDS: set[str] = {
    "sap_sids",
    "sap_system",
    "sap_instance_number",
    "sap_version",
    "ansible",
    "intersystems",
    "mssql",
    "sap",
    "crowdstrike",
    "ibm_db2",
    "oracle_db",
    "rhel_ai",
}

# Datetime fields that require normalized comparison.
DATETIME_FIELDS: set[str] = {"last_boot_time", "captured_date"}


def _assert_sp_values_match(sent: dict, received: dict) -> None:
    """Assert that all sent system_profile fields appear correctly in received."""
    for key, sent_value in sent.items():
        if key in LEGACY_SP_FIELDS:
            continue
        assert key in received, f"Key '{key}' missing from system_profile response"
        received_value = received[key]
        if key in DATETIME_FIELDS:
            _assert_datetime_equal(sent_value, received_value, key)
        else:
            _assert_value_equal(sent_value, received_value, path=key)


def _assert_datetime_equal(sent: str, received: str, path: str) -> None:
    """Compare datetime strings after parsing and normalizing."""
    sent_dt = parse_datetime(sent)
    received_dt = parse_datetime(received)
    # The system stores naive datetimes as UTC; normalize for comparison.
    if sent_dt.tzinfo is None:
        sent_dt = sent_dt.replace(tzinfo=UTC)
    if received_dt.tzinfo is None:
        received_dt = received_dt.replace(tzinfo=UTC)
    assert sent_dt == received_dt, (
        f"Datetime mismatch at '{path}': sent {sent!r} ({sent_dt}), received {received!r} ({received_dt})"
    )


def _assert_value_equal(sent: object, received: object, path: str = "") -> None:
    """Recursively compare sent and received values."""
    if isinstance(sent, dict):
        assert isinstance(received, dict), f"Expected dict at '{path}', got {type(received)}"
        for k, v in sent.items():
            assert k in received, f"Key '{k}' missing at '{path}'"
            _assert_value_equal(v, received[k], path=f"{path}.{k}")
    elif isinstance(sent, (list, tuple)):
        assert isinstance(received, (list, tuple)), f"Expected list at '{path}', got {type(received)}"
        assert len(received) == len(sent), (
            f"List length mismatch at '{path}': sent {len(sent)}, received {len(received)}"
        )
        for i, (s, r) in enumerate(zip(sent, received, strict=True)):
            _assert_value_equal(s, r, path=f"{path}[{i}]")
    else:
        assert sent == received, f"Value mismatch at '{path}': sent {sent!r}, received {received!r}"


@pytest.mark.parametrize("system_profile", VALID_SYSTEM_PROFILES, ids=_sp_test_id)
def test_valid_system_profile(mq_create_or_update_host, api_get, system_profile: dict) -> None:
    """Valid system profiles pass through MQ, appear in event, and API."""
    host = minimal_host(system_profile=system_profile)
    created_host = mq_create_or_update_host(host)

    # 1. Host was created and event contains correct SP data
    assert created_host.id is not None
    event_sp: dict = created_host.system_profile or {}
    _assert_sp_values_match(system_profile, event_sp)

    # 2. API returns the correct SP data
    url: str = build_system_profile_url(created_host.id)
    status, data = api_get(url)
    assert status == 200
    api_sp: dict = data["results"][0]["system_profile"]
    _assert_sp_values_match(system_profile, api_sp)


@pytest.mark.parametrize("system_profile", INVALID_SYSTEM_PROFILES, ids=_sp_test_id)
def test_invalid_system_profile(
    mocker: MockerFixture, mq_create_or_update_host, db_get_hosts_by_subman_id, system_profile: dict
) -> None:
    """Invalid system profiles are rejected via MQ with a notification."""
    mock_notification = mocker.Mock()
    host = minimal_host(system_profile=system_profile)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification)
    mock_notification.write_event.assert_called_once()

    # Verify the host was not persisted
    assert db_get_hosts_by_subman_id(host.subscription_manager_id) == []
