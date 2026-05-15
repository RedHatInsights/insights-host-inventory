# mypy: disallow-untyped-defs

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pytest_mock import MockerFixture

from app.exceptions import ValidationException
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.host_field_utils import CANONICAL_FIELDS
from tests.helpers.host_field_utils import INVALID_HOST_FIELDS
from tests.helpers.host_field_utils import VALID_HOST_FIELDS
from tests.helpers.test_utils import base_host
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host


def _host_field_test_id(fields: dict) -> str:
    key = next(iter(fields))
    val = fields[key]
    return f"{key}-{val!r}"


def _expected_value(field_name: str, sent_value: Any) -> Any:
    if field_name in ("ip_addresses", "mac_addresses") and sent_value == []:
        return None
    if field_name in CANONICAL_FIELDS:
        if isinstance(sent_value, str):
            return sent_value.lower()
        if isinstance(sent_value, list):
            return [item.lower() if isinstance(item, str) else item for item in sent_value]
    return sent_value


def _sort_facts(facts: list[dict]) -> list[dict]:
    return sorted(facts, key=lambda f: f["namespace"])


def _assert_host_field_values_match(sent: dict, host_data: dict) -> None:
    for key, sent_value in sent.items():
        expected = _expected_value(key, sent_value)
        actual = host_data.get(key)
        if key == "facts":
            assert actual is not None and expected is not None
            assert _sort_facts(actual) == _sort_facts(expected), f"Facts mismatch: sent {expected!r}, got {actual!r}"
        else:
            assert actual == expected, (
                f"Field '{key}' mismatch: sent {sent_value!r}, expected {expected!r}, got {actual!r}"
            )


@pytest.mark.parametrize("host_fields", VALID_HOST_FIELDS, ids=_host_field_test_id)
def test_valid_host_field(mq_create_or_update_host: Callable, api_get: Callable, host_fields: dict) -> None:
    """Valid host fields pass through MQ, appear in event, and API."""
    host = minimal_host(**host_fields)
    created_host = mq_create_or_update_host(host)

    assert created_host.id is not None
    _assert_host_field_values_match(host_fields, created_host.data())

    url = build_hosts_url(created_host.id)
    status, data = api_get(url)
    assert status == 200
    api_host: dict = data["results"][0]
    _assert_host_field_values_match(host_fields, api_host)


@pytest.mark.parametrize("host_fields", INVALID_HOST_FIELDS, ids=_host_field_test_id)
def test_invalid_host_field(
    mocker: MockerFixture, mq_create_or_update_host: Callable, db_get_hosts_by_subman_id: Callable, host_fields: dict
) -> None:
    """Invalid host fields are rejected via MQ with a notification."""
    mock_notification = mocker.Mock()
    host = minimal_host(**host_fields)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification)
    mock_notification.write_event.assert_called_once()

    assert db_get_hosts_by_subman_id(host.subscription_manager_id) == []


def test_at_least_one_id_fact_required(mocker: MockerFixture, mq_create_or_update_host: Callable) -> None:
    """Creating a host without any ID facts should fail."""
    mock_notification = mocker.Mock()
    host = base_host()

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification)


def test_canonical_facts_forced_to_lowercase(mq_create_or_update_host: Callable, api_get: Callable) -> None:
    """Canonical facts are forced to lowercase during ingestion."""
    upper_fqdn = "HOST.EXAMPLE.COM"
    host = minimal_host(fqdn=upper_fqdn)
    created_host = mq_create_or_update_host(host)

    assert created_host.fqdn == "host.example.com"

    url = build_hosts_url(created_host.id)
    status, data = api_get(url)
    assert status == 200
    assert data["results"][0]["fqdn"] == "host.example.com"


def test_zero_mac_address_filtered(mq_create_or_update_host: Callable, api_get: Callable) -> None:
    """Zero MAC address (00:00:00:00:00:00) is filtered out."""
    host = minimal_host(mac_addresses=["00:00:00:00:00:00", "aa:bb:cc:dd:ee:ff"])
    created_host = mq_create_or_update_host(host)

    assert created_host.mac_addresses == ["aa:bb:cc:dd:ee:ff"]

    url = build_hosts_url(created_host.id)
    status, data = api_get(url)
    assert status == 200
    assert data["results"][0]["mac_addresses"] == ["aa:bb:cc:dd:ee:ff"]


def test_zero_mac_address_only_results_in_null(mq_create_or_update_host: Callable, api_get: Callable) -> None:
    """If zero MAC is the only MAC, mac_addresses becomes null."""
    host = minimal_host(mac_addresses=["00:00:00:00:00:00"])
    created_host = mq_create_or_update_host(host)

    assert created_host.mac_addresses is None

    url = build_hosts_url(created_host.id)
    status, data = api_get(url)
    assert status == 200
    assert data["results"][0]["mac_addresses"] is None


@pytest.mark.parametrize("field_name", ["org_id", "reporter"])
def test_missing_required_field_rejected(
    mocker: MockerFixture, mq_create_or_update_host: Callable, db_get_hosts_by_subman_id: Callable, field_name: str
) -> None:
    """Omitting a required field should be rejected."""
    mock_notification = mocker.Mock()
    host = minimal_host()
    host.data().pop(field_name)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification)
    mock_notification.write_event.assert_called_once()
    assert db_get_hosts_by_subman_id(host.subscription_manager_id) == []


def test_provider_type_without_provider_id(
    mocker: MockerFixture, mq_create_or_update_host: Callable, db_get_hosts_by_subman_id: Callable
) -> None:
    """provider_type without provider_id should be rejected."""
    mock_notification = mocker.Mock()
    host = minimal_host(provider_type="aws")

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification)
    mock_notification.write_event.assert_called_once()
    assert db_get_hosts_by_subman_id(host.subscription_manager_id) == []


def test_provider_id_without_provider_type(
    mocker: MockerFixture, mq_create_or_update_host: Callable, db_get_hosts_by_subman_id: Callable
) -> None:
    """provider_id without provider_type should be rejected."""
    mock_notification = mocker.Mock()
    host = minimal_host(provider_id=generate_uuid())

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification)
    mock_notification.write_event.assert_called_once()
    assert db_get_hosts_by_subman_id(host.subscription_manager_id) == []
