from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from pytest_mock import MockerFixture

from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.models import Host
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import create_hosts_by_reporter_and_staleness
from tests.helpers.db_utils import db_host
from tests.helpers.mq_utils import MockEventProducer
from tests.helpers.mq_utils import assert_delete_event_is_valid
from tests.helpers.test_utils import RHSM_ERRATA_IDENTITY_PROD
from tests.helpers.test_utils import RHSM_ERRATA_IDENTITY_STAGE
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now


@pytest.mark.usefixtures("notification_event_producer_mock")
def test_delete_hosts_filtered_by_subscription_manager_id(
    db_create_host,
    api_delete_filtered_hosts,
    event_datetime_mock,
    event_producer_mock,
):
    db_create_host(host=db_host())
    host = db_create_host(host=db_host())
    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={"subscription_manager_id": host.subscription_manager_id}
    )
    assert response_data["hosts_found"] == 1
    assert response_data["hosts_deleted"] == 1
    assert_response_status(response_status, expected_status=202)
    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)


@pytest.mark.parametrize(
    "host_type,system_type,nomatch_host_type",
    (
        (None, "conventional", "edge"),
        ("edge", "edge", "cluster"),
        ("cluster", "cluster", "edge"),
    ),
)
@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_hosts_filtered_by_system_type(
    host_type,
    system_type,
    nomatch_host_type,
    mq_create_or_update_host,
    db_get_host,
    api_delete_filtered_hosts,
):
    host_to_keep_id = mq_create_or_update_host(
        minimal_host(system_profile={"host_type": nomatch_host_type} if nomatch_host_type else {})
    ).id
    host_to_delete_id = mq_create_or_update_host(
        minimal_host(system_profile={"host_type": host_type} if host_type else {})
    ).id

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"system_type": system_type})

    assert response_data["hosts_found"] == 1
    assert response_data["hosts_deleted"] == 1
    assert_response_status(response_status, expected_status=202)

    assert not db_get_host(host_to_delete_id)
    assert db_get_host(host_to_keep_id)


@pytest.mark.usefixtures("notification_event_producer_mock")
def test_delete_all_hosts(
    event_producer_mock,
    db_create_multiple_hosts,
    db_get_hosts,
    api_delete_all_hosts,
):
    created_hosts = db_create_multiple_hosts(how_many=5)
    host_ids = [str(host.id) for host in created_hosts]

    response_status, response_data = api_delete_all_hosts({"confirm_delete_all": True})

    assert '"type": "delete"' in event_producer_mock.event
    assert response_data.get("hosts_deleted") == len(created_hosts)
    assert_response_status(response_status, expected_status=202)
    assert len(host_ids) == response_data["hosts_deleted"]

    host_id_list = [str(host.id) for host in created_hosts]
    deleted_hosts = db_get_hosts(host_id_list)
    assert deleted_hosts.count() == 0


def test_delete_all_hosts_with_missing_required_params(api_delete_all_hosts, event_producer_mock):
    response_status, _ = api_delete_all_hosts({})

    assert_response_status(response_status, expected_status=400)
    assert event_producer_mock.event is None


@pytest.mark.usefixtures("notification_event_producer_mock")
@pytest.mark.parametrize(
    "request_body",
    (
        {"hostname_or_id": "foo"},
        {"registered_with": "satellite"},
    ),
)
def test_postgres_delete_filtered_hosts(
    db_create_host, api_get, request_body, api_delete_filtered_hosts, event_producer_mock
):
    host_1_id = db_create_host(extra_data={"display_name": "foobar", "reporter": "satellite"}).id
    host_2_id = db_create_host(extra_data={"display_name": "foobaz", "reporter": "satellite"}).id
    host_3_id = db_create_host(extra_data={"display_name": "asdf", "reporter": "puptoo"}).id

    not_deleted_host_id = str(db_create_host(extra_data={"insights_id": generate_uuid()}).id)

    response_status, response_data = api_delete_filtered_hosts(request_body)
    assert_response_status(response_status, expected_status=202)
    assert response_data["hosts_deleted"] == 2

    assert '"type": "delete"' in event_producer_mock.event
    response_status, _ = api_get(build_hosts_url(host_1_id))
    assert response_status == 404
    response_status, _ = api_get(build_hosts_url(host_2_id))
    assert response_status == 404
    _, response_data = api_get(build_hosts_url(host_3_id))
    assert len(response_data["results"]) == 1

    response_status, response_data = api_get(build_hosts_url(not_deleted_host_id))
    assert_response_status(response_status, expected_status=200)
    assert response_data["results"][0]["id"] == not_deleted_host_id


