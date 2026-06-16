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


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_display_name(db_create_host, db_get_host, api_delete_filtered_hosts):
    target_name = "delete-me-display"
    match_ids = [str(db_create_host(extra_data={"display_name": target_name}).id) for _ in range(3)]
    nomatch_ids = [str(db_create_host(extra_data={"display_name": "keep-me"}).id) for _ in range(2)]

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"display_name": target_name})
    assert response_status == 202
    assert response_data["hosts_found"] == 3
    assert response_data["hosts_deleted"] == 3

    for host_id in match_ids:
        assert not db_get_host(host_id)
    for host_id in nomatch_ids:
        assert db_get_host(host_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_fqdn(db_create_host, db_get_host, api_delete_filtered_hosts):
    target_fqdn = "delete-me.example.com"
    match_ids = [str(db_create_host(extra_data={"fqdn": target_fqdn}).id) for _ in range(3)]
    nomatch_ids = [
        str(db_create_host(extra_data={"fqdn": "keep-me.example.com"}).id),
        str(db_create_host().id),
    ]

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"fqdn": target_fqdn})
    assert response_status == 202
    assert response_data["hosts_found"] == 3
    assert response_data["hosts_deleted"] == 3

    for host_id in match_ids:
        assert not db_get_host(host_id)
    for host_id in nomatch_ids:
        assert db_get_host(host_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_hostname_or_id_display_name(db_create_host, db_get_host, api_delete_filtered_hosts):
    target_name = "hostname-or-id-target"
    match_id = str(db_create_host(extra_data={"display_name": target_name}).id)
    nomatch_id = str(db_create_host(extra_data={"display_name": "other-name"}).id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"hostname_or_id": target_name})
    assert response_status == 202
    assert response_data["hosts_deleted"] >= 1

    assert not db_get_host(match_id)
    assert db_get_host(nomatch_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_hostname_or_id_fqdn(db_create_host, db_get_host, api_delete_filtered_hosts):
    target_fqdn = "hostname-or-id.example.com"
    match_id = str(db_create_host(extra_data={"fqdn": target_fqdn}).id)
    nomatch_id = str(db_create_host(extra_data={"fqdn": "other.example.com"}).id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"hostname_or_id": target_fqdn})
    assert response_status == 202
    assert response_data["hosts_deleted"] >= 1

    assert not db_get_host(match_id)
    assert db_get_host(nomatch_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_hostname_or_id_uuid(db_create_host, db_get_host, api_delete_filtered_hosts):
    host = db_create_host()
    match_id = str(host.id)
    nomatch_id = str(db_create_host().id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"hostname_or_id": match_id})
    assert response_status == 202
    assert response_data["hosts_deleted"] == 1

    assert not db_get_host(match_id)
    assert db_get_host(nomatch_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_insights_id(db_create_host, db_get_host, api_delete_filtered_hosts):
    target_insights_id = generate_uuid()
    match_id = str(db_create_host(extra_data={"insights_id": target_insights_id}).id)
    nomatch_id = str(db_create_host(extra_data={"insights_id": generate_uuid()}).id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"insights_id": target_insights_id})
    assert response_status == 202
    assert response_data["hosts_found"] == 1
    assert response_data["hosts_deleted"] == 1

    assert not db_get_host(match_id)
    assert db_get_host(nomatch_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_provider_id(db_create_host, db_get_host, api_delete_filtered_hosts):
    target_provider_id = generate_uuid()
    match_id = str(db_create_host(extra_data={"provider_id": target_provider_id, "provider_type": "aws"}).id)
    nomatch_id = str(db_create_host(extra_data={"provider_id": generate_uuid(), "provider_type": "aws"}).id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"provider_id": target_provider_id})
    assert response_status == 202
    assert response_data["hosts_found"] == 1
    assert response_data["hosts_deleted"] == 1

    assert not db_get_host(match_id)
    assert db_get_host(nomatch_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_provider_type(db_create_host, db_get_host, api_delete_filtered_hosts):
    match_ids = [
        str(db_create_host(extra_data={"provider_type": "ibm", "provider_id": generate_uuid()}).id) for _ in range(3)
    ]
    nomatch_ids = [
        str(db_create_host(extra_data={"provider_type": "aws", "provider_id": generate_uuid()}).id),
        str(db_create_host().id),
    ]

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"provider_type": "ibm"})
    assert response_status == 202
    assert response_data["hosts_found"] == 3
    assert response_data["hosts_deleted"] == 3

    for host_id in match_ids:
        assert not db_get_host(host_id)
    for host_id in nomatch_ids:
        assert db_get_host(host_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_tags(db_create_host, db_get_host, api_delete_filtered_hosts):
    match_ids = [
        str(db_create_host(extra_data={"tags": {"ns1": {"key1": ["val1"]}}}).id),
        str(db_create_host(extra_data={"tags": {"ns1": {"key1": ["val1"]}, "ns2": {"k": ["v"]}}}).id),
    ]
    nomatch_ids = [
        str(db_create_host(extra_data={"tags": {"ns2": {"key2": ["val2"]}}}).id),
        str(db_create_host().id),
    ]

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"tags": "ns1/key1=val1"})
    assert response_status == 202
    assert response_data["hosts_found"] == 2
    assert response_data["hosts_deleted"] == 2

    for host_id in match_ids:
        assert not db_get_host(host_id)
    for host_id in nomatch_ids:
        assert db_get_host(host_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_tags_multiple(db_create_host, db_get_host, api_delete_filtered_hosts):
    # Multiple tags use OR logic - any host with at least one of the tags matches
    tag1 = {"ns1": {"key1": ["val1"]}}
    tag2 = {"ns2": {"key2": ["val2"]}}
    both_tags = {"ns1": {"key1": ["val1"]}, "ns2": {"key2": ["val2"]}}
    other_tag = {"ns3": {"key3": ["val3"]}}

    # All these have at least one of the target tags
    match_ids = [
        str(db_create_host(extra_data={"tags": both_tags}).id),
        str(db_create_host(extra_data={"tags": tag1}).id),
        str(db_create_host(extra_data={"tags": tag2}).id),
        str(db_create_host(extra_data={"tags": {**both_tags, "ns3": {"k": ["v"]}}}).id),
    ]
    # This one has neither tag
    nomatch_id = str(db_create_host(extra_data={"tags": other_tag}).id)

    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={"tags": ["ns1/key1=val1", "ns2/key2=val2"]}
    )
    assert response_status == 202
    assert response_data["hosts_found"] == 4
    assert response_data["hosts_deleted"] == 4

    for host_id in match_ids:
        assert not db_get_host(host_id)
    assert db_get_host(nomatch_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_group_name(
    db_create_host, db_get_host, db_create_group, db_create_host_group_assoc, api_delete_filtered_hosts
):
    host_in_group = db_create_host()
    host_in_other_group = db_create_host()
    host_ungrouped = db_create_host()

    group = db_create_group("target-group")
    other_group = db_create_group("other-group")
    db_create_host_group_assoc(host_in_group.id, group.id)
    db_create_host_group_assoc(host_in_other_group.id, other_group.id)

    match_id = str(host_in_group.id)
    nomatch_ids = [str(host_in_other_group.id), str(host_ungrouped.id)]

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"group_name": group.name})
    assert response_status == 202
    assert response_data["hosts_found"] == 1
    assert response_data["hosts_deleted"] == 1

    assert not db_get_host(match_id)
    for host_id in nomatch_ids:
        assert db_get_host(host_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_group_name_case_insensitive(
    db_create_host, db_get_host, db_create_group, db_create_host_group_assoc, api_delete_filtered_hosts
):
    host = db_create_host()
    group = db_create_group("My-Group")
    db_create_host_group_assoc(host.id, group.id)
    host_id = str(host.id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"group_name": "MY-GROUP"})
    assert response_status == 202
    assert response_data["hosts_deleted"] == 1
    assert not db_get_host(host_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_group_name_empty(
    db_create_host, db_get_host, db_create_group, db_create_host_group_assoc, api_delete_filtered_hosts
):
    grouped_host = db_create_host()
    ungrouped_host = db_create_host()
    group = db_create_group("some-group")
    db_create_host_group_assoc(grouped_host.id, group.id)

    grouped_id = str(grouped_host.id)
    ungrouped_id = str(ungrouped_host.id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"group_name": ""})
    assert response_status == 202
    assert response_data["hosts_deleted"] >= 1

    assert not db_get_host(ungrouped_id)
    assert db_get_host(grouped_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_group_name_multiple(
    db_create_host, db_get_host, db_create_group, db_create_host_group_assoc, api_delete_filtered_hosts
):
    host1 = db_create_host()
    host2 = db_create_host()
    host3 = db_create_host()
    host_other = db_create_host()

    group1 = db_create_group("group-one")
    group2 = db_create_group("group-two")
    other_group = db_create_group("group-other")
    db_create_host_group_assoc(host1.id, group1.id)
    db_create_host_group_assoc(host2.id, group2.id)
    db_create_host_group_assoc(host3.id, group2.id)
    db_create_host_group_assoc(host_other.id, other_group.id)

    match_ids = [str(host1.id), str(host2.id), str(host3.id)]
    nomatch_id = str(host_other.id)

    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={"group_name": [group1.name, group2.name]}
    )
    assert response_status == 202
    assert response_data["hosts_found"] == 3
    assert response_data["hosts_deleted"] == 3

    for host_id in match_ids:
        assert not db_get_host(host_id)
    assert db_get_host(nomatch_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_group_id(
    db_create_host, db_get_host, db_create_group, db_create_host_group_assoc, api_delete_filtered_hosts
):
    host_in_group = db_create_host()
    host_other = db_create_host()

    group = db_create_group("id-group")
    other_group = db_create_group("other-id-group")
    db_create_host_group_assoc(host_in_group.id, group.id)
    db_create_host_group_assoc(host_other.id, other_group.id)

    match_id = str(host_in_group.id)
    nomatch_id = str(host_other.id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"group_id": str(group.id)})
    assert response_status == 202
    assert response_data["hosts_found"] == 1
    assert response_data["hosts_deleted"] == 1

    assert not db_get_host(match_id)
    assert db_get_host(nomatch_id)


