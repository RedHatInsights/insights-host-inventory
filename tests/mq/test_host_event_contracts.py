"""Local ingress-to-event contracts; no broker or deployed inventory requests."""

from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.queue.event_producer import _encode_headers
from tests.helpers.mq_utils import HOST_EVENT_HEADER_CASES
from tests.helpers.mq_utils import expected_headers
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host


def _expected_mq_host(data, host_id, group_id, created, checked_in, profile):
    lifecycle = {
        "last_check_in": checked_in.isoformat(),
        "stale_timestamp": (checked_in + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS)).isoformat(),
        "stale_warning_timestamp": (
            checked_in + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
        ).isoformat(),
        "culled_timestamp": (checked_in + timedelta(seconds=CONVENTIONAL_TIME_TO_DELETE_SECONDS)).isoformat(),
    }
    return {
        "id": host_id,
        "account": "test",
        "org_id": "test",
        "display_name": data["display_name"],
        "ansible_host": "ansible.example.com",
        "insights_id": data.get("insights_id", "00000000-0000-0000-0000-000000000000"),
        "subscription_manager_id": data["subscription_manager_id"],
        "fqdn": data["fqdn"],
        "bios_uuid": None,
        "satellite_id": None,
        "ip_addresses": None,
        "mac_addresses": None,
        "provider_id": None,
        "provider_type": None,
        "openshift_cluster_id": None,
        "facts": [{"namespace": "inventory", "facts": {"keep": "value"}}],
        "tags": [{"namespace": "inventory", "key": "role", "value": "test"}],
        "reporter": "puptoo",
        "system_profile": {"owner_id": SYSTEM_IDENTITY["system"]["cn"], **profile},
        "created": created.isoformat(),
        "updated": checked_in.isoformat(),
        **lifecycle,
        "per_reporter_staleness": {"puptoo": {**lifecycle, "check_in_succeeded": True}},
        "groups": [{"id": group_id, "name": "Ungrouped Hosts", "ungrouped": True}],
    }


@pytest.mark.parametrize("operation", ("created", "updated"))
def test_mq_create_update_event_contracts(
    operation,
    mq_create_or_update_host,
    db_create_group,
    db_get_host,
    event_producer_mock,
    event_datetime_mock,
    mocker,
    subtests,
):
    group_id = str(db_create_group("Ungrouped Hosts", ungrouped=True).id)
    model_clock = mocker.patch("app.models.utils.datetime")
    created = event_datetime_mock - timedelta(minutes=2)
    updated = created + timedelta(minutes=1)
    request_values = ("28a936a4-cb68-4153-a03d-d0109acf0eb9", "", None, "absent")
    for index, (profile, host_type, os_name, is_bootc) in enumerate(HOST_EVENT_HEADER_CASES):
        for with_insights_id in (False, True):
            with subtests.test(profile=profile, with_insights_id=with_insights_id):
                data = {
                    "account": "test",
                    "display_name": "original",
                    "ansible_host": "ansible.example.com",
                    "subscription_manager_id": generate_uuid(),
                    "fqdn": f"{generate_uuid()}.example.com",
                    "reporter": "puptoo",
                    "system_profile": deepcopy(profile),
                    "facts": [{"namespace": "inventory", "facts": {"keep": "value"}}],
                    "tags": [{"namespace": "inventory", "key": "role", "value": "test"}],
                }
                if with_insights_id:
                    data["insights_id"] = generate_uuid()
                metadata = get_platform_metadata()
                request_value = request_values[index % len(request_values)]
                if request_value == "absent":
                    del metadata["request_id"]
                    request_id = None
                else:
                    metadata["request_id"] = request_value
                    request_id = request_value

                original_id = None
                steps = (
                    (("created", created),) if operation == "created" else (("created", created), ("updated", updated))
                )
                for event_type, checked_in in steps:
                    model_clock.now.return_value = checked_in
                    if event_type == "updated":
                        data["display_name"] = "updated"
                    event_producer_mock.events.clear()
                    key, event, headers = mq_create_or_update_host(
                        minimal_host(**deepcopy(data)),
                        platform_metadata=deepcopy(metadata),
                        return_all_data=True,
                    )
                    assert len(event_producer_mock.events) == 1
                    assert UUID(key).version == 4
                    if original_id is None:
                        original_id = key
                    assert key == original_id
                    assert db_get_host(key).display_name == data["display_name"]
                    expected_host = _expected_mq_host(data, key, group_id, created, checked_in, deepcopy(profile))
                    assert event == {
                        "type": event_type,
                        "timestamp": event_datetime_mock.isoformat(),
                        "host": expected_host,
                        "platform_metadata": metadata,
                        "metadata": {"request_id": request_id},
                    }
                    assert headers == expected_headers(
                        event_type, request_id, expected_host["insights_id"], "puptoo", host_type, os_name, is_bootc
                    )
                    assert dict(_encode_headers(headers))["request_id"] == (request_id.encode() if request_id else b"")


def test_mq_sparse_update_uses_stored_header_sources(
    mq_create_or_update_host,
    db_create_group,
    event_producer_mock,
    event_datetime_mock,
    mocker,
):
    group_id = str(db_create_group("Ungrouped Hosts", ungrouped=True).id)
    model_clock = mocker.patch("app.models.utils.datetime")
    created = event_datetime_mock - timedelta(minutes=2)
    model_clock.now.return_value = created
    profile = {"host_type": "edge", "operating_system": {"name": "RHEL", "major": 9, "minor": 4}}
    insights_id = generate_uuid()
    data = {
        "account": "test",
        "display_name": "original",
        "ansible_host": "ansible.example.com",
        "subscription_manager_id": generate_uuid(),
        "fqdn": f"{generate_uuid()}.example.com",
        "insights_id": insights_id,
        "reporter": "puptoo",
        "system_profile": deepcopy(profile),
        "facts": [{"namespace": "inventory", "facts": {"keep": "value"}}],
        "tags": [{"namespace": "inventory", "key": "role", "value": "test"}],
    }
    metadata = get_platform_metadata()
    key, _, _ = mq_create_or_update_host(
        minimal_host(**deepcopy(data)), platform_metadata=metadata, return_all_data=True
    )
    updated = created + timedelta(minutes=1)
    model_clock.now.return_value = updated
    event_producer_mock.events.clear()
    update_key, event, headers = mq_create_or_update_host(
        minimal_host(
            subscription_manager_id=data["subscription_manager_id"], reporter="puptoo", display_name="updated"
        ),
        platform_metadata=metadata,
        return_all_data=True,
    )
    assert update_key == key
    assert len(event_producer_mock.events) == 1
    data["display_name"] = "updated"
    assert event == {
        "host": _expected_mq_host(data, key, group_id, created, updated, profile),
        "type": "updated",
        "timestamp": event_datetime_mock.isoformat(),
        "metadata": {"request_id": metadata["request_id"]},
        "platform_metadata": metadata,
    }
    assert headers == expected_headers(
        "updated", metadata["request_id"], insights_id, "puptoo", "edge", "RHEL", "False"
    )