@pytest.mark.usefixtures("event_producer_mock")
def test_postgres_delete_filtered_hosts_nomatch(db_create_host, api_get, api_delete_filtered_hosts):
    not_deleted_host_id = str(db_create_host(extra_data={"insights_id": generate_uuid()}).id)

    response_status, response_data = api_delete_filtered_hosts({"insights_id": generate_uuid()})
    assert response_data["hosts_found"] == 0
    assert response_data["hosts_deleted"] == 0

    response_status, response_data = api_get(build_hosts_url(not_deleted_host_id))
    assert_response_status(response_status, expected_status=200)
    assert response_data["results"][0]["id"] == not_deleted_host_id


@pytest.mark.usefixtures("notification_event_producer_mock")
@pytest.mark.parametrize("identity", (RHSM_ERRATA_IDENTITY_PROD, RHSM_ERRATA_IDENTITY_STAGE), ids=("prod", "stage"))
def test_delete_hosts_by_subman_id_internal_rhsm_request(
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
    api_delete_filtered_hosts: Callable[..., tuple[int, dict]],
    event_producer_mock: MockEventProducer,
    identity: dict[str, Any],
):
    """
    This test simulates the internal `DELETE /hosts?subscription_manager_id=...` request from RHSM
    that they make when a host is unregistered from RHSM, to delete it from Insights Inventory.
    """
    searched_subman_id = generate_uuid()
    matching_host_id = str(db_create_host(extra_data={"subscription_manager_id": searched_subman_id}).id)
    not_matching_host_id = str(db_create_host(extra_data={"subscription_manager_id": generate_uuid()}).id)
    different_org_host_id = str(
        db_create_host(extra_data={"subscription_manager_id": searched_subman_id, "org_id": "12345"}).id
    )

    response_status, response_data = api_delete_filtered_hosts(
        {"subscription_manager_id": searched_subman_id},
        identity=identity,
        extra_headers={"x-inventory-org-id": "test"},
    )
    assert_response_status(response_status, expected_status=202)
    assert response_data["hosts_deleted"] == 1
    assert response_data["hosts_found"] == 1

    assert '"type": "delete"' in event_producer_mock.event

    response_status, _ = api_get(build_hosts_url([matching_host_id, not_matching_host_id, different_org_host_id]))
    assert response_status == 404

    _, response_data = api_get(build_hosts_url([not_matching_host_id]))
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == not_matching_host_id

    different_org_identity = deepcopy(USER_IDENTITY)
    different_org_identity["org_id"] = "12345"
    _, response_data = api_get(
        build_hosts_url([different_org_host_id]),
        identity=different_org_identity,
    )
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == different_org_host_id


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_delete_hosts_filter_last_check_in_both_same(db_create_host, db_get_host, api_delete_filtered_hosts):
    match_host = db_create_host()
    match_host_id = str(match_host.id)
    nomatch_host_id = str(db_create_host().id)
    response_status, _ = api_delete_filtered_hosts(
        query_parameters={
            "last_check_in_start": match_host.last_check_in,
            "last_check_in_end": match_host.last_check_in,
        }
    )
    assert response_status == 202
    assert not db_get_host(match_host_id)
    assert db_get_host(nomatch_host_id)


def test_delete_hosts_filter_last_check_in_invalid_format(api_delete_filtered_hosts, subtests):
    invalid_formats = ("foobar", "{}", "[]", generate_uuid(), [datetime.now(), datetime.now() - timedelta(days=7)])
    for invalid_format in invalid_formats:
        for param in ("last_check_in_start", "last_check_in_end"):
            with subtests.test(invalid_format=invalid_format, param=param):
                response_status, response_data = api_delete_filtered_hosts(
                    query_parameters={param: str(invalid_format)}
                )
                assert response_status == 400
                assert "is not a 'date-time'" in response_data["detail"]