def test_delete_bulk_group_name_and_group_id_conflict(db_create_group, api_delete_filtered_hosts):
    group = db_create_group("conflict-group")

    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={"workspace_name": group.name, "workspace_id": str(group.id)}
    )
    assert response_status == 400
    assert "Cannot use both" in response_data["detail"]


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_registered_with_negative(db_create_host, db_get_host, api_delete_filtered_hosts):
    satellite_id = str(db_create_host(extra_data={"reporter": "satellite"}).id)
    puptoo_id = str(db_create_host(extra_data={"reporter": "puptoo"}).id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"registered_with": "!satellite"})
    assert response_status == 202
    assert response_data["hosts_deleted"] >= 1

    assert db_get_host(satellite_id)
    assert not db_get_host(puptoo_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_registered_with_old_insights(db_create_host, db_get_host, api_delete_filtered_hosts):
    insights_host_id = str(db_create_host(extra_data={"insights_id": generate_uuid()}).id)
    no_insights_host_id = str(
        db_create_host(
            extra_data={
                "insights_id": None,
                "subscription_manager_id": generate_uuid(),
            }
        ).id
    )

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"registered_with": "insights"})
    assert response_status == 202
    assert response_data["hosts_deleted"] >= 1

    assert not db_get_host(insights_host_id)
    assert db_get_host(no_insights_host_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_filter_operating_system(db_create_host, db_get_host, api_delete_filtered_hosts):
    match_ids = [
        str(
            db_create_host(
                extra_data={"system_profile_facts": {"operating_system": {"name": "RHEL", "major": "8", "minor": "4"}}}
            ).id
        )
        for _ in range(2)
    ]
    nomatch_ids = [
        str(
            db_create_host(
                extra_data={"system_profile_facts": {"operating_system": {"name": "RHEL", "major": "7", "minor": "4"}}}
            ).id
        ),
        str(
            db_create_host(
                extra_data={
                    "system_profile_facts": {"operating_system": {"name": "CentOS", "major": "7", "minor": "4"}}
                }
            ).id
        ),
        str(db_create_host().id),
    ]

    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={"filter[system_profile][operating_system][RHEL][version][eq][]": "8.4"}
    )
    assert response_status == 202
    assert response_data["hosts_found"] == 2
    assert response_data["hosts_deleted"] == 2

    for host_id in match_ids:
        assert not db_get_host(host_id)
    for host_id in nomatch_ids:
        assert db_get_host(host_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_by_filter_operating_system_multiple(db_create_host, db_get_host, api_delete_filtered_hosts):
    match_84_id = str(
        db_create_host(
            extra_data={"system_profile_facts": {"operating_system": {"name": "RHEL", "major": "8", "minor": "4"}}}
        ).id
    )
    match_83_id = str(
        db_create_host(
            extra_data={"system_profile_facts": {"operating_system": {"name": "RHEL", "major": "8", "minor": "3"}}}
        ).id
    )
    nomatch_id = str(
        db_create_host(
            extra_data={"system_profile_facts": {"operating_system": {"name": "RHEL", "major": "7", "minor": "4"}}}
        ).id
    )

    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={"filter[system_profile][operating_system][RHEL][version][eq][]": ["8.4", "8.3"]}
    )
    assert response_status == 202
    assert response_data["hosts_found"] == 2
    assert response_data["hosts_deleted"] == 2

    assert not db_get_host(match_84_id)
    assert not db_get_host(match_83_id)
    assert db_get_host(nomatch_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
@pytest.mark.parametrize("param_prefix", ("updated", "last_check_in"))
def test_delete_bulk_timestamp_start(db_create_host, db_get_host, api_delete_filtered_hosts, param_prefix):
    host_before = db_create_host()
    host_before_id = str(host_before.id)

    host_after_1 = db_create_host()
    host_after_1_id = str(host_after_1.id)
    attr = "modified_on" if param_prefix == "updated" else "last_check_in"
    time_filter = str(getattr(host_after_1, attr))

    db_create_host()  # Additional host after the filter timestamp

    response_status, response_data = api_delete_filtered_hosts(query_parameters={f"{param_prefix}_start": time_filter})
    assert response_status == 202
    assert response_data["hosts_deleted"] >= 1

    assert db_get_host(host_before_id)
    assert not db_get_host(host_after_1_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
@pytest.mark.parametrize("param_prefix", ("updated", "last_check_in"))
def test_delete_bulk_timestamp_end(db_create_host, db_get_host, api_delete_filtered_hosts, param_prefix):
    host_before_1 = db_create_host()
    host_before_1_id = str(host_before_1.id)

    host_before_2 = db_create_host()
    attr = "modified_on" if param_prefix == "updated" else "last_check_in"
    time_filter = str(getattr(host_before_2, attr))

    host_after = db_create_host()
    host_after_id = str(host_after.id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={f"{param_prefix}_end": time_filter})
    assert response_status == 202
    assert response_data["hosts_deleted"] >= 1

    assert not db_get_host(host_before_1_id)
    assert db_get_host(host_after_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
@pytest.mark.parametrize("param_prefix", ("updated", "last_check_in"))
def test_delete_bulk_timestamp_range(db_create_host, db_get_host, api_delete_filtered_hosts, param_prefix):
    host_before = db_create_host()
    host_before_id = str(host_before.id)

    host_in_range_1 = db_create_host()
    host_in_range_1_id = str(host_in_range_1.id)
    attr = "modified_on" if param_prefix == "updated" else "last_check_in"
    time_start = str(getattr(host_in_range_1, attr))

    host_in_range_2 = db_create_host()
    time_end = str(getattr(host_in_range_2, attr))

    host_after = db_create_host()
    host_after_id = str(host_after.id)

    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={
            f"{param_prefix}_start": time_start,
            f"{param_prefix}_end": time_end,
        }
    )
    assert response_status == 202
    assert response_data["hosts_deleted"] >= 1

    assert db_get_host(host_before_id)
    assert not db_get_host(host_in_range_1_id)
    assert db_get_host(host_after_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
@pytest.mark.parametrize("param_prefix", ("updated", "last_check_in"))
def test_delete_bulk_timestamp_both_same(db_create_host, db_get_host, api_delete_filtered_hosts, param_prefix):
    match_host = db_create_host()
    match_host_id = str(match_host.id)
    attr = "modified_on" if param_prefix == "updated" else "last_check_in"
    time_filter = str(getattr(match_host, attr))

    nomatch_host = db_create_host()
    nomatch_host_id = str(nomatch_host.id)

    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={
            f"{param_prefix}_start": time_filter,
            f"{param_prefix}_end": time_filter,
        }
    )
    assert response_status == 202
    assert not db_get_host(match_host_id)
    assert db_get_host(nomatch_host_id)


@pytest.mark.parametrize("param_prefix", ("updated", "last_check_in"))
def test_delete_bulk_timestamp_incorrect_format(api_delete_filtered_hosts, subtests, param_prefix):
    invalid_formats = ("foobar", "{}", "[]", generate_uuid())
    for invalid_format in invalid_formats:
        for param in (f"{param_prefix}_start", f"{param_prefix}_end"):
            with subtests.test(invalid_format=invalid_format, param=param):
                response_status, response_data = api_delete_filtered_hosts(
                    query_parameters={param: str(invalid_format)}
                )
                assert response_status == 400
                assert "is not a 'date-time'" in response_data["detail"]


@pytest.mark.parametrize("param_prefix", ("updated", "last_check_in"))
def test_delete_bulk_timestamp_start_after_end(api_delete_filtered_hosts, param_prefix):
    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={
            f"{param_prefix}_start": str(datetime.now()),
            f"{param_prefix}_end": str(datetime.now() - timedelta(days=1)),
        }
    )
    assert response_status == 400
    assert f"{param_prefix}_start cannot be after {param_prefix}_end." in response_data["detail"]


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
@pytest.mark.parametrize("field", ("display_name", "hostname_or_id"))
def test_delete_bulk_wildcard(db_create_host, db_get_host, api_delete_filtered_hosts, field):
    match_ids = [
        str(db_create_host(extra_data={"display_name": "abc12lmxyz", "fqdn": "abc12lmxyz.test"}).id),
        str(db_create_host(extra_data={"display_name": "qwer12lmst", "fqdn": "qwer12lmst.test"}).id),
    ]
    nomatch_id = str(db_create_host(extra_data={"display_name": "nomatchhere", "fqdn": "nomatchhere.test"}).id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={field: "1*m"})
    assert response_status == 202
    assert response_data["hosts_deleted"] >= 2

    for host_id in match_ids:
        assert not db_get_host(host_id)
    assert db_get_host(nomatch_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
@pytest.mark.parametrize("field", ("display_name", "hostname_or_id"))
def test_delete_bulk_only_wildcard(db_create_host, db_get_host, api_delete_filtered_hosts, field):
    host_ids = [str(db_create_host().id) for _ in range(3)]

    response_status, response_data = api_delete_filtered_hosts(query_parameters={field: "*"})
    assert response_status == 202
    assert response_data["hosts_deleted"] >= 3

    for host_id in host_ids:
        assert not db_get_host(host_id)


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
@pytest.mark.parametrize("field", ("fqdn", "provider_id"))
def test_delete_bulk_wildcard_not_accepted(db_create_host, db_get_host, api_delete_filtered_hosts, field):
    extra = {"fqdn": generate_uuid(), "provider_id": generate_uuid(), "provider_type": "aws"}
    host_id = str(db_create_host(extra_data=extra).id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={field: "*"})
    assert response_status == 202
    assert response_data["hosts_found"] == 0
    assert db_get_host(host_id)


@pytest.mark.parametrize(
    "params",
    [
        ("display_name", "fqdn"),
        ("display_name", "insights_id"),
        ("display_name", "hostname_or_id"),
        ("fqdn", "insights_id"),
        ("fqdn", "hostname_or_id"),
        ("insights_id", "hostname_or_id"),
        ("display_name", "fqdn", "insights_id"),
        ("display_name", "fqdn", "hostname_or_id"),
        ("display_name", "insights_id", "hostname_or_id"),
        ("fqdn", "insights_id", "hostname_or_id"),
        ("display_name", "fqdn", "insights_id", "hostname_or_id"),
    ],
)
def test_delete_bulk_invalid_parameter_combinations(api_delete_filtered_hosts, params):
    parameters = {}
    for param in params:
        parameters[param] = generate_uuid() if param == "insights_id" else "test-value"

    response_status, response_data = api_delete_filtered_hosts(query_parameters=parameters)
    assert response_status == 400
    assert (
        "Only one of [fqdn, display_name, hostname_or_id, insights_id] "
        "may be provided at a time." in response_data["detail"]
    )


@pytest.mark.parametrize("field", ("insights_id", "provider_type"))
def test_delete_bulk_parameters_verification(api_delete_filtered_hosts, field):
    response_status, response_data = api_delete_filtered_hosts(query_parameters={field: "not-a-valid-value"})
    assert response_status == 400


def test_delete_bulk_without_parameters(api_delete_filtered_hosts):
    response_status, response_data = api_delete_filtered_hosts(query_parameters={})
    assert response_status == 400
    assert "bulk-delete operation needs at least one input property" in response_data["detail"]


@pytest.mark.parametrize("confirm_delete_all", (None, False, "random-string", 0, 1))
def test_delete_bulk_wrong_delete_all_params(api_delete_all_hosts, confirm_delete_all):
    params = {}
    if confirm_delete_all is not None:
        params["confirm_delete_all"] = confirm_delete_all

    response_status, _ = api_delete_all_hosts(params)
    assert response_status == 400


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_bulk_different_account(db_create_host, db_get_host, api_delete_filtered_hosts):
    secondary_org_id = "different-org-12345"
    target_name = "cross-account-test"

    primary_id = str(db_create_host(extra_data={"display_name": target_name}).id)
    secondary_id = str(db_create_host(extra_data={"display_name": target_name, "org_id": secondary_org_id}).id)

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"display_name": target_name})
    assert response_status == 202
    assert response_data["hosts_deleted"] == 1

    assert not db_get_host(primary_id)
    assert db_get_host(secondary_id, org_id=secondary_org_id)


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