@pytest.mark.parametrize("param_prefix", ("updated", "last_check_in"))
def test_delete_hosts_filter_updated_last_check_in_start_after_end(api_delete_filtered_hosts, param_prefix):
    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={
            f"{param_prefix}_start": datetime.now(),
            f"{param_prefix}_end": datetime.now() - timedelta(days=1),
        }
    )
    assert response_status == 400
    assert f"{param_prefix}_start cannot be after {param_prefix}_end." in response_data["detail"]


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
@pytest.mark.parametrize(
    "staleness_filter",
    [
        ["fresh"],
        ["stale"],
        ["stale_warning"],
        ["fresh", "stale"],
        ["fresh", "stale_warning"],
        ["stale", "stale_warning"],
        ["fresh", "stale", "stale_warning"],
    ],
    ids=lambda param: ",".join(param),
)
@pytest.mark.parametrize("host_type", ("conventional", "edge"))
def test_delete_hosts_filtered_by_staleness(
    db_create_host: Callable[..., Host],
    db_get_host: Callable[..., Host | None],
    api_delete_filtered_hosts: Callable[..., tuple[int, dict]],
    mocker: Any,
    staleness_filter: list[str],
    host_type: str,
):
    """
    Test DELETE on /hosts endpoint with 'staleness' parameter.
    This test creates hosts in different staleness states and verifies that
    only hosts matching the staleness filter are deleted.
    """
    secondary_org_id = "12345"

    staleness_timestamps = {
        "fresh": now(),
        "stale": now() - timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS),
        "stale_warning": now() - timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS),
    }

    host_ids_to_delete = []
    host_ids_to_keep = []
    different_org_host_ids = []
    for staleness_state, last_check_in_timestamp in staleness_timestamps.items():
        with mocker.patch("app.models.utils.datetime", **{"now.return_value": last_check_in_timestamp}):
            system_profile_facts = {"host_type": host_type} if host_type == "edge" else {}
            host_id = str(db_create_host(extra_data={"system_profile_facts": system_profile_facts}).id)

            if staleness_state in staleness_filter:
                host_ids_to_delete.append(host_id)
            else:
                host_ids_to_keep.append(host_id)

            different_org_host_ids.append(
                str(
                    db_create_host(
                        extra_data={"system_profile_facts": system_profile_facts, "org_id": secondary_org_id}
                    ).id
                )
            )

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"staleness": staleness_filter})
    assert response_status == 202
    assert response_data["hosts_found"] == len(host_ids_to_delete)
    assert response_data["hosts_deleted"] == len(host_ids_to_delete)

    for host_id in host_ids_to_delete:
        assert not db_get_host(host_id), f"Host {host_id} should have been deleted"

    for host_id in host_ids_to_keep:
        assert db_get_host(host_id), f"Host {host_id} should not have been deleted"

    for host_id in different_org_host_ids:
        assert db_get_host(host_id, org_id=secondary_org_id), f"Host {host_id} should not have been deleted"


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_hosts_filtered_default_staleness(
    db_create_host: Callable[..., Host],
    db_get_host: Callable[..., Host | None],
    api_delete_filtered_hosts: Callable[..., tuple[int, dict]],
    mocker: Any,
):
    """
    Test default staleness on DELETE /hosts endpoint.
    When no staleness filter is provided, the default is to delete fresh, stale, and stale_warning hosts.
    """
    staleness_timestamps = {
        "fresh": now(),
        "stale": now() - timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS),
        "stale_warning": now() - timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS),
    }

    host_ids = []
    for last_check_in_timestamp in staleness_timestamps.values():
        with mocker.patch("app.models.utils.datetime", **{"now.return_value": last_check_in_timestamp}):
            host = db_create_host(extra_data={"reporter": "puptoo"})
            host_ids.append(str(host.id))

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"registered_with": "puptoo"})
    assert response_status == 202
    assert response_data["hosts_deleted"] == len(host_ids)

    for host_id in host_ids:
        assert not db_get_host(host_id), f"Host {host_id} should have been deleted"


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_hosts_filter_by_reporter_and_staleness(
    db_create_host: Callable[..., Host],
    db_get_host: Callable[..., Host | None],
    api_delete_filtered_hosts: Callable[..., tuple[int, dict]],
    mocker: MockerFixture,
    subtests,
):
    hosts = create_hosts_by_reporter_and_staleness(db_create_host, mocker)
    all_host_ids = {str(hosts[s][r].id) for s in hosts for r in hosts[s]}

    for state in ("fresh", "stale", "stale_warning"):
        for reporter in ("puptoo", "yupana"):
            with subtests.test(state=state, reporter=reporter):
                target_id = str(hosts[state][reporter].id)

                response_status, response_data = api_delete_filtered_hosts(
                    query_parameters={"staleness": [state], "registered_with": reporter}
                )
                assert response_status == 202
                assert response_data["hosts_deleted"] >= 1

                assert not db_get_host(target_id), f"Host {target_id} should have been deleted"
                all_host_ids.discard(target_id)

                for remaining_id in all_host_ids:
                    assert db_get_host(remaining_id), f"Host {remaining_id} should not have been deleted"


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_hosts_filtered_by_all_parameters(
    db_create_host: Callable[..., Host],
    db_get_host: Callable[..., Host | None],
    api_delete_filtered_hosts: Callable[..., tuple[int, dict]],
    db_create_group: Callable,
    db_create_host_group_assoc: Callable,
):
    """
    Test DELETE /hosts with all filter parameters combined.
    Creates 7 hosts: 1 target matching all filters and 6 decoys, each differing
    in exactly one dimension. Verifies only the target is deleted.

    Filters tested: display_name, provider_type, staleness, tags, group_name, registered_with.
    """
    target_display_name = "target-host"
    other_display_name = "other-host"
    target_tags = {"ns": {"k": ["v"]}}
    other_tags = {"ns2": {"k2": ["v2"]}}
    target_provider_type = "aws"
    other_provider_type = "ibm"
    target_provider_id = "i-target-001"
    other_provider_id = "i-other-001"
    target_reporter = "puptoo"
    other_reporter = "yupana"

    stale_timestamp = now() - timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS)

    with mock.patch("app.models.utils.datetime", **{"now.return_value": stale_timestamp}):
        host3 = db_create_host(
            extra_data={
                "display_name": target_display_name,
                "provider_type": target_provider_type,
                "provider_id": target_provider_id,
                "tags": target_tags,
                "reporter": target_reporter,
            }
        )

    host0_target = db_create_host(
        extra_data={
            "display_name": target_display_name,
            "provider_type": target_provider_type,
            "provider_id": target_provider_id,
            "tags": target_tags,
            "reporter": target_reporter,
        }
    )
    host1 = db_create_host(
        extra_data={
            "display_name": other_display_name,
            "provider_type": target_provider_type,
            "provider_id": target_provider_id,
            "tags": target_tags,
            "reporter": target_reporter,
        }
    )
    host2 = db_create_host(
        extra_data={
            "display_name": target_display_name,
            "provider_type": other_provider_type,
            "provider_id": other_provider_id,
            "tags": target_tags,
            "reporter": target_reporter,
        }
    )
    host4 = db_create_host(
        extra_data={
            "display_name": target_display_name,
            "provider_type": target_provider_type,
            "provider_id": target_provider_id,
            "tags": other_tags,
            "reporter": target_reporter,
        }
    )
    host5 = db_create_host(
        extra_data={
            "display_name": target_display_name,
            "provider_type": target_provider_type,
            "provider_id": target_provider_id,
            "tags": target_tags,
            "reporter": target_reporter,
        }
    )
    host6 = db_create_host(
        extra_data={
            "display_name": target_display_name,
            "provider_type": target_provider_type,
            "provider_id": target_provider_id,
            "tags": target_tags,
            "reporter": other_reporter,
        }
    )

    group = db_create_group("test-group")
    for host in (host0_target, host1, host2, host3, host4, host6):
        db_create_host_group_assoc(host.id, group.id)

    target_id = str(host0_target.id)
    decoy_ids = [str(h.id) for h in (host1, host2, host3, host4, host5, host6)]

    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={
            "display_name": target_display_name,
            "provider_type": target_provider_type,
            "staleness": ["fresh"],
            "tags": "ns/k=v",
            "group_name": group.name,
            "registered_with": target_reporter,
        }
    )

    assert response_status == 202
    assert response_data["hosts_found"] == 1
    assert response_data["hosts_deleted"] == 1

    assert not db_get_host(target_id), "Target host should have been deleted"

    for host_id in decoy_ids:
        assert db_get_host(host_id), f"Host {host_id} should not have been deleted"
